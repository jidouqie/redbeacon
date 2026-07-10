# RedBeacon Skill 通道表

`.claude/commands/redbeacon*.md` 是 stable skill 的真源目录。这个目录名是历史遗留，不代表后续维护必须使用 Claude Code；Codex 端、测试版 skill、用户机安装包都从这里派生。

## 正式版 skill

正式版文件名保持 `redbeacon*.md`，正文调用 `redbeacon`，安装到用户的 AI 命令目录后再由 updater 派生 Codex skill。

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
- 发布到 OSS `skill-test/`，manifest 是 `latest-test.json`

测试版 skill 必须独立于正式版，避免测试命令误驱动正式客户端或正式数据。

## 刷新方式

- 用户机更新：`redbeacon update` 或 `redbeacon-test update`，按当前通道全量刷新客户端、CLI 兼容通道和 skill。
- 开发态刷新 Codex skill：改 `.claude/commands/` 后运行 `python tools/sync-codex-skills.py`；它会同时刷新用户目录 `~/.codex/skills/` 和仓库工作台 `.agents/skills/source-command-redbeacon*/`，后者只是派生副本。
- 发布态刷新 OSS skill：运行 `tools/release.sh` 或 `tools/release.sh --channel test`。
