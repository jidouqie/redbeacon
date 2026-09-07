#!/usr/bin/env python3
"""Read-only inventory of the three-version receipt window; never prune files."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "docs/download-node/releases"
MAX_VERSIONS = 3
CHANNELS = ("stable", "test")


@dataclass(frozen=True)
class Receipt:
    path: str
    channel: str
    version: str
    status: str
    tracked: bool


def version_key(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"unsupported version: {version}")
    return tuple(map(int, version.split(".")))


def read_receipt(path: Path, root: Path, tracked: set[str]) -> Receipt:
    relative = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    versions = set(re.findall(r"^\|\s*app\s*\|\s*(\d+\.\d+\.\d+)\s*\|", text, re.M))
    if not versions:
        versions = set(re.findall(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"', text))
    channels = re.findall(r"^- channel: (\w+)\s*$", text, re.M)
    statuses = re.findall(r"^- result: ([A-Z_]+)\s*$", text, re.M)
    if len(versions) != 1 or channels != [path.parent.name] or len(statuses) != 1:
        raise ValueError(f"ambiguous receipt metadata; review manually: {relative}")
    return Receipt(relative, channels[0], versions.pop(), statuses[0], relative in tracked)


def inventory(root: Path) -> list[Receipt]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", f"{PREFIX}/*/*.md"],
        cwd=root, check=True, capture_output=True,
    )
    tracked = set(result.stdout.decode("utf-8").split("\0")) - {""}
    # Do not search historical archives, other documents or user data.
    return [read_receipt(path, root, tracked) for channel in CHANNELS
            for path in sorted((root / PREFIX / channel).glob("*.md"))]


def plan(receipts: list[Receipt], canonical: dict[str, str]) -> dict:
    if set(canonical) != set(CHANNELS):
        raise ValueError("supply the canonical version for both stable and test")
    groups = {}
    for channel in CHANNELS:
        current = canonical[channel]
        version_key(current)
        members = [item for item in receipts if item.channel == channel]
        completed = [item for item in members if item.status == f"COMPLETE_{channel.upper()}"]
        versions = sorted({item.version for item in completed}, key=version_key, reverse=True)
        if current not in versions:
            raise ValueError(f"{channel} canonical {current} has no complete local receipt; no plan")
        kept = {current, *[version for version in versions if version != current][:MAX_VERSIONS - 1]}
        groups[channel] = {
            "canonical_version": current,
            "retained_versions": sorted(kept, key=version_key, reverse=True),
            "keep": [item.path for item in completed if item.version in kept],
            "outside_window_tracked": [item.path for item in completed
                                       if item.version not in kept and item.tracked],
            "manual_review": [{"path": item.path, "status": item.status, "tracked": item.tracked}
                              for item in members if item not in completed or not item.tracked],
        }
    return {"read_only": True, "max_versions_per_channel": MAX_VERSIONS,
            "tracked_receipts": sum(item.tracked for item in receipts), "channels": groups}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-version", action="append", required=True, metavar="CHANNEL=VERSION",
                        help="version verified from the small canonical manifest or current publication result")
    args = parser.parse_args()
    canonical = {}
    try:
        for item in args.canonical_version:
            channel, version = item.split("=", 1)
            if channel in canonical:
                raise ValueError(f"duplicate canonical channel: {channel}")
            canonical[channel] = version
        print(json.dumps(plan(inventory(ROOT), canonical), ensure_ascii=False, indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
