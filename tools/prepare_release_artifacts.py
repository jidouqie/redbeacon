#!/usr/bin/env python3
"""Build the clean, publication-agnostic RedBeacon artifact tree."""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import io
import json
import os
import shutil
import tarfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from cloakbrowser.config import DOWNLOAD_BASE_URL, PLATFORM_CHROMIUM_VERSIONS

from redbeacon import __version__
from redbeacon.services.browser_downloads import DownloadSource, download_resumable
from redbeacon.services.browser_engine import _playwright_archive_url


ROOT = Path(__file__).resolve().parent.parent
CLOAKBROWSER_ARCHIVE_SUFFIXES = {
    "darwin-arm64": ".tar.gz",
    "windows-x64": ".zip",
}


@contextmanager
def _environment(name: str, value: str | None):
    previous = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _load_skill_builder():
    path = ROOT / "tools" / "build_channel_skills.py"
    spec = importlib.util.spec_from_file_location("redbeacon_skill_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the channel skill builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file() or source.stat().st_size <= 0:
        raise RuntimeError(f"release input is missing or empty: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o644)


def _skill_bundle(channel: str, version: str, output: Path) -> None:
    builder = _load_skill_builder()
    staging = output.parent / ".skill-staging"
    staging.mkdir(parents=True)
    files = builder.build(channel, staging)
    manifest = {
        "schema": 2,
        "channel": channel,
        "version": version,
        "files": [path.name for path in files],
        "assistants": list(builder.SUPPORTED_ASSISTANTS),
        "portable_skills": [
            path.relative_to(staging).as_posix()
            for path in sorted((staging / "agent-skills").glob("*/SKILL.md"))
        ],
    }
    metadata = staging / "redbeacon-skill-manifest.json"
    metadata.write_text(
        json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                members = [metadata, *sorted(
                    (path for path in staging.rglob("*") if path.is_file() and path != metadata),
                    key=lambda item: item.relative_to(staging).as_posix(),
                )]
                for source in sorted(members, key=lambda item: item.relative_to(staging).as_posix()):
                    relative = source.relative_to(staging).as_posix()
                    info = tarfile.TarInfo(relative)
                    body = source.read_bytes()
                    info.size = len(body)
                    info.mode = 0o644
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(body))
    shutil.rmtree(staging)
    output.chmod(0o644)


def _cached_download(
    *,
    sources: list[DownloadSource],
    relative: str,
    cache_root: Path,
    output_root: Path,
) -> None:
    cache_path = cache_root / relative
    print(f"Preparing runtime dependency: {relative}", flush=True)
    archive = download_resumable(
        sources,
        cache_path,
        artifact_key=relative,
        progress=lambda payload: print(
            f"  {payload.get('source', '')} {payload.get('progress', '')}% {payload.get('message', '')}",
            flush=True,
        ) if payload.get("phase") in {"source", "source_error", "verify"} else None,
    )
    _copy(archive, output_root / relative)


def _cloakbrowser_archive_url(platform_tag: str) -> str:
    """Return the locked upstream archive for one explicit target platform.

    CloakBrowser can temporarily ship different Chromium versions per platform.
    Its public helper chooses the host platform for both version and extension,
    so a macOS release process must not use that helper to derive Windows URLs.
    """
    try:
        version = PLATFORM_CHROMIUM_VERSIONS[platform_tag]
        suffix = CLOAKBROWSER_ARCHIVE_SUFFIXES[platform_tag]
    except KeyError as exc:
        raise RuntimeError(f"unsupported CloakBrowser release target: {platform_tag}") from exc

    base = DOWNLOAD_BASE_URL.rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("CloakBrowser release origin must be a plain HTTPS URL")
    filename = f"cloakbrowser-{platform_tag}{suffix}"
    return f"{base}/chromium-v{version}/{filename}"


def _runtime_dependencies(output: Path, cache_root: Path) -> None:
    for platform_override in (None, "win64"):
        with _environment("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", platform_override):
            official = _playwright_archive_url(None)
        path = urlsplit(official).path.lstrip("/")
        relative = f"dependencies/playwright/{path}"
        sources = [
            DownloadSource(
                f"https://registry.npmmirror.com/-/binary/playwright/{path}",
                "npmmirror-playwright-1",
                trust_env=True,
            ),
            DownloadSource(
                f"https://cdn.npmmirror.com/binaries/playwright/{path}",
                "npmmirror-playwright-2",
                trust_env=True,
            ),
            DownloadSource(official, "playwright-official", trust_env=True),
        ]
        _cached_download(
            sources=sources,
            relative=relative,
            cache_root=cache_root,
            output_root=output,
        )

    for platform_tag in CLOAKBROWSER_ARCHIVE_SUFFIXES:
        url = _cloakbrowser_archive_url(platform_tag)
        path = urlsplit(url).path.lstrip("/")
        relative = f"dependencies/cloakbrowser/{path}"
        _cached_download(
            sources=[DownloadSource(url, "cloakbrowser-official", trust_env=True)],
            relative=relative,
            cache_root=cache_root,
            output_root=output,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=("test", "stable"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--dependency-cache",
        type=Path,
        default=Path.home() / "Library" / "Caches" / "RedBeaconBuild" / "release-dependencies",
    )
    args = parser.parse_args()

    if args.version != __version__:
        raise SystemExit(f"version mismatch: requested {args.version}, CLI reports {__version__}")
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")
    args.output_dir.mkdir(parents=True, mode=0o755)

    app_name = "RedBeacon_test" if args.channel == "test" else "RedBeacon"
    for platform_name in ("mac-arm64", "win-x64"):
        filename = f"{app_name}-{platform_name}.zip"
        _copy(args.package_dir / filename, args.output_dir / "packages" / filename)

    for name in (
        "install.sh",
        "install.ps1",
        "install-test.sh",
        "install-test.ps1",
        "uninstall.sh",
        "uninstall.ps1",
        "uninstall-test.sh",
        "uninstall-test.ps1",
    ):
        _copy(ROOT / "install" / name, args.output_dir / "installers" / name)

    _skill_bundle(
        args.channel,
        args.version,
        args.output_dir / "skill" / "redbeacon-skill.tar.gz",
    )
    _runtime_dependencies(args.output_dir, args.dependency_cache)

    provenance = ROOT / "release" / "release-contract.json"
    _copy(provenance, args.output_dir / "metadata" / "release-contract.json")
    for directory in [args.output_dir, *args.output_dir.rglob("*")]:
        if directory.is_dir():
            directory.chmod(0o755)
    print(args.output_dir.resolve())


if __name__ == "__main__":
    main()
