#!/usr/bin/env python3
"""Offline smoke for staged dependency preparation and installer rollback."""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        pass


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _platform_layout() -> tuple[str, Path, str]:
    if platform.system() == "Darwin":
        plat = "mac-arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "mac-x64"
        return plat, Path("RedBeacon.app/Contents/MacOS"), "RedBeacon.app"
    return "linux-x64", Path("RedBeacon"), "RedBeacon"


def _build_bundle(oss: Path, version: str, base_url: str, failure: str = "") -> None:
    plat, executable_dir, archive_root = _platform_layout()
    build = oss.parent / f"build-{version}"
    shutil.rmtree(build, ignore_errors=True)
    cli = build / executable_dir / "redbeacon-cli"
    installed_markers = (
        "*/Applications/RedBeacon.app/*|*/.local/share/redbeacon/RedBeacon/*"
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
        'EXPECTED_DATA="$HOME/.redbeacon/data"\n'
        'EXPECTED_PW="$HOME/.redbeacon/browser/ms-playwright"\n'
        'EXPECTED_CB="$HOME/.redbeacon/browser/cloakbrowser"\n'
        "case \"${1:-}\" in\n"
        "  --version) echo \"redbeacon $VERSION\" ;;\n"
        f"  setup) {setup_logic or ':'}; "
        '[ "$REDBEACON_DATA_DIR" = "$EXPECTED_DATA" ] || exit 34; '
        '[ "$PLAYWRIGHT_BROWSERS_PATH" = "$EXPECTED_PW" ] || exit 35; '
        '[ "$CLOAKBROWSER_CACHE_DIR" = "$EXPECTED_CB" ] || exit 36; '
        '[ -f "$REDBEACON_INSTALL_MANIFEST_FILE" ] || exit 37; '
        "echo '{\"ok\":true}' ;;\n"
        "  config) : ;;\n"
        f"  *) if [ \"${{REDBEACON_DESKTOP_SMOKE:-}}\" = 1 ]; then {desktop_logic or ':'}; "
        "echo 'RedBeacon desktop smoke ok'; fi ;;\n"
        "esac\n",
    )
    _write_executable(build / executable_dir / "RedBeacon", "#!/bin/sh\nexit 0\n")
    if platform.system() == "Darwin":
        bundle_entry = "RedBeaconRenderer" if failure == "bundle_entry" else "RedBeacon"
        (build / "RedBeacon.app/Contents/Info.plist").write_text(
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

    package_dir = oss / "packages"
    package_dir.mkdir(parents=True, exist_ok=True)
    bundle = package_dir / f"RedBeacon-{plat}.zip"
    subprocess.run(
        ["zip", "-qry", str(bundle), archive_root], cwd=build, check=True
    )
    sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    skill_root = oss.parent / f"skill-{version}"
    shutil.rmtree(skill_root, ignore_errors=True)
    command_dir = skill_root / ".claude" / "commands"
    command_dir.mkdir(parents=True)
    (command_dir / "redbeacon.md").write_text(
        f"---\ndescription: transaction smoke {version}\n---\n# RedBeacon {version}\n",
        encoding="utf-8",
    )
    portable = skill_root / "agent-skills" / "redbeacon" / "SKILL.md"
    portable.parent.mkdir(parents=True)
    portable.write_text(
        f"---\nname: redbeacon\ndescription: \"transaction smoke {version}\"\n---\n\n# RedBeacon {version}\n",
        encoding="utf-8",
    )
    (skill_root / "redbeacon-skill-manifest.json").write_text(
        json.dumps({
            "schema": 2,
            "channel": "stable",
            "version": version,
            "commit": "smoke",
            "assistants": ["claude-code", "codex", "openclaw", "hermes", "workbuddy"],
            "portable_skills": ["agent-skills/redbeacon/SKILL.md"],
        }),
        encoding="utf-8",
    )
    skill_dir = oss / "skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_bundle = skill_dir / "redbeacon-skill.tar.gz"
    with tarfile.open(skill_bundle, "w:gz") as tar:
        tar.add(skill_root / ".claude", arcname=".claude")
        tar.add(skill_root / "agent-skills", arcname="agent-skills")
        tar.add(skill_root / "redbeacon-skill-manifest.json", arcname="redbeacon-skill-manifest.json")
    skill_sha = hashlib.sha256(skill_bundle.read_bytes()).hexdigest()

    (oss / "latest.json").write_text(
        json.dumps({
            "schema": 1,
            "project": "redbeacon",
            "channel": "stable",
            "version": version,
            "created_at": "2026-07-17T00:00:00Z",
            "commit": "installer-smoke",
            "artifacts": [
                {
                    "path": f"packages/RedBeacon-{plat}.zip",
                    "size": bundle.stat().st_size,
                    "sha256": sha,
                    "url": f"{base_url}/packages/RedBeacon-{plat}.zip",
                    "download_urls": [f"{base_url}/packages/RedBeacon-{plat}.zip"],
                },
                {
                    "path": "skill/redbeacon-skill.tar.gz",
                    "size": skill_bundle.stat().st_size,
                    "sha256": skill_sha,
                    "url": f"{base_url}/skill/redbeacon-skill.tar.gz",
                    "download_urls": [f"{base_url}/skill/redbeacon-skill.tar.gz"],
                },
            ],
        }, separators=(",", ":")),
        encoding="utf-8",
    )


def _installed_cli(home: Path) -> Path:
    if platform.system() == "Darwin":
        return home / "Applications/RedBeacon.app/Contents/MacOS/redbeacon-cli"
    return home / ".local/share/redbeacon/RedBeacon/redbeacon-cli"


def _version(cli: Path) -> str:
    return subprocess.check_output([str(cli), "--version"], text=True).strip().split()[-1]


def _run_installer(home: Path, base_url: str, *, expect_ok: bool) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "REDBEACON_UPDATE_URL": f"{base_url}/latest.json",
        "REDBEACON_INSTALLER_TEST_MODE": "1",
        "REDBEACON_FORCE_INSTALL": "1",
        "REDBEACON_NO_PAUSE": "1",
        "REDBEACON_SKIP_OS_REFRESH": "1",
        "REDBEACON_SKIP_PROCESS_STOP": "1",
        "REDBEACON_SKILL_DIR": str(home / "skills"),
        # Deliberately hostile inherited locations: the installer must ignore
        # these and prepare the canonical stable-channel runtime directories.
        "REDBEACON_DATA_DIR": str(home / "foreign-data"),
        "REDBEACON_PLAYWRIGHT_DIR": str(home / "foreign-playwright"),
        "REDBEACON_CLOAKBROWSER_DIR": str(home / "foreign-cloak"),
        "PLAYWRIGHT_BROWSERS_PATH": str(home / "foreign-system-playwright"),
        "CLOAKBROWSER_CACHE_DIR": str(home / "foreign-system-cloak"),
    })
    result = subprocess.run(
        ["bash", str(ROOT / "install/install.sh")],
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


def _run_uninstaller(home: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "REDBEACON_CHANNEL": "stable",
        "REDBEACON_PURGE": "0",
        "REDBEACON_SKIP_PROCESS_STOP": "1",
        "REDBEACON_SKILL_DIR": str(home / "skills"),
    })
    return subprocess.run(
        ["bash", str(ROOT / "install/uninstall.sh")],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


def _run_test_wrappers(oss: Path, base_url: str, home: Path) -> None:
    release = oss / "projects/redbeacon/test/releases/9.9.0/installers"
    release.mkdir(parents=True, exist_ok=True)
    marker = home / "test-wrapper-marker"
    for name, value in (("install.sh", "install"), ("uninstall.sh", "uninstall")):
        _write_executable(
            release / name,
            "#!/bin/sh\n"
            '[ "${REDBEACON_CHANNEL:-}" = "test" ] || exit 71\n'
            f"printf '{value}' > \"$REDBEACON_WRAPPER_MARKER\"\n",
        )
    artifacts = []
    for name in ("install.sh", "uninstall.sh"):
        path = release / name
        url = f"{base_url}/projects/redbeacon/test/releases/9.9.0/installers/{name}"
        artifacts.append({
            "path": f"installers/{name}",
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "url": url,
            "download_urls": [url],
        })
    manifest = oss / "projects/redbeacon/test/latest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({
            "schema": 1,
            "project": "redbeacon",
            "channel": "test",
            "version": "9.9.0",
            "artifacts": artifacts,
        }, separators=(",", ":")),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "REDBEACON_UPDATE_URL": f"{base_url}/projects/redbeacon/test/latest.json",
        "REDBEACON_INSTALLER_TEST_MODE": "1",
        "REDBEACON_WRAPPER_MARKER": str(marker),
    })
    for wrapper, expected in (("install-test.sh", "install"), ("uninstall-test.sh", "uninstall")):
        marker.unlink(missing_ok=True)
        result = subprocess.run(
            ["bash", str(ROOT / "install" / wrapper)],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout)
        assert marker.read_text(encoding="utf-8") == expected


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="redbeacon-install-transaction-") as td:
        root = Path(td)
        oss = root / "oss"
        home = root / "home"
        oss.mkdir()
        home.mkdir()
        handler = functools.partial(_QuietHandler, directory=str(oss))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            _run_test_wrappers(oss, base_url, home)
            _build_bundle(oss, "9.9.1", base_url)
            _run_installer(home, base_url, expect_ok=True)
            cli = _installed_cli(home)
            assert _version(cli) == "9.9.1"
            business_db = home / ".redbeacon/data/redbeacon.db"
            business_db.parent.mkdir(parents=True, exist_ok=True)
            business_db.write_text("account-data-must-survive-update", encoding="utf-8")
            codex_skill = home / ".codex/skills/redbeacon/SKILL.md"
            claude_skill = home / "skills/redbeacon.md"
            portable_skills = [
                codex_skill,
                home / ".openclaw/skills/redbeacon/SKILL.md",
                home / ".hermes/skills/redbeacon/SKILL.md",
                home / ".workbuddy/skills/redbeacon/SKILL.md",
            ]
            for skill in portable_skills:
                assert skill.is_file(), f"assistant skill was not installed: {skill}"
                assert "9.9.1" in skill.read_text(encoding="utf-8")
            assert "9.9.1" in claude_skill.read_text(encoding="utf-8")

            if platform.system() == "Darwin":
                _build_bundle(oss, "9.9.15", base_url, failure="bundle_entry")
                result = _run_installer(home, base_url, expect_ok=False)
                assert "icon points to RedBeaconRenderer" in result.stdout
                assert _version(cli) == "9.9.1", "bad macOS icon target replaced old app"

            _build_bundle(oss, "9.9.2", base_url, failure="stage")
            _run_installer(home, base_url, expect_ok=False)
            assert _version(cli) == "9.9.1", "pre-replacement dependency failure replaced old app"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            assert "9.9.1" in codex_skill.read_text(encoding="utf-8")

            _build_bundle(oss, "9.9.3", base_url, failure="placed")
            _run_installer(home, base_url, expect_ok=False)
            assert _version(cli) == "9.9.1", "post-placement verification failure did not roll back"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            assert "9.9.1" in claude_skill.read_text(encoding="utf-8")

            _build_bundle(oss, "9.9.35", base_url, failure="post_skills")
            _run_installer(home, base_url, expect_ok=False)
            assert _version(cli) == "9.9.1", "final runtime failure did not restore old app"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            for skill in portable_skills:
                assert "9.9.1" in skill.read_text(encoding="utf-8"), f"assistant skill did not roll back: {skill}"
            assert "9.9.1" in claude_skill.read_text(encoding="utf-8"), "Claude skill did not roll back"

            _build_bundle(oss, "9.9.4", base_url)
            _run_installer(home, base_url, expect_ok=True)
            assert _version(cli) == "9.9.4"
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            snapshots = sorted((home / ".redbeacon/backups/pre-update").glob("*/redbeacon.db"))
            assert snapshots, "update did not create a pre-update account database snapshot"
            assert snapshots[-1].read_text(encoding="utf-8") == "account-data-must-survive-update"
            assert not list(home.rglob("*.redbeacon-rollback"))

            _run_uninstaller(home)
            assert business_db.read_text(encoding="utf-8") == "account-data-must-survive-update"
            assert not claude_skill.exists()
            for skill in portable_skills:
                assert not skill.exists(), f"assistant skill survived uninstall: {skill}"
        finally:
            server.shutdown()
            server.server_close()
    print("Unix installer transaction smoke passed: hostile env + five-host skill rollback, commit and uninstall")


if __name__ == "__main__":
    main()
