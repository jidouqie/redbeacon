#!/usr/bin/env python3
"""Validate locked cross-platform runtime coordinates before an expensive build."""
from __future__ import annotations

import importlib.metadata
import re
import tomllib
from pathlib import Path

from cloakbrowser.config import DOWNLOAD_BASE_URL, PLATFORM_CHROMIUM_VERSIONS

from prepare_release_artifacts import (
    CLOAKBROWSER_ARCHIVE_SUFFIXES,
    _cloakbrowser_archive_url,
)


ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise SystemExit(f"release dependency contract failed: {message}")


def _verify_control_dependencies() -> dict[str, str]:
    data = tomllib.loads((ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data.get("project", {}).get("dependencies", [])
    versions = {}
    for package in ("playwright", "cloakbrowser"):
        matches = [re.fullmatch(rf"{package}==([0-9]+(?:\.[0-9]+){{2}})", str(dep).strip()) for dep in dependencies]
        locked = next((match.group(1) for match in matches if match), None)
        if locked is None:
            fail(f"cli/pyproject.toml must pin {package} with an exact == version")
        installed = importlib.metadata.version(package)
        if installed != locked:
            fail(f"build environment {package} version mismatch: locked={locked}, installed={installed}")
        versions[package] = locked
    return versions


def main() -> None:
    versions = _verify_control_dependencies()
    for platform_tag, suffix in CLOAKBROWSER_ARCHIVE_SUFFIXES.items():
        version = PLATFORM_CHROMIUM_VERSIONS.get(platform_tag)
        if not version:
            fail(f"locked CloakBrowser package has no version for {platform_tag}")
        expected = (
            f"{DOWNLOAD_BASE_URL.rstrip('/')}/chromium-v{version}/"
            f"cloakbrowser-{platform_tag}{suffix}"
        )
        actual = _cloakbrowser_archive_url(platform_tag)
        if actual != expected:
            fail(f"{platform_tag} resolved to {actual}, expected {expected}")

    mac_version = PLATFORM_CHROMIUM_VERSIONS["darwin-arm64"]
    windows_version = PLATFORM_CHROMIUM_VERSIONS["windows-x64"]
    print(
        "release dependencies: shared CloakBrowser targets verified "
        f"(Playwright control library {versions['playwright']}; "
        f"CloakBrowser wrapper {versions['cloakbrowser']}; "
        f"macOS {mac_version}, Windows {windows_version}; no stock Chromium)"
    )


if __name__ == "__main__":
    main()
