#!/usr/bin/env python3
"""Release gate for the exact browser archives required by this CLI lockfile.

The check performs one-byte Range GETs against RedBeacon's public OSS URLs. It
therefore catches missing objects, wrong platform names, and origins that cannot
support resumable downloads without pulling the large archives during release.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mirror_cloakbrowser_browsers  # noqa: E402
import mirror_playwright_browsers  # noqa: E402


RELEASE_CLOAK_PLATFORMS = {"windows-x64", "darwin-arm64", "linux-x64"}


def fail(message: str) -> None:
    raise SystemExit(f"xx {message}")


def range_probe(url: str) -> None:
    proc = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--range",
            "0-0",
            "--connect-timeout",
            "8",
            "--max-time",
            "20",
            "--max-filesize",
            "1048576",
            "-o",
            os.devnull,
            "-w",
            "%{http_code} %{size_download}",
            url,
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    result = proc.stdout.strip()
    if proc.returncode != 0 or result != "206 1":
        detail = proc.stderr.strip() or result or f"curl exit {proc.returncode}"
        fail(f"browser mirror does not support a one-byte Range GET: {url} ({detail})")


def playwright_urls(python: str, base_url: str) -> list[str]:
    host = f"{base_url.rstrip('/')}/playwright"
    urls: list[str] = []
    for platform_key in mirror_playwright_browsers.PLATFORMS.values():
        candidates = mirror_playwright_browsers.dry_run_urls(python, platform_key, host)
        full = mirror_playwright_browsers.full_chromium_urls(candidates)
        if len(full) != 1:
            fail(f"expected one full Chromium archive for {platform_key}, got {full}")
        urls.extend(full)
    return urls


def cloakbrowser_urls(python: str, base_url: str) -> list[str]:
    base = f"{base_url.rstrip('/')}/cloakbrowser"
    urls: list[str] = []
    found: set[str] = set()
    for tag, version, archive in mirror_cloakbrowser_browsers.cloak_targets(python):
        if tag not in RELEASE_CLOAK_PLATFORMS:
            continue
        found.add(tag)
        urls.append(f"{base}/chromium-v{version}/{archive}")
    missing = RELEASE_CLOAK_PLATFORMS - found
    if missing:
        fail(f"CloakBrowser has no release archive for: {', '.join(sorted(missing))}")
    return urls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--base-url",
        default="https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com",
    )
    args = parser.parse_args()

    urls = [
        *playwright_urls(args.python, args.base_url),
        *cloakbrowser_urls(args.python, args.base_url),
    ]
    for url in urls:
        range_probe(url)
        print(f"  ok range: {url}")
    print(f"ok browser mirrors ready: {len(urls)} release archives")


if __name__ == "__main__":
    main()
