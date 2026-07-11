#!/usr/bin/env python3
"""生成版本清单 latest.json（升级检查的单一事实源）。

version 取自 CLI 的 __version__（cli/src/redbeacon/__init__.py），
skill_files 扫描 .claude/commands，避免手工维护漂移。
完整发布流程见根 CLAUDE.md「打包 / 交付」：客户端包先由 GitHub Actions 打包上传 OSS，
本脚本只负责 latest.json 内容。

用法（在 redbeacon 仓根目录）：
    python tools/gen_latest.py --notes "本次更新说明" --skill-sha256 <64位哈希>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OSS_BASE = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com"
sys.path.insert(0, str(ROOT / "tools"))

from build_channel_skills import skill_names  # noqa: E402


def read_version() -> str:
    init = ROOT / "cli" / "src" / "redbeacon" / "__init__.py"
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"未能从 {init} 解析 __version__")
    return m.group(1)


def skill_prefix(channel: str) -> str:
    return "skill-test" if channel == "test" else "skill"


def skill_raw_base(channel: str, version: str) -> str:
    prefix = "skill-test" if channel == "test" else "skill"
    return f"{OSS_BASE}/{prefix}/releases/{version}/commands"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=["stable", "test"], default="stable", help="发布通道")
    ap.add_argument("--notes", default="", help="更新说明（人话，给用户看）")
    ap.add_argument(
        "--app-sha256",
        action="append",
        default=[],
        metavar="PLAT=SHA256",
        help="客户端整包哈希，如 win-x64=<64位sha256>；可重复传",
    )
    ap.add_argument(
        "--skill-sha256",
        required=True,
        help="与该版本客户端绑定的 skill tarball SHA-256",
    )
    ap.add_argument("--out", default="", help="输出文件；默认 stable=latest.json, test=latest-test.json")
    args = ap.parse_args()
    out = args.out or str(ROOT / ("latest-test.json" if args.channel == "test" else "latest.json"))

    app_sha256: dict[str, str] = {}
    for item in args.app_sha256:
        if "=" not in item:
            raise SystemExit(f"--app-sha256 格式应为 PLAT=SHA256：{item}")
        plat, sha = item.split("=", 1)
        plat, sha = plat.strip(), sha.strip().lower()
        if not plat or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise SystemExit(f"--app-sha256 不合法：{item}")
        app_sha256[plat] = sha

    version = read_version()
    skill_sha256 = args.skill_sha256.strip().lower()
    if len(skill_sha256) != 64 or any(c not in "0123456789abcdef" for c in skill_sha256):
        raise SystemExit("--skill-sha256 必须是 64 位十六进制 SHA-256")
    app_prefix = "app/test" if args.channel == "test" else "app"
    app_name = "RedBeacon_test" if args.channel == "test" else "RedBeacon"
    skill_release_prefix = f"{skill_prefix(args.channel)}/releases/{version}"
    manifest = {
        "channel": args.channel,
        "version": version,
        "notes": args.notes,
        "skill_version": version,
        "skill_bundle_url": f"{OSS_BASE}/{skill_release_prefix}/redbeacon-skill.tar.gz",
        "skill_sha256": skill_sha256,
        "skill_raw_base": skill_raw_base(args.channel, version),
        "skill_files": skill_names(args.channel),
    }
    if app_sha256:
        manifest["app_sha256"] = app_sha256
        manifest["app"] = {
            plat: {
                "url": f"{OSS_BASE}/{app_prefix}/releases/{version}/{app_name}-{plat}.zip",
                "sha256": sha,
            }
            for plat, sha in app_sha256.items()
        }
    Path(out).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写 {out}：channel={args.channel}, version={manifest['version']}, "
          f"{len(manifest['skill_files'])} 个 skill 文件")


if __name__ == "__main__":
    main()
