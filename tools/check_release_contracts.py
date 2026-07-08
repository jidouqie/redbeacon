#!/usr/bin/env python3
"""Release contract checks that must pass before publishing.

This is intentionally lightweight and offline. It catches drift in the release
flow before packages or scripts are uploaded to OSS.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import build_channel_skills

ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise SystemExit(f"xx {message}")


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        fail(f"缺少文件：{rel}")
    return path.read_text(encoding="utf-8")


def require(text: str, needle: str, rel: str, why: str) -> None:
    if needle not in text:
        fail(f"{rel} 缺少发布契约：{why}（需要包含 {needle!r}）")


def check_installers() -> None:
    sh = read("install/install.sh")
    ps1 = read("install/install.ps1")
    unsh = read("install/uninstall.sh")
    unps1 = read("install/uninstall.ps1")

    require(sh, 'codex_dir="$HOME/.codex/skills"', "install/install.sh", "Mac/Linux 安装必须写入 Codex 扫描目录")
    require(sh, 'install_codex_skills "$SRC"', "install/install.sh", "Mac/Linux 安装必须从 skill tarball 派生 Codex SKILL.md")
    require(ps1, 'Join-Path $HOME ".codex\\skills"', "install/install.ps1", "Windows 安装必须写入 Codex 扫描目录")
    require(ps1, "Write-CodexSkills $src.FullName", "install/install.ps1", "Windows 安装必须从 skill tarball 派生 Codex SKILL.md")

    require(unsh, 'CODEX_SKILL_DIR="$HOME/.codex/skills"', "install/uninstall.sh", "Mac/Linux 卸载必须清理对应通道 Codex skill")
    require(unps1, '$CodexSkillDir = "$HOME\\.codex\\skills"', "install/uninstall.ps1", "Windows 卸载必须清理对应通道 Codex skill")
    require(unsh, 'redbeacon-test*', "install/uninstall.sh", "测试版卸载只能动 redbeacon-test*")
    require(unps1, 'redbeacon-test*', "install/uninstall.ps1", "测试版卸载只能动 redbeacon-test*")


def _frontmatter_name(text: str) -> str:
    match = re.search(r"(?m)^name:\s*([A-Za-z0-9_.-]+)\s*$", text)
    return match.group(1) if match else ""


def _to_codex_skill(stem: str, text: str) -> str:
    body = text
    desc = f"RedBeacon ability: {stem}"
    if text.startswith("---"):
        match = re.match(r"(?s)^---\r?\n(.*?)\r?\n---\r?\n?", text)
        if match:
            head = match.group(1)
            body = text[match.end():]
            for line in head.splitlines():
                if line.strip().startswith("description:"):
                    desc = line.split("description:", 1)[1].strip().strip('"').strip("'")
                    break
    desc = desc.replace("\\", "\\\\").replace('"', '\\"')
    return f'---\nname: {stem}\ndescription: "{desc}"\nmetadata:\n  short-description: "{desc}"\n---\n\n{body}'


def check_channel_skills() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        stable = root / "stable"
        test = root / "test"
        stable_files = build_channel_skills.build("stable", stable)
        test_files = build_channel_skills.build("test", test)

        if not stable_files:
            fail("stable skill 为空")
        if not test_files:
            fail("test skill 为空")
        if len(stable_files) != len(test_files):
            fail(f"stable/test skill 数量不一致：{len(stable_files)} != {len(test_files)}")

        stable_names = {p.name for p in stable_files}
        test_names = {p.name for p in test_files}
        if "redbeacon.md" not in stable_names:
            fail("stable skill 必须包含 redbeacon.md")
        if "redbeacon-test.md" not in test_names:
            fail("test skill 必须包含 redbeacon-test.md")
        bad_test_names = sorted(n for n in test_names if not n.startswith("redbeacon-test"))
        if bad_test_names:
            fail(f"test skill 文件名必须全部是 redbeacon-test*：{', '.join(bad_test_names)}")

        for path in test_files:
            text = path.read_text(encoding="utf-8")
            if "redbeacon-test" not in text:
                fail(f"{path.name} 正文没有指向测试版命令 redbeacon-test")
            codex = _to_codex_skill(path.stem, text)
            if _frontmatter_name(codex) != path.stem:
                fail(f"{path.name} 派生 Codex SKILL.md 后 name 不等于文件名")


def main() -> None:
    check_installers()
    check_channel_skills()
    print("  ✓ 发布契约检查通过：installer/Codex skill/test skill 隔离都满足")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))
