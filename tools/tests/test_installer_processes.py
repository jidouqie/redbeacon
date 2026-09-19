"""Exercise the installed-channel stop boundary with real disposable processes."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
INSTALLERS = ("install.sh", "install-test.sh")


def stop_functions(installer: str) -> str:
    source = (ROOT / "install" / installer).read_text(encoding="utf-8")
    return source[source.index("running_redbeacon_pids() {"):source.index("backup_business_database() {")]


@unittest.skipUnless(sys.platform == "darwin", "macOS executable-path process matching")
class MacInstallerProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="rb installer stop ")
        cls.root = Path(cls.temporary.name)
        source = cls.root / "probe.c"
        source.write_text(r'''
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stopping = 0;
static void terminate(int signal_number) { stopping = 1; }
int main(int argc, char **argv) {
    signal(SIGTERM, strcmp(argv[1], "ignore") == 0 ? SIG_IGN : terminate);
    FILE *ready = fopen(argv[2], "w"); fputs("ready", ready); fclose(ready);
    while (!stopping) pause();
    if (strcmp(argv[1], "delayed") == 0) {
        struct timespec delay = {2, 0};
        while (nanosleep(&delay, &delay) != 0) {}
    }
    FILE *closed = fopen(argv[3], "w"); fputs("closed", closed); fclose(closed);
    return 0;
}
''', encoding="ascii")
        cls.binary = cls.root / "probe"
        subprocess.run(["/usr/bin/clang", "-o", str(cls.binary), str(source)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def launch(self, path: Path, mode: str = "normal"):
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.binary, path)
        ready, closed = path.with_suffix(".ready"), path.with_suffix(".closed")
        process = subprocess.Popen([str(path), mode, str(ready), str(closed)])
        self.addCleanup(self.cleanup_process, process)
        deadline = time.monotonic() + 5
        while not ready.exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                self.fail("disposable process did not become ready")
            time.sleep(0.02)
        return process, closed

    @staticmethod
    def cleanup_process(process):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)

    def script(self, installer, app, cli):
        return ("set -uo pipefail\nEXECUTION_MODE=production\n"
                f"APP_NAME={shlex.quote(app)}\nCLI_NAME={shlex.quote(cli)}\n"
                'say() { :; }\ndie() { printf "%s\\n" "$*" >&2; exit 1; }\n'
                + stop_functions(installer))

    def test_waits_for_final_write_and_leaves_other_channel_and_unrelated_renderers_running(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                directory = self.root / uuid.uuid4().hex
                stem = "RBP" + uuid.uuid4().hex[:7]
                app, other = (stem + "_test", stem) if "-test" in installer else (stem, stem + "_test")
                cli = app + "-cli"
                binaries = directory / f"{app}.app" / "Contents" / "MacOS"
                target, closed = self.launch(binaries / app, "delayed")
                target_cli, _ = self.launch(binaries / cli)
                renderer, _ = self.launch(binaries / "RedBeaconRenderer")
                opposite, _ = self.launch(directory / f"{other}.app" / "Contents" / "MacOS" / "RedBeaconRenderer")
                opposite_app, _ = self.launch(directory / f"{other}.app" / "Contents" / "MacOS" / other)
                unrelated, _ = self.launch(directory / "unrelated" / "RedBeaconRenderer")
                script = self.script(installer, app, cli) + '\nstop_running_redbeacon\n'
                # A database snapshot can start only after the shutdown's last write.
                script += f'test -f {shlex.quote(str(closed))} || exit 91\n'
                result = subprocess.run(["/bin/bash"], input=script, text=True, capture_output=True, timeout=25)
                self.assertEqual(result.returncode, 0, result.stderr)
                for process in (target, target_cli, renderer):
                    self.assertEqual(process.wait(timeout=2), 0)
                for process in (opposite, opposite_app, unrelated):
                    self.assertIsNone(process.poll(), "another channel or application was stopped")
                    self.cleanup_process(process)

    def test_force_stop_rechecks_that_ignoring_process_really_exited(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                app = "RBK" + uuid.uuid4().hex[:7]
                process, _ = self.launch(self.root / f"{app}.app" / "Contents" / "MacOS" / "RedBeaconRenderer", "ignore")
                script = self.script(installer, app, app + "-cli") + '\nstop_running_redbeacon\n'
                result = subprocess.run(["/bin/bash"], input=script, text=True, capture_output=True, timeout=25)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(process.wait(timeout=2), -9)

    def test_unstoppable_process_blocks_snapshot_and_replacement(self):
        script = self.script("install.sh", "RBMissing", "RBMissing-cli")
        # Failed termination remains visible to the exact production wait loop.
        script += '\nrunning_redbeacon_pids() { printf "99999999\\n"; }\n'
        script += 'stop_running_redbeacon\nprintf "unsafe-snapshot"\n'
        result = subprocess.run(["/bin/bash"], input=script, text=True, capture_output=True, timeout=25)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not exit", result.stderr)
        self.assertNotIn("unsafe-snapshot", result.stdout)

    def test_process_inspection_error_blocks_snapshot(self):
        for installer in INSTALLERS:
            script = self.script(installer, "RBMissing", "RBMissing-cli")
            script += '\nrunning_redbeacon_pids() { return 1; }\nstop_running_redbeacon\nprintf "unsafe-snapshot"\n'
            result = subprocess.run(["/bin/bash"], input=script, text=True, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Could not inspect", result.stderr)
            self.assertNotIn("unsafe-snapshot", result.stdout)


@unittest.skipIf(os.name == "nt", "Bash installer PATH hint")
class InstallerPathHintTests(unittest.TestCase):
    def test_hint_uses_callers_original_path_and_execution_keeps_trusted_path(self):
        bindir = "/Users/test person/.local/bin"
        for installer in INSTALLERS:
            source = (ROOT / "install" / installer).read_text(encoding="utf-8")
            capture = source[source.index('INSTALLER_CALLER_PATH='):source.index('LC_ALL="C"')]
            start = source.index('case ":$INSTALLER_CALLER_PATH:" in')
            hint = source[start:source.index('\nesac', start) + len('\nesac')]
            for caller_path, warned in ((f"/usr/bin:{bindir}:/bin", False),
                                        (f"/usr/bin:{bindir}-other:/bin", True), ("", True)):
                with self.subTest(installer=installer, caller_path=caller_path):
                    script = capture + f'\nBINDIR={shlex.quote(bindir)}\nCMD_NAME=redbeacon\n'
                    script += 'warn() { printf "PATH-WARNING\\n"; }\n' + hint
                    script += '\ntest "$PATH" = "/usr/bin:/bin:/usr/sbin:/sbin"\n'
                    result = subprocess.run(["/bin/bash"], input=script, text=True, capture_output=True,
                                            env={**os.environ, "PATH": caller_path, "INSTALLER_CALLER_PATH": "poison"})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual("PATH-WARNING" in result.stdout, warned)


if __name__ == "__main__":
    unittest.main()
