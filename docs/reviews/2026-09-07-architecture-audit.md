# RedBeacon 架构与可维护性审计（2026-09-07）

> 本文只做**架构 / 可维护性 / 重复造轮子**审计，不重复 [2026-09-05 功能审查](2026-09-05-recent-change-audit.md) 已覆盖的行为缺陷。
> 审计范围：根仓 HEAD `e2ea75a`、CLI 子仓 HEAD `76647eb`。只读代码、跑了测试套件与 code-health，未修改任何源码、安装入口或用户数据。

## 规模基线

| 区域 | 行数 |
|---|---|
| `core/`（domain + ports + usecases） | 9,544 |
| `services/` | 12,115 |
| `infra/` | 5,224 |
| `adapters/`（UI 后端） | 5,042 |
| `routers/`（CLI） | 4,092 |
| 前端 js/css/html | 5,073 |
| `tasks/`（遗留） | 604 |
| 测试 | 24,712 |
| 跟踪的 markdown | 28,651 |

测试：`1116 passed, 2 failed`（失败见 P3-2）。code-health 预算通过。

## 先做对的地方

- `core/` 对外零依赖 —— 全树 grep 不到一条从 `core` 指向 `infra` / `services` / `adapters` 的 import。这个边界是真的，值得守住。
- `tools/check_code_health.py` 有模块/函数行数预算 + 重复函数体检测，且把已有债务显式列成 `FUNCTION_BUDGETS` 而不是静默豁免。
- `platform_account/` 分层清晰（client / checkin / scheduler / billing / errors 各司其职），AI 调度用 `~/.bytestaff/ai_scheduler.sqlite3` 做跨进程协调而不是进程内 Semaphore。
- 安装事务 smoke 是真跑的（临时文件系统、跨通道、进程观察），不是自报 passed。

---

## P0 — 立刻处理

### P0-1 明文阿里云 AccessKey 躺在工作区，只靠本机私有规则挡着

`redbeacon传图.csv`（仓库根目录）是一份两行 CSV：表头 + 一对明文阿里云 AccessKey ID / Secret。此处不复制其内容。

现状核实：**没有**被 git 跟踪，历史里也搜不到。但拦住它的是 `.git/info/exclude` 第 18 行 —— 这个文件**只存在于这台机器的 .git 目录里，不随仓库分发、不进任何 clone**。`.gitignore` 里没有它。

后果：换一台机器、重新 clone、或 `.git` 被重建，这个文件就会被 `git add -A` 直接提交进公开根仓。而 AGENTS.md 明确要求「项目不持有 OSS 凭据」。

处置（按顺序）：
1. 在阿里云控制台**轮换/禁用**这对 AK/SK —— 它已经在明文工作区躺了近 3 个月，按已泄露处理。
2. 把文件移出仓库目录树（不要只删，先确认没有别的流程在读它）。
3. 在 `.gitignore` 里加上 `*.csv` 或显式条目，让保护随仓库走。

---

## P1 — 架构性问题（重构成本随时间线性上涨）

### P1-1 飞书双数据源是死抽象，但它的词汇焊死在 domain 和 ports 里

AGENTS.md 写着「飞书云端源现阶段搁置」。代码里它仍是一等公民：全树 **875 处** `飞书/feishu/Feishu`，其中最刺眼的是 **`core/domain.py` 52 处、`core/ports.py` 40 处** —— 这是本该与厂商无关的那一层。

具体证据：

- `core/ports.py` 的端口**直接以厂商命名**：`FeishuSummaryPort`、`FeishuReviewPort`、`FeishuPublishPort`、`FeishuSetupPort`。而 `composition.py` 的模块 docstring 声称「适配器拿到的是端口类型，不知道背后是飞书还是桩件」—— 端口类型本身就叫 Feishu，这句话是假的。
- 端口方法签名一律吃 `app_token: str`（飞书 Base 句柄），于是本地实现必须伪造它。`infra/local_accounts.py::LocalNamespaceAccountStore` 把每个账号的 `feishu_app_token` 覆写成 `local:{id}` 字符串，只为骗过用例里的「数据源绑定闸」。
- 领域对象带着 `feishu_ok` / `feishu_error` / `feishu_unbound` / `feishu_app_token` 字段，这些字段**穿过 JSON API 一路漏到前端**：`review.js` 里 `res.feishu_unbound`、`publish.js` 里 `PUB.feishu_error`、`content.js` 里 `ARCHIVE.feishu_unbound`。改名要同时动 domain、ports、两个 infra 实现、UI 路由、5 个 JS 文件。
- 用户可见文案被污染：`core/usecases/topic_manage.py:80` 在本地模式下仍可能抛「该账号还没绑定飞书多维表格，先去设置绑表」；`adapters/ui_backend/routes/topics.py:70` 的写失败一律报「写回飞书失败」。
- 切换开关仍然对用户开放：`GET/POST /api/data-source` 接受 `feishu`，UI 设置页可以把整个产品切到一条没人测的路径上。

专属体积：`services/feishu_api.py` 859 + `services/feishu_schema.py` 183 + `infra/feishu_data.py` 459 + `routers/feishu.py` 132 + `routers/source.py` 29 = **1,855 行**，另加 `cli/tools/feishu_*_selfcheck.py` **582 行**、22 个测试文件里的飞书分支。连 `requests==2.34.2` 这个依赖也**只**被 `feishu_api.py` 用（23 处，全树独此一家），删掉飞书就能少打包一个 HTTP 栈。

建议给 Codex 的动作：把 `CK_DATA_SOURCE` 收敛成常量 `local` → 删掉 `_is_local()` 分支 → 端口改名（`SummaryPort`/`ReviewPort`/…）、签名从 `app_token` 换成 `account_id` → 删 feishu 模块与 `requests` 依赖 → 最后清 domain 字段和前端键名。这是个可以分 4~5 个 PR 走完的机械重构，越晚做越贵。

### P1-2 CLI 和 UI 是两套业务实现，方向和 AGENTS.md 的告警正好相反

AGENTS.md 防的是「UI 寄生 CLI」。实际情况是 **UI 走 core，CLI 绕过 core**。

以选题为例：

| | UI (`adapters/ui_backend/routes/topics.py`) | CLI (`routers/topics.py`) |
|---|---|---|
| 读盘面 | `uc_topic.load_topic_board(...)` → `admin.list_board(token)` | 自己调 `admin.list_rows(token, stage=...)` **两次** |
| 统计 | 用例返回 | 在路由层自己聚合 `by_domain` |
| 批量建题去重 | 用例 | 路由层自己拉全表算 `existing` 集合 |

各 CLI 路由的分层实况（`uc` = 引用 core.usecases，`db` = 直接打 SQLite）：

```
routers/backup.py     uc=0  db=5     ← 纯裸 SQL，还有 f-string 拼表名
routers/strategy.py   uc=0  db=7
routers/publish.py    uc=0  db=3
routers/content.py    uc=3  db=4
routers/accounts.py   uc=3  db=2
routers/_runtime.py   uc=2  db=4
```

`routers/topics.py` 更进一步：业务数据以**中文列名 dict** 在层间传递（`r.get("内容类型")`、`r.get("应用域")`）—— 飞书表格的列名当成了领域模型的键。没有类型、IDE 查不到引用、改一个字段名要全树 grep 中文。

后果很直接：同一个业务规则在两处维护，UI 修了 CLI 不会跟着修。而 skill 全部走 CLI，也就是说**AI 助手走的是没被 core 覆盖的那条路**。

### P1-3 `tasks/` 是遗留层，但 infra 和 adapters 在反向 import 它的私有函数

`tasks/generate.py` 和 `tasks/publish.py` 自己的 docstring 都承认是退役残留。可它现在被上层依赖：

```
infra/local_data.py:100      from redbeacon.tasks.publish  import _markdown_to_plain
infra/feishu_data.py:72      from redbeacon.tasks.publish  import _markdown_to_plain   ← 同一个包装写了两遍
infra/generation.py:183      from redbeacon.tasks.generate import _render_cards
routers/content.py:116       from redbeacon.tasks.generate import _push_to_review
adapters/.../plans.py:211    from redbeacon.tasks.generate import build_cover_prompt
```

四个问题叠在一起：依赖方向倒置（infra → tasks → database）、跨模块 import 单下划线私有名、同一个 `_markdown_to_plain` 包装在两个 adapter 里各抄一遍、`tasks` 因为被引用而无法删除。

同类还有 `infra/account_profile.py:11`，代码里自己写了注释：

```python
from redbeacon.infra.generation import _bound_feishu   # infra↔infra 复用：构造绑该号 Base 的 FeishuAPI
```

建议：把 `_markdown_to_plain` / `_render_cards` / `build_cover_prompt` 提到 `core/presets.py` 或新的 `services/text.py`、`services/cards.py`，`tasks/` 整个删掉。

### P1-4 「所有生成入口共用一个串行队列」这个不变量只在桌面进程内成立

`adapters/ui_backend/app.py:164` 的 `_SerialJobQueue` docstring 写「所有生成入口共用一个串行队列」，实现是一个**进程内**的 `queue.Queue` + 单 daemon 线程：

```python
_gen_queue = _SerialJobQueue(max_pending=20)
_automation_active_accounts: set[int] = set()   # 也是进程内
```

但 `routers/generate.py`（`redbeacon generate`，所有 skill 走的路）里 grep 不到任何 lock / queue / 跨进程互斥。也就是说：用户在客户端点生成的同时，AI 助手在终端触发一次 `redbeacon generate`，两篇会**并行跑**，并且可能预留到同一条选题。

AGENTS.md 的要求是「客户端生成笔记必须严格串行……多选只负责入队」。跨进程那半没有实现。平台侧的 AI 并发闸（`ai_scheduler.sqlite3`）是跨进程的，但它管的是算力并发，不是选题预留和 FIFO 次序。

同一位置还有 11 个模块级 `threading.Lock` + 内存 job dict（`_gen_jobs` / `_pub_lock` / `_sug_lock` / `_benchmark_lock` / `_note_style_lock` / …），外加从 `routes/xhs_login.py` **import 进来的私有全局** `_qr_jobs` / `_qr_lock` / `_qr_sessions`。客户端一退出，所有在途 job 状态全丢，CLI 也永远看不见它们。

---

## P2 — 重复造轮子

### P2-1 两个浏览器内核 = 两套手抄的平行实现（`browser_engine.py`，1,542 行）

```
playwright_status()                  ⟷  cloakbrowser_status()
_verify_playwright_launch()          ⟷  _verify_cloakbrowser_launch()
_verify_playwright_launch_in_process ⟷  _verify_cloakbrowser_launch_in_process
_ensure_playwright_engine()          ⟷  _ensure_cloakbrowser_engine()
playwright_cache_dir()               ⟷  cloakbrowser_cache_dir()
```

两个 `*_status` 返回同一套 10 个键的裸 `dict[str, Any]`（`ok` / `chromium_executable` / `chromium_expected_executable` / `chromium_executable_exists` / `chromium_launch_verified` / `chromium_launch_error` / `cache_dir` / `message` …），连 `except` 分支里的字典字面量都各抄一份。加一个键要改 4 个地方，漏一个不会报错、只会在运行时缺字段。

应该是一个 `BrowserEngine` Protocol（`status()` / `verify_launch()` / `ensure()` / `cache_dir`）+ 两个实现 + 一个 dataclass 返回类型。

### P2-2 四个下载器 + 四个安装脚本各写一遍下载校验

- `services/browser_downloads.py` — httpx，Range 分段、断点续传、切源
- `services/release_download.py` — httpx **+ 裸 `http.client`**，节点→OSS 回落
- `services/browser_engine.py:1186` `_download_file` — 第三个，简版
- `install/install.sh|install-test.sh|install.ps1|install-test.ps1` — 每个再用 bash/PowerShell 实现一遍下载 + SHA-256 校验

HTTP 栈同时用 `httpx`（4 个模块）、`requests`（只有飞书）、`http.client`（release_download）。

### P2-3 安装入口是 2 对 ~750 行的手工孪生

```
install.sh      769 行  ⟷  install-test.sh    769 行   diff = 30 行（全是 channel 常量）
install.ps1     748 行  ⟷  install-test.ps1   748 行   diff = 32 行
uninstall.sh / uninstall-test.sh / uninstall.ps1 / uninstall-test.ps1  同理
```

AGENTS.md 说「可以在构建前从同一受控源机械生成」—— 但 `tools/` 里**没有这个生成器**。现状是每个 bug 都要手工改两遍（2026-09-05 的 macOS 回滚修复就是 `install.sh:576` 和 `install-test.sh:576` 各改一次），漂移无人检测。

> ⚠️ 这四个文件是 AGENTS.md 明确保护的「受用户保护的稳定接口」。写生成器**必须先拿到你的显式授权**才能动，Codex 不能自作主张。可以先只写一个「diff 只允许出现在白名单常量行」的校验器，零风险地防漂移。

### P2-4 测试版 skill 靠对 250KB 散文做正则替换

`tools/build_channel_skills.py:50-66`：

```python
text = re.sub(r"(?<![A-Za-z0-9_.-])redbeacon(?![A-Za-z0-9_.-])", "redbeacon-test", text)
text = text.replace("~/.redbeacon", "~/.redbeacon_test")
text = text.replace("/install.ps1", "/install-test.ps1")
```

在 ~250KB 的中文散文上按词形猜测替换，还要先用 `__REDBEACON_TEST_CANONICAL_MANIFEST__` 占位符把 canonical URL 保护起来再放回去 —— 这个 workaround 本身就说明方案是脆的。源文档里新写一个路径或 URL，可能被误改，也可能该改没改，而且**两种错误都不会有任何检查报出来**（AGENTS.md 说「缺一个即为坏包」，但坏在正文里没人验）。

应该在 `.claude/commands/*.md` 里用具名占位符（`{{CLI}}` / `{{DATA_DIR}}` / `{{MANIFEST_URL}}` / `{{INSTALL_URL}}`），生成器做变量代入，并在生成后断言产物里不再残留任何未替换的占位符或对方通道的字面量。

---

## P3 — 死代码与失效功能

### P3-1 `strategy image-ref-add` 返回成功，但对出图零影响

链路核实：

- 写入端 `routers/strategy.py:177-197`：`shutil.copyfile` 拷进数据目录 → `UPDATE image_strategy SET reference_images=?` → 返回 `{"ok": true, "stored": ..., "count": n}`
- 读取端 `core/usecases/generate.py:566`：参考图**只**从 `plan.reference_images` 取，即 `content_plan` 表
- 全树 grep `image_strategy`：只有 `database.py`（建表/迁移）、`routers/backup.py`（备份表清单）、`routers/strategy.py`（自读自写）、`infra/generation.py:187`（只读 `card_theme` 一列）

也就是说 `image_strategy.reference_images` 写进去之后没有任何生成路径读它。而 `.claude/commands/redbeacon-strategy.md` 仍在教 AI 助手用 `image-set` / `image-ref-add` 挂「人物写真 / 风格参考图」。真正生效的是 `redbeacon plans material`（写 `content_plan`）。同一件事有两条命令，一条静默无效。

附带问题：这条路径用裸 `shutil.copyfile` 落盘，绕过了 `services/image_sanitize.py`（`infra/creation.py` 的宿主图片导入器是走净化的）。AGENTS.md 要求所有入库图片先净化再落地。

`strategy image-set` 是部分生效的：`mode` / `prompt_template` 写账号档案（有效），`card_theme` 写 `image_strategy`（有效，被 `infra/generation.py:189` 读），`reference_images` / `ai_model` / `template_mode`（无效）。这种「一半生效」比全废更难查。

### P3-2 死代码清单

| 位置 | 行数 | 状态 |
|---|---|---|
| `install/install-core.sh` + `install-core.ps1` | 1,403 | 制品已不再打包（`prepare_release_artifacts.py` 只发 `uninstall-core.*`），且 `check_release_contracts.py:324` **主动禁止**它出现。文件仍留在受保护的 `install/` 目录里 |
| `cli/src/redbeacon/schemas.py` | 307 | 307 行 TypedDict 契约，全树**零 import**，只在 `cli.py:7` 的注释里被提到一句。skill 按它解析 CLI 输出，但没有任何测试或类型检查把它和真实输出绑起来 |
| `routers/feishu.py` + `routers/source.py` | 161 | 没注册进 `_load_dispatchers()`，产品里不可达；只有测试在 import 它们，等于用测试养着死代码 |
| `utils/machine.py` | 15 | 完全无引用 |
| `services/codex_image_handoff.py` | ~200 | 只被 `test_codex_image_handoff_spike.py` 调用 —— 一个 spike 留在了生产源码树里 |
| `openai==2.45.0` 依赖 | — | 全树没有 `import openai`（只有 `image_gen.py:343` 一句提到它的注释）。被打进 Windows/macOS 两个冻结包 |

### P3-3 无人 import 的 `schemas.py` 与 skill 的解析约定脱钩

这条单独拎出来，因为它有实际风险：skill 是按 CLI 的 JSON 输出形状写的，`schemas.py` 本该是那份契约。它现在纯属文档，**改 CLI 输出不会让任何东西变红**。建议要么让 `routers/_runtime.py::out()` 在 debug 模式下按 schema 校验，要么删掉它别再假装有契约。

---

## P4 — 工程流程

### P4-1 没有 CI

`.github/workflows/` 是**空目录**。全仓库没有 Makefile / justfile / tox / nox / pre-commit，`pyproject.toml` 里也没有 `[tool.ruff]` / `[tool.mypy]`（虽然存在 `.ruff_cache`，说明有人手跑过）。

也就是说：1,118 个测试、`check_code_health.py`、`check_release_contracts.py`、`check_release_artifacts.py`、`test_installer_regressions.py`、两个安装事务 smoke —— **全部靠人记得跑**。这些工具质量不低，缺的只是自动触发。

最低成本的第一步：一个只跑 `pytest` + `check_code_health.py` + `check_release_contracts.py` 的 workflow（都不需要网络和真实浏览器）。

### P4-2 测试套件不隔离环境变量，绿灯不可复现

`tests/conftest.py` 只隔离了 `BYTESTAFF_HOME`。`REDBEACON_CHANNEL` / `REDBEACON_DATA_DIR` / `REDBEACON_BUILD_CHANNEL` / `PLAYWRIGHT_BROWSERS_PATH` / `CLOAKBROWSER_CACHE_DIR` 全部从开发者 shell 继承。

我这次跑的实测：

```
$ .venv/bin/python -m pytest tests -q
2 failed, 1116 passed
  FAILED tests/test_updater.py::test_manifest_url_ignores_legacy_github_config
  FAILED tests/test_updater.py::test_manifest_url_ignores_legacy_oss_config

$ env -u REDBEACON_CHANNEL .venv/bin/python -m pytest tests/test_updater.py -q
29 passed
```

原因：我的 shell 里有 `REDBEACON_CHANNEL=test`（大概率是之前跑过测试版客户端留下的），而这两个测试拿运行时 URL 去比 `CK_UPDATE_MANIFEST_URL.default` 这个 stable 常量。

值得注意的是，[2026-09-05 修复记录](2026-09-05-recent-change-fixes.md) 的验证段里已经记下了这个现象 ——「首次使用测试通道环境运行时，两项旧 updater 测试的模块级默认值与运行时通道不一致；按套件默认环境重跑通过」—— 但处理方式是**换个环境重跑**，而不是修隔离。这正是 AGENTS.md 花大篇幅防的通道串染，只不过发生在测试层。

修法很短：在 `conftest.py` 加一个 autouse fixture，把这几个变量 `monkeypatch.delenv(..., raising=False)`。

### P4-3 迁移引擎只能加列，且吞掉失败

`database.py:68-124`：一个 36 条的 `ALTER TABLE ... ADD COLUMN` 列表，逐条 try：

```python
except Exception as e:
    if "duplicate column" not in str(e).lower():
        _log.getLogger("database").warning(f"[migrate] {table}.{col}: {e}")
```

问题：
- 「已存在」靠**匹配异常消息字符串**判断，随 SQLite 版本/语言可能失配
- 其他任何失败只打一条 warning 然后**继续往下跑**，应用带着半迁移的 schema 正常启动
- 没有 schema version 表 → 只能加列，改不了类型、改不了名、backfill 无处安放；也**检测不到降级**（安装失败回滚到旧客户端后，旧代码会打开新 schema 的库）

考虑到 AGENTS.md 对安装事务的要求（快照主库 + 在副本上跑迁移 + 失败回滚），迁移引擎本身没有失败语义是个明显的不对称。

### P4-4 code-health 预算把债务制度化了

```python
MAX_PYTHON_MODULE_LINES   = 1600
DEFAULT_MAX_FUNCTION_LINES = 320
FUNCTION_BUDGETS = {
    ("adapters/ui_backend/app.py", "create_app"): 850,
    ("cli.py", "_build_parser"): 500,
    ("database.py", "_create_tables"): 400,
}
```

守卫本身是好的，但 1600 行的模块、320 行的函数、850 行的 `create_app` 是「允许长期停在这里」的信号。建议改成**棘轮**：每次触碰这些文件时预算只许降不许升，并给三个具名例外写上目标值和拆分计划。

当前顶在预算线上的：`services/browser_engine.py` 1542、`adapters/ui_backend/app.py` 1529、`core/usecases/creation.py` 1498。

### P4-5 109 处静默吞异常，其中发布链路 20 处

全树 `except Exception:` 450 处（没有裸 `except:`，这点是好的），其中**紧跟 `pass` / `continue`** 的有 109 处。分布最集中的是 `services/xhs/publish.py`（43 个 except，20 个静默）。

Playwright 自动化里大量 best-effort 兜底是合理的，但有具体代价。例如 `services/xhs/publish.py:296-310` 的 `_find_tab`：

```python
try:
    elems = page.locator("div.creator-tab"); n = elems.count()
except Exception:
    return None, False          # 浏览器已死 → 和「页面上没有这个 tab」返回同一个值
```

调用方随后抛 `RuntimeError("没有找到发布 TAB - {tabname}")`。AGENTS.md 要求发布失败必须「返回具体错误及可取得的诊断截图」，而这里已经把根因抹平了。建议至少让这类 catch 记一条带异常类型的 log，让「浏览器死了」和「选择器过期」在日志里可区分。

### P4-6 文档比代码还多，构建产物入库

- 跟踪的 markdown **28,651 行** > cli/src 全部 Python
- `docs/download-node/releases/` 下 23 份发布回执共 **6,741 行**，是构建产物，只增不减地提交进仓
- 根目录并列 `AGENTS.md`(135) / `CLAUDE.md`(7) / `README.md`(90) / `RedBeacon-测试版验证指南.md`(59) / `数字员工-架构母本.md`(768)，`docs/archive/` 另有 1.3M
- `.claude/commands/*.md` 2,986 行 + `.agents/skills/*/SKILL.md` 3,018 行（后者由前者生成，双份入库）

不是要求删文档，而是：发布回执应该有保留窗口（和 OSS「最多留 3 个版本」的策略对齐），生成产物 `.agents/skills/` 应该考虑是否需要入库。

---

## 建议的执行顺序

给 Codex 排的话，按「风险 × 解锁后续」排序：

1. **P0-1** 轮换 AK/SK + 移文件 + 补 `.gitignore`。今天做完。
2. **P4-2** conftest 加环境隔离 fixture。5 行代码，让绿灯可复现，是后面所有重构的前提。
3. **P4-1** 加一个最小 CI（pytest + check_code_health + check_release_contracts）。没有这个，后面的重构没有安全网。
4. **P3-2 / P3-3** 删死代码（`install-core.*` 需你授权，因为在受保护目录）、删 `openai` 依赖。低风险，先把噪音清掉。
5. **P3-1** 修 `strategy image-ref-add`：要么让它写 `content_plan`，要么退役它并同步改 `redbeacon-strategy` skill。顺带补上 `image_sanitize`。
6. **P1-1** 飞书退场，分 4~5 个 PR：常量化 `CK_DATA_SOURCE` → 删分支 → 端口改名与签名换 `account_id` → 删模块和 `requests` → 清 domain 字段与前端键名。
7. **P1-3** `tasks/` 解散，共享零件上提。
8. **P1-2** CLI routers 收口到 `core/usecases`，从 `topics` / `strategy` / `backup` 这三个最偏的开刀。
9. **P2-1** `browser_engine` 抽 `BrowserEngine` Protocol。
10. **P2-4** skill 生成改占位符契约 + 产物断言。
11. **P2-3** 安装入口防漂移校验器（生成器需你单独授权）。
12. **P4-3** 迁移引擎加 schema version 与失败语义。

前 5 项互不冲突，可以并行。第 6 项开始建议串行，每步跑完整测试套件。

---

*审计人：Claude Opus 5 · 只读审计，未修改任何源码、安装入口或用户数据*
