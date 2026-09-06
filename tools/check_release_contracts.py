#!/usr/bin/env python3
"""Fail closed when RedBeacon drifts from the central publication contract."""
from __future__ import annotations

import ast
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
FORBIDDEN_PUBLIC_AMBIENT_INPUTS = (
    "BYTESTAFF_HOME", "CLOAKBROWSER_AUTO_UPDATE", "CLOAKBROWSER_BINARY_PATH",
    "CLOAKBROWSER_CACHE_DIR", "CLOAKBROWSER_DOWNLOAD_URL", "CLOAKBROWSER_SKIP_CHECKSUM",
    "CLOAKBROWSER_VERSION", "PLAYWRIGHT_BROWSERS_PATH", "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST",
    "PLAYWRIGHT_DOWNLOAD_HOST", "REDBEACON_BUILD_CHANNEL", "REDBEACON_CHANNEL",
    "REDBEACON_CLOAKBROWSER_DIR", "REDBEACON_CLOAKBROWSER_DOWNLOAD_URL",
    "REDBEACON_CODEX_SKILL_DIR", "REDBEACON_DATA_DIR", "REDBEACON_HERMES_SKILL_DIR",
    "REDBEACON_INSTALLER_TEST_MODE", "REDBEACON_INSTALL_MANIFEST_FILE",
    "REDBEACON_INSTALL_ROOT", "REDBEACON_LOG_DIR", "REDBEACON_OPENCLAW_SKILL_DIR",
    "REDBEACON_PLAYWRIGHT_DIR", "REDBEACON_PLAYWRIGHT_DOWNLOAD_URL", "REDBEACON_RENDERER",
    "REDBEACON_SKILL_DIR", "REDBEACON_UPDATE_URL", "REDBEACON_UPDATE_WORKDIR",
    "REDBEACON_WORKBUDDY_SKILL_DIR",
)
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


def literal_assignment(path: Path, name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(node.value)
    fail(f"{path.relative_to(ROOT)} does not define literal {name}")


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
    if release_contract.get("schema") != "redbeacon-release-provenance/v3":
        fail("release contract does not use the channel-isolation-aware provenance schema")
    if release_contract.get("channel_identity_contract") != {
        "schema": "bytestaff-channel-identity-evidence/v3",
        "identity_source": "immutable-public-entrypoint",
        "ambient_override_policy": "forbidden",
        "artifact_evidence_path": "metadata/channel-identity.json",
        "hostile_environment_smoke_required": True,
        "hashed_platform_smoke_receipts_required": True,
        "frozen_packages_bound": True,
        "canonical_manifest_literal_required": True,
        "public_entrypoints_no_arguments": True,
        "opposite_channel_entrypoints_forbidden": True,
    }:
        fail("release contract channel identity policy is incomplete")
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
    for marker in (
        "assert_source_unchanged",
        'git -C "$CLI_ROOT" archive --format=tar "$CLI_COMMIT"',
        'git -C "$ROOT" archive --format=tar "$ROOT_COMMIT"',
        'python3 "$RELEASE_SOURCE/tools/smoke_unix_install_transaction.py"',
        '"$RELEASE_SOURCE/tools/prepare_release_artifacts.py"',
        '"$RELEASE_SOURCE/tools/check_release_artifacts.py"',
        'assert_source_unchanged "source snapshot"',
        'assert_source_unchanged "artifact preparation"',
        'assert_source_unchanged "final artifact handoff"',
        'BUILD_RUN_ID="redbeacon-${CHANNEL}-',
        "--contract-commit",
        "--build-run-id",
        "--cli-commit",
        "-BuildRunId $BUILD_RUN_ID",
        "-CliCommit $CLI_COMMIT",
        "frozen-bundle-smoke-macos.json",
        "frozen-bundle-smoke-windows.json",
        "installer-transaction-smoke-macos.json",
        "installer-transaction-smoke-windows.json",
        "redbeacon-local-build-evidence/v2",
        '"build_run_id": build_run_id',
    ):
        if marker not in build_script:
            fail(f"the build lost its immutable-source provenance gate: {marker}")

    receipt_writer_path = ROOT / "tools" / "write_channel_isolation_receipt.py"
    if not receipt_writer_path.is_file() or receipt_writer_path.stat().st_size <= 0:
        fail("the hashed package channel-isolation receipt writer is missing")
    receipt_writer = receipt_writer_path.read_text(encoding="utf-8")
    for marker in (
        "bytestaff-channel-isolation-smoke-receipt/v2",
        "redbeacon-frozen-bundle-smoke-report/v1",
        "redbeacon-installer-transaction-smoke-report/v1",
        "redbeacon-frozen-identity/v1",
        "redbeacon-runtime-identity-probe/v1",
        "caller-environment-preserved",
        "channel-aliases",
        "exact-process-isolation",
        "foreign-data-cache",
        "forged-update-source",
        "immutable-canonical-source",
        "opposite-channel",
        "other-channel-state-preserved",
        "canonical_manifest_url",
        "fixed_channel_argument",
        "verify_bundle_report",
        "verify_installer_report",
        "merge_evidence",
        "raw_reports",
        "runtime_identity_sha256",
        "observed_manifest_request_path",
        "single-stage-public-entrypoint",
        "secondary_shell_observed_count",
    ):
        if marker not in receipt_writer:
            fail(f"the package channel-isolation receipt lost required proof: {marker}")
    verifier_path = ROOT / "cli" / "packaging" / "verify_frozen_bundle_smoke_report.py"
    if literal_assignment(receipt_writer_path, "BUNDLE_ASSERTIONS") != literal_assignment(
        verifier_path, "ASSERTIONS"
    ):
        fail("the root evidence merger and CLI frozen smoke verifier disagree on assertions")

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
    for name in ("uninstall-core.sh", "uninstall-core.ps1"):
        text = (ROOT / "install" / name).read_text(encoding="utf-8")
        if "# BYTESTAFF_INTERNAL_CHANNEL_HELPER: explicit-only" not in text.splitlines():
            fail(f"{name} is not marked as a non-public explicit-channel helper")

    for channel, suffix in (("stable", ""), ("test", "-test")):
        for operation in ("install", "uninstall"):
            for extension in ("sh", "ps1"):
                name = f"{operation}{suffix}.{extension}"
                text = (ROOT / "install" / name).read_text(encoding="utf-8")
                lines = text.splitlines()
                if f"# BYTESTAFF_CHANNEL_IDENTITY: {channel}" not in lines:
                    fail(f"{name} is not immutably bound to {channel}")
                canonical = f"{CENTRAL_ORIGIN}/projects/redbeacon/{channel}/latest.json"
                if lines.count(f"# BYTESTAFF_CANONICAL_MANIFEST_URL: {canonical}") != 1:
                    fail(f"{name} does not declare its exact canonical manifest")
                if lines.count(f"# BYTESTAFF_FIXED_CHANNEL_ARGUMENT: {channel}") != 1:
                    fail(f"{name} does not declare its fixed channel argument")
                if "# BYTESTAFF_AMBIENT_CHANNEL_OVERRIDES: forbidden" not in lines:
                    fail(f"{name} does not forbid ambient channel overrides")
                if canonical not in text:
                    fail(f"{name} does not bind the {channel} canonical manifest")
                opposite = "test" if channel == "stable" else "stable"
                opposite_canonical = f"{CENTRAL_ORIGIN}/projects/redbeacon/{opposite}/latest.json"
                if opposite_canonical in text:
                    fail(f"{name} contains the opposite-channel canonical manifest")
                if f'"{channel}"' not in text:
                    fail(f"{name} does not pass its fixed {channel} identity explicitly")
                if "--redbeacon-" in text or "REDBEACON_INSTALLER_TEST_MODE" in text:
                    fail(f"{name} still exposes a runtime source override")
                if extension == "sh" and "accepts no arguments" not in text:
                    fail(f"{name} does not reject every shell argument")
                if extension == "ps1" and ("param()" not in text or "$args.Count -ne 0" not in text):
                    fail(f"{name} does not reject every PowerShell argument")
                if operation == "install":
                    lower_text = text.lower()
                    fixed_channel_line = (
                        f'CHANNEL="{channel}"'
                        if extension == "sh" else f'$Channel = "{channel}"'
                    )
                    fixed_manifest_line = (
                        f'MANIFEST_URL="{canonical}"'
                        if extension == "sh"
                        else f'$script:CanonicalManifestUrl = "{canonical}"'
                    )
                    if text.splitlines().count(fixed_channel_line) != 1:
                        fail(f"{name} does not assign its fixed channel exactly once")
                    if text.splitlines().count(fixed_manifest_line) != 1:
                        fail(f"{name} does not assign its fixed canonical manifest exactly once")
                    if "download node" not in lower_text:
                        fail(f"{name} does not implement node-first artifact installation")
                    launch_marker = "launch_installed_app" if extension == "sh" else "Start-InstalledApp"
                    if text.count(launch_marker) < 3:
                        fail(f"{name} does not auto-launch after fresh and healthy repeat installs")
                    if extension == "sh" and (
                        "unset TMP TEMP TMPDIR CURL_HOME XDG_CONFIG_HOME; /usr/bin/open" not in text
                    ):
                        fail(f"{name} can leak its disposable installer temp into the desktop app")
                    for assistant in ("codex", "openclaw", "hermes", "workbuddy"):
                        if assistant not in lower_text:
                            fail(f"{name} does not install the {assistant} skill adapter")
                    progress_marker = (
                        "progress and speed shown below"
                        if extension == "sh" else "MiB/s from download node"
                    )
                    if progress_marker not in text:
                        fail(f"{name} does not show live size/speed feedback during package download")
                    if "install-core" in lower_text:
                        fail(f"{name} still downloads or invokes an install-core helper")
                    if extension == "ps1":
                        if (
                            "function Remove-InstallerTemp" not in text
                            or "finally { Remove-InstallerTemp $tmp }" not in text
                        ):
                            fail(f"{name} can misreport success when Windows locks cleanup files")
                        if (
                            "powershellexe" in lower_text
                            or re.search(
                                r"(?im)^\s*(?:&\s*)?(?:['\"]?[^\s'\"]*[\\/])?"
                                r"(?:powershell|pwsh)(?:\.exe)?['\"]?(?:\s|$)",
                                lower_text,
                            )
                        ):
                            fail(f"{name} starts or locates a second PowerShell")
                    elif re.search(r"(?:^|[;&|])\s*/bin/bash(?:\s|$)", text, re.MULTILINE):
                        fail(f"{name} starts a second Bash process")
                else:
                    leaked = [
                        value for value in FORBIDDEN_PUBLIC_AMBIENT_INPUTS
                        if value in text.upper()
                    ]
                    if leaked:
                        fail(f"{name} still references ambient channel inputs: {', '.join(leaked)}")

    updater = (ROOT / "cli" / "src" / "redbeacon" / "services" / "updater.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        '_PUBLIC_INSTALL_ORIGIN = "https://bytestaff.jiomig.com"',
        'product = "redbeacon-test" if build_meta.is_test() else "redbeacon"',
        'return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]',
        'return ["/bin/sh", "-lc", f"curl -fsSL {shlex_quote(url)} | bash"]',
    ):
        if marker not in updater:
            fail("the long-lived user-facing installer command or website route changed")

    artifact_builder = (ROOT / "tools" / "prepare_release_artifacts.py").read_text(encoding="utf-8")
    if '"install-core.ps1"' in artifact_builder or '"install-core.sh"' in artifact_builder:
        fail("artifact builder still publishes the retired runtime install-core stage")
    for marker in (
        "bytestaff-channel-identity-evidence/v3",
        "bytestaff-channel-isolation-smoke-receipt/v2",
        "metadata/channel-identity.json",
        "metadata/channel-isolation-receipt.json",
        "frozen-bundle-smoke-macos.json",
        "frozen-bundle-smoke-windows.json",
        "installer-transaction-smoke-macos.json",
        "installer-transaction-smoke-windows.json",
        "build_run_id",
        "root_commit",
        "cli_commit",
        "packages",
        "uninstall-core.ps1",
        "uninstall-core.sh",
    ):
        if marker not in artifact_builder:
            fail(f"artifact builder lost the channel identity gate: {marker}")

    artifact_checker = (ROOT / "tools" / "check_release_artifacts.py").read_text(encoding="utf-8")
    for marker in (
        "bytestaff-channel-identity-evidence/v3",
        "bytestaff-channel-isolation-smoke-receipt/v2",
        "redbeacon-local-build-evidence/v2",
        "channel-isolation-receipt.json",
        "raw_reports",
        "runtime_identity_sha256",
        "observed_manifest_request_path",
        "public entrypoint exposes ambient identity",
        "only the current channel public entrypoints",
        "frozen package",
    ):
        if marker not in artifact_checker:
            fail(f"artifact checker lost the channel identity gate: {marker}")

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
        "不再询问，直接由 RedBeacon 平台接力",
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
