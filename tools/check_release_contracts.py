#!/usr/bin/env python3
"""Fail closed when RedBeacon drifts from the central publication contract."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from build_channel_skills import (
    STABLE_MANIFEST_URL,
    SUPPORTED_ASSISTANTS,
    TEST_MANIFEST_URL,
    build as build_channel_skills,
    transform_test_text,
)


ROOT = Path(__file__).resolve().parent.parent
CENTRAL_ORIGIN = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
CONTRACTS = (
    "docs/download-node-integration.md",
    "docs/download-node-project-intake.yaml",
    "docs/download-node-project-receipt.json",
    "release/release-contract.json",
)
REMOVED_ACTIVE_PATHS = (
    "latest.json",
    "latest-test.json",
    "tools/release.sh",
    "tools/gen_latest.py",
    "tools/release_source_fingerprint.py",
    "tools/check_browser_mirrors.py",
    "tools/mirror_playwright_browsers.py",
    "tools/mirror_cloakbrowser_browsers.py",
)


def fail(message: str) -> None:
    raise SystemExit(f"release contract failed: {message}")


def tracked(path: str) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def main() -> None:
    for path in REMOVED_ACTIVE_PATHS:
        if (ROOT / path).exists():
            fail(f"legacy project-local publication path is active: {path}")

    archive = ROOT / ".history" / "redbeacon-legacy-project-release-2026-07-17.tar.gz"
    if not archive.is_file() or archive.stat().st_size <= 0:
        fail("cold archive for the retired project-local release implementation is missing")

    for path in CONTRACTS:
        file_path = ROOT / path
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            fail(f"canonical contract is missing: {path}")
        if not tracked(path):
            fail(f"canonical contract is not committed: {path}")
        text = file_path.read_text(encoding="utf-8")
        if any(marker in text for marker in ("<project>", "example-project", "TODO", "TBD")):
            fail(f"canonical contract still contains a placeholder: {path}")

    release_contract = json.loads((ROOT / "release" / "release-contract.json").read_text(encoding="utf-8"))
    cli_version_text = (ROOT / "cli" / "src" / "redbeacon" / "__init__.py").read_text(encoding="utf-8")
    version_match = re.search(r'__version__\s*=\s*"([^"]+)"', cli_version_text)
    if version_match is None or release_contract.get("version") != version_match.group(1):
        fail("release contract version does not match the CLI source version")
    cli_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT / "cli",
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if release_contract.get("cli_commit") != cli_head:
        fail("release contract CLI commit does not match the checked-out CLI HEAD")

    build_script = (ROOT / "tools" / "build_desktop_local.sh").read_text(encoding="utf-8")
    forbidden_build_terms = ("ossutil", "OSS_PROFILE", "OSS_BUCKET", "upload-batch")
    if any(term in build_script for term in forbidden_build_terms):
        fail("the project build script still owns publication or credentials")
    if "prepare_release_artifacts.py" not in build_script:
        fail("the build does not create the clean central publication source tree")
    if "check_release_dependency_contract.py" not in build_script:
        fail("the build does not validate cross-platform runtime dependency coordinates")

    build_meta = (ROOT / "cli" / "src" / "redbeacon" / "build_meta.py").read_text(encoding="utf-8")
    downloader = (ROOT / "cli" / "src" / "redbeacon" / "services" / "release_download.py").read_text(encoding="utf-8")
    browser = (ROOT / "cli" / "src" / "redbeacon" / "services" / "browser_engine.py").read_text(encoding="utf-8")
    if CENTRAL_ORIGIN not in build_meta or CENTRAL_ORIGIN not in downloader:
        fail("client canonical manifest does not use the fixed central origin")
    if "Range\": \"bytes=0-" not in downloader or "settimeout(8.0)" not in downloader or "settimeout(15.0)" not in downloader:
        fail("client node-first timeout/Range contract is incomplete")
    legacy_origin = "bytestaff" + "-redbeacon.oss-cn-shanghai.aliyuncs.com"
    if legacy_origin in build_meta or legacy_origin in downloader or legacy_origin in browser:
        fail("runtime still points at the retired project bucket")

    for path in (ROOT / "install").glob("*.ps1"):
        try:
            path.read_bytes().decode("ascii")
        except UnicodeDecodeError as exc:
            fail(f"PowerShell installer must remain ASCII-only: {path.name}: {exc}")
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / "install" / name).read_text(encoding="utf-8")
        if CENTRAL_ORIGIN not in text or "download node" not in text.lower():
            fail(f"{name} does not implement central node-first installation")
        launch_marker = "launch_installed_app" if name.endswith(".sh") else "Start-InstalledApp"
        if text.count(launch_marker) < 3:
            fail(f"{name} does not auto-launch after fresh and healthy repeat installs")
        for assistant in ("codex", "openclaw", "hermes", "workbuddy"):
            if assistant not in text.lower():
                fail(f"{name} does not install the {assistant} skill adapter")
        progress_marker = "progress and speed shown below" if name.endswith(".sh") else "MiB/s from download node"
        if progress_marker not in text:
            fail(f"{name} does not show live size/speed feedback during the primary package download")
        if name.endswith(".ps1"):
            if "function Remove-InstallerTemp" not in text or "finally { Remove-InstallerTemp $tmp }" not in text:
                fail("install.ps1 can misreport a successful install when Windows temporarily locks cleanup files")

    locate_source = (ROOT / ".claude" / "commands" / "redbeacon-locate.md").read_text(encoding="utf-8")
    for marker in ("我先简述整体想法", "你逐题带我梳理", "不得把他已经说过的内容换个说法再问一次"):
        if marker not in locate_source:
            fail(f"locate skill lost the whole-picture-first onboarding rule: {marker}")

    main_skill = (ROOT / ".claude" / "commands" / "redbeacon.md").read_text(encoding="utf-8")
    accounts_skill = (ROOT / ".claude" / "commands" / "redbeacon-accounts.md").read_text(encoding="utf-8")
    benchmark_skill = (ROOT / ".claude" / "commands" / "redbeacon-benchmark.md").read_text(encoding="utf-8")
    note_style_skill = (ROOT / ".claude" / "commands" / "redbeacon-note-style.md").read_text(encoding="utf-8")
    topics_skill = (ROOT / ".claude" / "commands" / "redbeacon-topics.md").read_text(encoding="utf-8")
    generate_skill = (ROOT / ".claude" / "commands" / "redbeacon-generate.md").read_text(encoding="utf-8")
    if "ui app --detach --page" not in main_skill:
        fail("main skill no longer makes UI milestones visible with a non-blocking deep link")
    for marker in (
        "accounts create` 返回成功只算中间状态",
        "同一轮",
        "redbeacon xhs-login start --account-id {新id}",
        "禁止只回复“账号已创建，请自行去登录”就结束",
    ):
        if marker not in accounts_skill:
            fail(f"accounts skill lost the create-then-scan-login contract: {marker}")
    for marker in (
        "redbeacon benchmark analyze",
        "redbeacon benchmark apply",
        "默认优先使用 RedBeacon 完整能力",
        "用户明确要求宿主 AI 接管",
        "strategy patch",
        "plans save",
        "不静默切换",
        "不得把这类结果冒充成平台对标分析结果",
    ):
        if marker not in benchmark_skill:
            fail(f"benchmark skill lost the product-first/host-takeover contract: {marker}")
    for marker in (
        "照这篇做",
        "redbeacon note-style analyze",
        "redbeacon note-style apply",
        "用户没有明确选择 1 或 2 时，到此停止",
        "--make-default",
        "ui app --detach --page 方案",
    ):
        if marker not in note_style_skill:
            fail(f"note-style skill lost the single-note learning contract: {marker}")
    for marker in ("/redbeacon-benchmark", "/redbeacon-note-style", "小红书链接的路由铁律"):
        if marker not in main_skill:
            fail(f"main skill lost Xiaohongshu link intent routing: {marker}")
    for marker in ("--require-complete", "内容类型、应用域、问题类型", "无额外备注",
                   "ui app --detach --page 选题"):
        if marker not in topics_skill:
            fail(f"topics skill lost the complete-brief/UI handoff contract: {marker}")
    for marker in (
        "当前宿主明确是 Codex",
        "其它受支持 AI 客户端",
        "不能因此把已经能由宿主完成的文案也改走平台",
        "redbeacon creation batch-prepare --json-file",
        "redbeacon creation batch-recover",
        "redbeacon creation copy-validate",
        "redbeacon creation copy-fallback",
        "redbeacon creation image-import",
        "redbeacon creation image-fallback",
        "redbeacon creation fail",
        "redbeacon creation batch-cancel",
        "内置生图工具",
        "未经允许不得调用收费平台能力",
        "严格串行",
        "不自动通过、不自动发布",
        "ui app --detach --page 审稿",
    ):
        if marker not in generate_skill:
            fail(f"generate skill lost the host-capability creation contract: {marker}")
    if "宿主零点创作例外" not in main_skill:
        fail("main skill still blocks a zero-platform host creation path")

    with tempfile.TemporaryDirectory(prefix="redbeacon-skill-contract-") as temp:
        for channel in ("stable", "test"):
            root = Path(temp) / channel
            commands = build_channel_skills(channel, root)
            stems = {path.stem for path in commands}
            portable = {
                path.parent.name
                for path in (root / "agent-skills").glob("*/SKILL.md")
            }
            if not stems or stems != portable:
                fail(f"{channel} Claude commands and portable Agent Skills drifted")
            for path in (root / "agent-skills").glob("*/SKILL.md"):
                text = path.read_text(encoding="utf-8")
                if f"name: {path.parent.name}" not in text or "�" in text:
                    fail(f"invalid portable skill: {path}")
                if channel == "test" and "redbeacon-test" not in text:
                    fail(f"test portable skill still targets stable: {path}")
            generated = root / "agent-skills" / (
                "redbeacon-test-generate" if channel == "test" else "redbeacon-generate"
            ) / "SKILL.md"
            generated_text = generated.read_text(encoding="utf-8")
            expected_cli = "redbeacon-test creation" if channel == "test" else "redbeacon creation"
            if expected_cli not in generated_text:
                fail(f"{channel} generate skill lost its channel-owned creation CLI")
            if channel == "test" and "redbeacon creation batch-prepare" in generated_text:
                fail("test generate skill can still start a stable creation batch")
    if set(SUPPORTED_ASSISTANTS) != {"claude-code", "codex", "openclaw", "hermes", "workbuddy"}:
        fail("assistant support matrix changed without updating the release contract")

    for source in sorted((ROOT / ".claude" / "commands").glob("redbeacon*.md")):
        stable_text = source.read_text(encoding="utf-8")
        test_text = transform_test_text(stable_text)
        if STABLE_MANIFEST_URL in stable_text and TEST_MANIFEST_URL not in test_text:
            fail(f"test skill lost the central test manifest: {source.name}")
        if "/projects/redbeacon-test/" in test_text:
            fail(f"test skill changed the shared product slug: {source.name}")
        if STABLE_MANIFEST_URL in test_text:
            fail(f"test skill still points at the stable manifest: {source.name}")
        if "installers/install.ps1" in test_text or "installers/install.sh" in test_text:
            fail(f"test skill still points at a stable installer: {source.name}")

    if os.environ.get("OSS_ACCESS_KEY_ID") or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID"):
        fail("project build environment must not inherit OSS credentials")
    if os.environ.get("CLOAKBROWSER_DOWNLOAD_URL"):
        fail("project build environment must not override the locked CloakBrowser release origin")

    print("release contracts: central Skill boundary verified")


if __name__ == "__main__":
    main()
