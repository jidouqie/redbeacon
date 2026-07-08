# RedBeacon · Codex 工作台说明

RedBeacon 是一个小红书运营数字员工：本机客户端 + CLI + AI skill 共同操作同一套本地业务数据。以后维护本项目，优先按本文件判断；如果旧文档和本文件冲突，以本文件、`tools/release.sh`、安装脚本和 CLI updater 代码为准。

## 当前事实

- **当前主路径是本机客户端**：UI 是主入口，CLI 和 skill 是给 AI 助手调用的能力入口。用户即便没有 AI 助手，也应该能直接打开客户端完成主要流程。
- **业务数据默认全在本机**：账号资料、选题、待审稿、归档都在 `~/.redbeacon`；测试版在 `~/.redbeacon_test`。飞书云端源现阶段搁置，不要把“绑飞书表 / 飞书审核”写成当前主流程。
- **平台只负责身份和 AI 能力**：设备令牌正式版在 `~/.bytestaff`，测试版在 `~/.bytestaff_test`。客户端不保存上游模型 key。
- **官网旧地址已退役**：对外产品页是 `https://bytestaff.jiomig.com/market/redbeacon`。安装、更新、zip 包、skill、manifest 的下载源都是 OSS：`https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com`。
- **GitHub 只做构建机**：三端包先由 GitHub Actions 在 Windows/macOS/Linux runner 上打包并上传 OSS；对外发布不走 GitHub Release、GitHub Raw 或服务器下载。

## 主流程

当前用户链路是：

**安装 / 更新 -> 平台登录 -> 建账号 -> 小红书扫码登录 -> 定位 / 选题 -> 生成 -> 本机审核 -> 发布**

- 审核改稿在客户端操作台或对话命令里完成，不依赖飞书。
- 生成和发布是用户主动触发的前台动作；不要承诺后台常驻服务。
- 小红书原生定时字段如果存在，是提交给小红书侧，不是 RedBeacon 自己常驻调度。

## 架构原则

- **一份业务核心**：核心业务逻辑应收口到 `cli/src/redbeacon/core/usecases/`、`core/ports.py` 和对应 `infra/` 实现。CLI、UI 后端、skill 都只是薄入口。
- **UI 不寄生 CLI**：UI 后端不能靠拼 CLI 命令、爬 CLI 文本来完成业务；它应和 CLI 一样调用同一套 usecase。
- **预设集中**：用户可调的默认模板、提示词骨架、视觉/文案预设，优先集中在 `core/presets.py` 或明确的资源文件里，避免多处手写第二份。
- **发布源单一**：不要把安装包、skill 或版本清单重新指回旧官网、GitHub Raw、仓内 `pip/`，或任何非 OSS 的对外下载源。

## Skill 与通道

- `.claude/commands/redbeacon*.md` 只是历史命名下的 **stable skill 真源目录**，不代表项目必须继续用 Claude Code 维护。
- Codex skill 由真源派生；测试版 skill 由 `tools/build_channel_skills.py --channel test` 生成，文件名是 `redbeacon-test*.md`，正文调用 `redbeacon-test`。
- 正式版和测试版必须隔离：
  - 正式版：`RedBeacon`、`redbeacon`、`~/.redbeacon`、`~/.bytestaff`、`latest.json`、`skill/`
  - 测试版：`RedBeacon_test`、`redbeacon-test`、`~/.redbeacon_test`、`~/.bytestaff_test`、`latest-test.json`、`skill-test/`

## 更新与卸载

- 所有更新入口都应是**全量更新**：客户端设置页、`redbeacon update`、AI 助手触发升级，都下载当前通道的整包 zip 并替换客户端，同时刷新 CLI 兼容通道和 skill。
- 重复执行安装脚本时，只先拉很小的 manifest 判断版本；本地已是最新则跳过大包下载，避免浪费 OSS 流量。要强制重装并重新拉 skill，用 `REDBEACON_FORCE_INSTALL=1`。
- 卸载默认保留业务数据；只有设置 `REDBEACON_PURGE=1` 才删除账号数据和平台登录令牌。测试版卸载只清测试版路径，不碰正式版。
- 安装阶段必须预热 Playwright 浏览器内核（扫码登录、发布、卡片渲染都依赖它）。Windows/macOS/Linux 的内核包不同，由 `redbeacon setup` 按当前系统下载；下载源顺序包含 npmmirror、RedBeacon OSS `playwright/` 兜底和官方 CDN。不要再把内核下载留到用户第一次扫码。
- Windows `.ps1/.cmd` 安装链路必须 ASCII-only；skill 和 Codex `SKILL.md` 必须 UTF-8，发布前检查不能出现 `�` 这类替换字符。
- Windows bundle smoke 必须捕获桌面初始化里的 `Traceback` / `ModuleNotFoundError` / `ImportError`；如果日志里有隐藏崩溃，即使 workflow 标绿也不准发布。PyInstaller spec 必须显式包含 `_sqlite3`。

## 发布流程

发布纪律是硬规则：**永远先发测试版，让用户测；用户明确确认通过后，才允许发正式版。**

- 测试版和正式版的客户端打包必须走同一个 GitHub Actions `Build desktop bundles`、同一个 PyInstaller spec、同一份代码；只能因为 channel 不同导致应用名、命令名、bundle id、数据目录、manifest、OSS 路径、skill 名不同。
- 如果测试版发布后又改了任何客户端、CLI、skill、安装/更新/卸载、发布脚本相关代码，之前的测试结论作废，必须重新发测试版让用户测，不能直接发正式版。
- 正式版发布必须是“把用户确认通过的测试版同一套代码切到 stable 通道再打一次包”。绝不允许测试版能跑、正式版因为另一套流程或另一份代码崩掉。
- 发布前必须通过 `tools/check_release_contracts.py`。其中一条硬约束是：测试版 Codex skill 只能写到 Codex 真正扫描的 `~/.codex/skills/redbeacon-test*/SKILL.md`，不能写到独立根目录；安装、更新、卸载都要保持正式版和测试版 skill 隔离。

固定步骤：

1. 在 `cli/` 子仓库改版本并完成本地/CI 自检。
2. 先触发 GitHub Actions `Build desktop bundles`，`channel=test`，让三端 runner 构建测试版 PyInstaller 包并上传 OSS `app/test/`。
3. 在根仓库运行 `tools/release.sh --channel test "测试版更新说明"`，发布脚本会先跑发布契约检查，再发布 `latest-test.json`、测试版安装/卸载入口和测试版 skill。
4. 把测试版链接交给用户测试；等待用户明确说“测试通过 / 可以发正式版”。
5. 用户确认后，不改代码，触发同一个 GitHub Actions，`channel=stable`，从同一套代码构建正式版包并上传 OSS `app/`。
6. 运行 `REDBEACON_STABLE_APPROVED=1 tools/release.sh "正式版更新说明"`，发布 `latest.json`、正式版安装/卸载入口和正式版 skill。
7. 验证正式版 manifest、三端 zip、安装脚本、skill 都来自 OSS。测试方法见 `RedBeacon-测试版验证指南.md`。

## 给 agent 的工作规则

- 面向终端用户时用人话，不主动暴露 skill 名、内部命令名和实现细节；用户主动要命令时再给。
- 给选择时用编号，推荐项标清楚，让用户能回一个数字。
- onboarding 可自动推进，只有需要扫码、用户提供信息、真正分支或不可逆动作时再停。
- 遇到旧文档提到飞书主链路、旧官网、GitHub 发布源、Cloud Code/Claude Code 作为唯一维护方式时，按历史资料处理，不要照搬到当前实现。
