# RedBeacon 最近修改审查（2026-09-05）

> 本文保留修复前的审查证据。用户随后授权修复，结果见 [修复记录](2026-09-05-recent-change-fixes.md)。

本次确认 5 项功能问题，另有 1 项发布验证缺口。没有证据表明整套软件已经全面失效，但发布结果判定、安装失败回滚和 Windows 中文路径值得优先修复。本次只审查和复现，没有修改源码、安装入口或用户业务数据，也没有安装、打包、发布或提交。

**审查范围与版本边界**

- 根仓 HEAD：701dbd9；CLI 子仓 HEAD：c581bc2。重点检查 8 月 20 日客户端拆分，以及 9 月 3–4 日安装/通道隔离、浏览器修复、代理和发布收尾、登录状态、国版/外版账号改动。
- 检查了根仓当前未提交的四个安装入口，以及制品检查、安装事务 smoke、通道回执相关脚本。四个安装入口约 3,100 行的 diff，主要是把已有 core 重新合入单体入口；不能把搬动的每一行算作新逻辑。
- 发现问题后向前追查引入提交；以下明确区分近期新增与旧问题。未读取冷归档或 docs/archive。
- 本地 release/release-contract.json 仍绑定 CLI 64e6b9e（0.1.121），其后登录/RedNote 改动不在这份发布契约中。这里没有把当前源码直接等同于线上版本，也没有重新查询线上 canonical。

**1. P1：未确认发布成功，仍会结算并移入归档**

位置：[发布适配器第 280 行](/Users/diaojiawang/code/auto-redbook/redbeacon/cli/src/redbeacon/infra/xhs_publisher.py:280)、[发布用例第 394 行](/Users/diaojiawang/code/auto-redbook/redbeacon/cli/src/redbeacon/core/usecases/publish.py:394)。

点击发布后，如果 45 秒内既未识别成功信号，也未识别明确错误，浏览器层会返回 confirmed=False。适配器没有把这一状态传给业务层，而是返回可能为空的链接。业务层将“函数正常返回”当成成功，随后调用 billing.complete、archive_create 和 review_delete。

无副作用复现使用真实发布用例和适配器，仅替换浏览器、计费和存储 IO。结果为：browser_confirmed=False，result_status=published，archived=True，billing.complete 调用 1 次，archive_create 和 review_delete 均执行。没有向平台扣费或向小红书发帖。

影响：没有完成发布的笔记也可能被显示为已发布、结算点数并从待发/审稿流程移走。稿件仍在归档中，不能将此描述成正文被彻底删除。

归因：结果未知未传入业务层的问题至少可追溯到 f42efaa（7 月 9 日）。近期 ba25e66 又在[单篇发布收尾](/Users/diaojiawang/code/auto-redbook/redbeacon/cli/src/redbeacon/adapters/ui_backend/app.py:420)中无条件关闭浏览器，使这类结果不明的单篇发布失去原来保留的人工核查窗口。

修复方向：显式区分成功、失败和结果未知。未知态应保留稿件与待核查记录，不直接成功结算/归档，也不能自动重发，以免已经成功的笔记被重复提交。

**2. P1：macOS 备份失败时，清理过程会损坏旧客户端**

位置：[正式安装入口第 576 行](/Users/diaojiawang/code/auto-redbook/redbeacon/install/install.sh:576)、[测试安装入口第 576 行](/Users/diaojiawang/code/auto-redbook/redbeacon/install/install-test.sh:576)。

FINAL_PATH 在旧应用成功移到备份位置之前就已赋值。旧应用备份 mv 失败后，EXIT trap 发现没有 BACKUP_PATH，直接对 FINAL_PATH 执行 rm -rf；这个位置此时仍然是旧客户端。

已在临时目录做真实权限复现：模拟 Applications 父目录为 0555，旧 .app 内部可写；真实 mv 报 Permission denied，随后运行当前清理函数。结果：安装退出码 1、没有生成备份、.app 外层目录仍在，但旧客户端可执行文件已被删除。临时目录随后恢复权限并清理。

影响：一次失败的更新可能把原来能用的客户端也破坏掉。此复现没有证明业务数据库被删除，不能夸大为业务数据丢失。

归因：至少可追溯到 ab888c5（7 月 11 日）；9 月 3 日移入 core、当前未提交重新合回入口，都沿用了此逻辑。

修复方向：分别记录旧应用是否成功备份、新应用是否成功放置；备份失败时不得清理仍处于原位置的旧应用。

**3. P1：Windows 中文用户目录会使 CLI/AI 助手入口失效**

位置：[正式安装入口第 690 行](/Users/diaojiawang/code/auto-redbook/redbeacon/install/install.ps1:690)、[测试安装入口第 690 行](/Users/diaojiawang/code/auto-redbook/redbeacon/install/install-test.ps1:690)。

安装器先把 LOCALAPPDATA 展开成含真实用户名的绝对路径，再用 ASCII 写入 .cmd。例如用户名为“张三”，路径中的中文会变成问号。真实 Windows PowerShell 5.1 内存复现确认该编码替换。

影响：安装可以成功，桌面快捷方式也可能正常，但终端和 AI 助手通过 redbeacon/redbeacon-test 命令调用时找不到客户端。

归因：至少可追溯到 ded526a（7 月 8 日），当前改动照搬了旧逻辑；已提交 HEAD 的 install-core.ps1 第 625 行也存在。

修复方向：保持 .cmd 本身 ASCII-only，写入运行时环境变量或相对路径表达式，避免把展开后的中文绝对路径编码进去。

**4. P2：隐藏地址栏口令后，页面刷新直接失去访问权限**

位置：[前端 core.js 第 33–39 行](/Users/diaojiawang/code/auto-redbook/redbeacon/cli/src/redbeacon/adapters/ui_backend/static/js/core.js:33)、[后端访问校验第 827 行](/Users/diaojiawang/code/auto-redbook/redbeacon/cli/src/redbeacon/adapters/ui_backend/app.py:827)。

页面把 rb_token 从地址栏删除，口令只存在当前 JS 内存；后端对 HTML 根页面也要求口令，没有设置可供刷新使用的会话 Cookie。浏览器重新载入页面时既没有原 JS 内存，也没有 URL 口令。

已用真实前端片段在 Node 中执行地址清理，并用真实 FastAPI 应用验证：首次带口令加载为 200，响应 Cookie 数为 0；清理后的 /?view=review 再次加载为 403。此项指浏览器重新载入，不是界面右上角调用 API 的软刷新。

归因：7832089（8 月 20 日客户端模块拆分/加固）引入。

修复方向：隐藏地址栏口令时同时保留安全、能跨页面重新载入的会话机制。不要直接取消本机 API 的访问校验。

**5. P2：新增 RedNote 登录检测把旧 Cookie 当成实时登录成功**

位置：[登录判断第 81 行](/Users/diaojiawang/code/auto-redbook/redbeacon/cli/src/redbeacon/services/xhs/login.py:81)、[状态核验提前返回第 310 行](/Users/diaojiawang/code/auto-redbook/redbeacon/cli/src/redbeacon/services/xhs/login.py:310)。

外版分支仅凭非空 id_token 即可返回登录成功；调用方随后在检查 HTTP 响应、导航失败和安全验证正文之前返回，且强制设置 security_blocked=False、indeterminate=False。

无副作用复现：HTTP 403、页面显示“安全验证 操作频繁，请稍后重试”、没有登录 DOM，仅保留旧 id_token；实际检查函数返回 is_logged_in=True、security_blocked=False、indeterminate=False。

影响：账号在线状态不可信，重新登录与风控提示被跳过，后续发布仍可能继续尝试失败页面。

归因：9542e5b（9 月 4 日外版账号支持）新增。

修复方向：先排除导航失败、错误响应与风控页，再要求能证明当前认证有效的页面或接口结果；Cookie 存在本身不足以证明当前会话有效。

**6. P2 验证缺口：安装事务原始证据未写入回执，汇总仍声明全覆盖**

位置：[事务 smoke 第 1316 行](/Users/diaojiawang/code/auto-redbook/redbeacon/tools/smoke_unix_install_transaction.py:1316)、[写报告第 1346 行](/Users/diaojiawang/code/auto-redbook/redbeacon/tools/smoke_unix_install_transaction.py:1346)、[回执校验第 525 行](/Users/diaojiawang/code/auto-redbook/redbeacon/tools/write_channel_isolation_receipt.py:525)、[覆盖声明第 705 行](/Users/diaojiawang/code/auto-redbook/redbeacon/tools/write_channel_isolation_receipt.py:705)。

Unix smoke 已生成 observed_evidence，包含回滚结果、跨通道目录快照、进程隔离、调用者环境等，但写报告时没有传入。Windows 报告同样没有携带这组证据。汇总器中对应验证函数没有被调用，严格 schema 也不接受这些数据，最终却按常量写出 verified_coverage。

这不等于证明 smoke 没有运行：脚本内部确有断言。问题在于发布交接保存的原始报告不包含所声称覆盖的行为证据，后续只能信任摘要，不能据原始结果独立复核。

归因：346bd91（9 月 3 日安装隔离与证据改造）引入，当前未提交版本仍存在。

另有较低优先级的未提交验证缺口：macOS 的“没有第二个 shell”检测只匹配 install-core.sh/uninstall-core.sh，其他文件名的第二阶段不计入，ps 失败也等价于零个子进程。目前未发现当前真实安装入口启动这种别名第二阶段，因此不将其算作已发生的安装故障。

**验证结果与限制**

- CLI 测试套件共 1,045 项，排除 tests/smoke 的在线 smoke。首轮 1,043 通过；另外两项是沙箱下的进程枚举及 AppleScript 系统服务限制，分别在沙箱外定向重跑通过。因此没有把这两次环境失败列为软件缺陷。
- 四个安装入口做了静态核对；两个 shell 入口 bash -n 通过，两个 PowerShell 入口符合 ASCII-only。Windows PowerShell 5.1 做了编码/错误处理的微型验证，没有执行真实安装。
- 页面刷新、发布未知态、RedNote 风控页和 macOS 回滚问题均做了定向复现。未访问真实用户库、修改登录或发送真实发布请求。
- 根仓 release contract 检查目前在“契约 CLI commit 与实际 HEAD 不一致”处停止。这是当前开发快照尚未更新发版绑定的状态，不能把这次检查说成发布验收通过，也不应自动认定为已发布版本损坏。
- 现有测试未覆盖上述关键失败组合。部分测试只检查实现文本；外版登录测试还把“仅有 Cookie”定义为成功，所以全绿不足以排除这些行为问题。
- 尚未做本次代码的双平台完整安装事务、冻结包启动和真实小红书/RedNote 端到端发布验收。不能据本次审查宣称整个软件所有功能都已验收。

**没有误报的近期改动**

- 346bd91 拆出的第二个 PowerShell 带有 -ExecutionPolicy Bypass，不存在“漏掉 Bypass”这一问题。是否应保留二阶段与当前产品约束是另一个问题，当前未提交入口已经改回单体。
- 63068ca 修复了 macOS 自动启动向常驻客户端传递即将被删除的临时目录的问题，当前合并保留了修复。
- 浏览器事务修复、冻结通道身份、会话代次/取消、代理选择和数据库平台字段传递，暂未找到更多可确定的近期功能破坏；这个结论只限已检查的代码和测试。

建议修复顺序：发布未知态 → macOS 回滚 → Windows 中文路径 → RedNote 登录核验 → 页面刷新 → 验收证据接线。安装入口的任何修改仍需用户明确授权具体文件和行为。
