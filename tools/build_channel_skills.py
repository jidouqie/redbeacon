#!/usr/bin/env python3
"""Build RedBeacon skill files for a release channel.

Both channels render the same named-placeholder sources. Channel-owned literals
in source prose are rejected, so new paths cannot silently escape substitution.
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
SUPPORTED_ASSISTANTS = (
    "claude-code",
    "codex",
    "openclaw",
    "hermes",
    "workbuddy",
)


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


def channel_variables(channel: str) -> dict[str, str]:
    if channel not in {"stable", "test"}:
        raise ValueError(f"unsupported skill channel: {channel}")
    test = channel == "test"
    cli = "redbeacon-test" if test else "redbeacon"
    suffix = "-test" if test else ""
    return {
        "CLI": cli,
        "DATA_DIR": "~/.redbeacon_test" if test else "~/.redbeacon",
        "TOKEN_DIR": "~/.bytestaff_test" if test else "~/.bytestaff",
        "MANIFEST_URL": TEST_MANIFEST_URL if test else STABLE_MANIFEST_URL,
        "INSTALL_URL": f"https://bytestaff.jiomig.com/{cli}/install",
        "INSTALL_PS1_KEY": f"installers/install{suffix}.ps1",
        "INSTALL_SH_KEY": f"installers/install{suffix}.sh",
        "APP_NAME": "RedBeacon_test" if test else "RedBeacon",
        "COPY_CONTRACT": "redbeacon_copy_v1",
    }


_PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
_SOURCE_LITERAL = re.compile(
    r"redbeacon|\.bytestaff|installers/install|/(?:stable|test)/latest\.json"
    r"|RedBeacon[_-](?:test|<plat>)"
)


def validate_rendered(text: str, channel: str) -> None:
    variables = channel_variables(channel)
    if "{{" in text or re.search(r"\b[A-Z][A-Z0-9_]*}}", text):
        raise ValueError("unresolved skill placeholder")
    # The central manifest's product slug is deliberately shared. Exempt only
    # the exact current-channel URL, never arbitrary paths containing the slug.
    checked = text.replace(variables["MANIFEST_URL"], "").replace(variables["COPY_CONTRACT"], "")
    other = channel_variables("stable" if channel == "test" else "test")
    forbidden = [other[key] for key in ("MANIFEST_URL", "INSTALL_URL", "INSTALL_PS1_KEY", "INSTALL_SH_KEY")]
    if any(value in checked for value in forbidden):
        raise ValueError(f"{channel} skill contains another channel's download coordinates")
    if channel == "test":
        pattern = (r"(?<![A-Za-z0-9_.-])redbeacon(?!-test(?:$|[^A-Za-z0-9_]))"
                   r"|\.redbeacon(?!_test(?:$|[^A-Za-z0-9_]))"
                   r"|\.bytestaff(?!_test(?:$|[^A-Za-z0-9_]))")
    else:
        pattern = r"redbeacon-test|\.redbeacon_test|\.bytestaff_test|RedBeacon_test"
    if re.search(pattern, checked):
        raise ValueError(f"{channel} skill contains another channel's command or directory")


def render_text(text: str, channel: str) -> str:
    variables = channel_variables(channel)
    literal = _SOURCE_LITERAL.search(text)
    if literal:
        raise ValueError(f"channel literal must use a named placeholder: {literal.group()}")

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in variables:
            raise ValueError(f"unknown skill placeholder: {name}")
        return variables[name]

    rendered = _PLACEHOLDER.sub(replace, text)
    validate_rendered(rendered, channel)
    return rendered


def portable_skill_text(stem: str, text: str) -> str:
    """Convert one command source into the shared Agent Skills format.

    Codex, OpenClaw, Hermes and WorkBuddy all consume a directory containing
    SKILL.md. Keep their bytes identical so one host cannot silently drift from
    another during an install or update.
    """
    description = ""
    body = text
    if text.startswith("---\n"):
        match = re.match(r"\A---\n(?P<head>.*?)\n---\n?", text, flags=re.DOTALL)
        if match:
            body = text[match.end():]
            for line in match.group("head").splitlines():
                if line.strip().startswith("description:"):
                    description = line.split("description:", 1)[1].strip().strip('"').strip("'")
                    break
    description = description or f"RedBeacon ability: {stem}"
    short = description.split(" — ", 1)[0].split("—", 1)[0].strip()[:60] or stem

    def yaml_quote(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return (
        "---\n"
        f"name: {stem}\n"
        f"description: {yaml_quote(description)}\n"
        "metadata:\n"
        f"  short-description: {yaml_quote(short)}\n"
        "  redbeacon-channel: " + ("test" if stem.startswith("redbeacon-test") else "stable") + "\n"
        "---\n\n"
        + body.lstrip("\n")
    )


def build(channel: str, out_dir: Path) -> list[Path]:
    files = sorted(SRC_DIR.glob("redbeacon*.md"), key=lambda p: (p.name != "redbeacon.md", p.name))
    if not files:
        raise ValueError(f"no skill sources in {SRC_DIR}")
    # Validate the complete input before replacing any existing output tree.
    rendered = [(src, render_text(src.read_text(encoding="utf-8"), channel)) for src in files]
    commands_dir = out_dir / ".claude" / "commands"
    portable_dir = out_dir / "agent-skills"
    for directory in (commands_dir, portable_dir):
        if directory.exists():
            shutil.rmtree(directory)
    commands_dir.mkdir(parents=True, exist_ok=True)
    portable_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for src, text in rendered:
        name = test_skill_name(src.stem) + ".md" if channel == "test" else src.name
        dest = commands_dir / name
        dest.write_text(text, encoding="utf-8")
        skill_name = Path(name).stem
        skill_folder = portable_dir / skill_name
        skill_folder.mkdir(parents=True, exist_ok=True)
        (skill_folder / "SKILL.md").write_text(
            portable_skill_text(skill_name, text),
            encoding="utf-8",
        )
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
