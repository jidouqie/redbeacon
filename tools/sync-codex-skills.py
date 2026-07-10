#!/usr/bin/env python3
"""开发态：把 stable skill 真源同步到 Codex 用户目录和仓库工作台。

- 真源唯一：长逻辑只在 .claude/commands/，本脚本只做派生，不反向写。
- 转换逻辑复用 CLI 的 redbeacon.services.updater（与 `redbeacon update` 用户机派生同一套），
  保证开发态与线上派生完全一致。
- `.agents/skills/source-command-redbeacon*` 是仓库工作台副本，用 source-command 前缀
  避免覆盖用户已经安装的正式版/测试版 skill。
用法：  python tools/sync-codex-skills.py
"""
import re
import shutil
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


def _workspace_skill(stem: str, md: str) -> tuple[str, str]:
    name, skill_md = updater.claude_md_to_codex_skill(stem, md)
    workspace_name = f"source-command-{name}"
    skill_md = re.sub(r"(?m)^name:\s*[^\n]+$", f"name: {workspace_name}", skill_md, count=1)
    # Rewrite only slash-command references. Product URLs such as
    # /market/redbeacon have a word character before the slash and are kept.
    skill_md = re.sub(r"(?<![\w.-])/redbeacon", "/source-command-redbeacon", skill_md)
    return workspace_name, skill_md


def _sync_workspace_skills(files: list[Path]) -> tuple[list[tuple[str, str]], list[str]]:
    workspace_dir = ROOT / ".agents" / "skills"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, str]] = []
    for f in files:
        name, skill_md = _workspace_skill(f.stem, f.read_text(encoding="utf-8"))
        folder = workspace_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(skill_md, encoding="utf-8")
        written.append((f.stem, name))

    keep = {name for _stem, name in written}
    removed: list[str] = []
    for folder in sorted(workspace_dir.glob("source-command-redbeacon*")):
        if folder.is_dir() and folder.name not in keep:
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(folder.name)
    return written, removed


def main() -> int:
    files = sorted(SRC_DIR.glob("redbeacon*.md"))
    if not files:
        print(f"✗ 真源目录无 skill：{SRC_DIR}")
        return 1

    workspace_written, workspace_removed = _sync_workspace_skills(files)
    print(f"✓ 已派生 {len(workspace_written)} 个仓库 Codex skill → {ROOT / '.agents' / 'skills'}")
    if workspace_removed:
        print(f"🗑 清理了 {len(workspace_removed)} 个仓库旧 skill：{', '.join(workspace_removed)}")

    codex_dir = updater.find_codex_skill_dir()
    if codex_dir is None:
        print("! 没找到 ~/.codex/skills；仓库工作台已刷新，跳过用户目录。")
        return 0

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
