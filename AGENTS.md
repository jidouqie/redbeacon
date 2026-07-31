# RedBeacon · Codex 工作台说明

RedBeacon 是一个小红书运营数字员工：本机客户端 + CLI + AI skill 共同操作同一套本地业务数据。以后维护本项目，优先按本文件判断；如果旧文档和本文件冲突，以本文件、全局 `bytestaff-digital-employee-publish` Skill、安装脚本和 CLI updater 代码为准。

## 当前事实

- **当前主路径是本机客户端**：UI 是主入口，CLI 和 skill 是给 AI 助手调用的能力入口。用户即便没有 AI 助手，也应该能直接打开客户端完成主要流程。
- **业务数据默认全在本机**：账号资料、选题、待审稿、归档都在 `~/.redbeacon`；测试版在 `~/.redbeacon_test`。飞书云端源现阶段搁置，不要把“绑飞书表 / 飞书审核”写成当前主流程。
- **平台只负责身份和 AI 能力**：设备令牌正式版在 `~/.bytestaff`，测试版在 `~/.bytestaff_test`。客户端不保存上游模型 key。
- **统一下载入口与动态选择器**：对外产品页是 `https://bytestaff.jiomig.com/market/redbeacon`；正式版 `/redbeacon/install.*`、测试版 `/redbeacon-test/install.*` 等官网入口和用户命令长期不变。平台入口按通道解析中央上海 OSS `https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/projects/redbeacon/<channel>/latest.json`，校验身份、版本、大小、SHA-256 与不可变 URL 后，以 `307 + Cache-Control: no-store` 选择当前版本脚本或包；只允许很短且有明确上限的服务端清单缓存（当前 15 秒），不能让浏览器或 CDN 缓存选择结果。新发布的节点 origin 由受保护回执/Profile 固定为 `https://download.bytestaff.jiomig.com`，但客户端只能消费 manifest 的 `download_urls=[node_url,url]`，不得硬编码域名或 IP；历史 manifest 不回写。普通发新版只由全局发布 Skill 原子切换 canonical manifest，不修改官网页面、公开命令、数据库或 Nginx；大文件先试统一下载节点一次，失败后回落 manifest 中不可变的中央 OSS URL。
- **客户端在本机双平台构建**：Apple Silicon Mac 本机打 `mac-arm64`，Windows 11 ARM64 虚拟机通过 SSH 使用 **x64 CPython** 打 `win-x64`；两端必须来自同一个已提交的 CLI 源码归档。项目只负责构建并验证干净制品目录，不持有 OSS 凭据、不上传、不切 manifest。发布完全由全局 `bytestaff-digital-employee-publish` Skill 执行。
- **旧 GitHub 打包方案已冷归档**：历史文件只存在于不可直接索引的 `.history/redbeacon-legacy-github-build-2026-07-16.tar.gz`。除非用户明确要求“查看或恢复旧 GitHub 打包方案”，任何 agent 都不得列出、读取、解压、搜索、比较、引用该压缩包，也不得从 git 历史恢复旧 workflow。日常上下文和发布检查只能确认归档文件存在，不能打开内容。
- **旧项目内发布方案已冷归档**：历史文件只存在于不可直接索引的 `.history/redbeacon-legacy-project-release-2026-07-17.tar.gz`。除非用户明确要求“查看或恢复旧项目发布方案”，任何 agent 都不得列出、读取、解压、搜索、比较、引用该压缩包，也不得从 git 历史恢复项目内 OSS 上传、镜像同步、manifest 生成或发布脚本。日常检查只能确认该文件存在且非空。
- **Linux 客户端暂停分发**：现阶段不构建、不写入 manifest、不提供 Linux 下载链接。Linux 兼容代码可以保留，未来恢复时必须重新建立真实 Linux 构建机和完整 smoke，不能拿 Mac 包代替。
- **Windows 是首要兼容平台**：大多数终端用户在 Windows。安装、更新、卸载、CLI、skill、客户端启动、扫码登录和发布链路，都必须优先按 Windows PowerShell 5.1 / GBK 控制台 / 空格路径 / PyInstaller / Playwright 的约束设计；Windows 过不了，测试版也不准发布。

## 主流程

当前用户链路是：

**安装 / 更新 -> 平台登录 -> 建账号 -> 小红书扫码登录 -> 定位 / 选题 -> 生成 -> 本机审核 -> 发布**

- 审核改稿在客户端操作台或对话命令里完成，不依赖飞书。
- 生成和发布是用户主动触发的前台动作；不要承诺后台常驻服务。
- 小红书原生定时字段如果存在，是提交给小红书侧，不是 RedBeacon 自己常驻调度。
- 发布时间在发布页按**每篇笔记**选择：默认立即发布；切到定时发布后选择北京时间，必须距真正提交时至少 1 小时、最多 14 天。单篇和批量都要逐篇携带选择，批量任务排队后在每篇真正提交前重验；无效或过期时间必须拦截，绝不能静默降级成立即发布。

## 架构原则

- **一份业务核心**：核心业务逻辑应收口到 `cli/src/redbeacon/core/usecases/`、`core/ports.py` 和对应 `infra/` 实现。CLI、UI 后端、skill 都只是薄入口。
- **UI 不寄生 CLI**：UI 后端不能靠拼 CLI 命令、爬 CLI 文本来完成业务；它应和 CLI 一样调用同一套 usecase。
- **客户端按通道单例**：同一用户会话中正式版只能有一个正式窗口，测试版只能有一个测试窗口，但两通道可以并存。必须使用操作系统自动释放的文件锁，不能把“固定端口被占用”或残留 PID 文件当单例；第二次启动应通过仅限本机且带随机口令的唤醒通道恢复并置前已有窗口，不能再创建本机服务、数据库会话或工作队列。
- **预设集中**：用户可调的默认模板、提示词骨架、视觉/文案预设，优先集中在 `core/presets.py` 或明确的资源文件里，避免多处手写第二份。
- **用户模板自由**：文案和视觉模板里的占位符只是可选的自动填充工具，不要求出现、凑齐或保留。引擎只替换注册过且有明确语义的占位符；其他花括号内容按用户原文保留，不能以“变量未填写”为由阻止生成。
- **发布边界单一**：项目只产出已测试的干净制品树；不得新增 OSS SDK、凭据、上传、节点 SSH、manifest 生成/切换或兼容别名发布逻辑。所有公开发布只调用全局发布 Skill。
- **JSON 不走脆弱命令行参数**：面向 skill/agent 的中文、嵌套、多行 JSON 必须优先走 `--data-file` / `--json-file` 或 stdin；skill 示例里即使是短 JSON 也不要写成 `--data '{"..."}'` 这类内联参数。不要在文档里放 Bash heredoc、`/tmp/`、PowerShell 不通用的重定向示例。

## Skill 与通道

- `.claude/commands/redbeacon*.md` 只是历史命名下的 **stable skill 真源目录**，不代表项目必须继续用 Claude Code 维护。
- 当前正式支持 **Claude Code、Codex、OpenClaw、Hermes、腾讯 WorkBuddy**。Claude Code 使用命令文件；其余四个宿主消费同一份发布字节的标准 `SKILL.md`，分别安装到 `~/.codex/skills`、`~/.openclaw/skills`、`~/.hermes/skills`、`~/.workbuddy/skills`。不得为某个宿主复制并手改第二份正文。
- 测试版 skill 由 `tools/build_channel_skills.py --channel test` 统一生成，名称和正文都调用 `redbeacon-test`；正式版与测试版在五个宿主中都必须并存。skill bundle manifest 必须声明完整宿主矩阵，缺一个即为坏包。
- skill 可能被平台单独分发到一台尚未安装客户端的新机器，因此每个 skill 都必须先验证对应 CLI 是否存在；不存在时必须从当前通道 canonical manifest 精确读取 `installers/install.*` 后调用。禁止让 AI 猜测 zip 文件名、大小写、版本目录或下载节点地址，也禁止绕过安装脚本直接解压客户端。
- 正式版和测试版必须隔离：
  - 正式版：`RedBeacon`、`redbeacon`、`~/.redbeacon`、`~/.bytestaff`、`projects/redbeacon/stable/latest.json`
  - 测试版：`RedBeacon_test`、`redbeacon-test`、`~/.redbeacon_test`、`~/.bytestaff_test`、`projects/redbeacon/test/latest.json`

## 更新与卸载

- 所有更新入口都应是**全量更新**：客户端设置页、`redbeacon update`、任一受支持 AI 助手触发升级，都下载当前通道的整包 zip 并替换客户端，同时刷新 CLI 兼容通道和五宿主 skill。
- 所有更新入口必须委托官网长期不变的当前通道安装脚本：正式版使用 `https://bytestaff.jiomig.com/redbeacon/install.ps1` / `install.sh`，测试版使用 `/redbeacon-test/install.ps1` / `install.sh`。不得从 manifest 的 legacy OSS `url` 直接启动安装脚本，也不能在客户端里另写一套手工替换流程。官网固定路由依据 canonical 选择当前不可变脚本；脚本再拉小型 manifest 判断版本，并严格按 `download_urls=[下载节点, OSS]` 下载客户端、浏览器内核和 skill。已是最新则验证依赖并刷新 skill，旧版才下载整包并覆盖。
- 任何更新清单、域名、Bucket 或安装入口迁移，都必须先盘点仍在用户手里的最老冻结更新器，并用那个真实版本完成“发现新版 -> 点击更新 -> 进入当前官网安装器 -> 全量覆盖成功”回归。旧入口在支持周期内必须保留最小升级桥：旧格式清单只负责宣告一个更高版本，旧安装脚本只转交到当前官网固定入口；不得继续维护第二套安装实现，也不得把旧 OSS 上传能力放回项目发布流程。兼容清单必须最后切换，先验证 Windows/macOS 转发器均已公开可用；迁移验收缺这一项时禁止关闭旧入口。
- 重复执行安装脚本时，只先拉很小的中央 manifest；本地已是最新且健康则跳过客户端大包。要强制重装并重新拉 skill，用 `REDBEACON_FORCE_INSTALL=1`。
- 安装事务和最终健康检查全部成功后，Windows 与 macOS 安装器必须自动启动当前通道客户端；健康的最新版重复安装在刷新 skill 后也要启动。自动启动失败只能给出手动打开提示，不能把已经成功提交的安装判成失败；测试 smoke 必须显式跳过弹窗。
- 安装/更新必须按不可信旧环境做事务：新包先解压到临时目录，用新包自己的 CLI 在当前通道固定目录准备并真实验证它要求的 Playwright、CloakBrowser 和其他版本化运行时，同时预取并校验同版本 skill；全部通过后才停止旧进程。安装健康检查和 `setup` 不能初始化、迁移或写用户真实数据库；桌面 smoke 使用临时空库。停止旧进程后先保存当前 SQLite 主库及 WAL/SHM 的滚动快照，再在快照副本上运行新版本数据库迁移和桌面初始化；副本验证通过后才允许替换客户端。放置新客户端后再次运行临时库桌面初始化与真实卡片渲染，任何一步失败都同时恢复旧客户端和旧 skill，用户数据库保持原样。禁止继承用户遗留缓存变量，禁止先覆盖应用、再补依赖。
- 冻结正式包/测试包的 channel 是包内不可变身份：runtime hook 必须先清除继承的 `REDBEACON_CHANNEL` / `REDBEACON_BUILD_CHANNEL`，再以赋值而非 `setdefault` 写入构建通道。外部 PowerShell、旧安装器或另一通道不能把正式包带到 `~/.redbeacon_test`，也不能把测试包带到正式数据目录；测试版包装脚本结束后必须恢复调用者原有环境变量。
- 卸载默认保留业务数据；只有 `REDBEACON_PURGE` 是明确真值 `1/true/yes/on` 时才删除账号数据和平台登录令牌，`0/false/空值` 一律保留。测试版卸载只清测试版路径，不碰正式版。
- 卸载只能删除当前产品、当前通道拥有的浏览器缓存；不能删除系统全局 `ms-playwright`、`~/.cloakbrowser` 等可能被其他软件或另一通道使用的目录。
- 安装阶段必须预热两套浏览器内核：Playwright Chromium（卡片渲染）和 CloakBrowser Chromium（扫码登录 / 发布）。当前发布的 Windows/macOS 内核包不同，由 `redbeacon setup` 按当前系统下载；缓存固定在当前通道目录。版本化内核与客户端同属中央 manifest，先试统一下载节点一次，再回落中央 OSS；只有首次中央发布尚未建立时，构建机才可从公共镜像/官方源准备制品。不要把任一内核下载留到用户第一次扫码。
- 大型运行时下载必须支持 Range 分段、断点续传、实时速度/已下载大小和停滞超时。连接建立后 15 秒无数据也要中断并自动切源，不能让用户无限停在 0%；已经下载的有效分段必须跨重试复用。只下载业务真实使用的资产，例如 RedBeacon 显式使用 Playwright 完整 Chromium 时，不得再附带下载未使用的 headless shell。
- 冻结客户端和随包 CLI 启动时必须先清理继承的 `REDBEACON_CHANNEL`、`REDBEACON_BUILD_CHANNEL`、`REDBEACON_DATA_DIR`、`REDBEACON_LOG_DIR`、`BYTESTAFF_HOME`、Playwright/CloakBrowser 缓存与二进制覆盖变量，再按包内 build channel 选择固定目录。开发态可以保留测试覆盖能力，但交付给用户的程序不能被旧 shell 配置、旧安装器或其他项目带偏。
- 浏览器缓存“有文件”不等于当前版本可用。Playwright 就绪检查必须严格匹配随包 Python 依赖声明的内核 revision；旧 revision 只能显示为待清理诊断信息，不能满足 readiness。安装/更新结束前必须用当前通道内核真实启动并执行一次离线页面操作；启动失败时强制重装当前 revision。
- Windows 会在浏览器关闭后短暂保留可执行文件句柄。运行时安装事务不得先从 staging 启动浏览器、再重命名 staging；必须先把新目录放到最终位置，再从最终位置启动验证，目录删除/替换需有限重试，失败时恢复旧 revision。
- 小红书扫码 / 发布优先用 CloakBrowser；如果第三方内核虽然下载成功但启动后立即关闭，必须自动切到 RedBeacon 自己预热的 Playwright Chromium fallback，并使用当前通道下的独立 fallback profile。下载成功不等于可运行，关键链路必须验证“能启动并创建页面”。
- 小红书扫码入口每次开始前都必须先停止旧会话，不能复用用户可能已经手动关闭的浏览器窗口；“重新扫码/重新登录”还必须删除当前通道下的浏览器 profile 与 cookie 文件，再出新二维码。运行中遇到 `Target page, context or browser has been closed` 这类死 context，必须停止旧会话并重启后重试一次，旧 worker 退出时必须释放排队任务，避免下一次扫码卡到超时。
- 用户关闭扫码弹窗时必须同步取消后台等待并关闭对应浏览器会话；不能只隐藏 UI、让旧任务继续占用 profile。下载节点不要做 HEAD 预检；直接发一次带 `Range: bytes=0-` 的 GET，节点失败或校验不符后立即清理半包并回落中央 OSS。
- Windows ARM64 客户机不能直接判死。当前 Windows 桌面包是 x64 包，ARM64 Windows 通过系统 x64 仿真运行；CloakBrowser 要映射到 `windows-x64` 内核包，不能因为第三方库没有列 `Windows ARM64` 就让扫码登录失败。
- Windows `.ps1/.cmd` 安装链路必须 ASCII-only；命令文件和通用 `SKILL.md` 必须 UTF-8，发布前检查不能出现 `�` 这类替换字符。
- Windows bundle smoke 必须捕获桌面初始化里的 `Traceback` / `ModuleNotFoundError` / `ImportError`；如果日志里有隐藏崩溃，即使打包命令返回 0 也不准上传。PyInstaller spec 必须显式包含 `_sqlite3`，并把文字卡片所需的 `RedBeaconRenderer(.exe)` 作为独立可执行文件打进同一个包；Windows/macOS smoke 都要用冻结 CLI 准备当前 Playwright revision，再让冻结渲染器真实产出封面和正文 PNG，不能只验证主客户端或 `--list-styles`。
- PowerShell 5.1 在 `$ErrorActionPreference = "Stop"` 时会把原生程序写入 stderr 的普通 INFO 日志转换成 `NativeCommandError`。Windows smoke 捕获原生输出时必须临时使用非终止模式，最终只按真实退出码和 `Traceback` / ImportError 等错误特征判定，不能把“写过 stderr”直接当崩溃。
- macOS `.app` 同时包含桌面主程序、CLI 和渲染器时，`CFBundleExecutable` 必须显式等于当前通道的应用名，不能让 PyInstaller 自动选中辅助程序。本机 Mac 构建必须读取 `Info.plist` 核对该字段并直接运行字段指向的 GUI 可执行文件完成桌面 smoke；安装器在替换前后也必须复验，字段错误时即使版本号和 CLI 正常也视为坏包并回滚。
- 组合业务结果必须逐项验收：例如“AI 封面 + 文字卡片”要求两部分都成功，不能因为 AI 图存在就吞掉卡片渲染错误并保存半成品。渲染失败要阻止入库、记录完整日志，并给用户短而可操作的修复提示。

## ByteStaff 平台协作

- 平台设备令牌代表 ByteStaff 账号，不代表某个数字员工。`product` / `product_code` 只做来源归因，不参与权限；客户端不得发送 `account_id`，不得再从 `entitlements`、员工激活状态或产品上下架推导 AI 能力。
- `/device/checkin` 默认发送 `{}`，返回的账号、点数和 `limits.ai` 是客户端真源。checkin 要按 `refresh_after_seconds` 缓存并做账号级 single-flight；旧平台缺少 limits 时保守回退总并发 3、embedding 2、chat 2、image 1。
- 同一账号的客户端窗口、CLI 和 skill 必须共用账号级 AI 调度状态。RedBeacon 使用 `~/.bytestaff/ai_scheduler.sqlite3`（测试版对应测试目录）协调总并发、能力并发、令牌桶、租约、重试次数和熔断，不能只做单进程 Semaphore。
- 客户端生成笔记必须严格串行：普通生成、带货生成、预生成和继续出图共用一个 FIFO 工位，多选只负责入队，必须等前一篇完整成功或失败后才开始下一篇。禁止按“每篇一个线程/Promise”同时生成；本机等待队列最多保留 20 个任务，满了要明确提示用户。
- RedBeacon 文案属于机器可解析交付物，调用平台时必须声明 `redbeacon_copy_v1` 白名单输出契约。平台必须在结算前验收必需字段；格式损坏、缺字段或空正文按 `upstream_error` 原路回补。客户端只允许做不调用 AI 的确定性兼容修复，禁止为了修 JSON 再发一笔收费请求，也禁止由客户端事后自报失败申请退款。
- 合法 JSON 仍可能带可恢复表示偏差，例如正文换行被多转义一层后变成可见 `\n`。这类偏差必须在 `parse_copy` 入站和 `render_from_draft` 副作用前用同一套字段级、白名单、幂等规范化再验一次。禁止全局 `unicode_escape`/无条件反转义，必须保留 Windows 路径、正则、代码和用户真实反斜杠；UI 预览回传也不得绕过这道闸门。
- 平台生成图片的原始容器字节只能短暂存在于内存，禁止直接写入本地业务目录。客户端必须先解码、应用 EXIF 方向、把嵌入色彩配置转换到 sRGB，再从纯像素重写成不含任何 ancillary chunk 的 PNG，清除 EXIF/XMP/ICC/文本/注释/时间戳和未知应用块后才允许进入审核、发布或归档。净化失败必须丢弃该图并按生图失败处理，绝不能回退保存原文件；普通 RGB/RGBA 图片不得缩放、裁切或再次有损编码。
- 所有 AI 图片提示词必须从 `core/presets.py` 的单一规则追加图片文字规范：画面需要中文时使用中国大陆通用规范简体中文，禁止繁体、异体字、错别字和伪文字，并保持标题/文案原样；明确要求无文字的画面必须继续无字。内置模板、历史自定义方案和最终平台请求边界都要执行同一条幂等规则，不能只修某一个模板。
- `request_id` 必须遵守平台幂等语义：429 / duplicate_pending 沿用原 id；明确收到 duplicate_failed / 502 upstream_error 后换新 id；网络断线 / 503 结果未知时只沿用原 id 确认一次。所有重试先释放运行槽，遵守 Retry-After（秒数或 HTTP 日期）并做退避；连续故障触发短熔断。

## 发布流程

发布纪律是硬规则：**永远先发测试版，让用户测；用户明确确认通过后，才允许发正式版。**

- 项目唯一构建入口是 `tools/build_desktop_local.sh`。它只完成 Mac/Windows 双平台构建、安装事务 smoke、浏览器依赖收集和 `release-artifacts/` 验证，禁止联网发布。
- 测试版和正式版必须使用同一个构建入口、PyInstaller spec、已提交源码、`cli/uv.lock` 和锁定工具链；只有通道身份允许不同。
- Windows 虚拟机构建是阻断项：必须完成 x64 Python/PE 校验、冻结桌面启动、Traceback 扫描、浏览器预热、真实卡片渲染及 PowerShell 安装事务 smoke；安装事务必须验证五宿主 skill 的正式/测试共存、更新和卸载。Windows 未通过，不得交给发布 Skill。
- 项目仓库必须提交 `docs/download-node-integration.md`、`docs/download-node-project-intake.yaml`、`docs/download-node-project-receipt.json` 与 `release/release-contract.json`，且字节内容必须匹配受保护的中央项目 profile。
- 公开发布的唯一入口是全局 `bytestaff-digital-employee-publish` Skill 的 `publish_release.py`。项目不得复制、包装或局部重写该发布编排器。
- 中央 OSS 按项目、通道和可选 component **最多保留最近 3 个完整版本**，且必须始终包含 canonical `latest.json` 当前指向的版本；下载节点仍只保留 current，本机 `~/.local/state/bytestaff-download/<project>` 也只保留与 OSS 相同的三个版本运行目录。版本保留检查是每次发布同一 run 的强制收尾阶段，不是另起的维护任务。发布第 4 个版本后，主发布器必须列出将删版本、对象数、字节数和计划 SHA-256，停在确认门；取得当次明确确认后从同一 run 继续删除最旧 OSS 版本并复验，再自动删除对应通道/component 中不在远端保留集内、且已明确终态的本地旧 run；未完成、绑定异常或无法验证的本地 run 绝不删除。项目代码不得自行获得或调用 OSS 删除权限。
- 全局 Skill 先上传不可变 OSS/节点制品并停在 `PREPARED_AWAITING_SWITCH_GATE`；只有完成真实客户端 node 正常、node 失败回落 OSS、坏节点内容回落 OSS、旧 `url` 单源兼容四项验收后，才可用同一 run 的 prepare receipt 与验收凭证切换 test canonical。
- 若本次发布同时迁移更新入口，除常规四项下载验收外，还必须从迁移前最老受支持客户端的真实旧 URL 检查到更高版本，并验证其转发器最终取得当前通道官网安装脚本；这属于迁移阻断项。普通发版不触碰已经建立的旧版升级桥。
- 测试版发布后只要客户端、CLI、skill、安装/更新/卸载、制品结构或项目契约有任何修改，测试结论立即作废，必须重发测试版。
- 正式版必须由用户明确批准，并用测试通过的同一份代码重新构建 stable 通道，再由全局 Skill 发布；项目内没有正式版绕过开关。

固定步骤：

1. 在 `cli/` 子仓库改版本、完成测试并提交；CLI 工作区必须干净。
2. 提交根仓的客户端、安装器和四份中央接入契约；根仓与 CLI provenance 必须一致。
3. 保持 Windows 11 构建虚拟机运行且 SSH 可达，在根仓运行 `tools/build_desktop_local.sh --channel test`，得到唯一干净制品目录。
4. 从项目根目录调用全局发布 Skill 的唯一编排器，携带 test、版本、根仓 commit、`release/release-contract.json`、release unit、transaction 和唯一 run id；不得从别的 cwd 发布。
5. Skill 第一阶段停在 switch gate 后，按 `docs/download-node-integration.md` 用真实客户端完成四项下载验收，生成 `bytestaff-client-acceptance/v1` 凭证，再恢复同一个 run 完成 test canonical 切换。
6. 只以全局 Skill 校验过的 `publication-result.json` 为发布结果与下载链接真源，把测试版交给用户。
7. 用户明确确认后，在不改代码的前提下构建 stable，并通过同一全局 Skill 与独立 stable 批准凭证发布正式版。

## 给 agent 的工作规则

- 面向终端用户时用人话，不主动暴露 skill 名、内部命令名和实现细节；用户主动要命令时再给。
- RedBeacon 在客户端里是一位有名字的数字员工，不是无名的“AI 生成器”。长任务要用“RedBeacon + 正在做的真实动作 + 完成后去哪里”来表达，例如“RedBeacon 正在写这篇文案”“正在画封面”“正在把成稿放进审稿台”；避免只写“生成中 / 处理中 / 执行中”。拟人化不能虚构情绪、意识或完成情况，温度来自真实进度、连续上下文和把事情负责地做完。
- 给选择时用编号，推荐项标清楚，让用户能回一个数字。
- Skill 不是一条看不见的后台流水线。定位完成、选题入库、文案入审、审核通过、发布成功等关键成果出现后，必须通过非阻塞深链把客户端置前到对应页面，让用户看到并核查成果；用户既可留在 UI 继续，也可切回对话用自然语言继续操作同一份数据。不要对每次只读查询抢焦点。
- Skill 联网选题和客户端平台 AI 补题能力保持独立：前者可联网核查真实痛点，后者走平台算力；两者必须写入同一个本地选题库，并在写入前确保内容类型、应用域、问题类型、切入角度、要点提纲、价值点、互动钩子、聚焦人群、配图方向、备注全部非空。手动临时加题不受此硬闸限制。
- 引导用户时一次只问一个问题，一次只推进一件事；需要用户回应时给 2-3 个建议选项，让用户做选择题，不要把多个问题塞进同一轮。
- 全新账号开始定位时，先让用户选择“简述整体想法（推荐）”或“由数字员工逐题引导”，不能在不知道账号类型和目的时直接盘问赛道、受众等细项。用户已经表达过的信息先提炼复述，只补会改变定位的关键缺口，不重复提问。
- onboarding 可自动推进，只有需要扫码、用户提供信息、真正分支或不可逆动作时再停。
- 遇到旧文档提到飞书主链路、旧官网、GitHub 发布源、Cloud Code/Claude Code 作为唯一维护方式时，按历史资料处理，不要照搬到当前实现。
