#!/usr/bin/env python3
"""Validate the clean tree handed to the global publication Skill."""
from __future__ import annotations

import argparse
import json
import os
import stat
import tarfile
from pathlib import Path

from cloakbrowser.config import PLATFORM_CHROMIUM_VERSIONS


CLOAKBROWSER_ARCHIVE_SUFFIXES = {
    "darwin-arm64": ".tar.gz",
    "windows-x64": ".zip",
}


def fail(message: str) -> None:
    raise SystemExit(f"artifact contract failed: {message}")


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
    required = {
        f"packages/{app_name}-mac-arm64.zip",
        f"packages/{app_name}-win-x64.zip",
        "installers/install.sh",
        "installers/install.ps1",
        "installers/uninstall.sh",
        "installers/uninstall.ps1",
        "skill/redbeacon-skill.tar.gz",
        "metadata/release-contract.json",
        "metadata/build-evidence.json",
    }
    missing = sorted(required - set(files))
    if missing:
        fail("missing required artifacts: " + ", ".join(missing))

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
    if evidence.get("channel") != args.channel or evidence.get("version") != args.version:
        fail("build evidence channel/version mismatch")
    with tarfile.open(root / "skill" / "redbeacon-skill.tar.gz", "r:gz") as archive:
        names = archive.getnames()
        if "redbeacon-skill-manifest.json" not in names or not any(name.endswith("redbeacon.md") or name.endswith("redbeacon-test.md") for name in names):
            fail("skill bundle is incomplete")

    print(f"release artifacts: {len(files)} files verified")


if __name__ == "__main__":
    main()
