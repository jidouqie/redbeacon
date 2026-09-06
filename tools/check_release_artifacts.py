#!/usr/bin/env python3
"""Validate the clean tree handed to the global publication Skill."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tarfile
import zipfile
from pathlib import Path

from cloakbrowser.config import PLATFORM_CHROMIUM_VERSIONS
from write_channel_isolation_receipt import (
    BUNDLE_ASSERTIONS,
    DERIVED_INSTALLER_CASES,
    FROZEN_IDENTITY_SCHEMA,
    EvidenceError,
    verify_bundle_report,
    verify_installer_report,
)


CLOAKBROWSER_ARCHIVE_SUFFIXES = {
    "darwin-arm64": ".tar.gz",
    "windows-x64": ".zip",
}
SUPPORTED_ASSISTANTS = {
    "claude-code",
    "codex",
    "openclaw",
    "hermes",
    "workbuddy",
}
CHANNEL_IDENTITY_SCHEMA = "bytestaff-channel-identity-evidence/v3"
CHANNEL_SMOKE_RECEIPT_SCHEMA = "bytestaff-channel-isolation-smoke-receipt/v2"
FORBIDDEN_AMBIENT_INPUTS = [
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
]


def fail(message: str) -> None:
    raise SystemExit(f"artifact contract failed: {message}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_self_asserted_result_keys(value: object, label: str) -> None:
    if isinstance(value, dict):
        overlap = {"passed", "status", "success"} & set(value)
        if overlap:
            fail(f"{label} contains self-asserted result keys: {sorted(overlap)}")
        for child in value.values():
            reject_self_asserted_result_keys(child, label)
    elif isinstance(value, list):
        for child in value:
            reject_self_asserted_result_keys(child, label)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--channel", choices=("test", "stable"), required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir() or root.is_symlink():
        fail("artifact root must be a real directory")

    files: list[str] = []
    for path in [root, *root.rglob("*")]:
        relative = path.relative_to(root).as_posix() if path != root else ""
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            fail(f"unsafe path type: {relative}")
        if info.st_mode & 0o022:
            fail(f"group/world writable path: {relative or '.'}")
        if any(part.startswith(".") for part in Path(relative).parts):
            fail(f"hidden path in publication source: {relative}")
        if path.is_file():
            if info.st_nlink != 1 or info.st_size <= 0:
                fail(f"invalid file metadata: {relative}")
            files.append(relative)

    app_name = "RedBeacon_test" if args.channel == "test" else "RedBeacon"
    suffix = "-test" if args.channel == "test" else ""
    public_installers = {
        f"installers/install{suffix}.sh",
        f"installers/install{suffix}.ps1",
        f"installers/uninstall{suffix}.sh",
        f"installers/uninstall{suffix}.ps1",
    }
    internal_installers = {
        "installers/uninstall-core.sh",
        "installers/uninstall-core.ps1",
    }
    required = {
        f"packages/{app_name}-mac-arm64.zip",
        f"packages/{app_name}-win-x64.zip",
        *public_installers,
        *internal_installers,
        "skill/redbeacon-skill.tar.gz",
        "metadata/release-contract.json",
        "metadata/build-evidence.json",
        "metadata/channel-identity.json",
        "metadata/channel-isolation-receipt.json",
        "metadata/raw/frozen-bundle-smoke-macos.json",
        "metadata/raw/frozen-bundle-smoke-windows.json",
        "metadata/raw/installer-transaction-smoke-macos.json",
        "metadata/raw/installer-transaction-smoke-windows.json",
    }
    missing = sorted(required - set(files))
    if missing:
        fail("missing required artifacts: " + ", ".join(missing))
    installer_scripts = {
        path
        for path in files
        if path.startswith("installers/") and Path(path).suffix.lower() in {".ps1", ".sh", ".cmd", ".bat"}
    }
    expected_installers = public_installers | internal_installers
    if installer_scripts != expected_installers:
        fail(
            "release must contain only the current channel public entrypoints and internal helpers: "
            f"extra={sorted(installer_scripts - expected_installers)} "
            f"missing={sorted(expected_installers - installer_scripts)}"
        )

    playwright = [path for path in files if path.startswith("dependencies/playwright/")]
    cloak = [path for path in files if path.startswith("dependencies/cloakbrowser/")]
    if len(playwright) != 2 or len(cloak) != 2:
        fail("release must contain exactly two Playwright and two CloakBrowser platform archives")
    if not any("win64" in path for path in playwright) or not any("mac-arm64" in path for path in playwright):
        fail("Playwright dependencies do not cover Windows x64 and macOS arm64")
    try:
        expected_cloak = {
            (
                "dependencies/cloakbrowser/"
                f"chromium-v{PLATFORM_CHROMIUM_VERSIONS[tag]}/"
                f"cloakbrowser-{tag}{suffix}"
            )
            for tag, suffix in CLOAKBROWSER_ARCHIVE_SUFFIXES.items()
        }
    except KeyError as exc:
        fail(f"locked CloakBrowser package has no version for {exc.args[0]}")
    if set(cloak) != expected_cloak:
        fail(
            "CloakBrowser dependencies do not exactly match the locked per-platform versions: "
            + ", ".join(sorted(expected_cloak))
        )

    evidence = json.loads((root / "metadata" / "build-evidence.json").read_text(encoding="utf-8"))
    if set(evidence) != {
        "schema", "build_run_id", "channel", "version", "cli_commit",
        "contract_commit", "platforms", "source_archive_sha256",
        "installer_source_sha256", "uv_version", "python_version", "created_at",
    }:
        fail("build evidence fields are not exact")
    if (
        evidence.get("schema") != "redbeacon-local-build-evidence/v2"
        or evidence.get("channel") != args.channel
        or evidence.get("version") != args.version
        or evidence.get("platforms") != ["mac-arm64", "win-x64"]
        or not isinstance(evidence.get("build_run_id"), str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{15,127}", evidence["build_run_id"]) is None
    ):
        fail("build evidence coordinates are invalid")

    identity_path = root / "metadata" / "channel-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if set(identity) != {
        "schema", "project", "build_run_id", "channel", "version", "root_commit",
        "cli_commit", "identity_source", "ambient_override_policy",
        "forbidden_ambient_inputs", "entrypoints", "internal_helpers", "packages",
        "channel_isolation_receipt",
    }:
        fail("channel identity evidence fields are not exact")
    if (
        identity.get("schema") != CHANNEL_IDENTITY_SCHEMA
        or identity.get("project") != "redbeacon"
        or identity.get("channel") != args.channel
        or identity.get("version") != args.version
        or identity.get("build_run_id") != evidence.get("build_run_id")
        or identity.get("root_commit") != evidence.get("contract_commit")
        or identity.get("cli_commit") != evidence.get("cli_commit")
        or identity.get("identity_source") != "immutable-public-entrypoint"
        or identity.get("ambient_override_policy") != "forbidden"
        or identity.get("forbidden_ambient_inputs") != FORBIDDEN_AMBIENT_INPUTS
    ):
        fail("channel identity evidence does not match the build")

    expected_entrypoints = {
        ("install", "windows", f"installers/install{suffix}.ps1"),
        ("uninstall", "windows", f"installers/uninstall{suffix}.ps1"),
        ("install", "macos", f"installers/install{suffix}.sh"),
        ("uninstall", "macos", f"installers/uninstall{suffix}.sh"),
    }
    canonical = (
        "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/"
        f"projects/redbeacon/{args.channel}/latest.json"
    )
    actual_entrypoints: set[tuple[object, object, object]] = set()
    for entry in identity.get("entrypoints", []):
        expected_keys = {
            "operation", "platform", "path", "sha256", "canonical_manifest_url",
            "fixed_channel_argument", "observed_manifest_request_path",
            "internal_helper_path", "internal_helper_sha256",
            "observed_core_request_path", "observed_effective_core_channel",
        }
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            fail("channel identity public entrypoint declaration is invalid")
        operation = entry.get("operation")
        platform_name = entry.get("platform")
        relative = entry.get("path")
        extension = "ps1" if platform_name == "windows" else "sh"
        if not isinstance(relative, str) or relative not in public_installers:
            fail("channel identity declares a non-current public entrypoint")
        if entry.get("sha256") != sha256_file(root / relative):
            fail(f"channel identity SHA-256 mismatch: {relative}")
        if (
            entry.get("canonical_manifest_url") != canonical
            or entry.get("fixed_channel_argument") != args.channel
            or entry.get("observed_manifest_request_path") != f"/projects/redbeacon/{args.channel}/latest.json"
            or entry.get("observed_effective_core_channel") != args.channel
        ):
            fail(f"channel identity observation is not exact: {relative}")
        if operation == "install":
            if (
                entry.get("internal_helper_path") is not None
                or entry.get("internal_helper_sha256") is not None
                or entry.get("observed_core_request_path") is not None
            ):
                fail(f"public installer is not proven single-stage: {relative}")
        elif operation == "uninstall":
            helper = f"installers/uninstall-core.{extension}"
            helper_request_suffix = f"/installers/uninstall-core.{extension}"
            if (
                entry.get("internal_helper_path") != helper
                or entry.get("internal_helper_sha256") != sha256_file(root / helper)
                or not isinstance(entry.get("observed_core_request_path"), str)
                or not entry["observed_core_request_path"].startswith(
                    f"/projects/redbeacon/{args.channel}/releases/"
                )
                or not entry["observed_core_request_path"].endswith(helper_request_suffix)
            ):
                fail(f"public uninstaller helper observation is invalid: {relative}")
        else:
            fail(f"unknown public entrypoint operation: {relative}")
        actual_entrypoints.add((operation, platform_name, relative))
        text = (root / relative).read_text(encoding="utf-8")
        lines = text.splitlines()
        if lines.count(f"# BYTESTAFF_CHANNEL_IDENTITY: {args.channel}") != 1:
            fail(f"public entrypoint is not fixed to {args.channel}: {relative}")
        if lines.count("# BYTESTAFF_AMBIENT_CHANNEL_OVERRIDES: forbidden") != 1:
            fail(f"public entrypoint lacks the ambient-override prohibition: {relative}")
        if lines.count(f"# BYTESTAFF_CANONICAL_MANIFEST_URL: {canonical}") != 1:
            fail(f"public entrypoint lacks the exact canonical marker: {relative}")
        if lines.count(f"# BYTESTAFF_FIXED_CHANNEL_ARGUMENT: {args.channel}") != 1:
            fail(f"public entrypoint lacks the exact fixed-channel marker: {relative}")
        opposite = "test" if args.channel == "stable" else "stable"
        opposite_canonical = (
            "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com/"
            f"projects/redbeacon/{opposite}/latest.json"
        )
        if opposite_canonical in text:
            fail(f"public entrypoint contains the opposite-channel canonical: {relative}")
        if operation == "install":
            lower_text = text.lower()
            fixed_channel_line = (
                f'CHANNEL="{args.channel}"'
                if platform_name == "macos" else f'$Channel = "{args.channel}"'
            )
            fixed_manifest_line = (
                f'MANIFEST_URL="{canonical}"'
                if platform_name == "macos"
                else f'$script:CanonicalManifestUrl = "{canonical}"'
            )
            if lines.count(fixed_channel_line) != 1 or lines.count(fixed_manifest_line) != 1:
                fail(f"public installer fixed identity assignment is not exact: {relative}")
            if "install-core" in lower_text:
                fail(f"public installer still delegates to install-core: {relative}")
            if platform_name == "windows" and (
                "powershellexe" in lower_text
                or re.search(
                    r"(?im)^\s*(?:&\s*)?(?:['\"]?[^\s'\"]*[\\/])?"
                    r"(?:powershell|pwsh)(?:\.exe)?['\"]?(?:\s|$)",
                    lower_text,
                )
            ):
                fail(f"public Windows installer starts or locates a second PowerShell: {relative}")
            if platform_name == "macos" and re.search(r"(?:^|[;&|])\s*/bin/bash(?:\s|$)", text, re.MULTILINE):
                fail(f"public macOS installer starts a second Bash process: {relative}")
        else:
            leaked = [name for name in FORBIDDEN_AMBIENT_INPUTS if name in text.upper()]
            if leaked:
                fail(f"public uninstaller exposes ambient identity: {relative}")
        if "--redbeacon-" in text:
            fail(f"public entrypoint exposes ambient identity: {relative}")
    if actual_entrypoints != expected_entrypoints:
        fail("channel identity public entrypoint inventory is incomplete")

    expected_helpers = {relative: sha256_file(root / relative) for relative in internal_installers}
    actual_helpers: dict[str, str] = {}
    for helper in identity.get("internal_helpers", []):
        if not isinstance(helper, dict) or set(helper) != {"path", "sha256"}:
            fail("channel identity internal helper declaration is invalid")
        relative = helper.get("path")
        digest = helper.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            fail("channel identity internal helper binding is invalid")
        actual_helpers[relative] = digest
        if "# BYTESTAFF_INTERNAL_CHANNEL_HELPER: explicit-only" not in (root / relative).read_text(encoding="utf-8").splitlines():
            fail(f"installer helper is not marked internal-only: {relative}")
    if actual_helpers != expected_helpers:
        fail("channel identity internal helper inventory or SHA-256 is invalid")

    expected_package_paths = {
        "macos": f"packages/{app_name}-mac-arm64.zip",
        "windows": f"packages/{app_name}-win-x64.zip",
    }
    packages_by_platform: dict[str, dict[str, object]] = {}
    expected_runtime_identity = {
        "schema": FROZEN_IDENTITY_SCHEMA,
        "channel": args.channel,
        "version": args.version,
        "app_name": app_name,
        "cli_name": "redbeacon-test-cli" if args.channel == "test" else "redbeacon-cli",
    }
    for package in identity.get("packages", []):
        if not isinstance(package, dict) or set(package) != {
            "platform", "path", "sha256", "fixed_channel",
            "runtime_identity_path", "runtime_identity_sha256",
        }:
            fail("channel identity frozen package declaration is invalid")
        platform_name = package.get("platform")
        relative = package.get("path")
        if platform_name not in expected_package_paths or platform_name in packages_by_platform:
            fail("channel identity frozen package platform is invalid or duplicated")
        if relative != expected_package_paths[platform_name] or package.get("fixed_channel") != args.channel:
            fail("channel identity frozen package coordinate is invalid")
        package_path = root / str(relative)
        if package.get("sha256") != sha256_file(package_path):
            fail(f"channel identity frozen package SHA-256 mismatch: {relative}")
        member = package.get("runtime_identity_path")
        if not isinstance(member, str):
            fail("frozen package runtime identity path is invalid")
        try:
            with zipfile.ZipFile(package_path) as archive:
                raw_names = archive.namelist()
                normalized_to_raw = {
                    name.replace("\\", "/"): name for name in raw_names
                }
                if len(normalized_to_raw) != len(raw_names):
                    fail("frozen package contains duplicate normalized paths")
                identity_raw = archive.read(normalized_to_raw[member])
        except (KeyError, zipfile.BadZipFile) as exc:
            fail(f"frozen package runtime identity cannot be read: {exc}")
        if hashlib.sha256(identity_raw).hexdigest() != package.get("runtime_identity_sha256"):
            fail("frozen package runtime identity SHA-256 mismatch")
        if json.loads(identity_raw.decode("utf-8")) != expected_runtime_identity:
            fail("frozen package runtime identity does not match the release channel")
        packages_by_platform[str(platform_name)] = package
    if set(packages_by_platform) != {"macos", "windows"}:
        fail("channel identity does not bind both frozen application packages")

    descriptor = identity.get("channel_isolation_receipt")
    if not isinstance(descriptor, dict) or set(descriptor) != {"path", "sha256", "raw_reports"}:
        fail("channel isolation receipt descriptor is invalid")
    receipt_relative = "metadata/channel-isolation-receipt.json"
    if descriptor.get("path") != receipt_relative or descriptor.get("sha256") != sha256_file(root / receipt_relative):
        fail("channel isolation receipt binding is invalid")
    raw_descriptors = descriptor.get("raw_reports")
    if not isinstance(raw_descriptors, list) or len(raw_descriptors) != 4:
        fail("channel isolation evidence must bind four raw reports")
    expected_raw = {
        (platform_name, kind, f"metadata/raw/{kind}-smoke-{platform_name}.json")
        for platform_name in ("macos", "windows")
        for kind in ("frozen-bundle", "installer-transaction")
    }
    actual_raw: set[tuple[object, object, object]] = set()
    raw_by_platform: dict[str, list[dict[str, str]]] = {"macos": [], "windows": []}
    for item in raw_descriptors:
        if not isinstance(item, dict) or set(item) != {"platform", "kind", "path", "sha256"}:
            fail("raw smoke report descriptor is invalid")
        platform_name, kind, relative = item.get("platform"), item.get("kind"), item.get("path")
        actual_raw.add((platform_name, kind, relative))
        if not isinstance(relative, str) or item.get("sha256") != sha256_file(root / relative):
            fail("raw smoke report SHA-256 binding is invalid")
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
        reject_self_asserted_result_keys(payload, relative)
        if (
            payload.get("project") != "redbeacon"
            or payload.get("build_run_id") != evidence.get("build_run_id")
            or payload.get("version") != args.version
            or payload.get("channel") != args.channel
            or payload.get("platform") != platform_name
            or payload.get("cli_commit") != evidence.get("cli_commit")
            or payload.get("commit", payload.get("root_commit")) != evidence.get("contract_commit")
        ):
            fail(f"raw smoke report coordinates are invalid: {relative}")
        coordinates = dict(
            build_run_id=evidence["build_run_id"], root_commit=evidence["contract_commit"],
            cli_commit=evidence["cli_commit"], version=args.version,
            channel=args.channel, platform=str(platform_name),
        )
        try:
            if kind == "installer-transaction":
                verify_installer_report(
                    root / relative, installer_source=Path(__file__).resolve().parent.parent / "install",
                    artifact_root=root, **coordinates,
                )
            elif kind == "frozen-bundle":
                verify_bundle_report(
                    root / relative, package=root / expected_package_paths[str(platform_name)],
                    **coordinates,
                )
        except (EvidenceError, OSError) as exc:
            fail(f"raw smoke report verification failed: {relative}: {exc}")
        raw_by_platform[str(platform_name)].append({
            "kind": str(kind), "path": relative, "sha256": str(item["sha256"]),
        })
    if actual_raw != expected_raw:
        fail("raw smoke report inventory is incomplete")

    receipt = json.loads((root / receipt_relative).read_text(encoding="utf-8"))
    reject_self_asserted_result_keys(receipt, receipt_relative)
    if set(receipt) != {
        "schema", "project", "build_run_id", "root_commit", "cli_commit", "version",
        "channel", "platforms", "entrypoints", "verified_coverage",
    }:
        fail("combined channel isolation receipt fields are not exact")
    if (
        receipt.get("schema") != CHANNEL_SMOKE_RECEIPT_SCHEMA
        or receipt.get("project") != "redbeacon"
        or receipt.get("build_run_id") != evidence.get("build_run_id")
        or receipt.get("root_commit") != evidence.get("contract_commit")
        or receipt.get("cli_commit") != evidence.get("cli_commit")
        or receipt.get("version") != args.version
        or receipt.get("channel") != args.channel
        or receipt.get("entrypoints") != identity.get("entrypoints")
        or receipt.get("verified_coverage") != {
            "frozen_bundle": BUNDLE_ASSERTIONS,
            "installer_transaction": DERIVED_INSTALLER_CASES,
        }
    ):
        fail("combined channel isolation receipt does not match the build")
    expected_platform_rows = []
    for platform_name in ("macos", "windows"):
        package = packages_by_platform[platform_name]
        expected_platform_rows.append({
            "platform": platform_name,
            "package": {
                key: package[key]
                for key in ("path", "sha256", "runtime_identity_path", "runtime_identity_sha256")
            },
            "raw_reports": raw_by_platform[platform_name],
        })
    if receipt.get("platforms") != expected_platform_rows:
        fail("combined channel isolation receipt platform bindings are invalid")
    with tarfile.open(root / "skill" / "redbeacon-skill.tar.gz", "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            fail("skill bundle contains duplicate paths")
        non_files = [member.name for member in members if not member.isfile()]
        if non_files:
            fail("skill bundle contains non-file members: " + ", ".join(non_files))
        if "redbeacon-skill-manifest.json" not in names or not any(name.endswith("redbeacon.md") or name.endswith("redbeacon-test.md") for name in names):
            fail("skill bundle is incomplete")
        unsafe = [name for name in names if name.startswith("/") or ".." in Path(name).parts]
        if unsafe:
            fail("skill bundle contains unsafe paths: " + ", ".join(unsafe))
        metadata_file = archive.extractfile("redbeacon-skill-manifest.json")
        if metadata_file is None:
            fail("skill bundle manifest cannot be read")
        try:
            metadata = json.loads(metadata_file.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail(f"skill bundle manifest is invalid: {exc}")
        if (
            metadata.get("schema") != 2
            or metadata.get("channel") != args.channel
            or metadata.get("version") != args.version
            or set(metadata.get("assistants", [])) != SUPPORTED_ASSISTANTS
        ):
            fail("skill bundle does not declare the complete assistant support matrix")
        commands = sorted(
            name for name in names
            if name.startswith(".claude/commands/") and name.endswith(".md")
        )
        portable = sorted(
            name for name in names
            if name.startswith("agent-skills/") and name.endswith("/SKILL.md")
        )
        command_stems = {Path(name).stem for name in commands}
        portable_stems = {Path(name).parent.name for name in portable}
        if not commands or command_stems != portable_stems:
            fail("Claude commands and portable Agent Skills do not match")
        if args.channel == "test":
            wrong_stems = sorted(stem for stem in command_stems if not stem.startswith("redbeacon-test"))
        else:
            wrong_stems = sorted(
                stem for stem in command_stems
                if not stem.startswith("redbeacon") or stem.startswith("redbeacon-test")
            )
        if wrong_stems:
            fail("skill bundle contains opposite-channel skill stems: " + ", ".join(wrong_stems))
        if sorted(metadata.get("portable_skills", [])) != portable:
            fail("skill manifest portable skill inventory does not match the archive")
        for name in portable:
            skill_file = archive.extractfile(name)
            if skill_file is None:
                fail(f"portable skill cannot be read: {name}")
            try:
                text = skill_file.read().decode("utf-8")
            except UnicodeDecodeError as exc:
                fail(f"portable skill is not UTF-8: {name}: {exc}")
            stem = Path(name).parent.name
            if not text.startswith("---\n") or f"\nname: {stem}\n" not in text or "\ndescription:" not in text:
                fail(f"portable skill frontmatter is invalid: {name}")
            if "�" in text:
                fail(f"portable skill contains replacement characters: {name}")

    print(f"release artifacts: {len(files)} files verified")


if __name__ == "__main__":
    main()
