#!/usr/bin/env python3
"""Offline smoke for staged dependency preparation and installer rollback."""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_RELEASE_ORIGIN = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
INSTALLER_REPORT_SCHEMA = "redbeacon-installer-transaction-smoke-report/v1"
AMBIENT_INPUTS = [
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


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    request_paths: list[str] = []
    request_lock = threading.Lock()

    def log_message(self, _format: str, *_args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        with self.request_lock:
            self.request_paths.append(urlsplit(self.path).path)
        super().do_GET()


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _channel_spec(channel: str) -> dict[str, str]:
    if channel == "stable":
        return {
            "app_name": "RedBeacon",
            "cli_name": "redbeacon-cli",
            "share_name": "redbeacon",
            "skill_stem": "redbeacon",
            "runtime_root": ".redbeacon",
            "skill_dir": ".claude/commands",
        }
    if channel == "test":
        return {
            "app_name": "RedBeacon_test",
            "cli_name": "redbeacon-test-cli",
            "share_name": "redbeacon-test",
            "skill_stem": "redbeacon-test",
            "runtime_root": ".redbeacon_test",
            "skill_dir": ".claude/commands-redbeacon-test",
        }
    raise AssertionError(f"unsupported smoke channel: {channel}")


def _platform_layout(channel: str) -> tuple[str, Path, str]:
    app_name = _channel_spec(channel)["app_name"]
    if platform.system() == "Darwin":
        plat = "mac-arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "mac-x64"
        return plat, Path(f"{app_name}.app/Contents/MacOS"), f"{app_name}.app"
    return "linux-x64", Path(app_name), app_name


def _build_bundle(
    oss: Path,
    version: str,
    base_url: str,
    failure: str = "",
    *,
    channel: str = "stable",
) -> None:
    spec = _channel_spec(channel)
    app_name = spec["app_name"]
    cli_name = spec["cli_name"]
    skill_stem = spec["skill_stem"]
    runtime_root = spec["runtime_root"]
    plat, executable_dir, archive_root = _platform_layout(channel)
    build = oss.parent / f"build-{channel}-{version}"
    shutil.rmtree(build, ignore_errors=True)
    cli = build / executable_dir / cli_name
    installed_markers = (
        f"*/Applications/{app_name}.app/*|"
        f"*/.local/share/{spec['share_name']}/{app_name}/*"
    )
    setup_logic = ""
    if failure == "stage":
        setup_logic = "exit 31"
    elif failure == "placed":
        setup_logic = f'case "$0" in {installed_markers}) exit 32 ;; esac'
    desktop_logic = ""
    if failure == "post_skills":
        desktop_logic = f'case "$0" in {installed_markers}) exit 33 ;; esac'
    _write_executable(
        cli,
        "#!/bin/sh\n"
        f"VERSION='{version}'\n"
        f"EXPECTED_CHANNEL='{channel}'\n"
        f"EXPECTED_DATA=\"$HOME/{runtime_root}/data\"\n"
        f"EXPECTED_PW=\"$HOME/{runtime_root}/browser/ms-playwright\"\n"
        f"EXPECTED_CB=\"$HOME/{runtime_root}/browser/cloakbrowser\"\n"
        'if [ -n "${REDBEACON_EXPECTED_INSTALL_CHANNEL:-}" ]; then\n'
        '  [ "${REDBEACON_CHANNEL:-}" = "$EXPECTED_CHANNEL" ] || exit 42\n'
        '  [ "${REDBEACON_BUILD_CHANNEL:-}" = "$EXPECTED_CHANNEL" ] || exit 43\n'
        '  [ -z "${REDBEACON_UPDATE_URL:-}" ] || exit 44\n'
        "fi\n"
        "case \"${1:-}\" in\n"
        f"  --version) echo \"{skill_stem} $VERSION\" ;;\n"
        f"  setup) {setup_logic or ':'}; "
        '[ "$REDBEACON_DATA_DIR" = "$EXPECTED_DATA" ] || exit 34; '
        '[ "$PLAYWRIGHT_BROWSERS_PATH" = "$EXPECTED_PW" ] || exit 35; '
        '[ "$CLOAKBROWSER_CACHE_DIR" = "$EXPECTED_CB" ] || exit 36; '
        '[ "${2:-}" = "--manifest-file" ] || exit 37; '
        '[ -f "${3:-}" ] || exit 38; '
        "echo '{\"ok\":true}' ;;\n"
        "  config) : ;;\n"
        f"  *) if [ \"${{REDBEACON_DESKTOP_SMOKE:-}}\" = 1 ]; then {desktop_logic or ':'}; "
        "echo 'RedBeacon desktop smoke ok'; fi ;;\n"
        "esac\n",
    )
    _write_executable(build / executable_dir / app_name, "#!/bin/sh\nexit 0\n")
    if platform.system() == "Darwin":
        bundle_entry = "RedBeaconRenderer" if failure == "bundle_entry" else app_name
        (build / f"{app_name}.app/Contents/Info.plist").write_text(
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
            "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
            "<plist version=\"1.0\"><dict>"
            f"<key>CFBundleExecutable</key><string>{bundle_entry}</string>"
            "</dict></plist>\n",
            encoding="utf-8",
        )
    _write_executable(
        build / executable_dir / "RedBeaconRenderer",
        "#!/bin/sh\n"
        f"EXPECTED_CHANNEL='{channel}'\n"
        'if [ -n "${REDBEACON_EXPECTED_INSTALL_CHANNEL:-}" ]; then\n'
        '  [ "${REDBEACON_CHANNEL:-}" = "$EXPECTED_CHANNEL" ] || exit 45\n'
        '  [ "${REDBEACON_BUILD_CHANNEL:-}" = "$EXPECTED_CHANNEL" ] || exit 46\n'
        '  [ -z "${REDBEACON_UPDATE_URL:-}" ] || exit 47\n'
        "fi\n"
        'out=""\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--output-dir" ]; then shift; out="$1"; fi\n'
        '  shift\n'
        'done\n'
        '[ -n "$out" ] || exit 41\n'
        'mkdir -p "$out"\n'
        "printf 'png' > \"$out/cover.png\"\n"
        "printf 'png' > \"$out/card_1.png\"\n",
    )

    release = oss / "projects" / "redbeacon" / channel / "releases" / version
    release_url = f"{base_url}/projects/redbeacon/{channel}/releases/{version}"
    package_dir = release / "packages"
    package_dir.mkdir(parents=True, exist_ok=True)
    bundle = package_dir / f"{app_name}-{plat}.zip"
    subprocess.run(
        ["zip", "-qry", str(bundle), archive_root], cwd=build, check=True
    )
    sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    skill_root = oss.parent / f"skill-{channel}-{version}"
    shutil.rmtree(skill_root, ignore_errors=True)
    command_dir = skill_root / ".claude" / "commands"
    command_dir.mkdir(parents=True)
    (command_dir / f"{skill_stem}.md").write_text(
        f"---\ndescription: transaction smoke {version}\n---\n# {app_name} {version}\n",
        encoding="utf-8",
    )
    portable = skill_root / "agent-skills" / skill_stem / "SKILL.md"
    portable.parent.mkdir(parents=True)
    portable.write_text(
        f"---\nname: {skill_stem}\ndescription: \"transaction smoke {version}\"\n---\n\n# {app_name} {version}\n",
        encoding="utf-8",
    )
    (skill_root / "redbeacon-skill-manifest.json").write_text(
        json.dumps({
            "schema": 2,
            "channel": channel,
            "version": version,
            "commit": "smoke",
            "assistants": ["claude-code", "codex", "openclaw", "hermes", "workbuddy"],
            "portable_skills": [f"agent-skills/{skill_stem}/SKILL.md"],
        }),
        encoding="utf-8",
    )
    skill_dir = release / "skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_bundle = skill_dir / "redbeacon-skill.tar.gz"
    with tarfile.open(skill_bundle, "w:gz") as tar:
        tar.add(skill_root / ".claude", arcname=".claude")
        tar.add(skill_root / "agent-skills", arcname="agent-skills")
        tar.add(skill_root / "redbeacon-skill-manifest.json", arcname="redbeacon-skill-manifest.json")
    skill_sha = hashlib.sha256(skill_bundle.read_bytes()).hexdigest()

    artifacts = [
        {
            "path": f"packages/{app_name}-{plat}.zip",
            "size": bundle.stat().st_size,
            "sha256": sha,
            "url": f"{release_url}/packages/{app_name}-{plat}.zip",
            "download_urls": [f"{release_url}/packages/{app_name}-{plat}.zip"],
        },
        {
            "path": "skill/redbeacon-skill.tar.gz",
            "size": skill_bundle.stat().st_size,
            "sha256": skill_sha,
            "url": f"{release_url}/skill/redbeacon-skill.tar.gz",
            "download_urls": [f"{release_url}/skill/redbeacon-skill.tar.gz"],
        },
    ]
    installer_dir = release / "installers"
    installer_dir.mkdir(parents=True, exist_ok=True)
    for core_name in ("install-core.sh", "uninstall-core.sh"):
        core = installer_dir / core_name
        shutil.copy2(ROOT / "install" / core_name, core)
        core_sha = hashlib.sha256(core.read_bytes()).hexdigest()
        core_url = f"{release_url}/installers/{core_name}"
        artifacts.append({
            "path": f"installers/{core_name}",
            "size": core.stat().st_size,
            "sha256": core_sha,
            "url": core_url,
            "download_urls": [core_url],
        })

    manifest = oss / "projects" / "redbeacon" / channel / "latest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({
            "schema": 1,
            "project": "redbeacon",
            "channel": channel,
            "version": version,
            "created_at": "2026-07-17T00:00:00Z",
            "commit": "installer-smoke",
            "artifacts": artifacts,
        }, separators=(",", ":")),
        encoding="utf-8",
    )


def _manifest_url(base_url: str, channel: str) -> str:
    return f"{base_url}/projects/redbeacon/{channel}/latest.json"


def _hostile_execution_environment(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home / "caller-home-poison"),
        "PATH": f"{home / 'hostile-bin'}:/caller/path/must/not/run",
        "TEMP": str(home / "caller-temp-poison"),
        "TMP": str(home / "caller-tmp-poison"),
        "TMPDIR": str(home / "caller-tmpdir-poison"),
        "BASH_ENV": str(home / "caller-shell-poison/bash-env.sh"),
        "ENV": str(home / "caller-shell-poison/sh-env.sh"),
        "TAR_OPTIONS": "--checkpoint=1",
        "UNZIP": "-qq",
        "UNZIPOPT": "-qq",
        "DYLD_INSERT_LIBRARIES": str(home / "caller-dyld-poison.dylib"),
        "DYLD_LIBRARY_PATH": str(home / "caller-dyld-library-poison"),
        "LD_PRELOAD": str(home / "caller-ld-poison.so"),
        "LD_LIBRARY_PATH": str(home / "caller-ld-library-poison"),
        "PYTHONHOME": str(home / "caller-python-home-poison"),
        "PYTHONPATH": str(home / "caller-python-path-poison"),
        "CURL_CA_BUNDLE": str(home / "caller-ca-poison.pem"),
        "SSL_CERT_FILE": str(home / "caller-cert-poison.pem"),
    }


def _seed_execution_hijacks(home: Path) -> tuple[Path, list[Path]]:
    marker = home / "execution-hijack-ran.txt"
    hostile_bin = home / "hostile-bin"
    tools = (
        "awk", "bash", "curl", "find", "grep", "head", "mktemp", "osascript",
        "python3", "rm", "sed", "shasum", "tail", "tar", "tr", "unzip", "wc",
    )
    payload = (
        "#!/bin/sh\n"
        f"printf 'hijacked:%s\\n' \"$0\" >> {shlex.quote(str(marker))}\n"
        "exit 97\n"
    )
    for name in tools:
        _write_executable(hostile_bin / name, payload)
    shell_poison = home / "caller-shell-poison"
    for name in ("bash-env.sh", "sh-env.sh"):
        _write_executable(
            shell_poison / name,
            f"printf 'startup-hijack:%s\\n' \"$0\" >> {shlex.quote(str(marker))}\n",
        )
    protected = [
        home / "caller-home-poison",
        home / "caller-temp-poison",
        home / "caller-tmp-poison",
        home / "caller-tmpdir-poison",
    ]
    for directory in protected:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "must-survive.txt").write_text(directory.name, encoding="utf-8")
    return marker, protected


def _snapshot_directories(directories: list[Path]) -> dict[Path, tuple[tuple[str, bytes], ...]]:
    snapshots: dict[Path, tuple[tuple[str, bytes], ...]] = {}
    for directory in directories:
        rows: list[tuple[str, bytes]] = []
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                rows.append((path.relative_to(directory).as_posix(), path.read_bytes()))
            elif path.is_dir():
                rows.append((path.relative_to(directory).as_posix() + "/", b""))
        snapshots[directory] = tuple(rows)
    return snapshots


def _assert_directory_snapshots(
    snapshots: dict[Path, tuple[tuple[str, bytes], ...]]
) -> None:
    current = _snapshot_directories(list(snapshots))
    assert current == snapshots, "caller-owned HOME/TEMP/TMP/TMPDIR content changed"


def _write_smoke_wrappers(directory: Path, base_url: str, trusted_home: Path) -> None:
    """Create non-published wrapper copies with a loopback origin and smoke mode."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("install.sh", "install-test.sh", "uninstall.sh", "uninstall-test.sh"):
        source = (ROOT / "install" / name).read_text(encoding="utf-8")
        if PUBLIC_RELEASE_ORIGIN not in source:
            raise AssertionError(f"{name} lost its immutable public release origin")
        patched = source.replace(PUBLIC_RELEASE_ORIGIN, base_url)
        trusted_home_source = 'TRUSTED_HOME="$(resolve_trusted_home)"'
        trusted_home_smoke = f"TRUSTED_HOME={shlex.quote(str(trusted_home))}"
        if patched.count(trusted_home_source) != 1:
            raise AssertionError(f"{name} lost its fixed macOS trusted-home expression")
        patched = patched.replace(trusted_home_source, trusted_home_smoke)
        if name.startswith("install"):
            old = '"$CENTRAL_ORIGIN" "production"'
            new = '"$CENTRAL_ORIGIN" "smoke"'
        else:
            old = '"production"'
            new = '"smoke"'
        if patched.count(old) != 1:
            raise AssertionError(f"{name} does not expose one fixed production execution mode")
        patched = patched.replace(old, new)
        _write_executable(directory / name, patched)


@contextmanager
def _temporary_bytes(path: Path, body: bytes):
    original = path.read_bytes()
    path.write_bytes(body)
    try:
        yield
    finally:
        path.write_bytes(original)


def _installed_cli(home: Path, channel: str = "stable") -> Path:
    spec = _channel_spec(channel)
    app_name = spec["app_name"]
    cli_name = spec["cli_name"]
    if platform.system() == "Darwin":
        return home / f"Applications/{app_name}.app/Contents/MacOS/{cli_name}"
    return home / f".local/share/{spec['share_name']}/{app_name}/{cli_name}"


def _version(cli: Path) -> str:
    return subprocess.check_output([str(cli), "--version"], text=True).strip().split()[-1]


def _run_installer(
    home: Path,
    base_url: str,
    wrapper_dir: Path,
    *,
    channel: str = "stable",
    expect_ok: bool,
    force: bool = True,
    ambient_channel: str | None = None,
) -> subprocess.CompletedProcess:
    spec = _channel_spec(channel)
    opposite = "test" if channel == "stable" else "stable"
    wrapper = "install.sh" if channel == "stable" else "install-test.sh"
    env = os.environ.copy()
    env.update(_hostile_execution_environment(home))
    poisoned_channel = ambient_channel or opposite
    env.update({
        # Deliberately hostile inherited product identity. The public wrapper
        # must ignore all three values and the core must replace them before it
        # launches any bundled executable.
        "REDBEACON_CHANNEL": poisoned_channel,
        "REDBEACON_BUILD_CHANNEL": poisoned_channel,
        "REDBEACON_UPDATE_URL": _manifest_url(base_url, opposite),
        "REDBEACON_EXPECTED_INSTALL_CHANNEL": channel,
        "REDBEACON_INSTALLER_TEST_MODE": "hostile-must-be-ignored",
        "REDBEACON_NO_PAUSE": "1",
        "REDBEACON_SKILL_DIR": str(home / "foreign-claude-skills"),
        "REDBEACON_CODEX_SKILL_DIR": str(home / "foreign-codex-skills"),
        "REDBEACON_OPENCLAW_SKILL_DIR": str(home / "foreign-openclaw-skills"),
        "REDBEACON_HERMES_SKILL_DIR": str(home / "foreign-hermes-skills"),
        "REDBEACON_WORKBUDDY_SKILL_DIR": str(home / "foreign-workbuddy-skills"),
        "REDBEACON_UPDATE_WORKDIR": str(home / "foreign-update-workdir"),
        "BYTESTAFF_HOME": str(home / "foreign-token-home"),
        # Deliberately hostile inherited locations: the installer must ignore
        # these and prepare the canonical entrypoint-owned runtime directories.
        "REDBEACON_DATA_DIR": str(home / "foreign-data"),
        "REDBEACON_PLAYWRIGHT_DIR": str(home / "foreign-playwright"),
        "REDBEACON_CLOAKBROWSER_DIR": str(home / "foreign-cloak"),
        "PLAYWRIGHT_BROWSERS_PATH": str(home / "foreign-system-playwright"),
        "CLOAKBROWSER_CACHE_DIR": str(home / "foreign-system-cloak"),
    })
    if force:
        env["REDBEACON_FORCE_INSTALL"] = "1"
    else:
        env.pop("REDBEACON_FORCE_INSTALL", None)
    result = subprocess.run(
        [
            "/bin/sh",
            str(wrapper_dir / wrapper),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if expect_ok and result.returncode != 0:
        raise AssertionError(result.stdout)
    if not expect_ok and result.returncode == 0:
        raise AssertionError(f"installer unexpectedly succeeded:\n{result.stdout}")
    return result


def _run_uninstaller(
    home: Path, base_url: str, wrapper_dir: Path, *, channel: str = "stable"
) -> subprocess.CompletedProcess:
    spec = _channel_spec(channel)
    opposite = "test" if channel == "stable" else "stable"
    wrapper = "uninstall.sh" if channel == "stable" else "uninstall-test.sh"
    env = os.environ.copy()
    env.update(_hostile_execution_environment(home))
    env.update({
        "REDBEACON_CHANNEL": opposite,
        "REDBEACON_BUILD_CHANNEL": opposite,
        "REDBEACON_UPDATE_URL": _manifest_url(base_url, opposite),
        "REDBEACON_INSTALLER_TEST_MODE": "hostile-must-be-ignored",
        "REDBEACON_PURGE": "0",
        "REDBEACON_SKILL_DIR": str(home / "foreign-claude-skills"),
        "REDBEACON_CODEX_SKILL_DIR": str(home / "foreign-codex-skills"),
        "REDBEACON_OPENCLAW_SKILL_DIR": str(home / "foreign-openclaw-skills"),
        "REDBEACON_HERMES_SKILL_DIR": str(home / "foreign-hermes-skills"),
        "REDBEACON_WORKBUDDY_SKILL_DIR": str(home / "foreign-workbuddy-skills"),
        "REDBEACON_UPDATE_WORKDIR": str(home / "foreign-update-workdir"),
        "BYTESTAFF_HOME": str(home / "foreign-token-home"),
    })
    return subprocess.run(
        [
            "/bin/sh",
            str(wrapper_dir / wrapper),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


def _run_wrapper(
    home: Path, base_url: str, wrapper_dir: Path, wrapper: str
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(_hostile_execution_environment(home))
    env.update({
        "REDBEACON_INSTALLER_TEST_MODE": "hostile-must-be-ignored",
        "REDBEACON_CHANNEL": "ambient-poison",
        "REDBEACON_BUILD_CHANNEL": "ambient-poison",
        "REDBEACON_UPDATE_URL": _manifest_url(base_url, "test"),
        "REDBEACON_UPDATE_WORKDIR": str(home / "foreign-update-workdir"),
        "REDBEACON_SKILL_DIR": str(home / "foreign-claude-skills"),
    })
    return subprocess.run(
        ["/bin/sh", str(wrapper_dir / wrapper)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _rejection_observation(
    wrapper: str,
    probe: str,
    result: subprocess.CompletedProcess,
    diagnostic: str,
) -> dict[str, object]:
    raw_output = result.stdout
    return {
        "wrapper": wrapper,
        "probe": probe,
        "observed_exit_code": result.returncode,
        "diagnostic": diagnostic,
        "raw_output": raw_output,
        "raw_output_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
    }


def _assert_wrappers_reject_wrong_channel_manifest(
    oss: Path, home: Path, base_url: str, wrapper_dir: Path
) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    cases = (
        ("install.sh", "test", "stable"),
        ("uninstall.sh", "test", "stable"),
        ("install-test.sh", "stable", "test"),
        ("uninstall-test.sh", "stable", "test"),
    )
    for wrapper, supplied_channel, expected_channel in cases:
        canonical = oss / f"projects/redbeacon/{expected_channel}/latest.json"
        supplied = (oss / f"projects/redbeacon/{supplied_channel}/latest.json").read_bytes()
        with _temporary_bytes(canonical, supplied):
            result = _run_wrapper(home, base_url, wrapper_dir, wrapper)
        assert result.returncode != 0, f"{wrapper} accepted a {supplied_channel} manifest"
        assert f"does not match RedBeacon {expected_channel}" in result.stdout
        observations.append(_rejection_observation(
            wrapper, "opposite-channel-manifest", result,
            f"does not match RedBeacon {expected_channel}",
        ))
    return observations


def _assert_core_reference_guards(
    oss: Path, home: Path, base_url: str, wrapper_dir: Path
) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    stable_path = oss / "projects/redbeacon/stable/latest.json"
    stable_manifest = json.loads(stable_path.read_text(encoding="utf-8"))
    bad_schema_manifest = json.loads(json.dumps(stable_manifest))
    bad_schema_manifest["schema"] = 2
    with _temporary_bytes(stable_path, json.dumps(bad_schema_manifest).encode("utf-8")):
        result = _run_wrapper(home, base_url, wrapper_dir, "install.sh")
    assert result.returncode != 0, "stable installer accepted an unknown schema"
    assert "manifest schema is invalid" in result.stdout
    observations.append(_rejection_observation(
        "install.sh", "invalid-manifest-schema", result, "manifest schema is invalid"
    ))

    bad_url_manifest = json.loads(json.dumps(stable_manifest))
    install_core = next(
        row
        for row in bad_url_manifest["artifacts"]
        if row["path"] == "installers/install-core.sh"
    )
    install_core["url"] = "https://example.invalid/install-core.sh"
    with _temporary_bytes(stable_path, json.dumps(bad_url_manifest).encode("utf-8")):
        result = _run_wrapper(home, base_url, wrapper_dir, "install.sh")
    assert result.returncode != 0, "stable installer accepted an off-origin core URL"
    assert "core URL does not match the stable release" in result.stdout
    observations.append(_rejection_observation(
        "install.sh", "forged-core-url", result, "core URL does not match the stable release"
    ))

    test_path = oss / "projects/redbeacon/test/latest.json"
    test_manifest = json.loads(test_path.read_text(encoding="utf-8"))
    bad_version_manifest = json.loads(json.dumps(test_manifest))
    bad_version_manifest["version"] = "8.8"
    with _temporary_bytes(test_path, json.dumps(bad_version_manifest).encode("utf-8")):
        result = _run_wrapper(home, base_url, wrapper_dir, "uninstall-test.sh")
    assert result.returncode != 0, "test uninstaller accepted an invalid version"
    assert "manifest version is invalid" in result.stdout
    observations.append(_rejection_observation(
        "uninstall-test.sh", "invalid-manifest-version", result, "manifest version is invalid"
    ))

    core_path = oss / "projects/redbeacon/test/releases/8.8.1/installers/uninstall-core.sh"
    with _temporary_bytes(core_path, core_path.read_bytes() + b"\n# tampered\n"):
        result = _run_wrapper(home, base_url, wrapper_dir, "uninstall-test.sh")
    assert result.returncode != 0, "test uninstaller accepted a modified core"
    assert "core size verification failed" in result.stdout or "core SHA-256 verification failed" in result.stdout
    diagnostic = (
        "core size verification failed"
        if "core size verification failed" in result.stdout
        else "core SHA-256 verification failed"
    )
    observations.append(_rejection_observation(
        "uninstall-test.sh", "tampered-core", result, diagnostic
    ))
    return observations


def _assert_public_wrapper_contract() -> None:
    forbidden = (
        "BYTESTAFF_HOME",
        "CLOAKBROWSER_CACHE_DIR",
        "PLAYWRIGHT_BROWSERS_PATH",
        "REDBEACON_CHANNEL",
        "REDBEACON_BUILD_CHANNEL",
        "REDBEACON_DATA_DIR",
        "REDBEACON_INSTALLER_TEST_MODE",
        "REDBEACON_SKILL_DIR",
        "REDBEACON_UPDATE_URL",
        "REDBEACON_UPDATE_WORKDIR",
    )
    specs = {
        "install.sh": ("stable", "installers/install-core.sh"),
        "install-test.sh": ("test", "installers/install-core.sh"),
        "uninstall.sh": ("stable", "installers/uninstall-core.sh"),
        "uninstall-test.sh": ("test", "installers/uninstall-core.sh"),
    }
    for name, (channel, core_path) in specs.items():
        text = (ROOT / "install" / name).read_text(encoding="utf-8")
        assert f"# BYTESTAFF_CHANNEL_IDENTITY: {channel}" in text
        canonical = f"{PUBLIC_RELEASE_ORIGIN}/projects/redbeacon/{channel}/latest.json"
        assert f"# BYTESTAFF_CANONICAL_MANIFEST_URL: {canonical}" in text
        assert f"# BYTESTAFF_FIXED_CHANNEL_ARGUMENT: {channel}" in text
        assert "# BYTESTAFF_AMBIENT_CHANNEL_OVERRIDES: forbidden" in text
        assert all(value not in text for value in forbidden)
        assert f'MANIFEST_URL="{canonical}"' in text
        assert "accepts no arguments" in text
        assert "--redbeacon-" not in text
        assert core_path in text
        assert 'TRUSTED_HOME="$(resolve_trusted_home)"' in text
        assert 'PATH="/usr/bin:/bin:/usr/sbin:/sbin"' in text
        assert "/usr/bin/mktemp -d /private/tmp/" in text
        assert "/usr/bin/curl -q " in text
        assert '/bin/bash "$CORE_FILE"' in text
        assert "command -v" not in text
        for executable in (
            "awk", "bash", "curl", "grep", "mktemp", "osascript", "python3",
            "rm", "shasum", "tr", "wc",
        ):
            assert not re.search(rf"(?<![/A-Za-z0-9_-]){executable}[ \t]", text), (
                f"{name} invokes {executable} through caller PATH"
            )
    for name in ("install-core.sh", "uninstall-core.sh"):
        text = (ROOT / "install" / name).read_text(encoding="utf-8")
        assert "# BYTESTAFF_INTERNAL_CHANNEL_HELPER: explicit-only" in text
    uninstall_core = (ROOT / "install/uninstall-core.sh").read_text(encoding="utf-8")
    assert '/usr/bin/pkill -x "$APP_NAME"' in uninstall_core
    assert 'pkill -f' not in uninstall_core
    assert "REDBEACON_UPDATE_WORKDIR" not in uninstall_core


def _assert_public_wrappers_reject_arguments(home: Path) -> list[dict[str, object]]:
    env = {
        **os.environ,
        **_hostile_execution_environment(home),
        "REDBEACON_INSTALLER_TEST_MODE": "1",
        "REDBEACON_CHANNEL": "test",
        "REDBEACON_UPDATE_URL": "http://127.0.0.1:1/forged.json",
    }
    observations: list[dict[str, object]] = []
    for name in ("install.sh", "install-test.sh", "uninstall.sh", "uninstall-test.sh"):
        result = subprocess.run(
            ["/bin/sh", str(ROOT / "install" / name), "http://127.0.0.1:1/forged.json"],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert result.returncode == 2, f"{name} accepted a positional source override"
        assert "accepts no arguments" in result.stdout
        observations.append(_rejection_observation(
            name, "extra-arguments", result, "accepts no arguments"
        ))
    return observations


def _seed_foreign_sentinels(home: Path) -> list[Path]:
    roots = [
        "foreign-data",
        "foreign-playwright",
        "foreign-cloak",
        "foreign-system-playwright",
        "foreign-system-cloak",
        "foreign-token-home",
        "foreign-update-workdir",
        "foreign-claude-skills",
        "foreign-codex-skills",
        "foreign-openclaw-skills",
        "foreign-hermes-skills",
        "foreign-workbuddy-skills",
    ]
    sentinels: list[Path] = []
    for relative in roots:
        sentinel = home / relative / "must-survive.txt"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(relative, encoding="utf-8")
        sentinels.append(sentinel)
    return sentinels


def _seed_opposite_channel_sentinels(home: Path) -> list[Path]:
    files = [
        home / ".bytestaff_test/must-survive-stable.txt",
        home / ".redbeacon_test/browser/must-survive-stable.txt",
        home / ".claude/commands/redbeacon-test.md",
        home / ".codex/skills/redbeacon-test-legacy/SKILL.md",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test-channel-state", encoding="utf-8")
    return files


def _assert_sentinels(sentinels: list[Path]) -> None:
    missing = [str(path) for path in sentinels if not path.is_file()]
    assert not missing, f"hostile ambient path was modified: {missing}"


def _assert_exact_process_isolation(root: Path, home: Path) -> list[dict[str, object]]:
    if not Path("/usr/bin/pkill").is_file():
        raise AssertionError("exact-process isolation requires /usr/bin/pkill")
    process_dir = root / "processes"
    process_dir.mkdir()
    stable_exe = process_dir / "RBStable"
    test_exe = process_dir / "RBStable_test"
    shutil.copyfile("/bin/sleep", stable_exe)
    shutil.copyfile("/bin/sleep", test_exe)
    stable_exe.chmod(0o755)
    test_exe.chmod(0o755)
    stable_proc = subprocess.Popen([str(stable_exe), "30"])
    test_proc = subprocess.Popen([str(test_exe), "30"])
    core = (ROOT / "install/uninstall-core.sh").read_text(encoding="utf-8")
    core = core.replace('APP_NAME="RedBeacon"', 'APP_NAME="RBStable"')
    core = core.replace('CLI_NAME="redbeacon-cli"', 'CLI_NAME="RBStableCli"')
    core_path = root / "process-uninstall-core.sh"
    _write_executable(core_path, core)
    try:
        subprocess.run(
            ["bash", str(core_path), "stable", "production"],
            env={**os.environ, "HOME": str(home), "REDBEACON_PURGE": "0"},
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        stable_proc.wait(timeout=5)
        assert test_proc.poll() is None, "stable uninstall killed the test-channel process"
        return [{
            "target_channel": "stable",
            "target_process": "RBStable",
            "target_exit_code": stable_proc.returncode,
            "opposite_process": "RBStable_test",
            "opposite_process_observed_running": test_proc.poll() is None,
        }]
    finally:
        for proc in (stable_proc, test_proc):
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def _skill_paths(home: Path, channel: str) -> tuple[Path, list[Path]]:
    spec = _channel_spec(channel)
    stem = spec["skill_stem"]
    claude = home / spec["skill_dir"] / f"{stem}.md"
    portable = [
        home / f".{host}/skills/{stem}/SKILL.md"
        for host in ("codex", "openclaw", "hermes", "workbuddy")
    ]
    return claude, portable


def _assert_installed(home: Path, channel: str, version: str) -> None:
    cli = _installed_cli(home, channel)
    assert cli.is_file(), f"{channel} CLI was not installed"
    assert _version(cli) == version
    claude, portable = _skill_paths(home, channel)
    for skill in [claude, *portable]:
        assert skill.is_file(), f"{channel} assistant skill was not installed: {skill}"
        assert version in skill.read_text(encoding="utf-8")


def _assert_uninstalled(home: Path, channel: str) -> None:
    assert not _installed_cli(home, channel).exists(), f"{channel} CLI survived uninstall"
    claude, portable = _skill_paths(home, channel)
    for skill in [claude, *portable]:
        assert not skill.exists(), f"{channel} assistant skill survived uninstall: {skill}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _observe_entrypoint(
    home: Path,
    base_url: str,
    wrapper_dir: Path,
    *,
    channel: str,
    operation: str,
) -> dict[str, str]:
    before = len(_QuietHandler.request_paths)
    if operation == "install":
        result = _run_installer(
            home, base_url, wrapper_dir, channel=channel, expect_ok=True
        )
        _assert_installed(home, channel, "8.8.1" if channel == "test" else "9.9.4")
    else:
        result = _run_uninstaller(home, base_url, wrapper_dir, channel=channel)
        _assert_uninstalled(home, channel)
    observed = _QuietHandler.request_paths[before:]
    fixture_version = "8.8.1" if channel == "test" else "9.9.4"
    suffix = "-test" if channel == "test" else ""
    wrapper_name = f"{operation}{suffix}.sh"
    core_name = f"{operation}-core.sh"
    manifest_request = f"/projects/redbeacon/{channel}/latest.json"
    core_request = (
        f"/projects/redbeacon/{channel}/releases/{fixture_version}/installers/{core_name}"
    )
    assert manifest_request in observed, f"{wrapper_name} did not request its fixed manifest"
    assert core_request in observed, f"{wrapper_name} did not request its fixed core"
    marker = f"BYTESTAFF_SMOKE_CORE_CHANNEL={channel}"
    marker_lines = [line.strip() for line in result.stdout.splitlines() if line.strip() == marker]
    assert marker_lines == [marker], f"{wrapper_name} did not expose one effective core channel"
    return {
        "channel": channel,
        "operation": operation,
        "wrapper_path": f"install/{wrapper_name}",
        "wrapper_sha256": _sha256_file(ROOT / "install" / wrapper_name),
        "canonical_manifest_url": (
            f"{PUBLIC_RELEASE_ORIGIN}/projects/redbeacon/{channel}/latest.json"
        ),
        "manifest_request_path": manifest_request,
        "core_path": f"install/{core_name}",
        "core_sha256": _sha256_file(ROOT / "install" / core_name),
        "core_request_path": core_request,
        "effective_core_channel": channel,
        "effective_core_marker": marker,
    }


def _observe_alias(
    home: Path,
    base_url: str,
    wrapper_dir: Path,
    *,
    channel: str,
    alias: str,
) -> dict[str, str]:
    result = _run_installer(
        home,
        base_url,
        wrapper_dir,
        channel=channel,
        expect_ok=True,
        ambient_channel=alias,
    )
    marker = f"BYTESTAFF_SMOKE_CORE_CHANNEL={channel}"
    assert [line.strip() for line in result.stdout.splitlines() if line.strip() == marker] == [marker]
    observed_version = _version(_installed_cli(home, channel))
    return {
        "target_channel": channel,
        "ambient_alias": alias,
        "effective_core_channel": channel,
        "effective_core_marker": marker,
        "observed_installed_version": observed_version,
    }


def _json_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _snapshot_digest(
    snapshots: dict[Path, tuple[tuple[str, bytes], ...]], *, base: Path
) -> tuple[int, str]:
    rows = []
    for directory, entries in sorted(snapshots.items(), key=lambda item: str(item[0])):
        label = directory.relative_to(base).as_posix()
        for relative, body in entries:
            rows.append([label, relative, hashlib.sha256(body).hexdigest()])
    return len(rows), _json_digest(rows)


def _sentinel_digest(paths: list[Path], *, base: Path) -> tuple[int, str]:
    rows = [
        [path.relative_to(base).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()]
        for path in sorted(paths)
    ]
    return len(rows), _json_digest(rows)


def _write_installer_report(
    output: Path,
    *,
    build_run_id: str,
    root_commit: str,
    cli_commit: str,
    version: str,
    channel: str,
    entrypoint_observations: list[dict[str, str]],
    observed_evidence: dict[str, object],
) -> None:
    payload = {
        "schema": INSTALLER_REPORT_SCHEMA,
        "project": "redbeacon",
        "build_run_id": build_run_id,
        "root_commit": root_commit,
        "cli_commit": cli_commit,
        "version": version,
        "platform": "macos",
        "channel": channel,
        "entrypoint_observations": entrypoint_observations,
    }
    raw = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--build-run-id", required=True)
    parser.add_argument("--root-commit", required=True)
    parser.add_argument("--cli-commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=("stable", "test"), required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{15,127}", args.build_run_id):
        raise SystemExit("invalid build_run_id")
    for label, value in (("root", args.root_commit), ("CLI", args.cli_commit)):
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
            raise SystemExit(f"invalid {label} commit")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        raise SystemExit("invalid release version")
    if os.path.lexists(args.report_path):
        raise SystemExit(f"refusing to overwrite installer smoke report: {args.report_path}")
    if platform.system() != "Darwin":
        raise SystemExit("raw macOS installer evidence must run on Darwin")
    _QuietHandler.request_paths = []
    with tempfile.TemporaryDirectory(prefix="redbeacon-install-transaction-") as td:
        root = Path(td)
        oss = root / "oss"
        home = root / "home"
        wrapper_dir = root / "smoke-wrappers"
        oss.mkdir()
        home.mkdir()
        handler = functools.partial(_QuietHandler, directory=str(oss))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        wrapper_sources = {
            name: hashlib.sha256((ROOT / "install" / name).read_bytes()).hexdigest()
            for name in ("install.sh", "install-test.sh", "uninstall.sh", "uninstall-test.sh")
        }
        try:
            hijack_marker, protected_execution_dirs = _seed_execution_hijacks(home)
            sentinels = _seed_foreign_sentinels(home)
            protected_snapshots = _snapshot_directories(
                protected_execution_dirs
                + [home / "hostile-bin", home / "caller-shell-poison"]
                + [path.parent for path in sentinels]
            )
            protected_item_count, protected_before_sha = _snapshot_digest(
                protected_snapshots, base=home
            )
            rejection_runs: list[dict[str, object]] = []
            transaction_checks: list[dict[str, object]] = []
            _assert_public_wrapper_contract()
            rejection_runs.extend(_assert_public_wrappers_reject_arguments(home))
            _write_smoke_wrappers(wrapper_dir, base_url, home)
            for script in (
                "install.sh",
                "install-test.sh",
                "install-core.sh",
                "uninstall.sh",
                "uninstall-test.sh",
                "uninstall-core.sh",
            ):
                subprocess.run(
                    ["bash", "-n", str(ROOT / "install" / script)], check=True
                )

            _build_bundle(oss, "9.9.1", base_url)
            _build_bundle(oss, "8.8.1", base_url, channel="test")
            rejection_runs.extend(_assert_wrappers_reject_wrong_channel_manifest(
                oss, home, base_url, wrapper_dir
            ))
            rejection_runs.extend(_assert_core_reference_guards(oss, home, base_url, wrapper_dir))
            opposite_sentinels = _seed_opposite_channel_sentinels(home)
            opposite_item_count, opposite_before_sha = _sentinel_digest(
                opposite_sentinels[:3], base=home
            )
            parent_environment = dict(os.environ)
            parent_environment_before_sha = _json_digest(parent_environment)
            process_isolation = _assert_exact_process_isolation(root, home)

            _run_installer(home, base_url, wrapper_dir, expect_ok=True)
            _assert_installed(home, "stable", "9.9.1")
            _assert_sentinels(sentinels)
            _assert_sentinels(opposite_sentinels)
            for alias in ("testing", "beta"):
                _run_installer(
                    home,
                    base_url,
                    wrapper_dir,
                    expect_ok=True,
                    ambient_channel=alias,
                )
                _assert_installed(home, "stable", "9.9.1")
                _assert_sentinels(sentinels)
                _assert_sentinels(opposite_sentinels)
            cli = _installed_cli(home, "stable")
            business_db = home / ".redbeacon/data/redbeacon.db"
            business_db.parent.mkdir(parents=True, exist_ok=True)
            business_db.write_text("account-data-must-survive-update", encoding="utf-8")
            claude_skill, portable_skills = _skill_paths(home, "stable")
            codex_skill = portable_skills[0]
            for skill in portable_skills:
                assert skill.is_file(), f"assistant skill was not installed: {skill}"
                assert "9.9.1" in skill.read_text(encoding="utf-8")
            assert "9.9.1" in claude_skill.read_text(encoding="utf-8")

            if platform.system() == "Darwin":
                _build_bundle(oss, "9.9.15", base_url, failure="bundle_entry")
                result = _run_installer(home, base_url, wrapper_dir, expect_ok=False)
                assert "icon points to RedBeaconRenderer" in result.stdout
                assert _version(cli) == "9.9.1", "bad macOS icon target replaced old app"
                transaction_checks.append({
                    "probe": "invalid-bundle-entry-rollback",
                    "expected_version": "9.9.1",
                    "observed_version": _version(cli),
                    "database_sha256": _sha256_file(business_db),
                })

            _build_bundle(oss, "9.9.2", base_url, failure="stage")
            _run_installer(home, base_url, wrapper_dir, expect_ok=False)
            assert _version(cli) == "9.9.1", "pre-replacement dependency failure replaced old app"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            assert "9.9.1" in codex_skill.read_text(encoding="utf-8")
            transaction_checks.append({
                "probe": "pre-replacement-rollback",
                "expected_version": "9.9.1",
                "observed_version": _version(cli),
                "database_sha256": _sha256_file(business_db),
            })

            _build_bundle(oss, "9.9.3", base_url, failure="placed")
            _run_installer(home, base_url, wrapper_dir, expect_ok=False)
            assert _version(cli) == "9.9.1", "post-placement verification failure did not roll back"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            assert "9.9.1" in claude_skill.read_text(encoding="utf-8")
            transaction_checks.append({
                "probe": "post-placement-rollback",
                "expected_version": "9.9.1",
                "observed_version": _version(cli),
                "database_sha256": _sha256_file(business_db),
            })

            _build_bundle(oss, "9.9.35", base_url, failure="post_skills")
            _run_installer(home, base_url, wrapper_dir, expect_ok=False)
            assert _version(cli) == "9.9.1", "final runtime failure did not restore old app"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            for skill in portable_skills:
                assert "9.9.1" in skill.read_text(encoding="utf-8"), f"assistant skill did not roll back: {skill}"
            assert "9.9.1" in claude_skill.read_text(encoding="utf-8"), "Claude skill did not roll back"
            transaction_checks.append({
                "probe": "post-skills-rollback",
                "expected_version": "9.9.1",
                "observed_version": _version(cli),
                "database_sha256": _sha256_file(business_db),
            })

            _build_bundle(oss, "9.9.4", base_url)
            _run_installer(home, base_url, wrapper_dir, expect_ok=True)
            assert _version(cli) == "9.9.4"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            snapshots = sorted((home / ".redbeacon/backups/pre-update").glob("*/redbeacon.db"))
            assert snapshots, "update did not create a pre-update account database snapshot"
            assert snapshots[-1].read_text(encoding="utf-8") == "account-data-must-survive-update"
            assert not list(home.rglob("*.redbeacon-rollback"))
            transaction_checks.append({
                "probe": "committed-update-database-snapshot",
                "expected_version": "9.9.4",
                "observed_version": _version(cli),
                "database_sha256": _sha256_file(business_db),
                "snapshot_sha256": _sha256_file(snapshots[-1]),
            })

            # Install the test channel through its dedicated public wrapper
            # while every ambient identity variable points at stable.
            _run_installer(
                home, base_url, wrapper_dir, channel="test", expect_ok=True
            )
            _assert_installed(home, "test", "8.8.1")
            _assert_installed(home, "stable", "9.9.4")
            test_business_db = home / ".redbeacon_test/data/redbeacon.db"
            test_business_db.parent.mkdir(parents=True, exist_ok=True)
            test_business_db.write_text("test-account-data-must-survive", encoding="utf-8")

            # Each public uninstaller runs with the opposite hostile identity;
            # only its marker-owned channel may be removed.
            _run_uninstaller(home, base_url, wrapper_dir, channel="stable")
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            _assert_uninstalled(home, "stable")
            _assert_installed(home, "test", "8.8.1")
            assert test_business_db.read_text(encoding="utf-8") == "test-account-data-must-survive"
            _assert_sentinels(opposite_sentinels[:3])
            _, opposite_after_stable_uninstall_sha = _sentinel_digest(
                opposite_sentinels[:3], base=home
            )

            _run_installer(home, base_url, wrapper_dir, expect_ok=True)
            _assert_installed(home, "stable", "9.9.4")
            _run_uninstaller(home, base_url, wrapper_dir, channel="test")
            assert test_business_db.read_text(encoding="utf-8") == "test-account-data-must-survive"
            _assert_uninstalled(home, "test")
            _assert_installed(home, "stable", "9.9.4")
            _run_uninstaller(home, base_url, wrapper_dir, channel="stable")
            _assert_uninstalled(home, "stable")
            _assert_sentinels(sentinels)
            _assert_directory_snapshots(protected_snapshots)
            assert not hijack_marker.exists(), "caller-controlled executable or shell startup file ran"
            for name, digest in wrapper_sources.items():
                current = hashlib.sha256((ROOT / "install" / name).read_bytes()).hexdigest()
                assert current == digest, f"smoke mutated production wrapper source: {name}"
            assert os.environ == parent_environment, "installer smoke changed its caller environment"
            current_protected = _snapshot_directories(list(protected_snapshots))
            _, protected_after_sha = _snapshot_digest(current_protected, base=home)

            # Re-run each public entrypoint once as the final observed sequence.
            # The report records the actual loopback request paths and the
            # effective channel printed by the fetched, checksum-verified core.
            alias_runs = [
                _observe_alias(
                    home, base_url, wrapper_dir, channel=observed_channel, alias=alias
                )
                for observed_channel in ("stable", "test")
                for alias in ("testing", "beta")
            ]
            for observed_channel in ("stable", "test"):
                _run_uninstaller(home, base_url, wrapper_dir, channel=observed_channel)
            entrypoint_observations = [
                _observe_entrypoint(
                    home, base_url, wrapper_dir, channel=observed_channel, operation=operation
                )
                for observed_channel in ("stable", "test")
                for operation in ("install", "uninstall")
            ]
            _assert_sentinels(sentinels)
            _assert_directory_snapshots(protected_snapshots)
            assert not hijack_marker.exists(), "final observation invoked caller-controlled code"
            assert os.environ == parent_environment, "final observation changed caller environment"
            parent_environment_after_sha = _json_digest(dict(os.environ))
            current_protected = _snapshot_directories(list(protected_snapshots))
            _, protected_final_sha = _snapshot_digest(current_protected, base=home)
            observed_evidence = {
                "alias_runs": alias_runs,
                "rejection_runs": rejection_runs,
                "state_snapshots": [
                    {
                        "scope": "caller-controlled-paths",
                        "item_count": protected_item_count,
                        "before_sha256": protected_before_sha,
                        "after_sha256": protected_final_sha,
                    },
                    {
                        "scope": "opposite-test-state-during-stable-uninstall",
                        "item_count": opposite_item_count,
                        "before_sha256": opposite_before_sha,
                        "after_sha256": opposite_after_stable_uninstall_sha,
                    },
                ],
                "process_isolation": process_isolation,
                "transaction_checks": transaction_checks,
                "caller_environment": {
                    "before_sha256": parent_environment_before_sha,
                    "after_sha256": parent_environment_after_sha,
                },
                "execution_hijack": {
                    "probes": ["caller-path-binaries", "shell-startup-files"],
                    "protected_before_sha256": protected_before_sha,
                    "protected_after_sha256": protected_after_sha,
                    "marker_observed_count": 0,
                },
            }
            _write_installer_report(
                args.report_path,
                build_run_id=args.build_run_id,
                root_commit=args.root_commit,
                cli_commit=args.cli_commit,
                version=args.version,
                channel=args.channel,
                entrypoint_observations=entrypoint_observations,
                observed_evidence=observed_evidence,
            )
        finally:
            server.shutdown()
            server.server_close()
    print(
        "Unix installer transaction smoke passed: fixed stable/test wrappers, "
        "hostile env isolation, five-host skill rollback, commit and uninstall"
    )
    print(f"Raw installer transaction smoke report: {args.report_path.resolve()}")


if __name__ == "__main__":
    main()
