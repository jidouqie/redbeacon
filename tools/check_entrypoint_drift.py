#!/usr/bin/env python3
"""Read-only stable/test entrypoint comparison against exact audited differences."""
from __future__ import annotations

import difflib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = Path(__file__).with_name("entrypoint-channel-differences.json")
EXPECTED_PAIRS = {"install.sh", "install.ps1", "uninstall.sh", "uninstall.ps1"}


def compare_pair(stable: str, test: str, rules: list[dict], *, name: str) -> None:
    for index, rule in enumerate(rules):
        if not rule.get("reason") or not rule["stable"] or not rule["test"]:
            raise ValueError(f"{name}: invalid allowlist rule {index + 1}")
        # Pin whole lines and exact occurrence counts. No global stable/test
        # substitution can mask an extra branch, altered condition or command.
        for channel, text in (("stable", stable), ("test", test)):
            literal = rule[channel]
            if not literal.endswith("\n") or text.count(literal) != 1:
                raise ValueError(f"{name}: {channel} identity rule {index + 1} missing or duplicated")
        marker = f"<audited-channel-difference-{index + 1}>\n"
        stable = stable.replace(rule["stable"], marker)
        test = test.replace(rule["test"], marker)
    if stable != test:
        diff = list(difflib.unified_diff(stable.splitlines(), test.splitlines(),
                                        fromfile=name, tofile=name + " (test)", lineterm=""))
        raise ValueError("unapproved entrypoint drift:\n" + "\n".join(diff[:80]))


def check_all(root: Path = ROOT) -> int:
    contract = json.loads(RULES.read_text(encoding="utf-8"))
    pairs = contract["pairs"]
    if contract.get("schema") != 1 or set(pairs) != EXPECTED_PAIRS:
        raise ValueError("entrypoint drift contract must cover all four stable/test pairs")
    for name, pair in pairs.items():
        stem, suffix = name.rsplit(".", 1)
        if pair["test"] != f"{stem}-test.{suffix}":
            raise ValueError(f"{name}: invalid test entrypoint name")
        left = (root / "install" / name).read_text(encoding="utf-8")
        right = (root / "install" / pair["test"]).read_text(encoding="utf-8")
        compare_pair(left, right, pair["rules"], name=name)
    return len(pairs)


def main() -> None:
    try:
        count = check_all()
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"entrypoint drift: {count} channel pairs match the exact allowlist (read only)")


if __name__ == "__main__":
    main()
