#!/usr/bin/env python3
"""Build RedBeacon skill files for a release channel.

Stable publishes the source commands as-is. Test publishes a separately named
skill set that calls the test CLI, so it cannot drive the stable installation by
accident.
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / ".claude" / "commands"
CENTRAL_ORIGIN = "https://bytestaff-download-releases.oss-cn-shanghai.aliyuncs.com"
STABLE_MANIFEST_URL = f"{CENTRAL_ORIGIN}/projects/redbeacon/stable/latest.json"
TEST_MANIFEST_URL = f"{CENTRAL_ORIGIN}/projects/redbeacon/test/latest.json"


def test_skill_name(stem: str) -> str:
    if stem == "redbeacon":
        return "redbeacon-test"
    if stem.startswith("redbeacon-"):
        return "redbeacon-test-" + stem[len("redbeacon-"):]
    return stem


def skill_names(channel: str) -> list[str]:
    files = sorted(p for p in SRC_DIR.glob("redbeacon*.md"))
    if not files:
        raise SystemExit(f"{SRC_DIR} 下没有 redbeacon*.md 命令文件")
    files.sort(key=lambda p: (p.name != "redbeacon.md", p.name))
    if channel == "test":
        return [test_skill_name(p.stem) + ".md" for p in files]
    return [p.name for p in files]


def transform_test_text(text: str) -> str:
    # The product slug is shared by both channels. Protect the canonical URL
    # while command names and channel-owned local paths are rewritten below.
    manifest_token = "__REDBEACON_TEST_CANONICAL_MANIFEST__"
    text = text.replace(STABLE_MANIFEST_URL, manifest_token)
    text = re.sub(r"(?<![\w/-])/redbeacon(?!-test)(-[A-Za-z0-9]+)?",
                  lambda m: "/redbeacon-test" + (m.group(1) or ""), text)
    text = re.sub(r"(?<![A-Za-z0-9_.-])redbeacon(?![A-Za-z0-9_.-])",
                  "redbeacon-test", text)
    text = text.replace("~/.redbeacon", "~/.redbeacon_test")
    text = text.replace("~/.bytestaff", "~/.bytestaff_test")
    text = text.replace("/stable/latest.json", "/test/latest.json")
    text = text.replace("/install.ps1", "/install-test.ps1")
    text = text.replace("/install.sh", "/install-test.sh")
    text = text.replace(manifest_token, TEST_MANIFEST_URL)
    return text


def build(channel: str, out_dir: Path) -> list[Path]:
    commands_dir = out_dir / ".claude" / "commands"
    if commands_dir.exists():
        shutil.rmtree(commands_dir)
    commands_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    files = sorted(p for p in SRC_DIR.glob("redbeacon*.md"))
    files.sort(key=lambda p: (p.name != "redbeacon.md", p.name))
    for src in files:
        name = test_skill_name(src.stem) + ".md" if channel == "test" else src.name
        text = src.read_text(encoding="utf-8")
        if channel == "test":
            text = transform_test_text(text)
        dest = commands_dir / name
        dest.write_text(text, encoding="utf-8")
        written.append(dest)
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=["stable", "test"], required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    written = build(args.channel, Path(args.out_dir))
    print(f"wrote {len(written)} {args.channel} skill files to {Path(args.out_dir).resolve()}")


if __name__ == "__main__":
    main()
