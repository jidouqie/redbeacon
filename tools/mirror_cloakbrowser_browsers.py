#!/usr/bin/env python3
"""Mirror CloakBrowser Chromium archives required by RedBeacon to OSS.

QR login and publishing use CloakBrowser, not Playwright's stock Chromium.
`redbeacon setup` now prewarms both browser families. This script mirrors the
CloakBrowser archives and SHA256SUMS files to:

  oss://bytestaff-redbeacon/cloakbrowser/chromium-v<version>/...

Run when `cloakbrowser` is upgraded, or when public sources are unreliable.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUCKET = "bytestaff-redbeacon"
DEFAULT_PREFIX = "cloakbrowser"
PRIMARY_BASE = "https://cloakbrowser.dev"
GITHUB_BASE = "https://github.com/CloakHQ/cloakbrowser/releases/download"


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


def archive_name_for_tag(tag: str) -> str:
    """Return the CloakBrowser archive name for a target platform tag.

    cloakbrowser.config.get_archive_name(tag) uses the *current machine's*
    archive extension internally. That is fine at runtime, but wrong for this
    mirror script because it is normally run on macOS while mirroring Windows
    assets. Windows releases are zip files; Unix-like platforms are tarballs.
    """
    ext = ".zip" if tag.startswith("windows-") else ".tar.gz"
    return f"cloakbrowser-{tag}{ext}"


def cloak_targets(py: str) -> list[tuple[str, str, str]]:
    code = r"""
from cloakbrowser import config
for tag, version in sorted(config.PLATFORM_CHROMIUM_VERSIONS.items()):
    print(tag, version)
"""
    proc = subprocess.run([py, "-c", code], text=True, capture_output=True, timeout=30)
    if proc.returncode != 0:
        fail(proc.stderr.strip() or "cannot import cloakbrowser; run from cli build env")
    out: list[tuple[str, str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            out.append((parts[0], parts[1], archive_name_for_tag(parts[0])))
    if not out:
        fail("no CloakBrowser platform targets discovered")
    return out


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
    fail("all download sources failed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=os.environ.get("OSS_BUCKET", DEFAULT_BUCKET))
    ap.add_argument("--profile", default=os.environ.get("OSS_PROFILE", "redbeacon-release"))
    ap.add_argument("--ossutil", default=os.environ.get("OSSUTIL", str(Path.home() / ".local/bin/ossutil")))
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--platform", action="append", default=[],
                    help="CloakBrowser platform tag to mirror. Default: all release-supported tags.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Re-upload objects even when they already exist in OSS.")
    args = ap.parse_args()

    py = bundled_python()
    if not shutil.which("curl"):
        fail("curl is required")
    if not args.dry_run and not Path(os.path.expanduser(args.ossutil)).exists():
        fail(f"ossutil not found: {args.ossutil}")

    prefix = args.prefix.strip("/")
    targets = cloak_targets(py)
    wanted = set(args.platform or [])
    if wanted:
        targets = [t for t in targets if t[0] in wanted]
    if not targets:
        fail("no targets matched --platform")

    work = Path(tempfile.mkdtemp(prefix="rb-cloakbrowser-mirror-"))
    print(f"==> Using Python: {py}")
    print(f"==> Target: oss://{args.bucket}/{prefix}/")
    try:
        uploaded_sha: set[str] = set()
        for tag, version, archive in targets:
            rel_dir = f"chromium-v{version}"
            archive_oss = f"oss://{args.bucket}/{prefix}/{rel_dir}/{archive}"
            sha_oss = f"oss://{args.bucket}/{prefix}/{rel_dir}/SHA256SUMS"
            archive_urls = [
                f"{PRIMARY_BASE}/{rel_dir}/{archive}",
                f"{GITHUB_BASE}/{rel_dir}/{archive}",
            ]
            sha_urls = [
                f"{PRIMARY_BASE}/{rel_dir}/SHA256SUMS",
                f"{GITHUB_BASE}/{rel_dir}/SHA256SUMS",
            ]
            print(f"==> {tag}: {rel_dir}/{archive}")
            if args.dry_run:
                print(f"    archive sources: {archive_urls}")
                print(f"    checksum sources: {sha_urls}")
                print(f"    target: {archive_oss}")
                print(f"    checksum target: {sha_oss}")
                continue

            sha_key = rel_dir
            if sha_key not in uploaded_sha:
                if not args.force and oss_exists(args.ossutil, args.profile, sha_oss):
                    print(f"    checksum exists, skip: {sha_oss}")
                else:
                    sha_dest = work / f"{rel_dir}_SHA256SUMS"
                    used = download_first(sha_urls, sha_dest)
                    print(f"    checksum downloaded from: {used}")
                    run([args.ossutil, "cp", str(sha_dest), sha_oss, "--profile", args.profile, "-f"], timeout=1800)
                uploaded_sha.add(sha_key)

            if not args.force and oss_exists(args.ossutil, args.profile, archive_oss):
                print(f"    archive exists, skip: {archive_oss}")
                continue

            dest = work / archive
            used = download_first(archive_urls, dest)
            print(f"    archive downloaded from: {used}")
            run([args.ossutil, "cp", str(dest), archive_oss, "--profile", args.profile, "-f"], timeout=1800)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
