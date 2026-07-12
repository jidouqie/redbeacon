# RedBeacon · Codex 工作台说明

RedBeacon 是一个小红书运营数字员工：本机客户端 + CLI + AI skill 共同操作同一套本地业务数据。以后维护本项目，优先按本文件判断；如果旧文档和本文件冲突，以本文件、`tools/release.sh`、安装脚本和 CLI updater 代码为准。

## 当前事实

- **当前主路径是本机客户端**：UI 是主入口，CLI 和 skill 是给 AI 助手调用的能力入口。用户即便没有 AI 助手，也应该能直接打开客户端完成主要流程。
- **业务数据默认全在本机**：账号资料、选题、待审稿、归档都在 `~/.redbeacon`；测试版在 `~/.redbeacon_test`。飞书云端源现阶段搁置，不要把“绑飞书表 / 飞书审核”写成当前主流程。
- **平台只负责身份和 AI 能力**：设备令牌正式版在 `~/.bytestaff`，测试版在 `~/.bytestaff_test`。客户端不保存上游模型 key。
- **官网旧地址已退役**：对外产品页是 `https://bytestaff.jiomig.com/market/redbeacon`。安装、更新、zip 包、skill、manifest 的下载源都是 OSS：`https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com`。
- **GitHub 只做构建机**：三端包先由 GitHub Actions 在 Windows/macOS/Linux runner 上打包并上传 OSS；对外发布不走 GitHub Release、GitHub Raw 或服务器下载。GitHub 构建产物必须随用随清，不保留 Actions artifacts；连续触发时取消旧运行，避免无谓额度和存储成本。
- **Windows 是首要兼容平台**：大多数终端用户在 Windows。安装、更新、卸载、CLI、skill、客户端启动、扫码登录和发布链路，都必须优先按 Windows PowerShell 5.1 / GBK 控制台 / 空格路径 / PyInstaller / Playwright 的约束设计；Windows 过不了，测试版也不准发布。

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
- **JSON 不走脆弱命令行参数**：面向 skill/agent 的中文、嵌套、多行 JSON 必须优先走 `--data-file` / `--json-file` 或 stdin；skill 示例里即使是短 JSON 也不要写成 `--data '{"..."}'` 这类内联参数。不要在文档里放 Bash heredoc、`/tmp/`、PowerShell 不通用的重定向示例。

## Skill 与通道

- `.claude/commands/redbeacon*.md` 只是历史命名下的 **stable skill 真源目录**，不代表项目必须继续用 Claude Code 维护。
- Codex skill 由真源派生；测试版 skill 由 `tools/build_channel_skills.py --channel test` 生成，文件名是 `redbeacon-test*.md`，正文调用 `redbeacon-test`。
- 正式版和测试版必须隔离：
  - 正式版：`RedBeacon`、`redbeacon`、`~/.redbeacon`、`~/.bytestaff`、`latest.json`、`skill/`
  - 测试版：`RedBeacon_test`、`redbeacon-test`、`~/.redbeacon_test`、`~/.bytestaff_test`、`latest-test.json`、`skill-test/`

## 更新与卸载

- 所有更新入口都应是**全量更新**：客户端设置页、`redbeacon update`、AI 助手触发升级，都下载当前通道的整包 zip 并替换客户端，同时刷新 CLI 兼容通道和 skill。
- 更新入口必须委托当前通道的 OSS 安装脚本执行，不能在客户端里另写一套手工移动 zip/目录的替换流程。脚本负责拉 manifest 判断版本：已是最新则跳过大包下载，旧版则关闭旧客户端并覆盖安装。
- 重复执行安装脚本时，只先拉很小的 manifest 判断版本；本地已是最新则跳过大包下载，避免浪费 OSS 流量。要强制重装并重新拉 skill，用 `REDBEACON_FORCE_INSTALL=1`。
- 安装/更新必须按不可信旧环境做事务：新包先解压到临时目录，用新包自己的 CLI 在当前通道固定目录准备并真实验证它要求的 Playwright、CloakBrowser 和其他版本化运行时，同时预取并校验同版本 skill；全部通过后才停止旧进程。替换前把旧客户端和当前通道 skill 分别备份，放置新客户端后再次运行桌面初始化与真实卡片渲染，任何一步失败都同时恢复旧客户端和旧 skill。禁止继承用户遗留缓存变量，禁止先覆盖应用、再补依赖。
- 卸载默认保留业务数据；只有设置 `REDBEACON_PURGE=1` 才删除账号数据和平台登录令牌。测试版卸载只清测试版路径，不碰正式版。
- 卸载只能删除当前产品、当前通道拥有的浏览器缓存；不能删除系统全局 `ms-playwright`、`~/.cloakbrowser` 等可能被其他软件或另一通道使用的目录。
- 安装阶段必须预热两套浏览器内核：Playwright Chromium（卡片渲染）和 CloakBrowser Chromium（扫码登录 / 发布）。Windows/macOS/Linux 的内核包不同，由 `redbeacon setup` 按当前系统下载；缓存必须固定在当前通道的 `~/.redbeacon/browser/` 或 `~/.redbeacon_test/browser/`，不要依赖系统默认 `ms-playwright`、`~/.cloakbrowser`、PATH、HOME 或用户已有浏览器。下载源顺序必须包含 RedBeacon OSS `playwright/` / `cloakbrowser/` 兜底；不要再把任一内核下载留到用户第一次扫码。
- 冻结客户端和随包 CLI 启动时必须先清理继承的 `REDBEACON_DATA_DIR`、`BYTESTAFF_HOME`、Playwright/CloakBrowser 缓存与二进制覆盖变量，再按 build channel 选择固定目录。开发态可以保留测试覆盖能力，但交付给用户的程序不能被旧 shell 配置、旧安装器或其他项目带偏。
- 浏览器缓存“有文件”不等于当前版本可用。Playwright 就绪检查必须严格匹配随包 Python 依赖声明的内核 revision；旧 revision 只能显示为待清理诊断信息，不能满足 readiness。安装/更新结束前必须用当前通道内核真实启动并执行一次离线页面操作；启动失败时强制重装当前 revision。
- 小红书扫码 / 发布优先用 CloakBrowser；如果第三方内核虽然下载成功但启动后立即关闭，必须自动切到 RedBeacon 自己预热的 Playwright Chromium fallback，并使用当前通道下的独立 fallback profile。下载成功不等于可运行，关键链路必须验证“能启动并创建页面”。
- 小红书扫码入口每次开始前都必须先停止旧会话，不能复用用户可能已经手动关闭的浏览器窗口；“重新扫码/重新登录”还必须删除当前通道下的浏览器 profile 与 cookie 文件，再出新二维码。运行中遇到 `Target page, context or browser has been closed` 这类死 context，必须停止旧会话并重启后重试一次，旧 worker 退出时必须释放排队任务，避免下一次扫码卡到超时。
- 用户关闭扫码弹窗时必须同步取消后台等待并关闭对应浏览器会话；不能只隐藏 UI、让旧任务继续占用 profile。浏览器下载源不要先做脆弱的 HEAD 预检再决定是否使用 OSS，RedBeacon OSS 应直接优先尝试，失败才切官方源。
- Windows ARM64 客户机不能直接判死。当前 Windows 桌面包是 x64 包，ARM64 Windows 通过系统 x64 仿真运行；CloakBrowser 要映射到 `windows-x64` 内核包，不能因为第三方库没有列 `Windows ARM64` 就让扫码登录失败。
- Windows `.ps1/.cmd` 安装链路必须 ASCII-only；skill 和 Codex `SKILL.md` 必须 UTF-8，发布前检查不能出现 `�` 这类替换字符。
- Windows bundle smoke 必须捕获桌面初始化里的 `Traceback` / `ModuleNotFoundError` / `ImportError`；如果日志里有隐藏崩溃，即使 workflow 标绿也不准发布。PyInstaller spec 必须显式包含 `_sqlite3`，并把文字卡片所需的 `RedBeaconRenderer(.exe)` 作为独立可执行文件打进同一个包；三端 smoke 都要用冻结 CLI 准备当前 Playwright revision，再让冻结渲染器真实产出封面和正文 PNG，不能只验证主客户端或 `--list-styles`。
- 组合业务结果必须逐项验收：例如“AI 封面 + 文字卡片”要求两部分都成功，不能因为 AI 图存在就吞掉卡片渲染错误并保存半成品。渲染失败要阻止入库、记录完整日志，并给用户短而可操作的修复提示。

## ByteStaff 平台协作

- 平台设备令牌代表 ByteStaff 账号，不代表某个数字员工。`product` / `product_code` 只做来源归因，不参与权限；客户端不得发送 `account_id`，不得再从 `entitlements`、员工激活状态或产品上下架推导 AI 能力。
- `/device/checkin` 默认发送 `{}`，返回的账号、点数和 `limits.ai` 是客户端真源。checkin 要按 `refresh_after_seconds` 缓存并做账号级 single-flight；旧平台缺少 limits 时保守回退总并发 3、embedding 2、chat 2、image 1。
- 同一账号的客户端窗口、CLI 和 skill 必须共用账号级 AI 调度状态。RedBeacon 使用 `~/.bytestaff/ai_scheduler.sqlite3`（测试版对应测试目录）协调总并发、能力并发、令牌桶、租约、重试次数和熔断，不能只做单进程 Semaphore。
- 客户端生成笔记必须严格串行：普通生成、带货生成、预生成和继续出图共用一个 FIFO 工位，多选只负责入队，必须等前一篇完整成功或失败后才开始下一篇。禁止按“每篇一个线程/Promise”同时生成；本机等待队列最多保留 20 个任务，满了要明确提示用户。
- RedBeacon 文案属于机器可解析交付物，调用平台时必须声明 `redbeacon_copy_v1` 白名单输出契约。平台必须在结算前验收必需字段；格式损坏、缺字段或空正文按 `upstream_error` 原路回补。客户端只允许做不调用 AI 的确定性兼容修复，禁止为了修 JSON 再发一笔收费请求，也禁止由客户端事后自报失败申请退款。
- `request_id` 必须遵守平台幂等语义：429 / duplicate_pending 沿用原 id；明确收到 duplicate_failed / 502 upstream_error 后换新 id；网络断线 / 503 结果未知时只沿用原 id 确认一次。所有重试先释放运行槽，遵守 Retry-After（秒数或 HTTP 日期）并做退避；连续故障触发短熔断。

## 发布流程

发布纪律是硬规则：**永远先发测试版，让用户测；用户明确确认通过后，才允许发正式版。**

- 测试版和正式版的客户端打包必须走同一个 GitHub Actions `Build desktop bundles`、同一个 PyInstaller spec、同一份代码、同一份 `cli/uv.lock` 冻结依赖；只能因为 channel 不同导致应用名、命令名、bundle id、数据目录、manifest、OSS 路径、skill 名不同。
- 桌面运行依赖和 PyInstaller 必须锁定已验证版本，workflow 必须用 `uv sync --frozen`；三端 job 打包前先跑全量测试，macOS/Linux 和 Windows 都要跑冻结包桌面初始化 smoke。测试版与正式版分两次构建时，禁止临时解析到不同的上游依赖版本。
- 构建包上传到带版本号的 OSS 路径（`app[/test]/releases/<version>/`），skill 同样上传到 `skill[-test]/releases/<version>/` 并写入 SHA-256 与 channel/version/commit 元数据。不能在构建阶段覆盖当前线上固定包。发布时先准备客户端、CLI、安装脚本和版本化 skill，最后一步才上传 `latest.json` / `latest-test.json` 切流量；固定下载直链只是兼容别名，不是安装事务真源。
- Windows job 是发布阻断项：`windows-latest` runner 必须完成 PyInstaller 打包、zip 解压、桌面 smoke、Traceback/ImportError 日志扫描和 OSS 上传；即使 macOS/Linux 通过，只要 Windows 未通过或未运行，都不能执行 `tools/release.sh --channel test`。
- GitHub Actions 只允许把构建包上传到 OSS，不允许保留 GitHub artifacts 或走 GitHub Release 兜底；没有 OSS key / OSS 上传失败就让 workflow 失败，不能留下临时包继续占私有仓库额度。
- 三端 matrix 全部成功后，独立 `mark-complete` job 才能在该版本 OSS 目录写入带 commit 的 `build-complete.json`。`tools/release.sh` 必须核对 marker 的 channel、version、commit 与本地 CLI HEAD 全部一致，防止同一版本重跑时混用旧平台包。
- 发布前必须确认 Playwright / CloakBrowser 当前依赖版本的三端内核包在 RedBeacon OSS 可访问；CloakBrowser 用 `tools/mirror_cloakbrowser_browsers.py` 同步，脚本默认跳过已存在对象，只有需要重传时才加 `--force`。注意 Windows 包名是 `.zip`，不能按 macOS/Linux 的 `.tar.gz` 推导。
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
- 引导用户时一次只问一个问题，一次只推进一件事；需要用户回应时给 2-3 个建议选项，让用户做选择题，不要把多个问题塞进同一轮。
- onboarding 可自动推进，只有需要扫码、用户提供信息、真正分支或不可逆动作时再停。
- 遇到旧文档提到飞书主链路、旧官网、GitHub 发布源、Cloud Code/Claude Code 作为唯一维护方式时，按历史资料处理，不要照搬到当前实现。
