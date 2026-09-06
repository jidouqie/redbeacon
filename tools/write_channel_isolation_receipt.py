#!/usr/bin/env python3
"""Verify platform-owned smoke reports and merge immutable channel evidence.

This program cannot manufacture a successful smoke result from release
coordinates. It accepts only raw reports emitted by the real platform smokes,
re-verifies them against the exact package and installer bytes, copies them
with exclusive-create semantics, and derives one combined receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


RECEIPT_SCHEMA = "bytestaff-channel-isolation-smoke-receipt/v2"
INSTALLER_REPORT_SCHEMA = "redbeacon-installer-transaction-smoke-report/v1"
BUNDLE_REPORT_SCHEMA = "redbeacon-frozen-bundle-smoke-report/v1"
FROZEN_IDENTITY_SCHEMA = "redbeacon-frozen-identity/v1"
RUNTIME_PROBE_SCHEMA = "redbeacon-runtime-identity-probe/v1"
CENTRAL_ORIGIN = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
BUILD_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{15,127}$")
COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

BUNDLE_ASSERTIONS = [
    "beta-alias-probe",
    "browser-launch-probes-process-isolated",
    "bundle-executables-present",
    "caller-environment-preserved",
    "cloakbrowser-chromium-launch-verified",
    "cloakbrowser-installed",
    "desktop-smoke-ready",
    "fixed-channel-browser-cache",
    "fixed-channel-data-root",
    "foreign-token-unchanged",
    "frozen-identity-package-owned",
    "frozen-identity-sha256-matched",
    "frozen-runtime-temp-normalized",
    "hostile-path-overrides-unused",
    "opposite-channel-probe",
    "opposite-channel-runtime-untouched",
    "opposite-channel-token-unchanged",
    "playwright-chromium-launch-verified",
    "probe-output-strict-json",
    "renderer-real-png",
    "renderer-styles-readable",
    "testing-alias-probe",
]
DERIVED_INSTALLER_CASES = [
    "argument-rejection-before-network",
    "caller-environment-preserved",
    "channel-aliases",
    "command-hijack-resistance",
    "exact-process-isolation",
    "foreign-data-cache",
    "forged-update-source",
    "immutable-canonical-source",
    "opposite-channel",
    "other-channel-state-preserved",
    "transactional-rollback",
]
AMBIENT_INPUTS = [
    "BYTESTAFF_HOME",
    "CLOAKBROWSER_AUTO_UPDATE",
    "CLOAKBROWSER_BINARY_PATH",
    "CLOAKBROWSER_CACHE_DIR",
    "CLOAKBROWSER_DOWNLOAD_URL",
    "CLOAKBROWSER_SKIP_CHECKSUM",
    "CLOAKBROWSER_VERSION",
    "PLAYWRIGHT_BROWSERS_PATH",
    "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST",
    "PLAYWRIGHT_DOWNLOAD_HOST",
    "REDBEACON_BUILD_CHANNEL",
    "REDBEACON_CHANNEL",
    "REDBEACON_CLOAKBROWSER_DIR",
    "REDBEACON_CLOAKBROWSER_DOWNLOAD_URL",
    "REDBEACON_CODEX_SKILL_DIR",
    "REDBEACON_DATA_DIR",
    "REDBEACON_HERMES_SKILL_DIR",
    "REDBEACON_INSTALLER_TEST_MODE",
    "REDBEACON_INSTALL_MANIFEST_FILE",
    "REDBEACON_INSTALL_ROOT",
    "REDBEACON_LOG_DIR",
    "REDBEACON_OPENCLAW_SKILL_DIR",
    "REDBEACON_PLAYWRIGHT_DIR",
    "REDBEACON_PLAYWRIGHT_DOWNLOAD_URL",
    "REDBEACON_RENDERER",
    "REDBEACON_SKILL_DIR",
    "REDBEACON_UPDATE_URL",
    "REDBEACON_UPDATE_WORKDIR",
    "REDBEACON_WORKBUDDY_SKILL_DIR",
]
EXECUTION_HIJACK_PROBES = {
    "macos": ["caller-path-binaries", "shell-startup-files"],
    "windows": ["caller-path-binaries", "powershell-command-shadows"],
}
PROBE_CASES = ("opposite", "testing", "beta")
FORBIDDEN_RESULT_KEYS = {"passed", "status", "success"}


class EvidenceError(RuntimeError):
    """Raw evidence is incomplete, stale, or not bound to exact bytes."""


def _fail(message: str) -> None:
    raise EvidenceError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _strict_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: _fail(f"invalid JSON constant {token} in {label}"),
        )
    except EvidenceError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"{label} is not strict UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        _fail(f"{label} must contain one JSON object")
    return value


def _strict_json_file(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        info = path.lstat()
    except OSError as exc:
        _fail(f"cannot stat {label}: {exc}")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size <= 0:
        _fail(f"{label} must be a non-empty singly linked regular file")
    raw = path.read_bytes()
    return raw, _strict_json_bytes(raw, label=label)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exclusive_write(path: Path, raw: bytes, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, mode)
    except FileExistsError:
        _fail(f"refusing to overwrite existing evidence: {path}")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _reject_self_asserted_result_keys(value: Any, *, label: str) -> None:
    if isinstance(value, dict):
        overlap = FORBIDDEN_RESULT_KEYS & set(value)
        if overlap:
            _fail(f"{label} contains self-asserted result keys: {sorted(overlap)}")
        for child in value.values():
            _reject_self_asserted_result_keys(child, label=label)
    elif isinstance(value, list):
        for child in value:
            _reject_self_asserted_result_keys(child, label=label)


def _coordinates(
    payload: dict[str, Any], *, build_run_id: str, root_commit: str,
    cli_commit: str, version: str, channel: str, platform: str, bundle: bool,
) -> None:
    expected = {
        "schema": BUNDLE_REPORT_SCHEMA if bundle else INSTALLER_REPORT_SCHEMA,
        "project": "redbeacon",
        "build_run_id": build_run_id,
        "version": version,
        "platform": platform,
        "channel": channel,
        "cli_commit": cli_commit,
        "commit" if bundle else "root_commit": root_commit,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            _fail(f"{platform} {'bundle' if bundle else 'installer'} report {key} mismatch")


def _expected_names(channel: str) -> tuple[str, str]:
    return (
        ("RedBeacon_test", "redbeacon-test-cli")
        if channel == "test"
        else ("RedBeacon", "redbeacon-cli")
    )


def _expected_identity(channel: str, version: str) -> dict[str, str]:
    app_name, cli_name = _expected_names(channel)
    return {
        "schema": FROZEN_IDENTITY_SCHEMA,
        "channel": channel,
        "version": version,
        "app_name": app_name,
        "cli_name": cli_name,
    }


def verify_bundle_report(
    report: Path, *, package: Path, build_run_id: str, root_commit: str,
    cli_commit: str, version: str, channel: str, platform: str,
) -> tuple[bytes, dict[str, Any]]:
    raw, payload = _strict_json_file(report, label=f"{platform} frozen bundle report")
    expected_keys = {
        "schema", "project", "build_run_id", "commit", "cli_commit", "version",
        "platform", "channel", "package", "runtime_identity", "probes", "assertions",
    }
    if set(payload) != expected_keys:
        _fail(f"{platform} frozen bundle report fields are not exact")
    _reject_self_asserted_result_keys(payload, label=f"{platform} frozen bundle report")
    _coordinates(
        payload, build_run_id=build_run_id, root_commit=root_commit,
        cli_commit=cli_commit, version=version, channel=channel,
        platform=platform, bundle=True,
    )
    if payload.get("assertions") != BUNDLE_ASSERTIONS:
        _fail(f"{platform} frozen bundle assertion inventory is not exact")

    app_name, _ = _expected_names(channel)
    platform_tag = "mac-arm64" if platform == "macos" else "win-x64"
    expected_package_name = f"{app_name}-{platform_tag}.zip"
    if package.name != expected_package_name or not package.is_file() or package.is_symlink():
        _fail(f"{platform} frozen package path is invalid")
    package_binding = payload.get("package")
    if package_binding != {"path": expected_package_name, "sha256": _sha256_file(package)}:
        _fail(f"{platform} bundle report does not bind the exact package bytes")

    identity_member = (
        f"{app_name}.app/Contents/Resources/redbeacon-frozen-identity.json"
        if platform == "macos"
        else f"{app_name}/_internal/redbeacon-frozen-identity.json"
    )
    runtime_identity = payload.get("runtime_identity")
    if not isinstance(runtime_identity, dict) or set(runtime_identity) != {"path", "sha256"}:
        _fail(f"{platform} runtime identity binding is invalid")
    if runtime_identity.get("path") != identity_member:
        _fail(f"{platform} runtime identity package path is not exact")
    identity_sha = runtime_identity.get("sha256")
    if not isinstance(identity_sha, str) or SHA256.fullmatch(identity_sha) is None:
        _fail(f"{platform} runtime identity digest is invalid")

    try:
        with zipfile.ZipFile(package) as archive:
            raw_names = archive.namelist()
            names = [name.replace("\\", "/") for name in raw_names]
            if not names or len(names) != len(set(names)):
                _fail(f"{platform} package is empty or has duplicate paths")
            for name in names:
                if name.startswith("/") or ".." in PurePosixPath(name).parts:
                    _fail(f"{platform} package contains an unsafe path")
            name_map = dict(zip(names, raw_names, strict=True))
            identity_raw = archive.read(name_map[identity_member])
            if platform == "macos":
                alias = f"{app_name}.app/Contents/Frameworks/redbeacon-frozen-identity.json"
                identity_names = {
                    name for name in names
                    if PurePosixPath(name).name == "redbeacon-frozen-identity.json"
                }
                if identity_names != {identity_member, alias}:
                    _fail("macOS package identity inventory is not exact")
                alias_info = archive.getinfo(name_map[alias])
                if (
                    not stat.S_ISLNK(alias_info.external_attr >> 16)
                    or archive.read(alias_info) != b"../Resources/redbeacon-frozen-identity.json"
                ):
                    _fail("macOS package identity alias is invalid")
    except (KeyError, zipfile.BadZipFile) as exc:
        _fail(f"{platform} package identity cannot be read: {exc}")
    if _sha256_bytes(identity_raw) != identity_sha:
        _fail(f"{platform} packaged runtime identity digest mismatch")
    identity = _strict_json_bytes(identity_raw, label=f"{platform} packaged runtime identity")
    expected_identity = _expected_identity(channel, version)
    if identity != expected_identity:
        _fail(f"{platform} packaged runtime identity schema/channel mismatch")

    probes = payload.get("probes")
    if not isinstance(probes, list) or len(probes) != 3:
        _fail(f"{platform} bundle report must contain three runtime probes")
    poisons = {
        "opposite": "stable" if channel == "test" else "test",
        "testing": "testing",
        "beta": "beta",
    }
    for index, case in enumerate(PROBE_CASES):
        record = probes[index]
        if not isinstance(record, dict) or set(record) != {
            "case", "poison_channel", "raw_stdout", "raw_stdout_sha256", "result"
        }:
            _fail(f"{platform} bundle probe {case} fields are invalid")
        if record.get("case") != case or record.get("poison_channel") != poisons[case]:
            _fail(f"{platform} bundle probe {case} coordinates are invalid")
        raw_stdout = record.get("raw_stdout")
        if not isinstance(raw_stdout, str) or not raw_stdout:
            _fail(f"{platform} bundle probe {case} has no raw stdout")
        if record.get("raw_stdout_sha256") != _sha256_bytes(raw_stdout.encode("utf-8")):
            _fail(f"{platform} bundle probe {case} stdout digest mismatch")
        result = record.get("result")
        if _strict_json_bytes(raw_stdout.encode("utf-8"), label=f"{platform} {case} probe") != result:
            _fail(f"{platform} bundle probe {case} parsed output mismatch")
        if not isinstance(result, dict) or set(result) != {
            "schema", "mode", "identity_path", "identity_sha256", "identity"
        }:
            _fail(f"{platform} bundle probe {case} result is invalid")
        if (
            result.get("schema") != RUNTIME_PROBE_SCHEMA
            or result.get("mode") != "frozen"
            or result.get("identity_sha256") != identity_sha
            or result.get("identity") != expected_identity
        ):
            _fail(f"{platform} bundle probe {case} did not observe fixed identity")
        probed_path = result.get("identity_path")
        if not isinstance(probed_path, str) or not probed_path.replace("\\", "/").endswith(
            "/" + identity_member
        ):
            _fail(f"{platform} bundle probe {case} identity path is not package-owned")
    return raw, payload


def _observation_specs(platform: str) -> list[tuple[str, str, str, str]]:
    extension = "ps1" if platform == "windows" else "sh"
    versions = (
        {"stable": "9.9.9", "test": "9.9.9"}
        if platform == "windows"
        else {"stable": "9.9.4", "test": "8.8.1"}
    )
    result = []
    for observed_channel in ("stable", "test"):
        suffix = "-test" if observed_channel == "test" else ""
        for operation in ("install", "uninstall"):
            result.append((observed_channel, operation, f"{operation}{suffix}.{extension}", versions[observed_channel]))
    return result


def _validate_observed_installer_evidence(value: Any, *, platform: str) -> list[str]:
    expected_keys = {
        "alias_runs", "rejection_runs", "state_snapshots", "process_isolation",
        "transaction_checks", "caller_environment", "execution_hijack",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        _fail(f"{platform} observed installer evidence fields are not exact")

    coverage: set[str] = set()
    aliases = value["alias_runs"]
    expected_aliases = [
        (target, alias) for target in ("stable", "test") for alias in ("testing", "beta")
    ]
    if not isinstance(aliases, list) or len(aliases) != len(expected_aliases):
        _fail(f"{platform} alias observation inventory is incomplete")
    fixture_versions = (
        {"stable": "9.9.9", "test": "9.9.9"}
        if platform == "windows"
        else {"stable": "9.9.4", "test": "8.8.1"}
    )
    for record, (target, alias) in zip(aliases, expected_aliases, strict=True):
        expected = {
            "target_channel": target,
            "ambient_alias": alias,
            "effective_core_channel": target,
            "effective_core_marker": f"BYTESTAFF_SMOKE_CORE_CHANNEL={target}",
            "observed_installed_version": fixture_versions[target],
        }
        if record != expected:
            _fail(f"{platform} alias {target}/{alias} did not observe fixed channel identity")

    coverage.add("channel-aliases")
    rejections = value["rejection_runs"]
    if not isinstance(rejections, list) or len(rejections) < 12:
        _fail(f"{platform} rejection observations are incomplete")
    probe_counts: dict[str, int] = {}
    probe_wrappers: dict[str, set[str]] = {}
    extension = ".ps1" if platform == "windows" else ".sh"
    for record in rejections:
        rejection_fields = {"wrapper", "probe", "observed_exit_code", "diagnostic", "raw_output", "raw_output_sha256"}
        if not isinstance(record, dict) or not rejection_fields.issubset(record) or not set(record).issubset(rejection_fields | {"observed_exception"}):
            _fail(f"{platform} rejection observation fields are invalid")
        wrapper = record.get("wrapper")
        probe = record.get("probe")
        exit_code = record.get("observed_exit_code")
        diagnostic = record.get("diagnostic")
        raw_output = record.get("raw_output")
        if not isinstance(wrapper, str) or not wrapper.endswith(extension):
            _fail(f"{platform} rejection wrapper is invalid")
        if not isinstance(probe, str) or not probe:
            _fail(f"{platform} rejection probe is invalid")
        exception = record.get("observed_exception", False)
        if type(exception) is not bool or type(exit_code) is not int or (exit_code == 0 and not exception):
            _fail(f"{platform} rejection did not observe an exit failure or exception")
        if not isinstance(diagnostic, str) or not diagnostic:
            _fail(f"{platform} rejection diagnostic is invalid")
        if not isinstance(raw_output, str) or diagnostic.lower() not in raw_output.lower():
            _fail(f"{platform} rejection raw output lacks its observed diagnostic")
        if record.get("raw_output_sha256") != _sha256_bytes(raw_output.encode("utf-8")):
            _fail(f"{platform} rejection raw output digest mismatch")
        probe_counts[probe] = probe_counts.get(probe, 0) + 1
        probe_wrappers.setdefault(probe, set()).add(wrapper)
    for required, minimum in {
        "extra-arguments": 4,
        "opposite-channel-manifest": 4,
        "forged-core-url": 1,
        "tampered-core": 1,
    }.items():
        if probe_counts.get(required, 0) < minimum:
            _fail(f"{platform} rejection coverage is missing {required}")

    expected_wrappers = {spec[2] for spec in _observation_specs(platform)}
    for probe in ("extra-arguments", "opposite-channel-manifest"):
        if probe_wrappers.get(probe) != expected_wrappers:
            _fail(f"{platform} rejection coverage does not test every public wrapper: {probe}")
    coverage.update({"argument-rejection-before-network", "opposite-channel", "forged-update-source"})
    snapshots = value["state_snapshots"]
    expected_scopes = [
        "caller-controlled-paths",
        "opposite-test-state-during-stable-uninstall",
    ]
    if not isinstance(snapshots, list) or len(snapshots) != 2:
        _fail(f"{platform} state snapshot evidence is incomplete")
    for record, scope in zip(snapshots, expected_scopes, strict=True):
        if not isinstance(record, dict) or set(record) != {
            "scope", "item_count", "before_sha256", "after_sha256"
        }:
            _fail(f"{platform} state snapshot fields are invalid")
        if record.get("scope") != scope or type(record.get("item_count")) is not int or record["item_count"] <= 0:
            _fail(f"{platform} state snapshot coordinates are invalid")
        before = record.get("before_sha256")
        after = record.get("after_sha256")
        if not isinstance(before, str) or SHA256.fullmatch(before) is None or after != before:
            _fail(f"{platform} preserved-state snapshot changed")

    coverage.update({"foreign-data-cache", "other-channel-state-preserved"})
    processes = value["process_isolation"]
    if not isinstance(processes, list) or not processes:
        _fail(f"{platform} process-isolation observations are missing")
    for record in processes:
        if not isinstance(record, dict) or set(record) != {
            "target_channel", "target_process", "target_exit_code", "opposite_process",
            "opposite_process_observed_running",
        }:
            _fail(f"{platform} process-isolation observation fields are invalid")
        if record.get("target_channel") not in {"stable", "test"}:
            _fail(f"{platform} process-isolation target channel is invalid")
        if any(not isinstance(record.get(key), str) or not record[key] for key in ("target_process", "opposite_process")) or record["target_process"] == record["opposite_process"]:
            _fail(f"{platform} process-isolation process names are invalid")
        if type(record.get("target_exit_code")) is not int:
            _fail(f"{platform} target process has no observed exit code")
        if record.get("opposite_process_observed_running") is not True:
            _fail(f"{platform} opposite-channel process was not observed alive")

    coverage.add("exact-process-isolation")
    transactions = value["transaction_checks"]
    required_transactions = {
        "invalid-bundle-entry-rollback",
        "pre-replacement-rollback",
        "post-placement-rollback",
        "post-skills-rollback",
        "committed-update-database-snapshot",
    }
    if not isinstance(transactions, list) or len(transactions) != len(required_transactions) or {row.get("probe") for row in transactions if isinstance(row, dict)} != required_transactions:
        _fail(f"{platform} transaction observations are incomplete")
    for record in transactions:
        allowed = {"probe", "expected_version", "observed_version", "database_sha256", "database_before_sha256", "snapshot_sha256", "observed_exit_code", "observed_exception"}
        if not isinstance(record, dict) or not set(record).issubset(allowed) or not {
            "probe", "expected_version", "observed_version", "database_sha256", "database_before_sha256", "observed_exit_code"
        }.issubset(record):
            _fail(f"{platform} transaction observation fields are invalid")
        expected_version = ("9.9.14" if platform == "windows" else "9.9.4") if record["probe"] == "committed-update-database-snapshot" else ("9.9.9" if platform == "windows" else "9.9.1")
        if record["expected_version"] != expected_version or record["expected_version"] != record["observed_version"]:
            _fail(f"{platform} transaction did not retain/commit the expected version")
        if not isinstance(record["database_sha256"], str) or SHA256.fullmatch(record["database_sha256"]) is None:
            _fail(f"{platform} transaction database digest is invalid")
        if record["database_before_sha256"] != record["database_sha256"]:
            _fail(f"{platform} transaction changed the business database")
        exit_code = record["observed_exit_code"]
        exception = record.get("observed_exception", False)
        if type(exception) is not bool or type(exit_code) is not int or (exit_code == 0 and not exception) != (record["probe"] == "committed-update-database-snapshot"):
            _fail(f"{platform} transaction exit code does not match its probe")
        if record["probe"] == "committed-update-database-snapshot":
            if record.get("snapshot_sha256") != record["database_sha256"]:
                _fail(f"{platform} committed update snapshot did not preserve the database")

    coverage.add("transactional-rollback")
    caller = value["caller_environment"]
    if not isinstance(caller, dict) or set(caller) != {"before_sha256", "after_sha256"}:
        _fail(f"{platform} caller-environment observation fields are invalid")
    if not isinstance(caller["before_sha256"], str) or SHA256.fullmatch(caller["before_sha256"]) is None or caller["after_sha256"] != caller["before_sha256"]:
        _fail(f"{platform} caller environment changed")

    coverage.add("caller-environment-preserved")
    hijack = value["execution_hijack"]
    if not isinstance(hijack, dict) or set(hijack) != {
        "probes", "protected_before_sha256", "protected_after_sha256", "marker_observed_count"
    }:
        _fail(f"{platform} execution-hijack observations are invalid")
    before = hijack.get("protected_before_sha256")
    if (
        hijack.get("probes") != EXECUTION_HIJACK_PROBES[platform]
        or hijack.get("marker_observed_count") != 0
        or not isinstance(before, str)
        or SHA256.fullmatch(before) is None
        or hijack.get("protected_after_sha256") != before
    ):
        _fail(f"{platform} caller-controlled execution probe was not preserved")

    coverage.add("command-hijack-resistance")
    return sorted(coverage)


def verified_installer_coverage(payload: dict[str, Any], *, platform: str) -> list[str]:
    """Derive coverage only after every required observation has been checked."""
    coverage = _validate_observed_installer_evidence(payload.get("observed_evidence"), platform=platform)
    # Entrypoint bytes, requests and process inventories are verified separately
    # by verify_installer_report before this derived inventory can be published.
    return sorted([*coverage, "immutable-canonical-source"])


def verify_installer_report(
    report: Path, *, installer_source: Path, artifact_root: Path,
    build_run_id: str, root_commit: str, cli_commit: str, version: str,
    channel: str, platform: str,
) -> tuple[bytes, dict[str, Any]]:
    raw, payload = _strict_json_file(report, label=f"{platform} installer transaction report")
    expected_keys = {
        "schema", "project", "build_run_id", "root_commit", "cli_commit", "version",
        "platform", "channel", "entrypoint_observations", "observed_evidence",
    }
    if set(payload) != expected_keys:
        _fail(f"{platform} installer transaction report fields are not exact")
    _reject_self_asserted_result_keys(payload, label=f"{platform} installer transaction report")
    _coordinates(
        payload, build_run_id=build_run_id, root_commit=root_commit,
        cli_commit=cli_commit, version=version, channel=channel,
        platform=platform, bundle=False,
    )
    _validate_observed_installer_evidence(payload.get("observed_evidence"), platform=platform)
    observations = payload.get("entrypoint_observations")
    specs = _observation_specs(platform)
    if not isinstance(observations, list) or len(observations) != len(specs):
        _fail(f"{platform} entrypoint observation inventory is incomplete")
    for record, (observed_channel, operation, wrapper_name, fixture_version) in zip(observations, specs, strict=True):
        expected_keys = {
            "channel", "operation", "entrypoint_path", "entrypoint_sha256",
            "canonical_manifest_url", "manifest_request_path", "observed_request_paths",
            "effective_channel", "effective_channel_marker", "execution_model",
            "secondary_shell_observed_count", "secondary_shells", "internal_helper",
        }
        if not isinstance(record, dict) or set(record) != expected_keys:
            _fail(f"{platform} {wrapper_name} observation fields are invalid")
        entrypoint_source = installer_source / wrapper_name
        canonical = f"{CENTRAL_ORIGIN}/projects/redbeacon/{observed_channel}/latest.json"
        manifest_request = f"/projects/redbeacon/{observed_channel}/latest.json"
        expected_base = {
            "channel": observed_channel,
            "operation": operation,
            "entrypoint_path": f"install/{wrapper_name}",
            "entrypoint_sha256": _sha256_file(entrypoint_source),
            "canonical_manifest_url": canonical,
            "manifest_request_path": manifest_request,
            "effective_channel": observed_channel,
            "effective_channel_marker": f"BYTESTAFF_SMOKE_CORE_CHANNEL={observed_channel}",
        }
        for key, expected_value in expected_base.items():
            if record.get(key) != expected_value:
                _fail(f"{platform} {wrapper_name} observation is not byte/request/channel exact")
        request_paths = record.get("observed_request_paths")
        if (
            not isinstance(request_paths, list)
            or not request_paths
            or any(not isinstance(path, str) or not path.startswith("/") for path in request_paths)
            or manifest_request not in request_paths
        ):
            _fail(f"{platform} {wrapper_name} observed request inventory is invalid")
        shells = record.get("secondary_shells")
        if not isinstance(shells, list) or type(record.get("secondary_shell_observed_count")) is not int or len(shells) != record["secondary_shell_observed_count"]:
            _fail(f"{platform} {wrapper_name} shell observation inventory is invalid")
        for shell in shells:
            if not isinstance(shell, dict) or set(shell) != {"pid", "command"} or type(shell["pid"]) is not int or shell["pid"] <= 0 or not isinstance(shell["command"], str) or not shell["command"]:
                _fail(f"{platform} {wrapper_name} shell observation is invalid")
        if len({shell["pid"] for shell in shells}) != len(shells):
            _fail(f"{platform} {wrapper_name} shell observations repeat a process")
        if operation == "install":
            if (
                record.get("execution_model") != "single-stage-public-entrypoint"
                or record.get("secondary_shell_observed_count") != 0
                or record.get("internal_helper") is not None
                or any("/installers/install-core." in path for path in request_paths)
            ):
                _fail(f"{platform} {wrapper_name} did not execute as one public installer stage")
        else:
            extension = "ps1" if platform == "windows" else "sh"
            core_name = f"uninstall-core.{extension}"
            core_source = installer_source / core_name
            core_request = (
                f"/projects/redbeacon/{observed_channel}/releases/{fixture_version}/"
                f"installers/{core_name}"
            )
            expected_helper = {
                "path": f"install/{core_name}",
                "sha256": _sha256_file(core_source),
                "request_path": core_request,
            }
            if (
                record.get("execution_model") != "public-entrypoint-with-internal-helper"
                or record.get("secondary_shell_observed_count") != 1
                or record.get("internal_helper") != expected_helper
                or core_request not in request_paths
            ):
                _fail(f"{platform} {wrapper_name} uninstaller helper observation is invalid")
        if record.get("effective_channel") != observed_channel:
            _fail(f"{platform} {wrapper_name} observation is not byte/request/channel exact")
        if observed_channel == channel:
            artifact_entrypoint = artifact_root / "installers" / wrapper_name
            if _sha256_file(artifact_entrypoint) != expected_base["entrypoint_sha256"]:
                _fail(f"{platform} release entrypoint changed after installer smoke: {wrapper_name}")
            helper = record.get("internal_helper")
            if isinstance(helper, dict):
                helper_name = Path(str(helper["path"])).name
                if _sha256_file(artifact_root / "installers" / helper_name) != helper["sha256"]:
                    _fail(f"{platform} release helper changed after installer smoke: {helper_name}")
    return raw, payload


def merge_evidence(
    *, artifact_root: Path, installer_source: Path,
    bundle_reports: dict[str, Path], installer_reports: dict[str, Path],
    build_run_id: str, root_commit: str, cli_commit: str,
    version: str, channel: str, output: Path,
) -> dict[str, Any]:
    if BUILD_RUN_ID.fullmatch(build_run_id) is None:
        _fail("build_run_id has an invalid format")
    if COMMIT.fullmatch(root_commit) is None or COMMIT.fullmatch(cli_commit) is None:
        _fail("root and CLI commits must be full lowercase Git object ids")
    if SEMVER.fullmatch(version) is None or channel not in {"stable", "test"}:
        _fail("release version/channel coordinates are invalid")
    if output.exists() or output.is_symlink():
        _fail(f"refusing to overwrite existing receipt: {output}")
    if set(bundle_reports) != {"macos", "windows"} or set(installer_reports) != {"macos", "windows"}:
        _fail("both raw report kinds are required for macOS and Windows")
    resolved_reports = [path.resolve(strict=True) for path in [*bundle_reports.values(), *installer_reports.values()]]
    if len(set(resolved_reports)) != 4:
        _fail("the four raw reports must be distinct files")

    app_name, _ = _expected_names(channel)
    platform_rows: list[dict[str, Any]] = []
    target_entrypoints: list[dict[str, Any]] = []
    bundle_coverage: list[set[str]] = []
    installer_coverage: list[set[str]] = []
    for platform in ("macos", "windows"):
        platform_tag = "mac-arm64" if platform == "macos" else "win-x64"
        package = artifact_root / "packages" / f"{app_name}-{platform_tag}.zip"
        bundle_raw, bundle_payload = verify_bundle_report(
            bundle_reports[platform], package=package, build_run_id=build_run_id,
            root_commit=root_commit, cli_commit=cli_commit, version=version,
            channel=channel, platform=platform,
        )
        installer_raw, installer_payload = verify_installer_report(
            installer_reports[platform], installer_source=installer_source,
            artifact_root=artifact_root, build_run_id=build_run_id,
            root_commit=root_commit, cli_commit=cli_commit, version=version,
            channel=channel, platform=platform,
        )
        bundle_coverage.append(set(bundle_payload["assertions"]))
        installer_coverage.append(set(verified_installer_coverage(installer_payload, platform=platform)))
        report_rows = []
        for kind, report_raw in (("frozen-bundle", bundle_raw), ("installer-transaction", installer_raw)):
            relative = f"metadata/raw/{kind}-smoke-{platform}.json"
            _exclusive_write(artifact_root / relative, report_raw)
            report_rows.append({"kind": kind, "path": relative, "sha256": _sha256_bytes(report_raw)})
        package_binding = bundle_payload["package"]
        identity_binding = bundle_payload["runtime_identity"]
        platform_rows.append({
            "platform": platform,
            "package": {
                "path": f"packages/{package_binding['path']}",
                "sha256": package_binding["sha256"],
                "runtime_identity_path": identity_binding["path"],
                "runtime_identity_sha256": identity_binding["sha256"],
            },
            "raw_reports": report_rows,
        })
        for record in installer_payload["entrypoint_observations"]:
            if record["channel"] != channel:
                continue
            entrypoint_name = Path(record["entrypoint_path"]).name
            entrypoint = {
                "operation": record["operation"],
                "platform": platform,
                "path": f"installers/{entrypoint_name}",
                "sha256": record["entrypoint_sha256"],
                "canonical_manifest_url": record["canonical_manifest_url"],
                "fixed_channel_argument": channel,
                "observed_manifest_request_path": record["manifest_request_path"],
                "internal_helper_path": None,
                "internal_helper_sha256": None,
                "observed_core_request_path": None,
                "observed_effective_core_channel": record["effective_channel"],
            }
            helper = record["internal_helper"]
            if helper is not None:
                helper_name = Path(helper["path"]).name
                entrypoint["internal_helper_path"] = f"installers/{helper_name}"
                entrypoint["internal_helper_sha256"] = helper["sha256"]
                entrypoint["observed_core_request_path"] = helper["request_path"]
            target_entrypoints.append(entrypoint)

    payload = {
        "schema": RECEIPT_SCHEMA,
        "project": "redbeacon",
        "build_run_id": build_run_id,
        "root_commit": root_commit,
        "cli_commit": cli_commit,
        "version": version,
        "channel": channel,
        "platforms": platform_rows,
        "entrypoints": target_entrypoints,
        "verified_coverage": {
            "frozen_bundle": sorted(set.intersection(*bundle_coverage)),
            "installer_transaction": sorted(set.intersection(*installer_coverage)),
        },
    }
    _exclusive_write(
        output,
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--installer-source", type=Path, required=True)
    parser.add_argument("--bundle-report-macos", type=Path, required=True)
    parser.add_argument("--bundle-report-windows", type=Path, required=True)
    parser.add_argument("--installer-report-macos", type=Path, required=True)
    parser.add_argument("--installer-report-windows", type=Path, required=True)
    parser.add_argument("--build-run-id", required=True)
    parser.add_argument("--root-commit", required=True)
    parser.add_argument("--cli-commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=("stable", "test"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        merge_evidence(
            artifact_root=args.artifact_root.resolve(strict=True),
            installer_source=args.installer_source.resolve(strict=True),
            bundle_reports={"macos": args.bundle_report_macos, "windows": args.bundle_report_windows},
            installer_reports={"macos": args.installer_report_macos, "windows": args.installer_report_windows},
            build_run_id=args.build_run_id, root_commit=args.root_commit,
            cli_commit=args.cli_commit, version=args.version, channel=args.channel,
            output=args.output,
        )
    except (EvidenceError, OSError) as exc:
        raise SystemExit(f"channel evidence merge failed: {exc}") from None
    print(args.output.resolve())


if __name__ == "__main__":
    main()
