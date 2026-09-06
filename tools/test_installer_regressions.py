#!/usr/bin/env python3
"""Exercise installer rollback code against disposable application directories.

The extracted production transaction runs real mv/rm commands, including an
actual permission-denied rename. No network, installed client, or user data is
used. Run with: python3 -m unittest discover -s tools -p test_installer_regressions.py
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "Unix installation transaction")
class UnixInstallerRollbackTests(unittest.TestCase):
    def run_transaction(self, installer: str, case: str) -> None:
        source = (ROOT / "install" / installer).read_text(encoding="utf-8")
        cleanup = source.split('FINAL_PATH=""\n', 1)[1].split(
            'mkdir -p "$BINDIR"', 1
        )[0]
        cleanup = 'FINAL_PATH=""\n' + cleanup
        placement = source.split('  APP="$HOME/Applications/$APP_NAME.app"\n', 1)[1]
        placement = placement.split('\nelse\n  DEST=', 1)[0]
        # Only the destination root changes; execute the production transaction
        # and EXIT cleanup without running the installer bootstrap or downloads.
        placement = '  APP="$FIXTURE_APPLICATIONS/$APP_NAME.app"\n' + placement
        placement = placement.replace('mkdir -p "$HOME/Applications"', 'mkdir -p "$FIXTURE_APPLICATIONS"')

        with tempfile.TemporaryDirectory(prefix="redbeacon-rollback-test-") as directory:
            fixture = Path(directory)
            applications = fixture / "Applications"
            applications.mkdir()
            app_name = "RedBeacon_test" if "-test" in installer else "RedBeacon"
            cmd_name = "redbeacon-test" if "-test" in installer else "redbeacon"
            old_app = applications / f"{app_name}.app"
            old_binary = old_app / "Contents" / "MacOS" / app_name
            bin_dir = fixture / "bin"
            bin_dir.mkdir()
            launcher = bin_dir / cmd_name
            existing = case != "fresh-health-failure"
            if existing:
                old_binary.parent.mkdir(parents=True)
                old_binary.write_bytes(b"old working executable\n")
                launcher.write_bytes(b"old working launcher\n")
            staged = fixture / "staged.app"
            staged.mkdir()
            (staged / "new-version").write_bytes(b"new executable\n")
            temp = fixture / "installer-temp"
            temp.mkdir()
            if case == "placement-failure":
                staged = fixture / "missing-staged.app"
            if case == "backup-permission-failure":
                applications.chmod(0o555)

            declarations = {
                "FIXTURE_APPLICATIONS": str(applications),
                "BINDIR": str(bin_dir),
                "CMD_NAME": cmd_name,
                "APP_NAME": app_name,
                "CLI_NAME": f"{cmd_name}-cli",
                "TMP": str(temp),
                "STAGED_APP": str(staged),
                "OS": "Darwin",
                "COMMITTED": "",
            }
            script = "set -uo pipefail\n" + "\n".join(
                f"{key}={shlex.quote(value)}" for key, value in declarations.items()
            )
            script += "\ndie() { printf '%s\\n' \"$*\" >&2; exit 1; }\n"
            script += "warn() { printf '%s\\n' \"$*\" >&2; }\n"
            script += "restore_skills() { :; }\nrefresh_macos_app_registration() { :; }\n"
            script += cleanup + placement
            script += "\nCOMMITTED=1\n" if case == "commit" else "\ndie simulated-health-failure\n"
            try:
                result = subprocess.run(
                    ["/bin/bash"], input=script, text=True, capture_output=True, check=False
                )
                if case == "commit":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue((old_app / "new-version").is_file())
                else:
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertFalse((old_app / "new-version").exists(), result.stderr)
                    if existing:
                        self.assertTrue(old_binary.is_file(), result.stderr)
                        self.assertEqual(old_binary.read_bytes(), b"old working executable\n")
                        self.assertEqual(launcher.read_bytes(), b"old working launcher\n")
                    else:
                        self.assertFalse(old_app.exists(), result.stderr)
                        self.assertFalse(launcher.exists(), result.stderr)
                    self.assertFalse(Path(f"{old_app}.redbeacon-rollback").exists(), result.stderr)
                if case == "backup-permission-failure":
                    self.assertIn("Permission denied", result.stderr)
                    self.assertIn("Could not back up the existing client", result.stderr)
                if case == "placement-failure":
                    self.assertIn("Could not place the new client", result.stderr)
                self.assertFalse(temp.exists(), result.stderr)
            finally:
                applications.chmod(0o755)

    def test_backup_permission_failure_preserves_old_executable(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("Requires unprivileged mv to exercise permission denial")
        for installer in ("install.sh", "install-test.sh"):
            with self.subTest(installer=installer):
                self.run_transaction(installer, "backup-permission-failure")

    def test_failed_new_placement_restores_old_app(self) -> None:
        for installer in ("install.sh", "install-test.sh"):
            with self.subTest(installer=installer):
                self.run_transaction(installer, "placement-failure")

    def test_failed_final_verification_restores_old_app(self) -> None:
        for installer in ("install.sh", "install-test.sh"):
            with self.subTest(installer=installer):
                self.run_transaction(installer, "health-failure")

    def test_failed_fresh_install_removes_new_app(self) -> None:
        for installer in ("install.sh", "install-test.sh"):
            with self.subTest(installer=installer):
                self.run_transaction(installer, "fresh-health-failure")

    def test_committed_app_is_not_removed_by_exit_trap(self) -> None:
        for installer in ("install.sh", "install-test.sh"):
            with self.subTest(installer=installer):
                self.run_transaction(installer, "commit")


if __name__ == "__main__":
    unittest.main()
