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
# skill 也走阿里云 OSS（散装 md，供 redbeacon update 逐个拉）——彻底不依赖 GitHub。
RAW_BASE = "https://bytestaff-redbeacon.oss-cn-shanghai.aliyuncs.com/skill/commands"


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes", default="", help="更新说明（人话，给用户看）")
    ap.add_argument("--out", default=str(ROOT / "latest.json"))
    args = ap.parse_args()

    manifest = {
        "version": read_version(),
        "notes": args.notes,
        "skill_raw_base": RAW_BASE,
        "skill_files": list_skill_files(),
    }
    Path(args.out).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写 {args.out}：version={manifest['version']}, "
          f"{len(manifest['skill_files'])} 个 skill 文件")


if __name__ == "__main__":
    main()
