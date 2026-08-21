# RedBeacon · 小红书运营数字员工

> 把账号定位、选题、创作、审稿和发布连成一套可持续的小红书自动化运营与获客系统。

RedBeacon 是一位运行在用户电脑上的小红书运营数字员工。它以桌面客户端为主入口，围绕每个账号保存独立的定位、选题库、内容方案、待审稿和发布归档；设置好账号后，既可以逐步人工操作，也可以在客户端运行期间按计划自动补题、写稿、配图、预审并发布。

没有 AI 助手也能直接使用完整客户端。使用 Codex、Claude Code、OpenClaw、Hermes 或腾讯 WorkBuddy 时，RedBeacon Skill 会读取同一份本机账号档案，优先使用宿主已有的文案与生图能力；宿主缺少能力或执行失败时，再由平台能力无感兜底，成果仍统一进入客户端审稿台和后续发布流程。

产品页：<https://bytestaff.jiomig.com/market/redbeacon>

## 主要能力

- **多账号工作台**：账号资料、登录态、定位、选题、方案、稿件和归档按账号隔离，切换账号即可进入各自的运营空间。
- **定位与对标学习**：可从零梳理账号定位，也可学习指定小红书账号或单篇笔记的内容节奏、表达方法和视觉语言；分析结果先预览，确认后才写入当前账号。
- **选题与内容方案**：按账号定位维护选题库，配置文案风格、视觉方案和不同笔记类型，并在选题不足时自动补充。
- **文案与图片创作**：支持平台创作、AI 助手协同创作、文字卡片和用户自备素材；所有导入或生成图片都会先按统一规则净化并重新存储。
- **本机审稿台**：可以自主添加完整笔记、修改标题与正文、回车添加标签，以及增加、更换、排序或删除图片。通过前强制检查标题不超过 20 个字、正文不超过 888 个字且至少保留 1 张图片。
- **发布与归档**：支持立即发布和逐篇设置小红书定时发布；提交前实时复验登录态和稿件完整性，成功后自动归档。发布点数由平台动态配置，发布失败不结算。
- **账号级全流程自动化**：可设置每天开始时间、执行次数、批次间隔和每批篇数，并选择自动补题、自动通过审稿和自动发布。自动化开启后会在客户端运行期间防止系统空闲休眠；关闭客户端或错过时间点不会偷偷补跑。
- **完整安装与更新**：客户端、CLI、浏览器运行时和五种 AI 助手 Skill 使用同一套全量安装、更新和回滚事务，正式版与测试版可以同时存在。

业务数据默认保存在本机，不需要配置飞书。平台只承担账号身份、AI 能力调度和发布结算，不保存用户的本地运营数据库，也不向客户端下发上游模型密钥。

## 安装

正式版使用长期不变的官网入口。安装器会自动选择当前版本，并准备客户端、命令、Skill 和所需浏览器运行时。

macOS：

```bash
curl -fsSL https://bytestaff.jiomig.com/redbeacon/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://bytestaff.jiomig.com/redbeacon/install.ps1 | iex
```

安装完成后可以直接打开 RedBeacon 桌面客户端。已安装 Codex、Claude Code、OpenClaw、Hermes 或腾讯 WorkBuddy 时，对应的 RedBeacon Skill 会一并更新；WorkBuddy 需要新建任务或重启后刷新技能列表。

## 正式版与测试版

每次正式发布前先走独立测试版通道。两个通道的应用名、命令、业务数据、平台令牌、浏览器缓存、Skill 和版本清单完全隔离，可以同时安装：

| 项目 | 正式版 | 测试版 |
| --- | --- | --- |
| 应用 / 命令 | `RedBeacon` / `redbeacon` | `RedBeacon_test` / `redbeacon-test` |
| 业务数据 | `~/.redbeacon` | `~/.redbeacon_test` |
| 平台登录 | `~/.bytestaff` | `~/.bytestaff_test` |

测试版安装与验收方法见 [RedBeacon-测试版验证指南.md](RedBeacon-测试版验证指南.md)。

## 更新与卸载

- 客户端设置页、`redbeacon update` 和 AI 助手触发的升级都是同一套全量更新。
- 重复执行安装脚本会先检查本机版本；已是最新且依赖健康时跳过客户端大包，只刷新必要组件和 Skill。
- 卸载默认保留账号资料、稿件和登录数据；只有明确设置 `REDBEACON_PURGE=1` 才会清除当前通道数据。

正式版卸载：

```bash
curl -fsSL https://bytestaff.jiomig.com/redbeacon/uninstall.sh | bash
```

Windows PowerShell：

```powershell
irm https://bytestaff.jiomig.com/redbeacon/uninstall.ps1 | iex
```

## 开源与专有边界

本公开仓库主要提供 RedBeacon Skill、安装与卸载脚本、公开文档，以及不含密钥的构建/发布辅助内容。这些公开文件按仓库 [LICENSE](LICENSE) 使用。

RedBeacon 客户端、CLI 内核、数据层、内容编排和小红书浏览器自动化实现属于专有软件，源码保存在独立私有仓库，不进入本公开仓库；对用户只分发封装后的 Windows 和 macOS 客户端制品。核心服务鉴权、AI 调度和计费逻辑保留在服务端。

## 仓库结构

```text
.agents/skills/         通用 Agent Skills 源文件
.claude/commands/       Claude Code 兼容命令源文件
install/                正式版 / 测试版安装与卸载脚本
tools/                  Skill 生成、双平台构建检查与公开辅助工具
docs/                   当前文档索引、下载节点契约和构建说明
release/                不含凭据的版本与发布契约
cli/                    本机私有内核仓库；被公开仓 .gitignore 明确排除
```

当前维护真源是 [AGENTS.md](AGENTS.md)，文档边界见 [docs/README.md](docs/README.md)，本地双平台构建说明见 [docs/local-desktop-build.md](docs/local-desktop-build.md)。项目仓库只产出经过验证的干净制品；对外发布由统一发布系统将同一份本机制品分别上传到中央 OSS 和下载节点。
