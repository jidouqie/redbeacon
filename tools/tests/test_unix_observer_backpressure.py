"""Only owned harmless Bash fixtures and pure process-table/pipe checks."""
from pathlib import Path
import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / 'smoke_unix_install_transaction.py'
spec = importlib.util.spec_from_file_location('staged_unix_smoke', SOURCE)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class ProcessTableTests(unittest.TestCase):
    def test_helper_gate_rejects_wrong_binary_path_filename_channel_or_mode(self):
        valid = '/bin/bash /private/tmp/redbeacon-test-uninstall.abc123/uninstall-core.sh test smoke'
        self.assertTrue(smoke._is_expected_uninstall_helper_command(valid, 'test'))
        for wrong in (valid.replace('/bin/bash', '/bin/sh'), valid.replace('/private/tmp/', '/tmp/'),
                      valid.replace('uninstall-core.sh', 'pretend-uninstall-core.sh'),
                      valid.replace(' test smoke', ' stable smoke'), valid.replace(' smoke', ' production')):
            with self.subTest(wrong=wrong):
                self.assertFalse(smoke._is_expected_uninstall_helper_command(wrong, 'test'))

    def test_parent_equal_argv_rows_are_excluded_even_below_helper(self):
        rows = ('10 1 /bin/sh /bin/sh wrapper.sh\n'
                '11 10 /bin/bash /bin/bash helper.sh test smoke\n'
                '12 11 /bin/bash /bin/bash helper.sh test smoke\n'
                '13 12 /bin/bash /bin/bash helper.sh test smoke\n'
                '14 11 python python worker.py\n'
                '15 14 /bin/sh /bin/sh renamed-stage.sh\n'
                '16 1 /bin/bash /bin/bash unrelated.sh\n'
                '17 10 /bin/sh /bin/sh wrapper.sh\n')
        with mock.patch.object(smoke.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, rows)):
            self.assertEqual(smoke._shell_descendants(10), {
                (11, '/bin/bash helper.sh test smoke'), (15, '/bin/sh renamed-stage.sh')})

    def test_failed_empty_or_unparseable_ps_never_becomes_zero_shells(self):
        for value in ((1, ''), (0, ''), (0, 'malformed')):
            with self.subTest(value=value), mock.patch.object(
                smoke.subprocess, 'run', return_value=subprocess.CompletedProcess([], *value)
            ), self.assertRaises(RuntimeError):
                smoke._shell_descendants(10)


class PipeTests(unittest.TestCase):
    def test_pipe_prefix_is_exact_and_pipe_is_completely_full(self):
        read_fd, write_fd, prefix = smoke._prefilled_stdout_pipe()
        try:
            self.assertGreater(len(prefix), 0)
            self.assertLess(len(prefix), 1024 * 1024)
            os.set_blocking(write_fd, False)
            with self.assertRaises(BlockingIOError):
                os.write(write_fd, b'x')
            received = bytearray()
            while len(received) < len(prefix):
                received.extend(os.read(read_fd, len(prefix) - len(received)))
            self.assertEqual(received, prefix)
        finally:
            os.close(read_fd); os.close(write_fd)

    def test_fill_limit_closes_both_file_descriptors(self):
        descriptors = os.pipe()
        with mock.patch.object(smoke.os, 'pipe', return_value=descriptors), mock.patch.object(
            smoke.os, 'write', side_effect=lambda _fd, body: len(body)
        ), self.assertRaisesRegex(RuntimeError, 'byte limit'):
            smoke._prefilled_stdout_pipe(maximum_bytes=8192)
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)


@unittest.skipUnless(sys.platform == 'darwin', 'macOS helper process observation')
class OwnedProcessTests(unittest.TestCase):
    def run_fixture(self, wrapper_text, helper_text='', **options):
        with tempfile.TemporaryDirectory(prefix='redbeacon-test-uninstall.', dir='/tmp') as directory:
            root = Path(directory).resolve()
            helper = root / 'uninstall-core.sh'
            helper.write_text(helper_text, encoding='utf-8')
            wrapper = root / 'wrapper.sh'
            wrapper.write_text(wrapper_text.replace('"HELPER"', '"HELPER" test smoke').replace('HELPER', str(helper)), encoding='utf-8')
            environment = dict(os.environ)
            before = dict(environment)
            parameters = dict(helper_observation_timeout=2, completion_timeout=2)
            parameters.update(options)
            try:
                return smoke._run_observed_entrypoint(
                    ['/bin/sh', str(wrapper)], env=environment,
                    hold_helper_output=True, expected_helper_channel='test', **parameters)
            finally:
                self.assertEqual(environment, before)

    def test_immediate_helper_is_observed_and_only_real_output_is_returned(self):
        result, shells = self.run_fixture(
            'trap ":" EXIT\n/bin/bash "HELPER"\n',
            "printf 'raw helper output\\n'\nprintf 'stderr output\\n' >&2\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'raw helper output\nstderr output\n')
        self.assertEqual(len(shells), 1, shells)
        self.assertIn('/bin/bash ', shells[0]['command'])
        self.assertIn('uninstall-core.sh test smoke', shells[0]['command'])
        self.assertNotIn('\0', result.stdout)

    def test_observer_failure_is_propagated_after_releasing_output(self):
        with mock.patch.object(smoke, '_shell_descendants', side_effect=OSError('injected ps failure')):
            with self.assertRaisesRegex(RuntimeError, 'observation failed'):
                self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n', "printf 'real output\\n'\n")

    def test_root_error_without_helper_is_drained_and_remains_a_failure(self):
        with mock.patch.object(smoke, '_shell_descendants', return_value=set()):
            with self.assertRaisesRegex(RuntimeError, 'root diagnostic'):
                self.run_fixture("printf 'root diagnostic\\n' >&2\nexit 7\n",
                                 helper_observation_timeout=0.1)

    def test_empty_root_exit_cannot_be_misreported_as_zero_success(self):
        with self.assertRaisesRegex(RuntimeError, 'not observed before output release'):
            self.run_fixture('exit 9\n')

    def test_helper_exit_code_is_preserved(self):
        result, shells = self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n',
                                         "printf 'expected failure\\n'\nexit 17\n")
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stdout, 'expected failure\n')
        self.assertEqual(len(shells), 1)

    def test_popen_failure_closes_prefilled_pipe(self):
        descriptors = os.pipe()
        with mock.patch.object(smoke, '_prefilled_stdout_pipe', return_value=(*descriptors, b'')), \
             mock.patch.object(smoke.subprocess, 'Popen', side_effect=OSError('spawn failed')), \
             self.assertRaisesRegex(OSError, 'spawn failed'):
            smoke._run_observed_entrypoint(['never-executed'], env={}, hold_helper_output=True,
                                           expected_helper_channel='test')
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_watcher_delayed_until_main_waits_cannot_miss_immediate_helper(self):
        real_event, real_thread = threading.Event, threading.Thread
        main_waiting = real_event()
        events = []
        class GateSeen(real_event):
            def wait(self, timeout=None):
                main_waiting.set()
                return super().wait(timeout)
        def make_event():
            value = real_event() if not events else GateSeen()
            events.append(value)
            return value
        def make_thread(*args, **kwargs):
            if kwargs['target'].__name__ == 'watch':
                original = kwargs['target']
                def delayed_watch():
                    if not main_waiting.wait(1):
                        raise AssertionError('main never reached the observation gate')
                    original()
                kwargs['target'] = delayed_watch
            return real_thread(*args, **kwargs)
        with mock.patch.object(smoke, 'threading', SimpleNamespace(Event=make_event, Thread=make_thread)):
            result, shells = self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n',
                                             "printf 'immediate output\\n'\n")
        self.assertTrue(main_waiting.is_set())
        self.assertEqual(result.stdout, 'immediate output\n')
        self.assertEqual(len(shells), 1, shells)

    def test_completion_timeout_terminates_and_reaps_owned_root(self):
        original_popen = subprocess.Popen
        processes = []
        def record_popen(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            if kwargs.get('start_new_session'):
                processes.append(process)
            return process
        with mock.patch.object(smoke.subprocess, 'Popen', side_effect=record_popen):
            with self.assertRaisesRegex(RuntimeError, 'completion timeout'):
                self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n',
                                 "printf 'helper before loop\\n'\nwhile :; do :; done\n",
                                 completion_timeout=0.1)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].returncode)

    def test_watcher_construction_failure_cleans_owned_process_and_fds(self):
        before = set(os.listdir('/dev/fd'))
        with mock.patch.object(smoke.threading, 'Thread', side_effect=RuntimeError('thread unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'thread unavailable'):
                self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n', "printf 'output\\n'\n")
        self.assertEqual(set(os.listdir('/dev/fd')), before)

    def test_slow_sampler_is_joined_while_main_already_reports_timeout(self):
        sampler_finished = threading.Event()
        def slow_sampler(_pid):
            # Deliberately model one in-flight ps call outliving the gate.
            threading.Event().wait(0.15)
            sampler_finished.set()
            return set()
        with mock.patch.object(smoke, '_shell_descendants', side_effect=slow_sampler):
            with self.assertRaisesRegex(RuntimeError, 'not observed before output release'):
                self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n', "printf 'output\\n'\n",
                                 helper_observation_timeout=0.02)
        self.assertTrue(sampler_finished.is_set())

    def test_wrong_shell_first_does_not_release_output_and_is_still_recorded(self):
        actual_sampler = smoke._shell_descendants
        calls = []
        reader_started = threading.Event()
        real_thread = threading.Thread
        def make_thread(*args, **kwargs):
            if kwargs['target'].__name__ == 'drain':
                reader_started.set()
            return real_thread(*args, **kwargs)
        def sample(pid):
            calls.append(pid)
            if len(calls) == 1:
                return {(987654321, '/bin/sh wrong-stage.sh')}
            if len(calls) == 2:
                self.assertFalse(reader_started.is_set(), 'wrong shell released output')
            return actual_sampler(pid)
        with mock.patch.object(smoke, '_shell_descendants', side_effect=sample), \
             mock.patch.object(smoke.threading, 'Thread', side_effect=make_thread):
            result, shells = self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n', "printf 'output\\n'\n")
        self.assertEqual(result.returncode, 0)
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(len(shells), 2, shells)  # The enclosing one-helper gate must reject this inventory.

    def test_cleanup_wait_error_does_not_skip_reader_or_watcher_join(self):
        original_popen, real_thread = subprocess.Popen, threading.Thread
        threads = []
        before = set(os.listdir('/dev/fd'))
        def record_popen(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            if kwargs.get('start_new_session'):
                original_wait = process.wait
                calls = []
                def fail_wait(*a, **k):
                    calls.append(1)
                    if len(calls) == 1:
                        raise RuntimeError('injected main wait failure')
                    original_wait(*a, **k)  # Really reap the owned process first.
                    raise OSError('injected cleanup wait failure')
                process.wait = fail_wait
            return process
        def record_thread(*args, **kwargs):
            thread = real_thread(*args, **kwargs)
            threads.append(thread)
            return thread
        with mock.patch.object(smoke.subprocess, 'Popen', side_effect=record_popen), \
             mock.patch.object(smoke.threading, 'Thread', side_effect=record_thread):
            with self.assertRaisesRegex(RuntimeError, 'observer cleanup failed') as raised:
                self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n',
                                 "printf 'output\\n'\nwhile :; do :; done\n")
        self.assertIsInstance(raised.exception.__cause__, OSError)
        self.assertTrue(threads)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(set(os.listdir('/dev/fd')), before)

    def test_output_reader_start_failure_cleans_owned_process_and_fds(self):
        real_thread = threading.Thread
        before = set(os.listdir('/dev/fd'))
        def make_thread(*args, **kwargs):
            thread = real_thread(*args, **kwargs)
            if kwargs['target'].__name__ == 'drain':
                thread.start = mock.Mock(side_effect=RuntimeError('reader unavailable'))
            return thread
        with mock.patch.object(smoke.threading, 'Thread', side_effect=make_thread):
            with self.assertRaisesRegex(RuntimeError, 'reader unavailable'):
                self.run_fixture('trap ":" EXIT\n/bin/bash "HELPER"\n', "printf 'output\\n'\n")
        self.assertEqual(set(os.listdir('/dev/fd')), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
