# RedBeacon Skill 通道表

`.claude/commands/redbeacon*.md` 是 stable skill 的真源目录。这个目录名是历史遗留，不代表后续维护必须使用 Claude Code；Codex、OpenClaw、Hermes、腾讯 WorkBuddy、测试版 skill 和用户机安装包都从这里派生。

## 支持宿主

| 宿主 | 用户级落点 | 发布格式 |
|---|---|---|
| Claude Code | `~/.claude/commands`（测试版为独立 commands 目录） | `redbeacon*.md` |
| Codex | `~/.codex/skills/redbeacon*/SKILL.md` | 通用 Agent Skills |
| OpenClaw | `~/.openclaw/skills/redbeacon*/SKILL.md` | 通用 Agent Skills |
| Hermes | `~/.hermes/skills/redbeacon*/SKILL.md` | 通用 Agent Skills |
| WorkBuddy | `~/.workbuddy/skills/redbeacon*/SKILL.md` | 兼容 OpenClaw 的通用 Agent Skills |

四个 `SKILL.md` 宿主安装的文件必须字节一致。安装、更新、回滚和卸载把五个宿主视为一个事务；测试版使用 `redbeacon-test*` 名称，因此能和正式版共存。

## 正式版 skill

正式版文件名保持 `redbeacon*.md`，正文调用 `redbeacon`。发布构建器同时生成 Claude Code 命令文件和四宿主共用的通用 `SKILL.md`，安装器直接放置经过制品校验的字节，不在用户机临时转换正文。

| 文件 | 说明 |
|---|---|
| `redbeacon.md` | 主入口 |
| `redbeacon-accounts.md` | 账号管理 |
| `redbeacon-config.md` | 平台登录 / 代理配置 |
| `redbeacon-diagnose.md` | 诊断 |
| `redbeacon-generate.md` | 生成内容 |
| `redbeacon-locate.md` | 账号定位 |
| `redbeacon-login.md` | 平台登录 |
| `redbeacon-panel.md` | 打开操作台 |
| `redbeacon-plans.md` | 生成方案 |
| `redbeacon-publish.md` | 发布 |
| `redbeacon-review.md` | 本机审核 |
| `redbeacon-strategy.md` | 策略微调 |
| `redbeacon-topics.md` | 选题 |
| `redbeacon-xhslogin.md` | 小红书扫码登录 |

`redbeacon-feishu` 已退役，不是当前主流程的一部分。

## 测试版 skill

测试版由 `tools/build_channel_skills.py --channel test` 自动生成：

- 文件名从 `redbeacon*.md` 变成 `redbeacon-test*.md`
- 正文里的 `redbeacon` 命令变成 `redbeacon-test`
- 本机路径从 `~/.redbeacon` / `~/.bytestaff` 变成 `~/.redbeacon_test` / `~/.bytestaff_test`
- 作为测试版应用 release unit 的 `skill/redbeacon-skill.tar.gz` 交给中央发布 Skill，canonical manifest 是 `projects/redbeacon/test/latest.json`。

测试版 skill 必须独立于正式版，避免测试命令误驱动正式客户端或正式数据。

## 刷新方式

- 用户机更新：`redbeacon update` 或 `redbeacon-test update`，按当前通道全量刷新客户端、CLI 兼容通道和 skill。
- 开发态仓库工作台刷新：改 `.claude/commands/` 后运行 `python tools/sync-codex-skills.py`；它刷新仓库 `.agents/skills/source-command-redbeacon*/` 和本机 Codex 开发副本。面向用户的五宿主文件只以 `tools/build_channel_skills.py` 生成的发布 bundle 为准。
- 发布态刷新 skill：先用 `tools/build_desktop_local.sh` 生成干净制品树，再由全局 `bytestaff-digital-employee-publish` Skill 发布整个 release unit；项目内不存在单独 OSS skill 上传入口。
