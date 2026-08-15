# RedBeacon · 小红书运营数字员工

RedBeacon 是一个本机客户端 + AI 助手能力组成的小红书运营工具。用户在客户端里看账号、选题、文案、图片和审核状态；有 AI 助手时，可以让它帮忙做定位、找选题、生成内容和处理重复操作。

产品页：<https://bytestaff.jiomig.com/market/redbeacon>

## 当前能力

- **账号与登录**：本机管理多个小红书账号，扫码登录，按账号保存资料和登录态。
- **定位与选题**：围绕账号定位生成选题，也可以在操作台里手动维护。
- **文案与配图**：通过 bytestaff 平台生成文案 / 图片，文字卡渲染在本机完成。
- **本机审核**：生成后的内容进入本机审核表，在客户端或 AI 对话里修改、通过、驳回。
- **发布**：发布前检查登录态，按通过的稿件逐条前台发布。
- **全量更新**：客户端、CLI 兼容通道和五种 AI 助手 skill 使用同一套更新能力，不只更新其中一个片段。

业务数据默认保存在本机，不需要配置飞书。飞书云端源属于历史方案，现阶段不作为主流程。

## 安装

正式版只使用长期不变的官网入口；官网会动态选择并校验当前安装器。macOS：

```bash
curl -fsSL https://bytestaff.jiomig.com/redbeacon/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://bytestaff.jiomig.com/redbeacon/install.ps1 | iex
```

装好后可以直接打开桌面应用，也可以在 Claude Code、Codex、OpenClaw、Hermes 或腾讯 WorkBuddy 中使用已安装的 RedBeacon skill。四种采用 Agent Skills 标准的宿主会收到字节一致的 `SKILL.md`；WorkBuddy 需要新建任务或重启后刷新技能列表。

## 测试版

每次正式发布前先走独立测试版通道。测试版和正式版名字、命令、数据、token、skill、manifest 都隔离，可以同时安装。

测试版安装与验证方法见 [RedBeacon-测试版验证指南.md](RedBeacon-测试版验证指南.md)。

## 更新与卸载

- 客户端设置页点击更新、命令行 `redbeacon update`、AI 助手触发升级，都是全量更新。
- 重复执行安装脚本会先检查本机版本；已是最新时跳过大包下载。
- 卸载默认保留业务数据；加 `REDBEACON_PURGE=1` 才清账号数据和平台登录令牌。

正式版卸载：

```bash
curl -fsSL https://bytestaff.jiomig.com/redbeacon/uninstall.sh | bash
```

Windows PowerShell：

```powershell
irm https://bytestaff.jiomig.com/redbeacon/uninstall.ps1 | iex
```

## 仓库结构

```text
.claude/commands/       stable skill 真源目录（发布时派生五宿主格式）
install/                作为制品交给中央发布 Skill 的安装与卸载脚本
tools/                  本机构建、测试、干净制品准备和 skill 通道生成
docs/                   当前文档索引、下载节点契约、本地构建说明与历史归档
release/                构建与发布 provenance（不含凭据）
cli/                    闭源客户端与 CLI 子仓库
```

当前维护入口是 [AGENTS.md](AGENTS.md)，文档边界见 [docs/README.md](docs/README.md)。项目不再管理 OSS 或公开发布；公开发布只使用全局 `bytestaff-digital-employee-publish` Skill。发布前测试入口是 [RedBeacon-测试版验证指南.md](RedBeacon-测试版验证指南.md)，本地双平台构建与 Windows 虚拟机部署见 [docs/local-desktop-build.md](docs/local-desktop-build.md)。
