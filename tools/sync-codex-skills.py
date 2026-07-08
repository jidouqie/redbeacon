#!/usr/bin/env python3
"""开发态：把 .claude/commands/redbeacon*.md（真源）派生同步到 Codex 端 ~/.codex/skills/。

- 真源唯一：长逻辑只在 .claude/commands/，本脚本只做派生，不反向写。
- 转换逻辑复用 CLI 的 redbeacon.services.updater（与 `redbeacon update` 用户机派生同一套），
  保证开发态与线上派生完全一致。
用法：  python tools/sync-codex-skills.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / ".claude" / "commands"

# 复用 CLI 包里的转换/定位逻辑（editable 安装下可直接 import；否则把 cli/src 加进 path）
try:
    from redbeacon.services import updater
except ImportError:
    sys.path.insert(0, str(ROOT / "cli" / "src"))
    from redbeacon.services import updater


def main() -> int:
    codex_dir = updater.find_codex_skill_dir()
    if codex_dir is None:
        print("✗ 没找到 ~/.codex/skills（本机未安装 Codex？）。建好该目录或装 Codex 后再跑。")
        return 1

    files = sorted(SRC_DIR.glob("redbeacon*.md"))
    if not files:
        print(f"✗ 真源目录无 skill：{SRC_DIR}")
        return 1

    written = []
    for f in files:
        stem = f.stem  # 去 .md
        md = f.read_text(encoding="utf-8")
        name, skill_md = updater.claude_md_to_codex_skill(stem, md)
        folder = codex_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(skill_md, encoding="utf-8")
        written.append((stem, name))

    # 清理孤儿：删掉真源里已不存在的旧 redbeacon* skill 目录（如封存/改名后残留），
    # 让 Codex 端与真源严格一致（与 `redbeacon update` 用户机清理逻辑对齐）。
    import shutil
    keep = {name for _stem, name in written}
    removed = []
    for d in sorted(codex_dir.glob("redbeacon*")):
        if d.name.startswith("redbeacon-test"):
            continue
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d.name)

    print(f"✓ 已从真源 {SRC_DIR} 派生 {len(written)} 个 Codex skill → {codex_dir}")
    for stem, name in written:
        tag = "  (ASCII 别名)" if stem != name else ""
        print(f"   {stem}  →  {name}/SKILL.md{tag}")
    if removed:
        print(f"🗑 清理了 {len(removed)} 个已不在真源的旧 skill：{', '.join(removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
