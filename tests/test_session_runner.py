"""CPU-only orchestration contracts; no model imports or real shutdown."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'b-side'))
import e2e_lease
import session_runner as s

class SessionTests(unittest.TestCase):
    def setup_session(self, tmp):
        root=Path(tmp);repo=root/'repo';(repo/'b-side').mkdir(parents=True)
        (repo/'b-side/e2e_smoke.py').write_text('stub')
        stages=[]
        for i in range(3):
            plan=root/f'plan{i}.json';lease=root/f'lease{i}.json'
            plan.write_text(json.dumps(dict(entry='b-side/e2e_smoke.py',estimate_seconds=10,
                source_pins={'b-side/e2e_smoke.py':e2e_lease.sha(repo/'b-side/e2e_smoke.py')})))
            lease.write_text(json.dumps(dict(execution_authorized=True,protocol_approved=True,
                shutdown_verified=True,charge_start_epoch=0,deadline_epoch=3900,
                quoted_rate_cny_hour=1,max_rate_cny_hour=2.18,max_incremental_cny=3,
                incurred_cny=0,storage_reserve_cny=.5,instance_id='test',lease_id=f'lease{i}',
                plan_sha256=e2e_lease.sha(plan),data_root=str(root),output_path=str(root/f'out{i}'))))
            stages.append(dict(label=f'S{i}',plan=str(plan),lease=str(lease),entry='b-side/e2e_smoke.py'))
        return root,repo,stages

    def invoke(self,root,repo,stages,**kw):
        shutdown=Mock();watchdog=Mock();handle=Mock();watchdog.return_value=handle
        called=[]
        def supervise(command,payload,archive,seconds,shutdown):
            called.append(Path(payload).name)
            # Reuse the real archiver with a harmless local CPU child.
            return e2e_lease.supervise([sys.executable,'-c','print("synthetic stage")'],payload,archive,5,shutdown)
        opts=dict(shutdown_fn=shutdown,watchdog_fn=watchdog,supervise_fn=supervise,
            clock=lambda:100,repo=repo,hostname='autodl-container-test',
            validators={'b-side/e2e_smoke.py':lambda *args: {'status':'validated'}})
        opts.update(kw)
        result=s.run_session(stages,root,Path(sys.executable),3900,root/'session',**opts)
        return result,shutdown,watchdog,called,handle

    def test_order_archive_watchdog_and_exactly_one_final_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,repo,stages=self.setup_session(tmp)
            result,shutdown,watchdog,called,handle=self.invoke(root,repo,stages)
            self.assertEqual(called,['out0','out1','out2'])
            self.assertEqual(result['status'],'completed')
            shutdown.assert_called_once_with();watchdog.assert_called_once()
            for i in range(3):
                path=root/f'out{i}.private.tar.gz'
                self.assertTrue(e2e_lease.verify_archive(path));self.assertTrue(Path(str(path)+'.verified.json').exists())
            self.assertEqual(json.loads((root/'session/session-receipt.json').read_text())['status'],'completed')

    def test_failure_aborts_without_retry_and_preserves_partial_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,repo,stages=self.setup_session(tmp);calls=[]
            def fail(cmd,payload,archive,seconds,shutdown):
                calls.append(payload)
                return e2e_lease.supervise([sys.executable,'-c','raise RuntimeError("failed")'],payload,archive,5,shutdown)
            result,shutdown,watchdog,_,_=self.invoke(root,repo,stages,supervise_fn=fail)
            self.assertEqual(len(calls),1);shutdown.assert_called_once()
            self.assertEqual(result['status'],'failed_partial_no_retry')
            self.assertEqual([x['status'] for x in result['stages']][1:],['skipped','skipped'])
            self.assertTrue((root/'out0.private.tar.gz').exists())
            self.assertFalse((root/'out1').exists())

    def reject(self, mutate, deadline=3900):
        with tempfile.TemporaryDirectory() as tmp:
            root,repo,stages=self.setup_session(tmp);mutate(root,stages)
            with self.assertRaises(ValueError):s.validate_stages(stages,root,deadline,100,repo=repo,hostname='autodl-container-test',validators={'b-side/e2e_smoke.py':lambda *a:None})

    def test_unknown_entry_rejected(self):
        self.reject(lambda r,x:x[0].update(entry='b-side/unknown.py'))

    def test_window_over_7200_rejected(self):
        self.reject(lambda r,x:None,7301)

    def test_existing_output_rejected(self):
        self.reject(lambda r,x:(r/'out1').mkdir())

    def test_plan_tamper_rejected(self):
        self.reject(lambda r,x:(r/'plan0.json').write_text('{}'))

    def test_duplicate_lease_or_overlapping_output_rejected(self):
        def mutate(root,stages):
            p=root/'lease1.json';v=json.loads(p.read_text());v['output_path']=str(root/'out0'/'nested');p.write_text(json.dumps(v))
        self.reject(mutate)

    def test_watchdog_failure_still_shuts_down_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,repo,stages=self.setup_session(tmp);shutdown=Mock()
            result,*_=self.invoke(root,repo,stages,shutdown_fn=shutdown,watchdog_fn=Mock(side_effect=RuntimeError('unarmed')))
            self.assertEqual(result['status'],'failed_partial_no_retry');shutdown.assert_called_once()
            self.assertFalse((root/'out0').exists())

    def test_archive_verification_failure_aborts_following_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,repo,stages=self.setup_session(tmp)
            result,shutdown,*_=self.invoke(root,repo,stages,supervise_fn=lambda *a:dict(status='completed',returncode=0,timed_out=False))
            self.assertEqual(result['status'],'failed_partial_no_retry');shutdown.assert_called_once()
            self.assertFalse((root/'out1').exists())

class WatchdogLaunchTests(unittest.TestCase):
    def test_watchdog_is_independent_and_acknowledged_before_work(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt=root/'watch.json';child=Mock();child.poll.return_value=None
            def launch(command,**kwargs):
                self.assertIn('--deadline-epoch',command)
                self.assertTrue(kwargs['start_new_session'])
                receipt.write_text(json.dumps(dict(status='armed')))
                return child
            with patch.object(s.subprocess,'Popen',side_effect=launch) as popen:
                result=s.start_watchdog(3900,receipt,Path(sys.executable),root)
            self.assertIs(result,child);popen.assert_called_once()

    def test_failed_shutdown_retains_watchdog_as_backstop(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper=SessionTests();root,repo,stages=helper.setup_session(tmp)
            handle=Mock();handle.poll.return_value=None
            result,*_=helper.invoke(root,repo,stages,shutdown_fn=Mock(side_effect=RuntimeError('signal failed')),
                                   watchdog_fn=Mock(return_value=handle))
            self.assertEqual(result['shutdown_status'],'failed_watchdog_retained')
            handle.terminate.assert_not_called()

class SessionSafetyTests(unittest.TestCase):
    def test_watchdog_arms_before_expensive_input_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper=SessionTests();root,repo,stages=helper.setup_session(tmp);events=[]
            def validator(*args):events.append('validate')
            def watchdog(*args):events.append('watchdog');return Mock()
            helper.invoke(root,repo,stages,watchdog_fn=watchdog,validators={'b-side/e2e_smoke.py':validator})
            self.assertEqual(events[0],'watchdog')

    def test_receipt_disk_error_cannot_skip_final_shutdown(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            helper=SessionTests();root,repo,stages=helper.setup_session(tmp);shutdown=Mock()
            with patch.object(s.boot_watchdog,'save',side_effect=OSError('disk full')):
                try:helper.invoke(root,repo,stages,shutdown_fn=shutdown)
                except OSError:pass
            shutdown.assert_called_once_with()
