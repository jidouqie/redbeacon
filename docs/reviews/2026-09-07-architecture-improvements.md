# RedBeacon 架构改进执行记录 · 2026-09-07

14 项完成，2 项部分完成：第 4 项仅剩受保护目录中的旧安装器核心待授权删除；第 6 项代码、5 个草稿 PR 与自动化测试完成，人工主要页面验收未完成。版本保持 0.1.122，本轮没有打包、发布或合并 PR。

## 最终验收

- 私有 CLI 源码：`0858572ee54d2b627e5f136883505daf70d95b24`。工作区干净，已推送私有分支 `codex/architecture-maintainability-20260907`。
- 第 16 项根仓提交：`558bb3ca1c2a83595599effd74ded493596056a7`。根仓 release contract 的 CLI provenance 与上述私有提交一致。
- 在显式设置 `REDBEACON_CHANNEL=test` 的 shell 中，全套 CLI 测试 **1177 passed, 1 warning in 17.86s**；code-health 通过。
- 最新源码 [GitHub Actions](https://github.com/jidouqie/redbeacon-cli/actions/runs/34100390248) 的 `windows-latest` 与 `ubuntu-latest` 两项均成功；绑定上述同一 CLI SHA。
- 根仓工具测试 **22 tests, OK**；公开范围与完整范围的 release contracts 均通过；4 对安装/卸载入口只读漂移检查通过；16 份工作台 skill 逐字检查通过。
- 唯一剩余 pytest warning 是 FastAPI/Starlette TestClient 对 httpx 的弃用提示，没有隐藏失败。

最后一轮原始日志保存在本机 `/private/tmp/redbeacon-architecture-task16-pytest.log` 与 `/private/tmp/redbeacon-architecture-task16-tools.log`，临时目录并非长期归档。

## 逐项结果和独立提交

表中测试数量是该步骤完成时的全量 CLI pytest 结果；删掉不可达模块和对应测试后，数量下降属于预期。每行对应的 code-health 均通过。第 6 项起按顺序实施，第 8 项也按单个路由分别提交和回归。

| 项 | 结果 | 主要提交（CLI / 根仓） | 全量测试 |
|---|---|---|---:|
| 1 | `.gitignore` 显式保护云凭据 CSV；只检查文件名引用和 Git 跟踪情况，没有读取其内容。当前工具无有效读取路径，文件移出与密钥轮换留给用户 | 根 `93984fb` | 1118 passed |
| 2 | 在测试收集前及 autouse fixture 中隔离通道、数据、构建通道及两套浏览器缓存环境；增加污染 shell 子进程验证 | CLI `c823c5d` | 1119 passed |
| 3 | 私有仓 Windows/Linux 源码 CI；公开仓独立契约 CI，无私有源码与令牌依赖；本地完整发布检查仍保留 | CLI `d9215f9` / 根 `b964aa1` | 1119 passed |
| 4 | 删除无引用 schemas/machine、未注册 feishu/source 路由、Codex 生图 spike 及其测试；移除 openai 和孤立依赖。安装核心文件待授权 | CLI `d39a388` / 根 `03333ee` | 1108 passed |
| 5 | 采用方案 b：退役失效的账号级参考图及模型/模板字段，明确拒绝无效请求；skill 改教内容方案素材入口；共享净化 PNG 导入和受控路径清理 | CLI `54c8ae1` / 根 `fa1ec84` | 1136 passed |
| 6.1 | 数据源固定 local，移除 UI 设置项与 `/api/data-source` 接口 | CLI `6fa018c` | 1139 passed |
| 6.2 | composition 只保留本地实现，删除 `local:{id}` 伪造 | CLI `99b59d0` | 1139 passed |
| 6.3 | 端口改为业务名称，签名改为整数 account_id | CLI `a27844e` | 1139 passed |
| 6.4 | 移除飞书实现、自检脚本、失效测试及 requests 依赖 | CLI `dd1fa33` | 1128 passed |
| 6.5 | 领域对象、前端键和可见文案统一为本地业务语义；保留历史 SQLite 列名/加密键的兼容性 | CLI `9e9fa52` / 根 `16aaaf9` | 1128 passed |
| 7 | 解散 tasks；文本、卡片能力进入 services，批量发布和旧内容入口进入共享 core usecase | CLI `bafe746` / 根 `6572c5a` | 1131 passed |
| 8 topics | typed 选题对象、共享 usecase，CLI 与 HTTP 等价验证 | CLI `c44846c` / 根 `0cea765` | 1135 passed |
| 8 strategy | typed 图片设置与档案更新，CLI 与 HTTP 等价验证 | CLI `7186534` / 根 `2af254d` | 1139 passed |
| 8 backup | typed 备份 v6、兼容 v5；读取一致性和恢复原子事务，CLI/HTTP 共用入口 | CLI `2939812` / 根 `7993c7c` | 1145 passed |
| 9 | BrowserEngine Protocol、两个实现、统一 dataclass 状态和离线探测；直接调用 ensure 仍遵守浏览器使用锁；确认下载路径已共用断点续传后端 | CLI `b9bd966` / 根 `9ac009b` | 1147 passed |
| 10 | 16 份真源改用具名占位符；未知变量、未完成变量和串通道输出均拒绝；两通道及五宿主共用生成字节 | 根 `d082a74` | 1147 passed |
| 11 | 仅新增 tools 中的精确白名单漂移检查与 CI，无安装生成器、无安装目录修改 | 根 `ff83cca` | 1147 passed |
| 12 | SQLite 跨进程 FIFO、账号/选题预留、操作系统自动释放的 owner 锁；UI/CLI/宿主创作共用执行边界，保留任务结果并标记中断，禁止自动重放 | CLI `dcfd62f` / 根 `07b3eec` | 1154 passed |
| 13 | schema_version、整批原子迁移、PRAGMA 列检测、迁移失败回滚、未来版本拒绝打开；阻止迁移回调隐式提交 | CLI `7545545` / 根 `f892f86` | 1162 passed |
| 14 | 按 Git 基线锁定只降不升预算，三个函数例外及热点模块设置目标；PR/push CI 使用对应基线 | CLI `ee9224b` / 根 `b3bf235` | 1173 passed |
| 15 | 发布链路 20 个静默兜底补操作名、异常类型及脱敏错误日志；保持原结果、重试和 fallback 语义 | CLI `0858572` / 根 `e1a1a0a` | 1177 passed |
| 16 | 每通道三版本回执政策及只读盘点工具；工作台派生 skill 继续入库，并由无需私有 CLI 的公开 CI 逐字校验 | 根 `558bb3c` | 1177 passed |

## 飞书退场的五个草稿 PR

五个 PR 按顺序堆叠，均保留为 draft；没有合并。

1. [PR 1](https://github.com/jidouqie/redbeacon-cli/pull/1)：固定本地数据源。
2. [PR 2](https://github.com/jidouqie/redbeacon-cli/pull/2)：本地 composition 和真实账号 ID。
3. [PR 3](https://github.com/jidouqie/redbeacon-cli/pull/3)：业务端口与整数账号签名。
4. [PR 4](https://github.com/jidouqie/redbeacon-cli/pull/4)：移除飞书实现和依赖。
5. [PR 5](https://github.com/jidouqie/redbeacon-cli/pull/5)：领域和 UI 字段清理。

Windows 回归发现虚拟环境启动器 PID 与真实锁持有子进程不同，原测试杀掉启动器后锁仍被子进程占有。修正为 multiprocessing spawn 并通过 Pipe 验证真实 owner PID，保留原锁释放断言；CLI 提交 `3c010b5`。相关修复已同步 PR 4/5，最终五个 PR 的 Windows/Linux CI 全部通过。Windows 真机独立锁验证重复 20 次通过。

主要页面人工验收仍未完成：源码客户端通过规定的开发入口启动，但 Chrome 访问本机页面返回 `ERR_BLOCKED_BY_CLIENT`；原生 Python 窗口也未能由当前 UI 工具选取。已询问内置浏览器例外，尚未取得授权，未自行切换浏览器。自动化测试和 JS 语法检查不替代该人工验收。

## 补充验证与限制

- 曾发现离线发布测试漏 stub 浏览器启动，导致测试尝试下载真实内核。提交 `4045b54` 补齐 fixture，同时断言启动和登录复验均被调用；之后全量测试约 18 秒，未取消原行为断言。
- 版本化迁移最初全量结果为 `1 failed, 1161 passed`：旧 UI 升级 fixture 先建新版库再删列，仍留有新版 schema_version。fixture 现在显式移除版本表以真实模拟旧库，原回归断言保留；最终全绿。
- 生成 FIFO 在真实 Windows x64 Python 3.12 上完成 10/10 次独立进程探测，覆盖互斥、owner 崩溃、20 个等待任务上限和账号预留；完整 Windows/Linux pytest 另由最新 CI 覆盖。没有冒充冻结客户端安装 smoke。
- [生成运行时说明](2026-09-07-generation-runtime.md) 记录了其余内存锁和 job dict 的持久化取舍。发布进度、扫码会话等并未被虚称为全部持久化；已完成的业务结果保留原有存储语义。
- [数据库迁移](../../cli/src/redbeacon/services/database_migrations.py) 的降级检查适用于具备该检查的版本；无法让此前已发布、完全不认识版本表的旧代码自动获得新保护。本轮没有触碰安装器或旧版升级桥。
- 本轮验证未调用真实收费 AI 或提交真实小红书发布，也没有执行冻结 Windows/macOS 构建和安装事务 smoke。交付新版仍需遵守先测试版、用户试用通过后再批准正式版的发布流程。

## 回执与派生产物

[保留规则及实施取舍](../repository-artifact-policy.md) 已提交。本地盘点保留候选为 stable 0.1.122 / 0.1.121 / 0.1.119，test 0.1.122 / 0.1.121 / 0.1.120；13 份已跟踪完整回执超出窗口，另有 1 份已中止回执和用户未提交的 stable 0.1.122 回执需单列。该工具不把候选窗口冒充 OSS 实际保留集。

本次没有删除既有回执。后续收敛窗口需要在发布收尾时与全局发布 Skill 的实际保留集核对，再作独立维护提交。16 份工作台副本只增加 stable 通道元数据，正文仍由唯一真源机械生成。

## 尚需用户决定的事项

1. **第 4 项**：只删除 `install/install-core.sh` 与 `install/install-core.ps1`。它们未进入当前制品，但用户任务明确要求「在受保护目录，先问我再删」。尚未获得当次授权，所以两个文件保留；四个公开安装入口未改。
2. **第 6 项**：补齐客户端主要页面人工验收。Chrome 本机访问受阻，是否允许本次使用内置浏览器的询问仍待答复；未把自动验收计为人工通过。

核对任务开始前后差异：四个公开安装入口、CLI updater、README 均无本轮改动；未访问冷归档，未新增 OSS SDK/凭据/上传或清单切换逻辑。公开根仓未跟踪 `cli/`，凭据 CSV 未读取、复制或提交。用户原有两份未提交文档保持原状。
