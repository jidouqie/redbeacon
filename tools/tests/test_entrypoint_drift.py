"""Mutation regressions for the protected entrypoint read-only drift checker."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_entrypoint_drift as checker


class EntrypointDriftTests(unittest.TestCase):
    def setUp(self):
        self.pairs = json.loads(checker.RULES.read_text(encoding="utf-8"))["pairs"]

    def contents(self, name):
        pair = self.pairs[name]
        return ((checker.ROOT / "install" / name).read_text(encoding="utf-8"),
                (checker.ROOT / "install" / pair["test"]).read_text(encoding="utf-8"), pair["rules"])

    def test_current_pairs_pass_without_writing_protected_files(self):
        paths = [checker.ROOT / "install" / name for name in self.pairs]
        paths += [checker.ROOT / "install" / pair["test"] for pair in self.pairs.values()]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        self.assertEqual(checker.check_all(), 4)
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})

    def test_unilateral_new_code_or_condition_changes_fail(self):
        for name in self.pairs:
            stable, test, rules = self.contents(name)
            mutations = [test + '\nexit 0\n', test.replace('latest.json', 'stale.json', 1)]
            condition = '-ne 0' if name.endswith('.ps1') else '[ "$#" -eq 0 ]'
            changed = condition.replace('0', '1')
            if condition in test:
                mutations.append(test.replace(condition, changed, 1))
            for mutated in mutations:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    checker.compare_pair(stable, mutated, rules, name=name)

    def test_even_constant_lines_cannot_hide_executable_changes(self):
        for name in self.pairs:
            stable, test, rules = self.contents(name)
            rule = next(rule for rule in rules if not rule['test'].startswith('#'))
            altered = rule['test'].rstrip('\n') + '; exit 0\n'
            with self.subTest(name=name), self.assertRaises(ValueError):
                checker.compare_pair(stable, test.replace(rule['test'], altered), rules, name=name)

    def test_same_wrong_channel_or_duplicated_identity_fails(self):
        for name in self.pairs:
            stable, test, rules = self.contents(name)
            for mutated in (stable, test + rules[0]['test']):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    checker.compare_pair(stable, mutated, rules, name=name)


if __name__ == '__main__':
    unittest.main()
