# RedBeacon · skill 改版 —— 现状与任务（专项交接文档）

> 用途：CLI 刚经历重大补全 + 飞书阉割，skill（`.claude/commands/redbeacon*.md`）需要跟着大改。
> 本文 = 给「skill 改版专项」一次性交底：**CLI 变了什么 → skill 现状 → 逐文件改版清单 → 约束与验证**。
> 压缩上下文后照这份接着干即可。日期锚点：2026-07-06。

---

## 一、CLI 近期重大改版（skill 的地基已换新）

### 1. CLI 与 UI 能力全等（skill 地基）
铁律：**UI 能干的，CLI 都能干**——CLI 是 skill 的地基，纯对话要能触达每一项能力。本轮补齐（全部薄壳调同一 core 用例）：
- **方案**：`plans save`（建/改整套模板，长模板走 stdin）、`plans delete`、`plans material`（挂/删/清参考图）、`plans meta`（合法取值）。
- **生成两步**：`generate --preview`（只写文案≈1点，出草稿+最终出图提示词，不出图）、`generate --commit --draft-file`（拿草稿出图入库）。对应 UI「预生成·看实发再花钱」。
- **AI 补题**：`topics suggest`（平台补候选·扣点）、`topics accept`（勾选写库）、`topics suggest-preview`（填充态·不扣点）、`topics suggest-template get/set`（引导语模板）。`topics inspire` 已改为 suggest 的兼容别名。

### 2. CRUD 彻底闭合（AI 权限≥用户，能删几乎所有数据）
- `review delete`（丢弃一条稿）、`content archive-delete` / `archive-edit`（删/改已发布归档）、`plans material --remove/--clear`（删单张/清空参考图）、`strategy image-ref-remove`（删单张账号参考图）、`config unset`（删配置项）。
- 破坏性删除的**运行时二次确认交给 skill 层**（CLI 不拦）。

### 3. 🔴 飞书暂时阉割（对 skill 影响最大）
- 客户端**默认纯本机**，UI 已用 `FEISHU_ENABLED=false` 藏掉数据源开关 + 飞书配置 + boot 兜底切 local。**代码保留，以后线上模式再启**。
- 含义：**skill 里"双源/飞书必需/飞书是真源"的话术全部过时**——一律按**本机**。审核、选题、定位、归档现在**都在本机**。

### 4. 平台 AI 能力开放（skill 基本无感）
- 对话/生图升级为平台级开放能力，门票=账号正常+有算力点，**不需先激活员工**；`product`/`capability` 降为归因标签。接口零变化。skill 里若有"去激活员工/加入我的团队"话术，删。

### 5. 两份 CLI 参照文档（写 skill 对着这俩）
- `项目文档/RedBeacon-CLI命令手册.md` —— 85 条命令全量：用途 + 全部参数 + 调用示例（参数由解析器自动生成）。
- `项目文档/RedBeacon-CLI命令能力总表.md` —— 速查语义：读/写 · 扣不扣点⚡ · 随不随数据源🔀 · 是否宜交棒 UI🤝 · 背后 core 用例。

---

## 二、skill 现状摸底（改版起点）

**家底**：13 个文件 / 2356 行。真源 `.claude/commands/`，Codex 端靠 `tools/sync-codex-skills.py` 派生（命名映射在 updater `_CODEX_NAME_MAP`）。

**✅ 底子好、保留的骨架**（改内容、别改风格）：
- 主入口交互骨架扎实：全程人话不露命令、**给选项必编号+换行**、输入成本压到最小、**两入口模型(UI主·skill合伙人)+ 深链交棒 `ui app --page`** 已写入。
- 平台登录(`redbeacon-login`) / 小红书登录(`redbeacon-xhslogin`) 拆分干净。

**⚠️ 三桶待改**：
1. **飞书写得极重、现已阉割**（最大一桶，11 文件不同程度涉及）：飞书提及密度——定位 32 / 主入口 26 / 发布 22 / 飞书 22 / config 21 / 看板 11 / 生成 11…；多处把飞书焊成"真源/必需"。→ 塌缩成纯本机，删双源分支。
2. **死概念残留**：`灵感箱/转选题`（topics+locate，那个"灵感→选题人工关卡"已删，入库直接落选题态）；`topics reset / topics types`（已退役空壳，仍被当可用写）。
3. **13 个新 CLI 能力一个没引用**（skill 都是补全前写的）→ 用户纯对话够不到：方案调整、生成两步、AI 补题走 CLI、丢弃稿/删改归档。

---

## 三、逐文件改版清单

> 通则：①飞书话术 → 纯本机（去"看数据源""飞书源才…"分支）②清死概念 ③接对应新命令 ④保留编号交互 + 深链交棒骨架。

| 文件 | 删/改（飞书·死概念） | 接入的新能力 |
|---|---|---|
| **redbeacon.md**（主入口） | 塌缩"两套数据源"→纯本机；链路图去掉"飞书源才需绑表"这步；去 26 处飞书 | 对话入口提示：生成两步(看实发)、AI补题、帮调方案、清理稿/归档 |
| **redbeacon-config.md** | 「飞书(必需)」→飞书搁置；config 只剩**平台登录(必需)+代理(可选)** | `config unset`（删配置项） |
| **redbeacon-feishu.md** | 整个 skill **休眠**：顶部加醒目"飞书暂时搁置，默认本机，无需绑表"，主体最小化保留（以后线上再启，别删文件） | — |
| **redbeacon-panel.md** | 「真源在飞书账号数据表」→本机；看板读本机 | — |
| **redbeacon-locate.md** | 飞书 32 处→本机档案；清「灵感箱/转选题」；定位写本机 | 写完铺选题用 `topics suggest`/`batch`；可提"帮你把方案也调一下"→`plans save` |
| **redbeacon-strategy.md** | 飞书 10 处→本机 | `plans save/material`（帮调方案/传删图）、`strategy image-ref-remove`、定位 `strategy patch` |
| **redbeacon-topics.md** | 清「灵感箱/reset/types」死概念；飞书 6 处→本机 | **AI 补题整条**：`topics suggest`→给用户挑→`topics accept`；引导语 `suggest-template`；`suggest-preview` |
| **redbeacon-generate.md** | 飞书 11 处→本机入审核表；去双源话术 | **生成两步**：默认可先 `--preview` 给用户看实发（标题/封面文案/出图提示词）→确认再 `--commit`（省点、透明）；带货多图 |
| **redbeacon-publish.md** | 飞书 22 处→本机审核表读「通过」；去双源 | — |
| **redbeacon-accounts.md** | 飞书 6 处→建号即扫码；本机无需绑表步 | — |
| **redbeacon-diagnose.md** | 技术排障去/降级"飞书连不上"分支；内容诊断保留 | 内容不行时可提"帮你清掉这篇重来"→`review delete` |
| **redbeacon-login.md**（平台） | 基本 OK；若有"激活员工"话术删（AI 能力已开放） | — |
| **redbeacon-xhslogin.md**（小红书） | 飞书 9 处多是链路描述，顺手去 | — |

---

## 四、改版约束（每一步都守）

- **纯本机口径**：不再提"两套数据源/飞书源/飞书必需/飞书是真源"。审核·选题·定位·归档都在本机。飞书 skill 休眠不删。
- **交互风格保留**：全程人话不露命令名/斜杠；给选择必编号+换行+推荐项；输入成本压最小；用户熟了就让自然语言直说。
- **两入口·深链交棒**：高信息密度（长模板比对、逐条审稿、逐项定位、多账号总览）→ 一句话弹 UI `redbeacon ui app --page <方案|审稿|定位|选题|生成|发布|归档|看板> --account-id N`；短动作留对话。**能力都在 CLI，交棒是 UX 选择。**
- **⚡ 扣点命令执行前先跟用户确认**：`generate`(文案+图) / `generate --preview`(≈1点) / `generate --commit`(出图) / `topics suggest`(≈1点) / `review rewrite`。别在自动流程默默烧点。
- **🗑️ 破坏性命令删前二次确认**：`*delete`、`accounts delete`、`review delete`、`content archive-delete`、`plans material --clear`、`config unset`——CLI 直接执行不拦，**skill 必须先跟用户确认**。
- **输出解析**：CLI 输出 JSON，**进度走 stderr**，取结果只读 stdout（别把 stderr 混进来 parse）。
- **单一真源**：skill 只翻译入参 + 念出参，不自己编业务逻辑；能力都走已有 CLI 命令。

## 五、验证与同步

- **改的是 `.claude/commands/*.md`**（Claude 端直接读、即时生效）。改完 **grep 全仓核对命名/调用点**（命令名 vs skill 文件名两套空间别混）。
- **Codex 派生**：`redbeacon update` 或 `python tools/sync-codex-skills.py` 刷 `~/.codex/skills/`。
- skill 是纯文档，不涉 `uv build`；但若顺手校验引用的 CLI 命令真实存在，可 `redbeacon <命令> --help` 对一下（对照命令手册）。
- 相关记忆：`cli-full-ui-parity`、`feishu-shelved-local-only`、`skill-ui-two-entrance`、`options-before-freetext`、`report-plain-language`、`codex-dual-host`、`skill-naming`。

---
**一句话**：交互骨架能留，内容三件事——①飞书→本机塌缩 ②清死概念 ③接 13 个新能力。建议顺序：先主入口定调，再 topics/generate（新能力密集）、再飞书塌缩批量扫其余。
