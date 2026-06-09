# RedBeacon · Agent 工作台说明（host 无关）

RedBeacon 是小红书内容自动化工具。本文件是给**任何 AI agent（Claude Code / Codex 等）**的项目级入口说明；具体每个能力的详细步骤在对应 skill 里。

## 架构（一句话）

- **真引擎是 `redbeacon` CLI**（harness 无关的命令行工具，闭源、装在本机）。所有实际动作——建号 / 扫码登录 / 绑飞书表 / 生成文案配图 / 发布——都是调 `redbeacon` 子命令完成。
- **能力以 skill 形式提供**，正文都是「人话指令 + 调 `redbeacon` CLI」。同一套正文在两端共用：
  - Claude Code：`.claude/commands/redbeacon*.md`（斜杠命令，如 `/redbeacon`）— **真源**
  - Codex：`~/.codex/skills/redbeacon*/SKILL.md`（文件夹式，从真源派生的 bridge）
- 真源始终是 `.claude/commands/` 的 markdown；Codex 端是生成物，不在 bridge 里维护长逻辑。

## 整条运作链路

**配置 → 建账号 → 登录小红书 → 飞书绑表 → 定位+选题 →（面板调样式·二次确认）→ 生成 →（飞书审核改稿）→ 发布**

- 审核与改稿 **100% 在飞书多维表格**，本地无审核。
- 生成与发布都是**手动命令触发**，无后台常驻服务 / 无定时自动发布。
- 进度判定用 `redbeacon readiness`（多账号逐个开号用 `readiness --account-id N`）。

## 能力 → skill 路由（两端 skill 名已统一，全英文）

| 用户意图 | skill 名（Claude 斜杠加 `/`，Codex 同名）|
|---|---|
| 不确定该干嘛 / 主入口 | `redbeacon` |
| 配 AI / 飞书 / 代理 | `redbeacon-config` |
| 建号 / 改名 / 删号 / 多账号解锁 | `redbeacon-accounts` |
| 扫码登录小红书 | `redbeacon-login` |
| 绑账号的飞书多维表 | `redbeacon-feishu` |
| 账号定位（赛道/受众/差异化/变现）| `redbeacon-locate` |
| 补题 / 重铺 / 选题规划 | `redbeacon-topics` |
| 单点改定位 / 文案预设 / 图片预设 | `redbeacon-strategy` |
| 弹网页面板审阅·微调·试生成 | `redbeacon-panel` |
| 「文案/图不对劲」诊断调参 | `redbeacon-diagnose` |
| 生成内容 | `redbeacon-generate` |
| 发布已通过内容 | `redbeacon-publish` |

> **两端 skill 名完全一致、全英文**（Claude Code 用 `/redbeacon-locate` 这样的斜杠命令，Codex 用同名 skill）。不再有中英差异。完整对照见 `tools/skill-bridge-map.md`。

## 给 agent 的硬规则

- **交互风格 = 像得力下属服务老板**：主动带领、别让用户懵；新用户你来引导，熟了就让他自然语言直说。
  - **全程人话**：给用户的回复不出现 skill 名 / 斜杠命令 / `redbeacon xxx`（那是你后台执行的）；除非用户主动要命令，否则别提、别列。
  - **给选择必须编号 + 换行排版**，让用户回一个数字就行（`1. … / 2. … / 3. …`，末尾补「回数字就行，也可以直接说」）。能给选项就别让用户打字，能一个数字就别让他写句子。
  - 该替用户想的下一步先想好、给推荐（标「推荐」）；用户熟了直接自然语言提要求就照做，别硬塞编号流程。
- **自动推进**：onboarding 链路每步都是必需的，默认一路推进到 ready，别在阶段间反复问「要不要继续」。只在「需用户给信息 / 扫码 / 真正的分支或不可逆动作」时停。
- **顺序固定**：登录 → 飞书绑表 → 定位（先扫码让账号落地，再绑审核表，最后定方向）。
- **多账号**：全局 `readiness` 是「任一账号满足即 ready」的聚合判断；开第 2+ 个号用 `readiness --account-id N` 逐号驱动，别因全局 ready 以为新号也配好了。
- **别承诺**：本地审核、定时自动发布、常驻后台服务——都没有，别向用户许诺。
- 命令成功走 stdout JSON、失败走 stderr `{"error","next"}`；把 error 讲人话给用户，按 next 自愈。

## 升级（两端一起刷）

`redbeacon update` 会同时：升级 CLI + 刷新 Claude 端 `.claude/commands/` + （若本机装了 Codex）派生刷新 `~/.codex/skills/`。开发态手动同步 Codex 端用 `tools/sync-codex-skills.py`。
