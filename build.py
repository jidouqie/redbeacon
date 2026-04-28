#!/usr/bin/env python3
"""
Build RedBeacon — 全部编译为二进制，交付包中不含任何 Python 源码。

产物结构（以 macOS 为例）：
  redbeacon-dist/mac/
    RedBeacon.app        ← launcher GUI（PyInstaller）
    RedBeaconServer      ← 后端服务（PyInstaller，含所有 backend/ 代码）
    RedBeaconRenderer    ← 图文卡片渲染器（PyInstaller）
    frontend/out/        ← 预编译静态页面（不需要 Node.js）
    data/playwright/     ← 捆绑 Chromium
    tools/               ← MCP 二进制
    data/ logs/ start.sh VERSION

Usage:
  python build.py
"""
import os
import subprocess
import sys
import platform
import shutil
from pathlib import Path

ROOT        = Path(__file__).parent.resolve()
SYSTEM      = platform.system()
ARCH        = platform.machine()
APP_VERSION = "0.0.1"

PLATFORM_DIR = {"Darwin": "mac", "Windows": "win", "Linux": "linux"}.get(SYSTEM, "linux")
DIST_ROOT = ROOT.parent / "redbeacon-dist"
DIST      = DIST_ROOT / PLATFORM_DIR


# ── helpers ───────────────────────────────────────────────────────────────────

def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)


def _pyinstall(entry: str, name: str, extra_args: list[str] | None = None, onefile: bool = True):
    """Run PyInstaller for a single entry point."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", name,
        "--noconfirm",
        "--clean",
    ]
    if onefile or SYSTEM != "Darwin":
        cmd += ["--onefile"]
    else:
        cmd += ["--onedir"]

    # Suppress console window on Windows only; keep it on macOS/Linux for debug
    if SYSTEM == "Windows":
        cmd += ["--noconsole"]

    if extra_args:
        cmd += extra_args
    cmd.append(entry)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _dir_size(p: Path) -> str:
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return f"{total / 1_048_576:.0f} MB"


# ── step 1: launcher (GUI) ────────────────────────────────────────────────────

def _build_launcher():
    print("\n[1/4] Building launcher (RedBeacon GUI)...")
    args = ["--windowed"]
    if SYSTEM == "Darwin":
        icon = ROOT / "assets" / "icon.icns"
        if icon.exists():
            args += ["--icon", str(icon)]
        # Use onedir for .app bundle
        _pyinstall("launcher.py", "RedBeacon", args, onefile=False)
    else:
        if SYSTEM == "Windows":
            icon = ROOT / "assets" / "icon.ico"
            if icon.exists():
                args += ["--icon", str(icon)]
        _pyinstall("launcher.py", "RedBeacon", args, onefile=True)


# ── step 2: backend server ────────────────────────────────────────────────────

# Hidden imports required by uvicorn / FastAPI / APScheduler
_BACKEND_HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl", "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "apscheduler.triggers.cron", "apscheduler.triggers.interval",
    "apscheduler.executors.default", "apscheduler.jobstores.memory",
    "fastapi", "fastapi.staticfiles", "fastapi.middleware.cors",
    "pydantic", "pydantic.v1",
    "cryptography", "cryptography.fernet",
    "openai", "httpx",
    "multipart", "python_multipart",
    "email.mime.multipart", "email.mime.text",
    "sqlite3", "apscheduler",
]


def _build_backend():
    print("\n[2/4] Building backend server (RedBeaconServer)...")
    hidden = []
    for h in _BACKEND_HIDDEN:
        hidden += ["--hidden-import", h]

    # Add backend/ to analysis paths so 'import main' resolves
    _pyinstall(
        "backend_server.py",
        "RedBeaconServer",
        extra_args=hidden + ["--paths", str(ROOT / "backend")],
        onefile=True,
    )


# ── step 3: renderer ─────────────────────────────────────────────────────────

def _build_renderer():
    print("\n[3/4] Building renderer (RedBeaconRenderer)...")
    _pyinstall(
        "renderer_main.py",
        "RedBeaconRenderer",
        extra_args=[
            "--paths", str(ROOT / "backend"),
            "--hidden-import", "playwright",
            "--hidden-import", "playwright.async_api",
            "--hidden-import", "markdown",
            "--hidden-import", "yaml",
        ],
        onefile=True,
    )


# ── step 4: assemble dist ────────────────────────────────────────────────────

def _assemble():
    print("\n[4/4] Assembling delivery directory...")
    DIST.mkdir(parents=True, exist_ok=True)
    build_out = ROOT / "dist"

    # 清理不应出现在交付包的目录（旧构建残留 / 源码目录）
    for stale in ["backend", "python", "frontend/node_modules"]:
        p = DIST / stale
        if p.exists():
            shutil.rmtree(p)
            print(f"  Removed stale: {stale}/")

    # Copy launcher
    if SYSTEM == "Darwin":
        src  = build_out / "RedBeacon.app"
        dest = DIST / "RedBeacon.app"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        _set_app_version_macos(dest)
        print(f"  RedBeacon.app -> {dest}")
    elif SYSTEM == "Windows":
        shutil.copy2(build_out / "RedBeacon.exe", DIST / "RedBeacon.exe")
    else:
        dest = DIST / "RedBeacon"
        shutil.copy2(build_out / "RedBeacon", dest)
        dest.chmod(0o755)

    # Copy backend server binary
    _copy_binary("RedBeaconServer")

    # Copy renderer binary
    _copy_binary("RedBeaconRenderer")

    # Build and copy frontend static files
    _build_frontend()

    # Install Playwright Chromium
    _install_playwright()

    # Copy start script
    script = ROOT / ("start.bat" if SYSTEM == "Windows" else "start.sh")
    if script.exists():
        dest_script = DIST / script.name
        shutil.copy2(script, dest_script)
        if SYSTEM != "Windows":
            dest_script.chmod(0o755)

    # Copy platform tools (MCP binaries)
    _copy_tools()

    # Ensure data / logs dirs
    (DIST / "data").mkdir(exist_ok=True)
    (DIST / "logs").mkdir(exist_ok=True)

    # Copy skills
    _copy_skills()

    # VERSION
    (DIST / "VERSION").write_text(APP_VERSION)
    print(f"  VERSION: {APP_VERSION}")

    print(f"\nDelivery directory: {DIST}  ({_dir_size(DIST)})")
    print("Done.")


def _copy_binary(name: str):
    ext = ".exe" if SYSTEM == "Windows" else ""
    src = ROOT / "dist" / f"{name}{ext}"
    if not src.exists():
        raise FileNotFoundError(f"Binary not found: {src}")
    dest = DIST / f"{name}{ext}"
    shutil.copy2(src, dest)
    if SYSTEM != "Windows":
        dest.chmod(0o755)
    print(f"  {name}{ext} -> {dest}")


def _find_npm_cli() -> str:
    """Find npm-cli.js bundled with Node.js (avoids cmd.exe for UNC paths on Windows)."""
    import shutil as _shutil
    node_exe = _shutil.which("node")
    if not node_exe:
        raise RuntimeError("node not found in PATH")
    # npm is installed alongside node: <node_dir>/node_modules/npm/bin/npm-cli.js
    node_dir = Path(node_exe).parent
    npm_cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if npm_cli.exists():
        return str(npm_cli)
    # fallback: newer Node puts npm one level up
    npm_cli2 = node_dir.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if npm_cli2.exists():
        return str(npm_cli2)
    raise RuntimeError(f"npm-cli.js not found near {node_exe}")


def _copy_tools():
    """Copy platform-specific MCP binaries to dist/tools/.
    Priority: tools-src/{platform}/ → tools/ (platform-specific filenames).
    """
    tools_dest = DIST / "tools"
    tools_dest.mkdir(exist_ok=True)
    copied = 0

    # 1. Try tools-src/{platform}/ (developer machine with full set)
    tools_src = ROOT / "tools-src" / PLATFORM_DIR
    if tools_src.exists():
        for f in tools_src.iterdir():
            if f.is_file():
                dest = tools_dest / f.name
                shutil.copy2(f, dest)
                if SYSTEM != "Windows":
                    dest.chmod(0o755)
                copied += 1
        print(f"  tools/ -> {tools_dest}  ({copied} binaries, from tools-src/)")
        return

    # 2. Fallback: copy from tools/ filtering by platform suffix
    tools_dir = ROOT / "tools"
    if not tools_dir.exists():
        print(f"  Warning: neither tools-src/{PLATFORM_DIR}/ nor tools/ found, skipping")
        return

    if SYSTEM == "Darwin":
        suffixes = ("-darwin-arm64", "-darwin-x86_64", "-darwin")
    elif SYSTEM == "Windows":
        suffixes = (".exe",)
    else:
        suffixes = ("-linux-amd64", "-linux-x86_64", "-linux")

    name_map = {
        "xiaohongshu-mcp": "xiaohongshu-mcp",
        "xiaohongshu-login": "xiaohongshu-login",
    }

    for src_file in tools_dir.iterdir():
        if not src_file.is_file():
            continue
        for tool, dest_name in name_map.items():
            if src_file.name.startswith(tool) and any(src_file.name.endswith(s) for s in suffixes):
                ext = ".exe" if SYSTEM == "Windows" else ""
                dest = tools_dest / f"{dest_name}{ext}"
                shutil.copy2(src_file, dest)
                if SYSTEM != "Windows":
                    dest.chmod(0o755)
                copied += 1

    print(f"  tools/ -> {tools_dest}  ({copied} binaries, from tools/)")


def _build_frontend():
    frontend_src = ROOT / "frontend"
    out_src      = frontend_src / "out"
    out_dest     = DIST / "frontend" / "out"

    if SYSTEM == "Windows":
        # Always reinstall on Windows: node_modules from Mac has incompatible native binaries
        node_modules = frontend_src / "node_modules"
        if node_modules.exists():
            shutil.rmtree(node_modules)
        print("  npm install in frontend/ (Windows) ...")
        # Use node to run npm directly, avoiding cmd.exe UNC path issue
        npm_cli = _find_npm_cli()
        subprocess.run(["node", npm_cli, "install"], cwd=str(frontend_src), check=True)
    elif not (frontend_src / "node_modules").exists():
        print("  npm install in frontend/ ...")
        subprocess.run(["npm", "install"], cwd=str(frontend_src), check=True)

    print("  next build --webpack (static export) ...")
    if SYSTEM == "Windows":
        # next entry point has no .js extension
        next_bin = str(frontend_src / "node_modules" / "next" / "dist" / "bin" / "next")
        subprocess.run(["node", next_bin, "build", "--webpack"], cwd=str(frontend_src), check=True)
    else:
        subprocess.run(
            ["./node_modules/.bin/next", "build", "--webpack"],
            cwd=str(frontend_src), check=True,
        )

    if out_dest.exists():
        shutil.rmtree(out_dest)
    out_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(out_src), str(out_dest))
    print(f"  frontend/out/ -> {out_dest}  ({_dir_size(out_dest)})")


def _install_playwright():
    playwright_dir = DIST / "data" / "playwright"
    playwright_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(playwright_dir)
    print("  Installing Playwright Chromium ...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env=env, check=True,
    )


def _copy_skills():
    src  = ROOT / ".claude" / "commands"
    dest = DIST_ROOT / ".claude" / "commands"
    if not src.exists():
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    print(f"  Skills -> {dest}  ({len(list(dest.glob('*.md')))} files)")


def _set_app_version_macos(app_path: Path):
    plist = app_path / "Contents" / "Info.plist"
    if not plist.exists():
        return
    try:
        subprocess.run(["plutil", "-replace", "CFBundleShortVersionString",
                        "-string", APP_VERSION, str(plist)], check=True)
        subprocess.run(["plutil", "-replace", "CFBundleVersion",
                        "-string", APP_VERSION, str(plist)], check=True)
    except Exception as e:
        print(f"  Warning: plist version: {e}")


def _cleanup():
    for p in [ROOT / "dist", ROOT / "build"]:
        if p.exists():
            shutil.rmtree(p)
    for spec in ROOT.glob("*.spec"):
        spec.unlink()


# ── main ─────────────────────────────────────────────────────────────────────

def build():
    ensure_pyinstaller()
    _build_launcher()
    _build_backend()
    _build_renderer()
    _assemble()
    _cleanup()


if __name__ == "__main__":
    build()
