#!/usr/bin/env python3
"""Mirror the Playwright browser archive required by RedBeacon to OSS.

RedBeacon launches the full Chrome for Testing executable directly and does not
use Playwright video recording or its headless-shell executable. This script
therefore discovers and mirrors only that one platform-specific archive via
Playwright's own `--dry-run --no-shell` output:

  oss://bytestaff-redbeacon/playwright/...

Run when Playwright is upgraded, or when public mirrors are unreliable.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUCKET = "bytestaff-redbeacon"
DEFAULT_ENDPOINT = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com"
DEFAULT_PREFIX = "playwright"
DEFAULT_SOURCE_HOSTS = [
    "https://cdn.npmmirror.com/binaries/playwright",
    "https://registry.npmmirror.com/-/binary/playwright",
]
PLATFORMS = {
    "win-x64": "win64",
    "mac-arm64": "mac13-arm64",
    "linux-x64": "ubuntu22.04-x64",
}


def fail(message: str) -> None:
    raise SystemExit(f"xx {message}")


def bundled_python() -> str:
    candidates = [
        ROOT / "cli" / ".buildvenv" / "bin" / "python",
        ROOT / "cli" / ".buildvenv" / "Scripts" / "python.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return sys.executable


def dry_run_urls(py: str, platform_key: str, host: str | None) -> list[str]:
    env = dict(os.environ)
    env["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = platform_key
    if host:
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = host.rstrip("/")
    else:
        env.pop("PLAYWRIGHT_DOWNLOAD_HOST", None)
    with tempfile.TemporaryDirectory() as td:
        env["PLAYWRIGHT_BROWSERS_PATH"] = td
        proc = subprocess.run(
            [
                py,
                "-m",
                "playwright",
                "install",
                "chromium",
                "--no-shell",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            env=env,
            timeout=60,
        )
    if proc.returncode != 0:
        fail(proc.stderr.strip() or proc.stdout.strip() or "playwright dry-run failed")
    urls: list[str] = []
    for line in proc.stdout.splitlines():
        match = re.search(r"Download (?:url|fallback \d+):\s*(https?://\S+)", line)
        if match:
            urls.append(match.group(1))
    if not urls:
        fail(f"no browser download URLs discovered for {platform_key}")
    return urls


def full_chromium_urls(urls: list[str]) -> list[str]:
    return [
        url
        for url in urls
        if "/builds/cft/" in url and "headless-shell" not in url
    ]


def relative_target_path(target_url: str, endpoint: str, prefix: str) -> str:
    target = urlparse(target_url)
    base = urlparse(f"{endpoint.rstrip('/')}/{prefix.strip('/')}")
    if target.netloc != base.netloc:
        fail(f"target URL host mismatch: {target_url}")
    base_path = base.path.rstrip("/") + "/"
    if not target.path.startswith(base_path):
        fail(f"target URL path is outside {base_path}: {target_url}")
    return target.path[len(base_path):]


def run(cmd: list[str], *, timeout: int | None = None) -> None:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, timeout=timeout)
    if proc.returncode != 0:
        fail(f"command failed: {' '.join(cmd)}")


def oss_exists(ossutil: str, profile: str, uri: str) -> bool:
    proc = subprocess.run(
        [ossutil, "stat", uri, "--profile", profile],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )
    return proc.returncode == 0


def download_first(urls: list[str], dest: Path) -> str:
    for url in urls:
        try:
            run([
                "curl", "-fL", "--connect-timeout", "10", "--retry", "3",
                "--retry-all-errors", "--speed-limit", "16384", "--speed-time", "30",
                "--continue-at", "-", "-o", str(dest), url,
            ], timeout=1800)
            return url
        except SystemExit:
            print(f"!! download stalled or failed, keeping partial bytes and trying next source: {url}")
    fail("all browser archive sources failed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=os.environ.get("OSS_BUCKET", DEFAULT_BUCKET))
    ap.add_argument("--profile", default=os.environ.get("OSS_PROFILE", "redbeacon-release"))
    ap.add_argument("--ossutil", default=os.environ.get("OSSUTIL", str(Path.home() / ".local/bin/ossutil")))
    ap.add_argument("--endpoint", default=f"https://{DEFAULT_BUCKET}.oss-cn-shanghai.aliyuncs.com")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--source-host", action="append", dest="source_hosts", default=[],
                    help="Playwright mirror host to download from; can repeat")
    ap.add_argument("--platform", action="append", choices=sorted(PLATFORMS), default=[],
                    help="Platform to mirror; can repeat. Default: all release platforms.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Re-upload objects even when they already exist in OSS.")
    args = ap.parse_args()

    py = bundled_python()
    if not shutil.which("curl"):
        fail("curl is required")
    if not args.dry_run and not Path(os.path.expanduser(args.ossutil)).exists():
        fail(f"ossutil not found: {args.ossutil}")

    endpoint = args.endpoint.rstrip("/")
    prefix = args.prefix.strip("/")
    target_host = f"{endpoint}/{prefix}"
    source_hosts = [h.rstrip("/") for h in (args.source_hosts or DEFAULT_SOURCE_HOSTS)]
    platforms = args.platform or list(PLATFORMS)

    work = Path(tempfile.mkdtemp(prefix="rb-playwright-mirror-"))
    print(f"==> Using Python: {py}")
    print(f"==> Target: oss://{args.bucket}/{prefix}/")
    try:
        for plat in platforms:
            override = PLATFORMS[plat]
            target_urls = full_chromium_urls(dry_run_urls(py, override, target_host))
            official_urls = full_chromium_urls(dry_run_urls(py, override, None))
            if len(target_urls) != 1:
                fail(f"expected one full Chromium archive for {override}, got {target_urls}")
            source_urls_by_rel: dict[str, list[str]] = {}
            for source_host in source_hosts:
                source_urls = full_chromium_urls(
                    dry_run_urls(py, override, source_host)
                )
                for url in source_urls:
                    rel = relative_target_path(url.replace(source_host, target_host, 1), endpoint, prefix)
                    source_urls_by_rel.setdefault(rel, []).append(url)
            official_by_name: dict[str, list[str]] = {}
            for url in official_urls:
                official_by_name.setdefault(Path(urlparse(url).path).name, []).append(url)

            for target_url in target_urls:
                rel = relative_target_path(target_url, endpoint, prefix)
                # GitHub runners normally reach Microsoft's official CDN best;
                # mainland public mirrors remain maintenance-time fallbacks.
                sources = [
                    *official_by_name.get(Path(urlparse(target_url).path).name, []),
                    *source_urls_by_rel.get(rel, []),
                ]
                oss_path = f"oss://{args.bucket}/{prefix}/{rel}"
                print(f"==> {plat}: {rel}")
                if args.dry_run:
                    for src in sources:
                        print(f"    source: {src}")
                    print(f"    target: {oss_path}")
                    continue
                if not args.force and oss_exists(args.ossutil, args.profile, oss_path):
                    print(f"    object exists, skip: {oss_path}")
                    continue
                dest = work / plat / rel.replace("/", "_")
                dest.parent.mkdir(parents=True, exist_ok=True)
                used = download_first(sources, dest)
                print(f"    downloaded from: {used}")
                run([args.ossutil, "cp", str(dest), oss_path, "--profile", args.profile, "-f"], timeout=1800)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
