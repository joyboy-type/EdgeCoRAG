"""CPU contracts for the independent boot watchdog; nothing is signalled for real."""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'b-side'))
import boot_watchdog as watchdog


def fake_proc(root, pids=('1234',)):
    for pid in pids:
        entry = Path(root)/pid
        entry.mkdir(parents=True)
        (entry/'comm').write_text('supervisord\n')
        (entry/'cmdline').write_bytes(b'/usr/bin/python3\x00/init/supervisor/supervisor.ini\x00')
    return Path(root)


class SupervisorContracts(unittest.TestCase):
    def test_exactly_one_platform_supervisor_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = fake_proc(Path(d))
            self.assertEqual(watchdog.supervisor_pid(root), 1234)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                watchdog.supervisor_pid(root)
        with tempfile.TemporaryDirectory() as d:
            root = fake_proc(Path(d), ('1234', '5678'))
            with self.assertRaises(ValueError):
                watchdog.supervisor_pid(root)

    def test_unrelated_processes_are_not_targeted(self):
        with tempfile.TemporaryDirectory() as d:
            root = fake_proc(Path(d), ())
            other = root/'999'
            other.mkdir()
            (other/'comm').write_text('python3\n')
            (other/'cmdline').write_bytes(b'python3\x00script.py\x00')
            with self.assertRaises(ValueError):
                watchdog.supervisor_pid(root)

    def test_shutdown_signals_the_supervisor_and_waits(self):
        with tempfile.TemporaryDirectory() as d:
            root = fake_proc(Path(d))
            signalled = []
            def kill(pid, sig):
                signalled.append((pid, sig))
                shutil.rmtree(root/str(pid))
            self.assertEqual(watchdog.shutdown(root, kill=kill, sync=False, pause=0), 1234)
            self.assertEqual(signalled, [(1234, 15)])


class WatchContracts(unittest.TestCase):
    def test_fires_only_at_the_deadline_and_records_it(self):
        with tempfile.TemporaryDirectory() as d:
            receipt = Path(d)/'watchdog.json'
            now = [1000.]
            fired = []
            def clock(): return now[0]
            def sleep(seconds): now[0] += seconds
            def shutdown_fn():
                fired.append(now[0])
                return 4242
            result = watchdog.watch(1060., receipt, poll_seconds=10., clock=clock,
                                    sleep=sleep, shutdown_fn=shutdown_fn)
            self.assertEqual(fired, [1060.])
            self.assertEqual(result['status'], 'shut_down')
            self.assertEqual(result['supervisor_pid'], 4242)
            self.assertEqual(result['deadline_epoch'], 1060.)
            self.assertEqual(json.loads(receipt.read_text())['status'], 'shut_down')

    def test_already_past_deadline_fires_immediately(self):
        with tempfile.TemporaryDirectory() as d:
            receipt = Path(d)/'watchdog.json'
            fired = []
            result = watchdog.watch(900., receipt, clock=lambda: 1000.,
                                    sleep=lambda seconds: None,
                                    shutdown_fn=lambda: fired.append(1) or 7)
            self.assertEqual(fired, [1])
            self.assertEqual(result['fired_epoch'], 1000.)

    def test_failed_shutdown_is_recorded_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            receipt = Path(d)/'watchdog.json'
            calls = []
            def shutdown_fn():
                calls.append(1)
                raise OSError('no supervisor')
            with self.assertRaises(OSError):
                watchdog.watch(900., receipt, clock=lambda: 1000.,
                               sleep=lambda seconds: None, shutdown_fn=shutdown_fn)
            self.assertEqual(calls, [1])
            recorded = json.loads(receipt.read_text())
            self.assertEqual(recorded['status'], 'shutdown_failed_no_retry')
            self.assertEqual(recorded['error_type'], 'OSError')

    def test_cli_refuses_a_stale_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            result = subprocess.run([sys.executable, str(REPO/'b-side/boot_watchdog.py'),
                                     '--deadline-epoch', str(time.time()-60),
                                     '--receipt', str(Path(d)/'w.json')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('must be in the future', result.stderr)


if __name__ == '__main__':
    unittest.main()
