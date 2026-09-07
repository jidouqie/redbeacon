#!/usr/bin/env python3
"""开发态：把 stable skill 真源同步到 Codex 用户目录和仓库工作台。

- 真源唯一：长逻辑只在 .claude/commands/，本脚本只做派生，不反向写。
- 工作台副本使用公开构建器，与发布包共享 Agent Skills 转换逻辑；无需私有 CLI。
- 只有显式同步用户目录时才加载 CLI updater，保留既有用户目录同步行为。
- `.agents/skills/source-command-redbeacon*` 是仓库工作台副本，用 source-command 前缀
  避免覆盖用户已经安装的正式版/测试版 skill。
用法：  python tools/sync-codex-skills.py
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

from build_channel_skills import portable_skill_text, render_text

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / ".claude" / "commands"

def _workspace_skill(stem: str, md: str) -> tuple[str, str]:
    skill_md = portable_skill_text(stem, md)
    workspace_name = f"source-command-{stem}"
    skill_md = re.sub(r"(?m)^name:\s*[^\n]+$", f"name: {workspace_name}", skill_md, count=1)
    # Rewrite only slash-command references. Product URLs such as
    # /market/redbeacon have a word character before the slash and are kept.
    skill_md = re.sub(r"(?<![\w.-])/redbeacon", "/source-command-redbeacon", skill_md)
    return workspace_name, skill_md


def _workspace_outputs(files: list[Path]) -> dict[str, bytes]:
    outputs = {}
    for source in files:
        name, text = _workspace_skill(source.stem, render_text(source.read_text(encoding="utf-8"), "stable"))
        outputs[name] = text.encode("utf-8")
    return outputs


def check_workspace_skills(files: list[Path]) -> list[str]:
    """Compare bytes without creating files or loading the private CLI."""
    outputs = _workspace_outputs(files)
    directory = ROOT / ".agents" / "skills"
    errors = []
    for name, expected in outputs.items():
        path = directory / name / "SKILL.md"
        if not path.is_file() or path.read_bytes() != expected:
            errors.append(f"missing or stale: {path.relative_to(ROOT)}")
    for path in sorted(directory.glob("source-command-redbeacon*")):
        if path.name not in outputs:
            errors.append(f"orphan output: {path.relative_to(ROOT)}")
    return errors


def _sync_workspace_skills(files: list[Path]) -> tuple[list[tuple[str, str]], list[str]]:
    # Validate every source before touching any previously generated output.
    outputs = _workspace_outputs(files)
    workspace_dir = ROOT / ".agents" / "skills"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, str]] = []
    for name, skill_md in outputs.items():
        folder = workspace_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_bytes(skill_md)
        written.append((name.removeprefix("source-command-"), name))

    keep = {name for _stem, name in written}
    removed: list[str] = []
    for folder in sorted(workspace_dir.glob("source-command-redbeacon*")):
        if folder.is_dir() and folder.name not in keep:
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(folder.name)
    return written, removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-only", action="store_true",
        help="只刷新仓库 .agents/skills 副本，不修改用户 ~/.codex/skills",
    )
    parser.add_argument("--check", action="store_true", help="只读校验仓库副本，供公开 CI 使用")
    args = parser.parse_args(argv)
    files = sorted(SRC_DIR.glob("redbeacon*.md"))
    if not files:
        print(f"✗ 真源目录无 skill：{SRC_DIR}")
        return 1
    if args.check:
        errors = check_workspace_skills(files)
        for error in errors:
            print(error)
        if not errors:
            print(f"Workspace skills match all {len(files)} sources")
        return int(bool(errors))

    workspace_written, workspace_removed = _sync_workspace_skills(files)
    print(f"✓ 已派生 {len(workspace_written)} 个仓库 Codex skill → {ROOT / '.agents' / 'skills'}")
    if workspace_removed:
        print(f"🗑 清理了 {len(workspace_removed)} 个仓库旧 skill：{', '.join(workspace_removed)}")
    if args.workspace_only:
        return 0

    try:
        from redbeacon.services import updater
    except ImportError:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        from redbeacon.services import updater

    codex_dir = updater.find_codex_skill_dir()
    if codex_dir is None:
        print("! 没找到 ~/.codex/skills；仓库工作台已刷新，跳过用户目录。")
        return 0

    written = []
    for f in files:
        stem = f.stem  # 去 .md
        md = render_text(f.read_text(encoding="utf-8"), "stable")
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
