#!/usr/bin/env python3
"""Validate locked cross-platform runtime coordinates before an expensive build."""
from __future__ import annotations

import importlib.metadata
import os
import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from cloakbrowser.config import DOWNLOAD_BASE_URL, PLATFORM_CHROMIUM_VERSIONS

from prepare_release_artifacts import (
    CLOAKBROWSER_ARCHIVE_SUFFIXES,
    _cloakbrowser_archive_url,
)
from redbeacon.services.browser_engine import _playwright_archive_url


ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise SystemExit(f"release dependency contract failed: {message}")


def _locked_playwright_version() -> str:
    data = tomllib.loads((ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data.get("project", {}).get("dependencies", [])
    for dependency in dependencies:
        match = re.fullmatch(r"playwright==([0-9]+(?:\.[0-9]+){2})", str(dependency).strip())
        if match:
            return match.group(1)
    fail("cli/pyproject.toml must pin Playwright with an exact == version")
    raise AssertionError("unreachable")


def _playwright_targets() -> dict[str, str]:
    targets: dict[str, str] = {}
    previous = os.environ.get("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE")
    try:
        for platform_name, override in (("mac-arm64", None), ("win-x64", "win64")):
            if override is None:
                os.environ.pop("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", None)
            else:
                os.environ["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = override
            targets[platform_name] = _playwright_archive_url(None)
    finally:
        if previous is None:
            os.environ.pop("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", None)
        else:
            os.environ["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = previous
    return targets


def _verify_playwright() -> tuple[str, dict[str, str]]:
    locked_version = _locked_playwright_version()
    installed_version = importlib.metadata.version("playwright")
    if installed_version != locked_version:
        fail(
            "build environment Playwright version mismatch: "
            f"pyproject locks {locked_version}, environment has {installed_version}"
        )

    targets = _playwright_targets()
    suffixes = {
        "mac-arm64": "/mac-arm64/chrome-mac-arm64.zip",
        "win-x64": "/win64/chrome-win64.zip",
    }
    browser_versions: set[str] = set()
    for platform_name, url in targets.items():
        parsed = urlsplit(url)
        path = parsed.path
        if parsed.scheme != "https" or not parsed.hostname:
            fail(f"{platform_name} Playwright archive is not a plain HTTPS URL: {url}")
        if "/builds/cft/" not in path or "headless-shell" in path:
            fail(f"{platform_name} did not resolve a full Chrome for Testing archive: {url}")
        if not path.endswith(suffixes[platform_name]):
            fail(f"{platform_name} resolved an unexpected Playwright archive: {url}")
        match = re.search(r"/builds/cft/([^/]+)/", path)
        if not match:
            fail(f"{platform_name} Playwright browser version is missing: {url}")
        browser_versions.add(match.group(1))
    if len(browser_versions) != 1:
        fail(f"macOS and Windows Playwright archives disagree: {targets}")
    return locked_version, targets


def main() -> None:
    playwright_version, playwright_targets = _verify_playwright()
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
        "release dependencies: locked Playwright and CloakBrowser targets verified "
        f"(Playwright {playwright_version}; "
        f"macOS {Path(urlsplit(playwright_targets['mac-arm64']).path).name}; "
        f"Windows {Path(urlsplit(playwright_targets['win-x64']).path).name}; "
        f"CloakBrowser macOS {mac_version}, Windows {windows_version})"
    )


if __name__ == "__main__":
    main()
