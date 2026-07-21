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
SUPPORTED_ASSISTANTS = {
    "claude-code",
    "codex",
    "openclaw",
    "hermes",
    "workbuddy",
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
        if metadata.get("schema") != 2 or set(metadata.get("assistants", [])) != SUPPORTED_ASSISTANTS:
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
