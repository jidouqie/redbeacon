#!/usr/bin/env python3
"""生成版本清单 latest.json（升级检查的单一事实源）。

version 取自 CLI 的 __version__（cli/src/redbeacon/__init__.py），
skill_files 扫描 .claude/commands，避免手工维护漂移。
完整发布流程见根 CLAUDE.md「打包 / 交付」：客户端包先由 GitHub Actions 打包上传 OSS，
本脚本只负责 latest.json 内容。

用法（在 redbeacon 仓根目录）：
    python tools/gen_latest.py --notes "本次更新说明"
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OSS_BASE = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com"


def read_version() -> str:
    init = ROOT / "cli" / "src" / "redbeacon" / "__init__.py"
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"未能从 {init} 解析 __version__")
    return m.group(1)


def list_skill_files() -> list[str]:
    cmd_dir = ROOT / ".claude" / "commands"
    files = sorted(p.name for p in cmd_dir.glob("*.md"))
    if not files:
        raise SystemExit(f"{cmd_dir} 下没有 .md 命令文件")
    files.sort(key=lambda n: (n != "redbeacon.md", n))  # 主入口排最前
    return files


def skill_raw_base(channel: str) -> str:
    prefix = "skill-test" if channel == "test" else "skill"
    return f"{OSS_BASE}/{prefix}/commands"


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

    manifest = {
        "channel": args.channel,
        "version": read_version(),
        "notes": args.notes,
        "skill_raw_base": skill_raw_base(args.channel),
        "skill_files": list_skill_files(),
    }
    if app_sha256:
        manifest["app_sha256"] = app_sha256
    Path(out).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写 {out}：channel={args.channel}, version={manifest['version']}, "
          f"{len(manifest['skill_files'])} 个 skill 文件")


if __name__ == "__main__":
    main()
