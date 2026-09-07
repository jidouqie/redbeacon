"""Public-checkout skill drift and non-destructive receipt retention checks."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import plan_release_receipts as receipts

spec = importlib.util.spec_from_file_location("workspace_sync", TOOLS / "sync-codex-skills.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class RepositoryArtifactTests(unittest.TestCase):
    def test_skill_check_works_in_public_checkout_without_private_cli_and_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tools").mkdir()
            for name in ("sync-codex-skills.py", "build_channel_skills.py"):
                shutil.copyfile(TOOLS / name, root / "tools" / name)
            source = root / ".claude" / "commands" / "redbeacon.md"
            source.parent.mkdir(parents=True)
            source.write_text('---\ndescription: demo\n---\n{{CLI}} {{DATA_DIR}}\n', encoding="utf-8")
            command = [sys.executable, str(root / "tools" / "sync-codex-skills.py")]
            subprocess.run([*command, "--workspace-only"], cwd=root, check=True, capture_output=True)
            output = root / ".agents" / "skills" / "source-command-redbeacon" / "SKILL.md"
            original = output.read_bytes()
            self.assertIn(b"redbeacon-channel: stable", original)
            for mutation in ("unchanged", "edit", "missing", "orphan"):
                with self.subTest(mutation=mutation):
                    output.write_bytes(original + (b"hand edit\n" if mutation == "edit" else b""))
                    if mutation == "missing":
                        output.unlink()
                    if mutation == "orphan":
                        orphan = output.parents[1] / "source-command-redbeacon-retired" / "SKILL.md"
                        orphan.parent.mkdir()
                        orphan.write_text("obsolete", encoding="utf-8")
                    before = {str(p.relative_to(root)): p.read_bytes()
                              for p in root.rglob("SKILL.md")}
                    result = subprocess.run([*command, "--check"], cwd=root, capture_output=True)
                    self.assertEqual(result.returncode, 0 if mutation == "unchanged" else 1)
                    self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes()
                                              for p in root.rglob("SKILL.md")})
            self.assertFalse((root / "cli").exists())

    def test_window_counts_versions_protects_old_canonical_and_retains_duplicate_receipts(self):
        items = [receipts.Receipt(f"{ch}-{version}", ch, f"0.1.{version}", f"COMPLETE_{ch.upper()}", True)
                 for ch in receipts.CHANNELS for version in (1, 2, 3, 4, 10)]
        items += [receipts.Receipt("test-rerun", "test", "0.1.10", "COMPLETE_TEST", True),
                  receipts.Receipt("stable-aborted", "stable", "0.1.11", "ABORTED", True),
                  receipts.Receipt("user-file", "test", "0.1.2", "COMPLETE_TEST", False)]
        result = receipts.plan(items, {"stable": "0.1.1", "test": "0.1.10"})
        self.assertTrue(result["read_only"])
        stable, test = (result["channels"][ch] for ch in receipts.CHANNELS)
        self.assertEqual(stable["retained_versions"], ["0.1.10", "0.1.4", "0.1.1"])
        self.assertEqual(test["retained_versions"], ["0.1.10", "0.1.4", "0.1.3"])
        self.assertIn("test-rerun", test["keep"])
        self.assertNotIn("stable-aborted", stable["outside_window_tracked"])
        self.assertNotIn("user-file", test["outside_window_tracked"])
        self.assertEqual(stable["manual_review"][0]["path"], "stable-aborted")
        self.assertEqual(test["manual_review"][0]["path"], "user-file")

    def test_unknown_or_missing_canonical_prevents_a_plan(self):
        for canonical in ({}, {"stable": "0.1.1"}, {"stable": "0.1.1", "test": "0.1.1"},
                          {"stable": "current", "test": "0.1.1"}):
            with self.subTest(canonical=canonical), self.assertRaises(ValueError):
                receipts.plan([], canonical)

    def test_receipt_parser_rejects_ambiguous_versions_and_wrong_channel(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "stable" / "receipt.md"
            path.parent.mkdir()
            text = '- channel: stable\n- result: COMPLETE_STABLE\n| app | 0.1.2 | application |\n'
            path.write_text(text, encoding="utf-8")
            self.assertEqual(receipts.read_receipt(path, root, {"stable/receipt.md"}).version, "0.1.2")
            for invalid in (text + '| app | 0.1.3 | application |\n', text.replace("channel: stable", "channel: test")):
                path.write_text(invalid, encoding="utf-8")
                with self.assertRaises(ValueError):
                    receipts.read_receipt(path, root, set())


if __name__ == "__main__":
    unittest.main()
