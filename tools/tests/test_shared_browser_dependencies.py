"""The release tree owns exactly one browser family for both target platforms."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import cloakbrowser
except ImportError:
    cloakbrowser = None


@unittest.skipIf(cloakbrowser is None, 'requires the locked CLI build environment')
class SharedBrowserDependencies(unittest.TestCase):
    def test_collector_requests_only_two_cloak_archives(self):
        import prepare_release_artifacts as prepare
        requested = []
        with patch.object(prepare, '_cached_download', side_effect=lambda **kw: requested.append(kw)):
            prepare._runtime_dependencies(Path('output'), Path('cache'))
        self.assertEqual(len(requested), 2)
        paths = [row['relative'] for row in requested]
        self.assertTrue(all(p.startswith('dependencies/cloakbrowser/') for p in paths))
        self.assertTrue(any('darwin-arm64' in p for p in paths))
        self.assertTrue(any('windows-x64' in p for p in paths))
        import check_release_artifacts as check
        check.check_runtime_archives(paths)
        for malformed in (paths[:1], paths + ['dependencies/playwright/unused.zip'],
                          [p.replace('windows-x64', 'windows-arm64') for p in paths]):
            with self.subTest(paths=malformed), self.assertRaises(SystemExit):
                check.check_runtime_archives(malformed)


if __name__ == '__main__':
    unittest.main()
