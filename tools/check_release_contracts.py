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

ROOT = Path(__file__).resolve().parent.parent
SINGLE_QUESTION_RULE = "一次只问一个问题，一次只推进一件事"
FORBIDDEN_SKILL_PHRASES = (
    "每次只问一到两件事",
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


def check_installers() -> None:
    sh = read("install/install.sh")
    ps1 = read("install/install.ps1")
    unsh = read("install/uninstall.sh")
    unps1 = read("install/uninstall.ps1")
    setup_py = read("cli/src/redbeacon/routers/setup.py")
    browser_engine_py = read("cli/src/redbeacon/services/browser_engine.py")
    bundle_spec = read("cli/packaging/RedBeacon.spec")
    win_smoke = read("cli/packaging/smoke_windows_bundle.ps1")

    for rel in (
        "install/install.ps1",
        "install/install-test.ps1",
        "install/uninstall.ps1",
        "install/uninstall-test.ps1",
    ):
        if any(b > 0x7F for b in read_bytes(rel)):
            fail(f"{rel} 必须保持 ASCII-only，避免 Windows PowerShell 5.1 编码/显示问题")

    require(sh, 'codex_dir="$HOME/.codex/skills"', "install/install.sh", "Mac/Linux 安装必须写入 Codex 扫描目录")
    require(sh, 'install_codex_skills "$SRC"', "install/install.sh", "Mac/Linux 安装必须从 skill tarball 派生 Codex SKILL.md")
    require(sh, 'run_browser_setup "$LOCAL_CLI"', "install/install.sh", "Mac/Linux 安装必须预热 Playwright 浏览器内核")
    require(ps1, 'Join-Path $HOME ".codex\\skills"', "install/install.ps1", "Windows 安装必须写入 Codex 扫描目录")
    require(ps1, "Write-CodexSkills $src.FullName", "install/install.ps1", "Windows 安装必须从 skill tarball 派生 Codex SKILL.md")
    require(ps1, "Run-BrowserSetup $cliExe", "install/install.ps1", "Windows 安装必须预热 Playwright 浏览器内核")

    require(unsh, 'CODEX_SKILL_DIR="$HOME/.codex/skills"', "install/uninstall.sh", "Mac/Linux 卸载必须清理对应通道 Codex skill")
    require(unps1, '$CodexSkillDir = "$HOME\\.codex\\skills"', "install/uninstall.ps1", "Windows 卸载必须清理对应通道 Codex skill")
    require(unsh, 'redbeacon-test*', "install/uninstall.sh", "测试版卸载只能动 redbeacon-test*")
    require(unps1, 'redbeacon-test*', "install/uninstall.ps1", "测试版卸载只能动 redbeacon-test*")
    require(setup_py, "browser_engine.ensure_browser_engine", "cli/src/redbeacon/routers/setup.py", "setup 命令必须走带进度的浏览器内核安装服务")
    require(browser_engine_py, "bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/playwright", "cli/src/redbeacon/services/browser_engine.py", "浏览器内核下载必须包含 RedBeacon OSS 兜底源")
    require(bundle_spec, 'collect_data_files("playwright")', "cli/packaging/RedBeacon.spec", "冻结包必须带 Playwright driver，才能在客户端内修复浏览器内核")
    require(bundle_spec, '"_sqlite3"', "cli/packaging/RedBeacon.spec", "Windows 冻结包必须显式包含 SQLite 扩展")
    require(win_smoke, "Traceback|ModuleNotFoundError|ImportError", "cli/packaging/smoke_windows_bundle.ps1", "Windows smoke 必须捕获桌面初始化异常")
    require(win_smoke, "RedBeacon desktop smoke ok", "cli/packaging/smoke_windows_bundle.ps1", "Windows smoke 必须确认桌面初始化到达 ready 标记")


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
    workflow = read("cli/.github/workflows/build-bundle.yml")
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
    for src in sorted((ROOT / ".claude" / "commands").glob("redbeacon*.md")):
        text = src.read_text(encoding="utf-8")
        rel = src.relative_to(ROOT)
        if "\ufffd" in text:
            fail(f"{rel} 含有 Unicode replacement character，疑似编码损坏")
        if SINGLE_QUESTION_RULE not in text:
            fail(f"{rel} 缺少 skill 单题引导规则：{SINGLE_QUESTION_RULE}")
        for phrase in FORBIDDEN_SKILL_PHRASES:
            if phrase in text:
                fail(f"{rel} 含有过时的多题引导口径：{phrase}")

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
                for phrase in FORBIDDEN_SKILL_PHRASES:
                    if phrase in text:
                        fail(f"{channel} skill {path.name} 含有过时的多题引导口径：{phrase}")

        for path in test_files:
            text = path.read_text(encoding="utf-8")
            if "\ufffd" in text:
                fail(f"{path.name} 含有 Unicode replacement character，疑似编码损坏")
            if "redbeacon-test" not in text:
                fail(f"{path.name} 正文没有指向测试版命令 redbeacon-test")
            codex = _to_codex_skill(path.stem, text)
            if "\ufffd" in codex:
                fail(f"{path.name} 派生 Codex SKILL.md 后疑似编码损坏")
            if _frontmatter_name(codex) != path.stem:
                fail(f"{path.name} 派生 Codex SKILL.md 后 name 不等于文件名")


def main() -> None:
    check_installers()
    check_client_startup()
    check_github_build_hygiene()
    check_channel_skills()
    print("  ✓ 发布契约检查通过：安装预热/Windows 编码/bundle smoke/GitHub 构建随用随清/skill 隔离/skill 单题引导/客户端启动资源都满足")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))
