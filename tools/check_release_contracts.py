#!/usr/bin/env python3
"""Release contract checks that must pass before publishing.

This is intentionally lightweight and offline. It catches drift in the release
flow before packages or scripts are uploaded to OSS.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import build_channel_skills
import mirror_cloakbrowser_browsers
import mirror_playwright_browsers

ROOT = Path(__file__).resolve().parent.parent
SINGLE_QUESTION_RULE = "一次只问一个问题，一次只推进一件事"
SKILL_BOOTSTRAP_RULE = "不得猜测、拼接或直接下载任何 zip 包名"
STABLE_INSTALL_PS1 = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.ps1"
STABLE_INSTALL_SH = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install.sh"
TEST_INSTALL_PS1 = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install-test.ps1"
TEST_INSTALL_SH = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/install-test.sh"
FORBIDDEN_SKILL_PHRASES = (
    "每次只问一到两件事",
    "<<'EOF'",
    '<<"EOF"',
    "--json <<",
    "--data <<",
    "--data '{",
    '--data "{',
    "--json '[",
    '--json "[',
    " /tmp/",
    ">/tmp/",
    "> /tmp/",
)


def fail(message: str) -> None:
    raise SystemExit(f"xx {message}")


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        fail(f"缺少文件：{rel}")
    return path.read_text(encoding="utf-8")


def read_bytes(rel: str) -> bytes:
    path = ROOT / rel
    if not path.exists():
        fail(f"缺少文件：{rel}")
    return path.read_bytes()


def require(text: str, needle: str, rel: str, why: str) -> None:
    if needle not in text:
        fail(f"{rel} 缺少发布契约：{why}（需要包含 {needle!r}）")


def forbid(text: str, needle: str, rel: str, why: str) -> None:
    if needle in text:
        fail(f"{rel} 违反发布契约：{why}（不得包含 {needle!r}）")


def check_installers() -> None:
    sh = read("install/install.sh")
    ps1 = read("install/install.ps1")
    unsh = read("install/uninstall.sh")
    unps1 = read("install/uninstall.ps1")
    setup_py = read("cli/src/redbeacon/routers/setup.py")
    browser_engine_py = read("cli/src/redbeacon/services/browser_engine.py")
    browser_downloads_py = read("cli/src/redbeacon/services/browser_downloads.py")
    xhs_login_py = read("cli/src/redbeacon/services/xhs/login.py")
    ui_app_py = read("cli/src/redbeacon/adapters/ui_backend/app.py")
    ui_index = read("cli/src/redbeacon/adapters/ui_backend/static/index.html")
    updater_py = read("cli/src/redbeacon/services/updater.py")
    bundle_spec = read("cli/packaging/RedBeacon.spec")
    runtime_sanitize = read("cli/packaging/_runtime_sanitize.py")
    win_smoke = read("cli/packaging/smoke_windows_bundle.ps1")
    workflow = read("cli/.github/workflows/build-bundle.yml")
    cloak_mirror = read("tools/mirror_cloakbrowser_browsers.py")
    playwright_mirror = read("tools/mirror_playwright_browsers.py")
    browser_mirror_check = read("tools/check_browser_mirrors.py")
    unix_transaction_smoke = read("tools/smoke_unix_install_transaction.py")
    unix_transaction_workflow = read(".github/workflows/unix-installer-transaction-smoke.yml")
    latest_generator = read("tools/gen_latest.py")

    for rel in (
        "install/install.ps1",
        "install/install-test.ps1",
        "install/uninstall.ps1",
        "install/uninstall-test.ps1",
    ):
        if any(b > 0x7F for b in read_bytes(rel)):
            fail(f"{rel} 必须保持 ASCII-only，避免 Windows PowerShell 5.1 编码/显示问题")

    require(sh, 'codex_dir="$HOME/.codex/skills"', "install/install.sh", "Mac/Linux 安装必须写入 Codex 扫描目录")
    require(sh, 'install_codex_skills "$PREPARED_SKILL_SRC"', "install/install.sh", "Mac/Linux 安装必须从已校验 skill tarball 派生 Codex SKILL.md")
    require(sh, 'run_browser_setup "$STAGED_CLI"', "install/install.sh", "Mac/Linux 必须先用新版本 CLI 准备依赖，再替换旧客户端")
    require(sh, 'verify_bundle "$STAGED_CLI"', "install/install.sh", "Mac/Linux 替换前必须让新包完成桌面初始化和真实渲染")
    require(sh, 'BACKUP_PATH="$APP.redbeacon-rollback"', "install/install.sh", "Mac/Linux 覆盖失败必须保留旧客户端回滚副本")
    require(sh, "restore_skills", "install/install.sh", "Mac/Linux 安装失败必须同时回滚当前通道 skill")
    require(sh, 'REDBEACON_DATA_DIR="$RUNTIME_DATA_DIR"', "install/install.sh", "Mac/Linux 安装不得继承用户遗留的数据/浏览器缓存路径")
    require(sh, 'SKILL_SHA', "install/install.sh", "Mac/Linux 安装必须校验版本化 skill 包哈希")
    staged_setup_pos = sh.index('run_browser_setup "$STAGED_CLI"')
    staged_stop_pos = sh.find("\nstop_running_redbeacon\n", staged_setup_pos)
    if staged_stop_pos < staged_setup_pos:
        fail("install/install.sh 必须在关闭/替换旧客户端前完成新版本依赖准备")
    require(sh, 'install_skills "$LOCAL_CLI"', "install/install.sh", "Mac/Linux 重复安装即使版本最新也必须修复 skill")
    require(sh, "--max-time 600", "install/install.sh", "Mac/Linux 大包下载必须有总超时，不能无限卡住")
    require(sh, "/releases/$LATEST/", "install/install.sh", "Mac/Linux 安装必须使用版本化客户端包，避免构建覆盖现网")
    require(ps1, 'Join-Path $HOME ".codex\\skills"', "install/install.ps1", "Windows 安装必须写入 Codex 扫描目录")
    require(ps1, "Write-CodexSkills $script:PreparedSkillSrc", "install/install.ps1", "Windows 安装必须从已校验 skill tarball 派生 Codex SKILL.md")
    require(ps1, "Run-BrowserSetup $stagedCli", "install/install.ps1", "Windows 必须先用新版本 CLI 准备依赖，再替换旧客户端")
    require(ps1, "Verify-Bundle $stagedCli", "install/install.ps1", "Windows 替换前必须让新包完成桌面初始化和真实渲染")
    require(ps1, '$backup = "$Dest.redbeacon-rollback"', "install/install.ps1", "Windows 覆盖失败必须保留旧客户端回滚副本")
    require(ps1, "Restore-Skills", "install/install.ps1", "Windows 安装失败必须同时回滚当前通道 skill")
    require(ps1, '"REDBEACON_DATA_DIR" = $RuntimeDataDir', "install/install.ps1", "Windows 安装不得继承用户遗留的数据/浏览器缓存路径")
    require(ps1, "$SkillSha", "install/install.ps1", "Windows 安装必须校验版本化 skill 包哈希")
    require(ps1, "Install-Skills $cliExe", "install/install.ps1", "Windows 重复安装即使版本最新也必须修复 skill")
    staged_setup_pos = ps1.index("Run-BrowserSetup $stagedCli")
    staged_stop_pos = ps1.find("\n  Stop-RunningRedBeacon\n", staged_setup_pos)
    if staged_stop_pos < staged_setup_pos:
        fail("install/install.ps1 必须在关闭/替换旧客户端前完成新版本依赖准备")
    require(ps1, "/releases/$latest/", "install/install.ps1", "Windows 安装必须使用版本化客户端包，避免构建覆盖现网")
    require(ps1, "Stop-RunningRedBeacon", "install/install.ps1", "Windows 安装/更新覆盖前必须关闭正在运行的客户端和 CLI")
    require(unix_transaction_smoke, 'failure="stage"', "tools/smoke_unix_install_transaction.py", "Unix 安装器必须验证依赖准备失败时旧版不被替换")
    require(unix_transaction_smoke, 'failure="placed"', "tools/smoke_unix_install_transaction.py", "Unix 安装器必须验证放置后二次校验失败会回滚")
    require(unix_transaction_smoke, 'failure="post_skills"', "tools/smoke_unix_install_transaction.py", "Unix 安装器必须验证最终校验失败时 app 与 skill 一起回滚")
    require(unix_transaction_smoke, 'foreign-system-playwright', "tools/smoke_unix_install_transaction.py", "Unix 安装器必须用恶意/遗留环境变量做隔离回归")
    require(unix_transaction_workflow, "macos-latest", ".github/workflows/unix-installer-transaction-smoke.yml", "Mac 安装事务冒烟必须在线上 runner 执行")
    require(unix_transaction_workflow, "ubuntu-latest", ".github/workflows/unix-installer-transaction-smoke.yml", "Linux 安装事务冒烟必须在线上 runner 执行")
    if "actions/upload-artifact" in unix_transaction_workflow:
        fail("Unix 安装事务冒烟不允许保留 GitHub artifact")

    require(unsh, 'CODEX_SKILL_DIR="$HOME/.codex/skills"', "install/uninstall.sh", "Mac/Linux 卸载必须清理对应通道 Codex skill")
    require(unps1, '$CodexSkillDir = "$HOME\\.codex\\skills"', "install/uninstall.ps1", "Windows 卸载必须清理对应通道 Codex skill")
    require(unsh, 'redbeacon-test*', "install/uninstall.sh", "测试版卸载只能动 redbeacon-test*")
    require(unps1, 'redbeacon-test*', "install/uninstall.ps1", "测试版卸载只能动 redbeacon-test*")
    for rel, text in (("install/uninstall.sh", unsh), ("install/uninstall.ps1", unps1)):
        for global_cache in ("Library/Caches/ms-playwright", ".cache/ms-playwright", "LOCALAPPDATA\\ms-playwright", ".cloakbrowser"):
            if global_cache in text:
                fail(f"{rel} 不能删除第三方全局浏览器缓存 {global_cache}；只能清当前 RedBeacon 通道自有目录")
    require(setup_py, "browser_engine.ensure_browser_engine", "cli/src/redbeacon/routers/setup.py", "setup 命令必须走带进度的浏览器内核安装服务")
    require(setup_py, "verify_launch=True", "cli/src/redbeacon/routers/setup.py", "安装完成必须真实启动当前浏览器内核，不能只检查文件存在")
    require(browser_engine_py, "bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/playwright", "cli/src/redbeacon/services/browser_engine.py", "Playwright 浏览器内核下载必须包含 RedBeacon OSS 主源")
    require(browser_engine_py, "bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/cloakbrowser", "cli/src/redbeacon/services/browser_engine.py", "CloakBrowser 小红书自动化内核下载必须包含 RedBeacon OSS 主源")
    require(browser_engine_py, "PLAYWRIGHT_OSS_HOST,", "cli/src/redbeacon/services/browser_engine.py", "Playwright 源顺序必须把 RedBeacon OSS 放在第一位")
    if browser_engine_py.index("PLAYWRIGHT_OSS_HOST,") > browser_engine_py.index("registry.npmmirror.com"):
        fail("cli/src/redbeacon/services/browser_engine.py 必须先尝试 RedBeacon OSS，再尝试 npmmirror")
    require(browser_engine_py, "no_shell=True", "cli/src/redbeacon/services/browser_engine.py", "只下载 RedBeacon 实际使用的完整 Chromium，不能额外拉无用 headless shell")
    require(browser_engine_py, "download_resumable", "cli/src/redbeacon/services/browser_engine.py", "两套浏览器内核必须共用分段续传下载器")
    require(browser_downloads_py, '"Range"', "cli/src/redbeacon/services/browser_downloads.py", "大文件下载必须使用 Range 分段与断点续传")
    require(browser_downloads_py, "ThreadPoolExecutor", "cli/src/redbeacon/services/browser_downloads.py", "大文件下载必须支持受控并行分段")
    require(browser_downloads_py, "_READ_TIMEOUT_SECONDS", "cli/src/redbeacon/services/browser_downloads.py", "下载停滞必须超时切源，不能无限卡在 0%")
    require(browser_engine_py, "PLAYWRIGHT_BROWSERS_PATH", "cli/src/redbeacon/services/browser_engine.py", "Playwright 缓存必须固定到 RedBeacon 通道目录")
    require(browser_engine_py, "CLOAKBROWSER_CACHE_DIR", "cli/src/redbeacon/services/browser_engine.py", "CloakBrowser 缓存必须固定到 RedBeacon 通道目录")
    require(browser_engine_py, "CLOAKBROWSER_WINDOWS_ARM64_ALIASES", "cli/src/redbeacon/services/browser_engine.py", "Windows ARM64 客户机必须映射到 Windows x64 CloakBrowser 内核，不能在扫码登录前被平台检测拦死")
    require(browser_engine_py, "Path(exe).is_file()", "cli/src/redbeacon/services/browser_engine.py", "Playwright 就绪必须严格检查当前依赖版本声明的可执行文件")
    require(browser_engine_py, "stale_chromium_executable", "cli/src/redbeacon/services/browser_engine.py", "旧 Playwright 内核只能作为诊断信息，不能冒充当前版本就绪")
    require(browser_engine_py, "_verify_playwright_launch", "cli/src/redbeacon/services/browser_engine.py", "Playwright 安装/修复必须做离线页面启动探测")
    if "actual = _find_cached_browser(exe" in browser_engine_py:
        fail("cli/src/redbeacon/services/browser_engine.py 不能用任意旧 chromium 缓存满足当前 Playwright 版本")
    xhs_session = read("cli/src/redbeacon/services/xhs/session.py")
    require(xhs_session, "browser_engine.ensure_browser_engine", "cli/src/redbeacon/services/xhs/session.py", "小红书浏览器会话启动前必须自检并修复浏览器内核")
    require(xhs_session, "_launch_playwright_context", "cli/src/redbeacon/services/xhs/session.py", "CloakBrowser 启动失败或启动后关闭时必须自动切到 Playwright Chromium 兜底")
    require(xhs_session, '"executable_path": pw.chromium.executable_path', "cli/src/redbeacon/services/xhs/session.py", "Playwright 兜底必须显式使用当前通道内核，不能依赖 PATH/系统浏览器")
    require(xhs_session, "_fallback_profile_dir", "cli/src/redbeacon/services/xhs/session.py", "浏览器兜底必须使用稳定的独立 profile，避免坏锁文件影响后续扫码和发布")
    require(xhs_session, "is_closed_error", "cli/src/redbeacon/services/xhs/session.py", "浏览器 context 运行中关闭后必须识别为死会话，避免继续复用坏 session")
    require(xhs_session, "get_nowait", "cli/src/redbeacon/services/xhs/session.py", "浏览器 context 关闭导致 worker 退出时必须释放排队任务，避免下一次扫码卡到超时")
    require(xhs_session, "_stop_requested", "cli/src/redbeacon/services/xhs/session.py", "关闭扫码窗口必须能协作取消后台等待，释放浏览器 profile")
    require(xhs_login_py, "_exec_with_live_session", "cli/src/redbeacon/services/xhs/login.py", "扫码出码遇到死 context 必须自动重启会话并重试一次")
    require(xhs_login_py, "_profile_dirs", "cli/src/redbeacon/services/xhs/login.py", "小红书登出/重新扫码必须删除当前通道浏览器 profile，不能只删 cookie 文件")
    require(ui_app_py, "if req.force:", "cli/src/redbeacon/adapters/ui_backend/app.py", "客户端重新扫码必须先清理旧登录态再出新二维码")
    require(ui_app_py, "xhs.session.stop(req.account_id)", "cli/src/redbeacon/adapters/ui_backend/app.py", "客户端每次扫码前必须停止旧小红书会话，不能复用用户可能已经手动关闭的浏览器")
    require(ui_app_py, '"/api/accounts/xhs-login/cancel"', "cli/src/redbeacon/adapters/ui_backend/app.py", "关闭扫码窗口必须通知后端取消旧任务")
    require(ui_index, "/api/accounts/xhs-login/cancel", "cli/src/redbeacon/adapters/ui_backend/static/index.html", "扫码弹窗关闭按钮必须释放后端浏览器会话")
    require(ui_index, "startXhsLogin(${a.id}, true)", "cli/src/redbeacon/adapters/ui_backend/static/index.html", "已登录账号的重新扫码按钮必须传 force=true")
    require(cloak_mirror, 'tag.startswith("windows-")', "tools/mirror_cloakbrowser_browsers.py", "CloakBrowser OSS 镜像脚本必须按目标平台决定 Windows zip 包名")
    require(cloak_mirror, "SHA256SUMS", "tools/mirror_cloakbrowser_browsers.py", "CloakBrowser OSS 镜像必须同步校验文件")
    require(cloak_mirror, "oss_exists", "tools/mirror_cloakbrowser_browsers.py", "CloakBrowser OSS 镜像脚本必须跳过已存在对象，避免重复上传大包")
    require(playwright_mirror, "oss_exists", "tools/mirror_playwright_browsers.py", "Playwright OSS 镜像脚本必须跳过已存在对象，避免重复上传大包")
    require(playwright_mirror, '"--no-shell"', "tools/mirror_playwright_browsers.py", "Playwright 镜像清单不能包含未使用的 headless shell")
    require(playwright_mirror, "full_chromium_urls", "tools/mirror_playwright_browsers.py", "Playwright 镜像只能同步业务实际使用的完整 Chromium")
    require(playwright_mirror, '"--continue-at"', "tools/mirror_playwright_browsers.py", "Playwright 镜像同步必须支持断点续传")
    require(cloak_mirror, '"--continue-at"', "tools/mirror_cloakbrowser_browsers.py", "CloakBrowser 镜像同步必须支持断点续传")
    require(browser_mirror_check, '"--range"', "tools/check_browser_mirrors.py", "发布前必须对当前三端浏览器对象执行真实 Range GET")
    if "REDBEACON_SETUP_COMPONENT=playwright" in workflow:
        fail("cli/.github/workflows/build-bundle.yml 三端 smoke 必须准备 Playwright 和 CloakBrowser，不能只测 Playwright")
    if "REDBEACON_SETUP_COMPONENT" in win_smoke:
        fail("cli/packaging/smoke_windows_bundle.ps1 必须准备两套浏览器内核，不能跳过 CloakBrowser")
    require(workflow, '"cloakbrowser_installed"', ".github/workflows/build-bundle.yml", "macOS/Linux 冻结包 smoke 必须确认 CloakBrowser 已安装")
    require(win_smoke, '"cloakbrowser_installed"', "cli/packaging/smoke_windows_bundle.ps1", "Windows 冻结包 smoke 必须确认 CloakBrowser 已安装")
    expected_archives = {
        "windows-x64": "cloakbrowser-windows-x64.zip",
        "linux-x64": "cloakbrowser-linux-x64.tar.gz",
        "darwin-arm64": "cloakbrowser-darwin-arm64.tar.gz",
    }
    for platform_tag, expected in expected_archives.items():
        actual = mirror_cloakbrowser_browsers.archive_name_for_tag(platform_tag)
        if actual != expected:
            fail(f"CloakBrowser {platform_tag} 镜像包名错误：{actual} != {expected}")
    release_sh = read("tools/release.sh")
    require(release_sh, "check_browser_mirrors.py", "tools/release.sh", "每次发布前必须阻断检查三端浏览器镜像")
    require(release_sh, "--max-time 300", "tools/release.sh", "发布阶段下载 OSS 大包计算 sha 必须有总超时，不能让发布流程无限卡住")
    require(release_sh, "--retry 3", "tools/release.sh", "发布阶段下载 OSS 大包计算 sha 必须有重试，避免偶发网络抖动导致发版失败")
    require(release_sh, 'APP_BUILD_PREFIX="${APP_PREFIX}/releases/${VER}"', "tools/release.sh", "发布构建包必须使用版本化 OSS 路径")
    require(release_sh, 'SKILL_RELEASE_PREFIX="${SKILL_PREFIX}/releases/${VER}"', "tools/release.sh", "skill 必须使用与客户端相同版本的不可变 OSS 路径")
    require(release_sh, '--skill-sha256 "$SKILL_SHA"', "tools/release.sh", "版本清单必须绑定 skill tarball 哈希")
    require(release_sh, "redbeacon-skill-manifest.json", "tools/release.sh", "skill 包必须内含 channel/version/commit 元数据")
    require(release_sh, "build-complete.json", "tools/release.sh", "发布前必须验证三端矩阵统一完成标记")
    require(release_sh, "redbeacon-skill.tar.gz", "tools/release.sh", "发布和公网验证必须使用安装器约定的 skill tarball 文件名")
    require(release_sh, "公网发布结果已验证", "tools/release.sh", "发布后必须从 OSS 公网入口反向验证清单、三端包和 skill")
    require(release_sh, "CURRENT_COMMIT", "tools/release.sh", "发布标记必须核对当前 CLI 提交，防止混用旧平台包")
    require(release_sh, "最后上传，正式切换", "tools/release.sh", "latest manifest 必须最后上传，避免半发布状态暴露给用户")
    require(latest_generator, '"skill_bundle_url"', "tools/gen_latest.py", "manifest 必须给安装器版本化 skill URL")
    require(latest_generator, '"skill_sha256"', "tools/gen_latest.py", "manifest 必须给安装器 skill SHA-256")
    require(updater_py, "launch_installer_update", "cli/src/redbeacon/services/updater.py", "所有更新入口必须委托 OSS 安装脚本执行")
    require(updater_py, "installer_url", "cli/src/redbeacon/services/updater.py", "更新入口必须选择当前通道的安装脚本 URL")
    if "schedule_bundle_replace(progress=progress" in updater_py:
        fail("cli/src/redbeacon/services/updater.py 的 run_update 不能再走手写 zip 替换流程，必须执行安装脚本")
    require(bundle_spec, 'collect_data_files("playwright")', "cli/packaging/RedBeacon.spec", "冻结包必须带 Playwright driver，才能在客户端内修复浏览器内核")
    require(bundle_spec, "RUNTIME_SANITIZE_HOOK", "cli/packaging/RedBeacon.spec", "冻结客户端启动前必须清理继承的旧版本路径变量")
    for inherited in (
        "REDBEACON_DATA_DIR", "REDBEACON_PLAYWRIGHT_DIR", "REDBEACON_CLOAKBROWSER_DIR",
        "PLAYWRIGHT_BROWSERS_PATH", "CLOAKBROWSER_CACHE_DIR", "CLOAKBROWSER_BINARY_PATH",
        "BYTESTAFF_HOME",
    ):
        require(runtime_sanitize, inherited, "cli/packaging/_runtime_sanitize.py", f"冻结客户端必须清理继承变量 {inherited}")
    require(bundle_spec, '"cloakbrowser"', "cli/packaging/RedBeacon.spec", "冻结包必须带 CloakBrowser Python 包，才能在客户端内修复小红书自动化内核")
    require(bundle_spec, '"_sqlite3"', "cli/packaging/RedBeacon.spec", "Windows 冻结包必须显式包含 SQLite 扩展")
    require(bundle_spec, '"CFBundleExecutable": APP_NAME', "cli/packaging/RedBeacon.spec", "macOS 图标必须显式指向桌面主程序，不能误启动渲染器")
    require(sh, "verify_macos_bundle_entry", "install/install.sh", "macOS 安装器必须拒绝图标入口错误的 bundle")
    require(win_smoke, "Traceback|ModuleNotFoundError|ImportError", "cli/packaging/smoke_windows_bundle.ps1", "Windows smoke 必须捕获桌面初始化异常")
    require(win_smoke, "RedBeacon desktop smoke ok", "cli/packaging/smoke_windows_bundle.ps1", "Windows smoke 必须确认桌面初始化到达 ready 标记")
    require(win_smoke, "Real card render", "cli/packaging/smoke_windows_bundle.ps1", "Windows 冻结包必须使用当前浏览器内核真实渲染 PNG")


def check_cli_windows_json_contracts() -> None:
    cli_py = read("cli/src/redbeacon/cli.py")
    runtime = read("cli/src/redbeacon/routers/_runtime.py")
    json_input = read("cli/src/redbeacon/routers/_json_input.py")
    stdio = read("cli/src/redbeacon/utils/stdio.py")
    accounts = read("cli/src/redbeacon/routers/accounts.py")
    strategy = read("cli/src/redbeacon/routers/strategy.py")
    topics = read("cli/src/redbeacon/routers/topics.py")
    generate_router = read("cli/src/redbeacon/routers/generate.py")
    setup_router = read("cli/src/redbeacon/routers/setup.py")
    platform_router = read("cli/src/redbeacon/routers/platform.py")
    login_router = read("cli/src/redbeacon/routers/login.py")
    xhs_publish = read("cli/src/redbeacon/services/xhs/publish.py")

    require(cli_py, "--data-file", "cli/src/redbeacon/cli.py", "Windows 长 JSON 命令必须支持从 UTF-8 文件读取")
    require(cli_py, "--json-file", "cli/src/redbeacon/cli.py", "topics 批量/采纳必须支持从 UTF-8 JSON 文件读取")
    require(runtime, "safe_json_dumps", "cli/src/redbeacon/routers/_runtime.py", "CLI JSON 输出必须经过 Windows 安全序列化")
    require(runtime, "ensure_ascii=True", "cli/src/redbeacon/routers/_runtime.py", "CLI JSON 输出必须转义非 ASCII，避免 GBK 控制台崩溃")
    require(stdio, "errors=\"replace\"", "cli/src/redbeacon/utils/stdio.py", "标准流必须用 replace 兜底，避免窗口/GBK 环境崩溃")
    require(json_input, "sys.stdin.read()", "cli/src/redbeacon/routers/_json_input.py", "JSON 输入 helper 必须支持 stdin")
    require(json_input, "read_text(encoding=\"utf-8\")", "cli/src/redbeacon/routers/_json_input.py", "JSON 文件必须按 UTF-8 读取")
    require(json_input, "sanitize_json_value", "cli/src/redbeacon/routers/_json_input.py", "JSON 入库前必须清理非法 surrogate")
    if "/tmp/" in xhs_publish:
        fail("cli/src/redbeacon/services/xhs/publish.py 不能写死 Unix /tmp；Windows 发布排障文件必须走跨平台日志目录")
    require(accounts, "data_file", "cli/src/redbeacon/routers/accounts.py", "accounts patch 必须接入 --data-file")
    require(strategy, "data_file", "cli/src/redbeacon/routers/strategy.py", "strategy patch/image-set 必须接入 --data-file")
    require(topics, "json_file", "cli/src/redbeacon/routers/topics.py", "topics batch/accept 必须接入 --json-file")
    for rel, text in (
        ("cli/src/redbeacon/routers/generate.py", generate_router),
        ("cli/src/redbeacon/routers/topics.py", topics),
        ("cli/src/redbeacon/routers/setup.py", setup_router),
        ("cli/src/redbeacon/routers/platform.py", platform_router),
        ("cli/src/redbeacon/routers/login.py", login_router),
    ):
        if "print(json.dumps" in text:
            fail(f"{rel} 不能直接 print(json.dumps(...))，进度/中间输出也必须走 safe_json_dumps")

    for rel in (
        "cli/src/redbeacon/routers/readiness.py",
        "cli/src/redbeacon/routers/topics.py",
        "cli/src/redbeacon/routers/strategy.py",
        "cli/src/redbeacon/routers/generate.py",
        "cli/src/redbeacon/routers/review.py",
    ):
        text = read(rel)
        for phrase in FORBIDDEN_SKILL_PHRASES:
            if phrase in text:
                fail(f"{rel} 含有 Windows 不友好的命令提示：{phrase}")


def check_content_guardrails() -> None:
    generate_py = read("cli/src/redbeacon/core/usecases/generate.py")
    presets_py = read("cli/src/redbeacon/core/presets.py")
    image_gen_py = read("cli/src/redbeacon/services/image_gen.py")
    publish_py = read("cli/src/redbeacon/core/usecases/publish.py")
    publish_task = read("cli/src/redbeacon/tasks/publish.py")
    local_data = read("cli/src/redbeacon/infra/local_data.py")
    account_map = read("cli/src/redbeacon/services/account_map.py")
    strategy = read("cli/src/redbeacon/routers/strategy.py")
    index = read("cli/src/redbeacon/adapters/ui_backend/static/index.html")

    require(generate_py, "平台返回不是合法的文案 JSON", "cli/src/redbeacon/core/usecases/generate.py", "生成解析失败必须 fail fast，不能写脏审核表")
    require(generate_py, "_ensure_clean_copy_field", "cli/src/redbeacon/core/usecases/generate.py", "生成入库前必须校验标题/正文/标签")
    require(generate_py, "if (image_mode or \"\").strip()", "cli/src/redbeacon/core/usecases/generate.py", "--image-mode 必须覆盖默认方案配图方式")
    require(presets_py, "IMAGE_TEXT_LANGUAGE_RULE", "cli/src/redbeacon/core/presets.py", "所有内置视觉提示词必须共用简体中文文字规范")
    require(presets_py, "禁止使用繁体字、异体字", "cli/src/redbeacon/core/presets.py", "图片文字规范必须明确禁止繁体字和异体字")
    require(image_gen_py, "with_image_text_language_rule(combined)", "cli/src/redbeacon/services/image_gen.py", "真正发送生图请求前必须补齐简体中文文字规范")
    if "正在入飞书审核表" in generate_py or "飞书补图" in generate_py:
        fail("cli/src/redbeacon/core/usecases/generate.py 不能在本机主流程进度里继续写飞书审核表/飞书补图")
    require(publish_py, "validate_publish_payload", "cli/src/redbeacon/core/usecases/publish.py", "发布前必须校验坏标题/坏正文/raw JSON/损坏标签")
    require(publish_task, "invalid_count", "cli/src/redbeacon/tasks/publish.py", "publish dry-run 必须提前暴露不可发布记录")
    require(publish_task, "validate_publish_payload", "cli/src/redbeacon/tasks/publish.py", "publish dry-run 必须复用正式发布的健康检查")
    require(local_data, "rowcount == 0", "cli/src/redbeacon/infra/local_data.py", "本地审核保存打不中记录时不能静默返回 ok")
    require(account_map, "splitlines()", "cli/src/redbeacon/services/account_map.py", "账号定位 list/dict 字段必须优先按换行边界解析，避免中文逗号拆坏结构化项")
    if "feishu_fields" in strategy:
        fail("cli/src/redbeacon/routers/strategy.py 输出不能暴露 feishu_fields 旧口径")
    for rel, text in (
        ("cli/src/redbeacon/adapters/ui_backend/static/index.html", index),
        ("cli/src/redbeacon/routers/publish.py", read("cli/src/redbeacon/routers/publish.py")),
        ("cli/src/redbeacon/routers/readiness.py", read("cli/src/redbeacon/routers/readiness.py")),
        ("cli/src/redbeacon/routers/review.py", read("cli/src/redbeacon/routers/review.py")),
    ):
        for phrase in ("绑飞书", "同步飞书", "飞书暂不可用", "飞书审核表的窗口", "飞书审核表里", "唯一发布数据源是飞书"):
            if phrase in text:
                fail(f"{rel} 不能再出现当前主流程的旧飞书引导口径：{phrase}")


def check_client_startup() -> None:
    index = read("cli/src/redbeacon/adapters/ui_backend/static/index.html")
    card = read("cli/src/redbeacon/assets/card.html")
    cover = read("cli/src/redbeacon/assets/cover.html")

    startup_patterns = {
        r"fonts\.googleapis\.com": "客户端启动页不能依赖 Google Fonts",
        r"fonts\.gstatic\.com": "客户端启动页不能预连 Google Fonts 静态域名",
        r"<script\b[^>]*\bsrc\s*=\s*['\"]https?://": "客户端启动页不能加载远程 JS",
        r"<link\b[^>]*\bhref\s*=\s*['\"]https?://": "客户端启动页不能加载/预连远程 CSS 或字体",
        r"@import\s+url\(\s*['\"]?https?://": "客户端启动页不能通过 CSS import 拉远程资源",
    }
    for pattern, why in startup_patterns.items():
        if re.search(pattern, index, flags=re.IGNORECASE):
            fail(f"cli/src/redbeacon/adapters/ui_backend/static/index.html 违反发布契约：{why}")
    require(index, ".gerr", "cli/src/redbeacon/adapters/ui_backend/static/index.html", "客户端必须有错误块样式")
    require(index, "overflow-wrap:anywhere", "cli/src/redbeacon/adapters/ui_backend/static/index.html", "长错误信息必须能在客户端内折行，不能冲出窗口")

    render_patterns = {
        r"fonts\.googleapis\.com": "渲染模板不能依赖 Google Fonts",
        r"fonts\.gstatic\.com": "渲染模板不能依赖 Google Fonts 静态域名",
        r"@import\s+url\(\s*['\"]?https?://": "渲染模板不能通过 CSS import 拉远程资源",
    }
    for rel, text in (
        ("cli/src/redbeacon/assets/card.html", card),
        ("cli/src/redbeacon/assets/cover.html", cover),
    ):
        for pattern, why in render_patterns.items():
            if re.search(pattern, text, flags=re.IGNORECASE):
                fail(f"{rel} 违反发布契约：{why}")


def check_github_build_hygiene() -> None:
    agents = read("AGENTS.md")
    workflow = read("cli/.github/workflows/build-bundle.yml")
    pyproject = read("cli/pyproject.toml")
    spec = read("cli/packaging/RedBeacon.spec")
    windows_smoke = read("cli/packaging/smoke_windows_bundle.ps1")
    generate_usecase = read("cli/src/redbeacon/core/usecases/generate.py")
    generate_task = read("cli/src/redbeacon/tasks/generate.py")
    read("cli/uv.lock")
    require(
        agents,
        "Windows 是首要兼容平台",
        "AGENTS.md",
        "项目规则必须把 Windows 兼容列为首要发布纪律",
    )
    require(
        agents,
        "Windows job 是发布阻断项",
        "AGENTS.md",
        "项目规则必须说明 Windows 构建/烟测失败会阻断测试版发布",
    )
    require(
        workflow,
        "concurrency:",
        "cli/.github/workflows/build-bundle.yml",
        "桌面打包 workflow 必须启用并发组，连续触发时取消旧运行",
    )
    require(
        workflow,
        "cancel-in-progress: true",
        "cli/.github/workflows/build-bundle.yml",
        "桌面打包 workflow 必须取消旧运行，避免无谓 Actions 额度",
    )
    require(
        workflow,
        "failing because GitHub artifacts are not retained",
        "cli/.github/workflows/build-bundle.yml",
        "缺少 OSS key 时必须失败，不能把 GitHub artifact 当兜底发布源",
    )
    require(
        workflow,
        "windows-latest",
        "cli/.github/workflows/build-bundle.yml",
        "桌面打包 workflow 必须包含 Windows runner",
    )
    require(
        workflow,
        "Smoke test Windows bundle",
        "cli/.github/workflows/build-bundle.yml",
        "桌面打包 workflow 必须执行 Windows bundle smoke",
    )
    require(
        workflow,
        "Run regression tests",
        "cli/.github/workflows/build-bundle.yml",
        "三端打包前必须运行全量回归测试",
    )
    require(
        workflow,
        "uv sync --frozen --extra dev",
        "cli/.github/workflows/build-bundle.yml",
        "三端构建必须使用同一份冻结依赖锁，不能在测试版/正式版各自临时解依赖",
    )
    require(
        workflow,
        "Smoke test macOS/Linux bundle",
        "cli/.github/workflows/build-bundle.yml",
        "macOS/Linux 包也必须运行桌面初始化 smoke",
    )
    require(
        workflow,
        'default: "test"',
        "cli/.github/workflows/build-bundle.yml",
        "手动打包默认通道必须是 test，防止误覆盖正式包",
    )
    require(
        workflow,
        "/releases/${VERSION}",
        "cli/.github/workflows/build-bundle.yml",
        "GitHub 构建只能上传版本化包，不能覆盖当前正式直链",
    )
    require(
        workflow,
        "mark-complete:",
        "cli/.github/workflows/build-bundle.yml",
        "三端矩阵必须有统一完成标记 job",
    )
    require(
        workflow,
        "needs: build",
        "cli/.github/workflows/build-bundle.yml",
        "完成标记只能在全部三端 job 成功后写入",
    )
    require(
        workflow,
        "build-complete.json",
        "cli/.github/workflows/build-bundle.yml",
        "OSS 完成标记必须记录当前版本与提交",
    )
    require(
        workflow,
        "smoke_windows_bundle.ps1",
        "cli/.github/workflows/build-bundle.yml",
        "Windows bundle smoke 必须运行项目内 PowerShell 脚本",
    )
    require(spec, 'name="RedBeaconRenderer"', "cli/packaging/RedBeacon.spec", "冻结包必须包含独立文字卡片渲染器")
    require(workflow, "RENDERER_SMOKE", "cli/.github/workflows/build-bundle.yml", "macOS/Linux 冻结包必须启动检查卡片渲染器")
    require(workflow, '"$CLI" setup', "cli/.github/workflows/build-bundle.yml", "macOS/Linux 冻结包必须准备 Playwright 与 CloakBrowser 后真实渲染")
    require(workflow, 'card_*.png', "cli/.github/workflows/build-bundle.yml", "macOS/Linux 冻结包必须产出正文卡片 PNG")
    require(windows_smoke, "RedBeaconRenderer.exe", "cli/packaging/smoke_windows_bundle.ps1", "Windows 冻结包必须包含并启动检查 RedBeaconRenderer.exe")
    require(generate_task, '"RedBeaconRenderer.exe" if sys.platform == "win32"', "cli/src/redbeacon/tasks/generate.py", "Windows 必须显式解析渲染器 .exe 路径")
    require(workflow, "PlistBuddy", "cli/.github/workflows/build-bundle.yml", "macOS CI 必须读取并核验 CFBundleExecutable")
    require(workflow, '"$GUI"', "cli/.github/workflows/build-bundle.yml", "macOS/Linux desktop smoke 必须真正启动 GUI 可执行文件")
    require(workflow, "REDBEACON_DESKTOP_SMOKE_FILE", "cli/.github/workflows/build-bundle.yml", "无控制台 macOS 主程序必须通过文件回传 desktop-ready 标记")
    require(read("cli/src/redbeacon/main_entry.py"), "REDBEACON_DESKTOP_SMOKE_FILE", "cli/src/redbeacon/main_entry.py", "GUI desktop smoke 必须写出可验证标记")
    require(generate_task, "subprocess.CREATE_NO_WINDOW", "cli/src/redbeacon/tasks/generate.py", "Windows 后台卡片渲染不能弹出黑窗")
    require(generate_usecase, "if want_cards and not cards:", "cli/src/redbeacon/core/usecases/generate.py", "组合配图要求文字卡片时不能静默保存 AI 单图半成品")
    if "downloads on first run" in workflow:
        fail("cli/.github/workflows/build-bundle.yml 含有过时口径：浏览器内核不能留到用户首次运行再下载")
    for package in (
        "pydantic", "cryptography", "requests", "httpx", "openai", "playwright",
        "cloakbrowser", "markdown", "pillow", "pyyaml", "fastapi", "uvicorn", "pywebview",
    ):
        if not re.search(rf'(?m)^\s*"{re.escape(package)}==[^\"]+",?\s*$', pyproject):
            fail(f"cli/pyproject.toml 必须锁定桌面运行依赖 {package}，避免测试/正式构建漂移")
    forbidden = (
        "actions/upload-artifact",
        "Upload GitHub artifact",
        "GitHub artifact still available",
    )
    for needle in forbidden:
        if needle in workflow:
            fail(f"cli/.github/workflows/build-bundle.yml 不允许保留 GitHub artifact：{needle}")


def _frontmatter_name(text: str) -> str:
    match = re.search(r"(?m)^name:\s*([A-Za-z0-9_.-]+)\s*$", text)
    return match.group(1) if match else ""


def _to_codex_skill(stem: str, text: str) -> str:
    body = text
    desc = f"RedBeacon ability: {stem}"
    if text.startswith("---"):
        match = re.match(r"(?s)^---\r?\n(.*?)\r?\n---\r?\n?", text)
        if match:
            head = match.group(1)
            body = text[match.end():]
            for line in head.splitlines():
                if line.strip().startswith("description:"):
                    desc = line.split("description:", 1)[1].strip().strip('"').strip("'")
                    break
    desc = desc.replace("\\", "\\\\").replace('"', '\\"')
    return f'---\nname: {stem}\ndescription: "{desc}"\nmetadata:\n  short-description: "{desc}"\n---\n\n{body}'


def check_channel_skills() -> None:
    sources = sorted((ROOT / ".claude" / "commands").glob("redbeacon*.md"))
    for src in sources:
        text = src.read_text(encoding="utf-8")
        rel = src.relative_to(ROOT)
        if "\ufffd" in text:
            fail(f"{rel} 含有 Unicode replacement character，疑似编码损坏")
        if SINGLE_QUESTION_RULE not in text:
            fail(f"{rel} 缺少 skill 单题引导规则：{SINGLE_QUESTION_RULE}")
        for required in (SKILL_BOOTSTRAP_RULE, STABLE_INSTALL_PS1, STABLE_INSTALL_SH):
            if required not in text:
                fail(f"{rel} 缺少 CLI 缺失时的官方安装自举规则：{required}")
        for phrase in FORBIDDEN_SKILL_PHRASES:
            if phrase in text:
                fail(f"{rel} 含有过时的多题引导口径：{phrase}")

    workspace_skills = sorted((ROOT / ".agents" / "skills").glob("source-command-redbeacon*/SKILL.md"))
    if len(workspace_skills) != len(sources):
        fail(f"仓库 Codex skill 与真源数量不一致：{len(workspace_skills)} != {len(sources)}；请运行 tools/sync-codex-skills.py")
    expected_workspace_names = {f"source-command-{src.stem}" for src in sources}
    actual_workspace_names = {path.parent.name for path in workspace_skills}
    if actual_workspace_names != expected_workspace_names:
        fail("仓库 Codex skill 命名与真源不一致；请运行 tools/sync-codex-skills.py")
    for path in workspace_skills:
        text = path.read_text(encoding="utf-8")
        if _frontmatter_name(text) != path.parent.name:
            fail(f"{path.relative_to(ROOT)} 的 name 必须等于目录名")
        if SINGLE_QUESTION_RULE not in text:
            fail(f"{path.relative_to(ROOT)} 缺少 skill 单题引导规则")
        if SKILL_BOOTSTRAP_RULE not in text:
            fail(f"{path.relative_to(ROOT)} 缺少禁止猜测客户端 zip 的自举规则")
        for phrase in FORBIDDEN_SKILL_PHRASES:
            if phrase in text:
                fail(f"{path.relative_to(ROOT)} 含有 Windows 不友好或过时示例：{phrase}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        stable = root / "stable"
        test = root / "test"
        stable_files = build_channel_skills.build("stable", stable)
        test_files = build_channel_skills.build("test", test)

        if not stable_files:
            fail("stable skill 为空")
        if not test_files:
            fail("test skill 为空")
        if len(stable_files) != len(test_files):
            fail(f"stable/test skill 数量不一致：{len(stable_files)} != {len(test_files)}")

        stable_names = {p.name for p in stable_files}
        test_names = {p.name for p in test_files}
        if "redbeacon.md" not in stable_names:
            fail("stable skill 必须包含 redbeacon.md")
        if "redbeacon-test.md" not in test_names:
            fail("test skill 必须包含 redbeacon-test.md")
        bad_test_names = sorted(n for n in test_names if not n.startswith("redbeacon-test"))
        if bad_test_names:
            fail(f"test skill 文件名必须全部是 redbeacon-test*：{', '.join(bad_test_names)}")

        for channel, files in (("stable", stable_files), ("test", test_files)):
            for path in files:
                text = path.read_text(encoding="utf-8")
                if SINGLE_QUESTION_RULE not in text:
                    fail(f"{channel} skill {path.name} 缺少单题引导规则：{SINGLE_QUESTION_RULE}")
                required_installers = (
                    (TEST_INSTALL_PS1, TEST_INSTALL_SH)
                    if channel == "test"
                    else (STABLE_INSTALL_PS1, STABLE_INSTALL_SH)
                )
                for required in (SKILL_BOOTSTRAP_RULE, *required_installers):
                    if required not in text:
                        fail(f"{channel} skill {path.name} 缺少官方安装自举规则：{required}")
                for phrase in FORBIDDEN_SKILL_PHRASES:
                    if phrase in text:
                        fail(f"{channel} skill {path.name} 含有过时的多题引导口径：{phrase}")

        for path in test_files:
            text = path.read_text(encoding="utf-8")
            if "\ufffd" in text:
                fail(f"{path.name} 含有 Unicode replacement character，疑似编码损坏")
            if "redbeacon-test" not in text:
                fail(f"{path.name} 正文没有指向测试版命令 redbeacon-test")
            if STABLE_INSTALL_PS1 in text or STABLE_INSTALL_SH in text:
                fail(f"{path.name} 测试版 skill 仍指向正式版安装器")
            codex = _to_codex_skill(path.stem, text)
            if "\ufffd" in codex:
                fail(f"{path.name} 派生 Codex SKILL.md 后疑似编码损坏")
            if _frontmatter_name(codex) != path.stem:
                fail(f"{path.name} 派生 Codex SKILL.md 后 name 不等于文件名")


def check_platform_account_contracts() -> None:
    checkin = read("cli/src/redbeacon/platform_account/checkin.py")
    scheduler = read("cli/src/redbeacon/platform_account/scheduler.py")
    chat = read("cli/src/redbeacon/platform_account/chat.py")
    image_gen = read("cli/src/redbeacon/services/image_gen.py")
    client = read("cli/src/redbeacon/platform_account/client.py")
    errors = read("cli/src/redbeacon/platform_account/errors.py")
    ui_app = read("cli/src/redbeacon/adapters/ui_backend/app.py")
    ui_index = read("cli/src/redbeacon/adapters/ui_backend/static/index.html")

    require(checkin, "json_body={}", "cli/src/redbeacon/platform_account/checkin.py", "新版 checkin 必须发送空对象，产品码只做兼容来源标签")
    require(checkin, '"entitlements": []', "cli/src/redbeacon/platform_account/checkin.py", "员工 entitlement 已归档，不能继续作为客户端权限真源")
    require(checkin, '"limits": limits', "cli/src/redbeacon/platform_account/checkin.py", "checkin 必须把 limits.ai 交给账号级调度层")
    require(scheduler, "ai_scheduler.sqlite3", "cli/src/redbeacon/platform_account/scheduler.py", "多窗口/CLI 必须通过共享 SQLite 协调账号级 AI 限额")
    for field in ("max_in_flight", "max_concurrent", "max_per_minute", "request_attempts"):
        require(scheduler, field, "cli/src/redbeacon/platform_account/scheduler.py", f"账号级调度必须实现 {field}")
    require(scheduler, "retry_after", "cli/src/redbeacon/platform_account/scheduler.py", "429/503 重试必须遵守 Retry-After")
    require(scheduler, 'code in {"duplicate_failed", "upstream_error"}', "cli/src/redbeacon/platform_account/scheduler.py", "明确退款失败后必须换 request_id 安全重试")
    require(chat, 'scheduler.execute_ai("chat"', "cli/src/redbeacon/platform_account/chat.py", "平台对话必须经过账号级共享调度器")
    require(image_gen, 'scheduler.execute_ai(', "cli/src/redbeacon/services/image_gen.py", "平台生图必须经过账号级共享调度器")
    require(client, '"Accept-Encoding": "gzip"', "cli/src/redbeacon/platform_account/client.py", "平台 HTTP 客户端必须复用 gzip 连接配置")
    require(errors, "parsedate_to_datetime", "cli/src/redbeacon/platform_account/errors.py", "Retry-After 必须同时兼容秒数和 HTTP 日期")
    require(ui_app, "_gen_queue = _SerialJobQueue(max_pending=20)", "cli/src/redbeacon/adapters/ui_backend/app.py", "客户端笔记生成必须使用有上限的串行队列")
    if ui_app.count("_enqueue_generation_job(job_id, _bg") != 4:
        fail("cli/src/redbeacon/adapters/ui_backend/app.py 四个生成入口必须全部进入同一个串行队列")
    require(ui_index, "RedBeacon 会按顺序一篇篇完成", "cli/src/redbeacon/adapters/ui_backend/static/index.html", "客户端必须用数字员工口吻显示真实排队状态")
    require(ui_index, "RedBeacon 在工作 · ${step}/4", "cli/src/redbeacon/adapters/ui_backend/static/index.html", "客户端创作进度必须体现有名字的数字员工")
    forbid(ui_index, "生成中 ${step}/4", "cli/src/redbeacon/adapters/ui_backend/static/index.html", "客户端不能退回冷冰冰的通用生成状态")


def main() -> None:
    check_installers()
    check_cli_windows_json_contracts()
    check_content_guardrails()
    check_client_startup()
    check_github_build_hygiene()
    check_channel_skills()
    check_platform_account_contracts()
    print("  ✓ 发布契约检查通过：安装预热/浏览器版本与启动探测/平台账号级调度/Windows 编码/长 JSON 文件输入/bundle smoke/GitHub 构建随用随清/skill 隔离/skill 单题引导/客户端启动资源都满足")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))
