#!/usr/bin/env python3
"""Validate cross-platform runtime coordinates before an expensive build."""
from __future__ import annotations

from cloakbrowser.config import DOWNLOAD_BASE_URL, PLATFORM_CHROMIUM_VERSIONS

from prepare_release_artifacts import (
    CLOAKBROWSER_ARCHIVE_SUFFIXES,
    _cloakbrowser_archive_url,
)


def fail(message: str) -> None:
    raise SystemExit(f"release dependency contract failed: {message}")


def main() -> None:
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
        "release dependencies: locked CloakBrowser targets verified "
        f"(macOS {mac_version}, Windows {windows_version})"
    )


if __name__ == "__main__":
    main()
