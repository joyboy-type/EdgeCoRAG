"""CPU contracts; CUDA calls alone are replaced by a deterministic runtime."""
import json
import os
import sys
import tempfile
import unittest
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'b-side'))
import e2e_smoke as e
import e2e_lease as guard


def query(i=0):
    return {'qid':str(i),'split':'smoke_20','question':'Which?',
            'choices':dict(A='a',B='b',C='c',D='d'),
            'query_image':{'path':'q.jpg','sha256':'self','size':[1,1]}}


def clean_env(**values):
    """Environment without inherited thread variables, plus the given ones."""
    base = {k: v for k, v in os.environ.items() if k not in e.THREAD_ENV_VARS}
    base.update(values)
    return base


class Runtime:
    synthetic = True
    def __init__(self, fail=False):
        self.t = 0.; self.fail = fail
    def sync(self): self.t += .25
    def reset_peak(self): pass
    def peak(self): return {'allocated_bytes':17,'reserved_bytes':23}
    def encode(self, q): self.t += 1.; return [1,0]
    def rank(self, v):
        self.t += 2.
        order = ['image:self'] + list('abcdefghijk')
        return order, [10. - .5 * i for i in range(len(order))]
    def search(self, v): return self.rank(v)[0]
    def utility(self,q,pool): self.t += 3.; return dict(zip(pool,range(10)))
    def infer(self,row):
        self.t += 4.
        if self.fail: raise RuntimeError('GPU failed')
        return {'final_output':'','final_extraction_error':None,'synthetic':True,
                'cuda_memory':{'process_allocator_peak_allocated':31,
                               'process_allocator_peak_reserved':37}}


class SmokeContracts(unittest.TestCase):
    def test_snapshot_contains_every_offline_adapter_import_dependency(self):
        repo=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            for name in e.REQUIRED_SOURCES:
                target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/name,target)
            p=subprocess.run([sys.executable,'-c','import model_adapters'],cwd=dest/'b-side',capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)

    def test_request_outer_timer_and_no_self_replenishment(self):
        r=Runtime(); corpus={c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'}
        result=e.request(query(),corpus,'utility',r,clock=lambda:r.t)
        self.assertEqual(result['candidate_ids'],list('abcdefghij'))
        self.assertEqual(result['selected_ids'],list('hij'))
        self.assertEqual(result['end_to_end_seconds'],11.25)
        self.assertEqual(result['memory']['allocated_bytes'],31)
        self.assertEqual(result['memory']['reserved_bytes'],37)
        self.assertEqual(result['final_output'],'')

    def test_duplicate_pool_and_short_pool_rejected(self):
        for ids in ([*'abcdefghij','a'],list('abc')):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                e.no_self_pool(ids,'self')

    def test_request_records_ranking_margins_and_query_vector_fingerprint(self):
        r=Runtime(); corpus={c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'}
        result=e.request(query(),corpus,'cosine',r,clock=lambda:r.t)
        evidence=result['ranking']
        self.assertEqual(evidence['candidate_ids'],list('abcdefghij'))
        self.assertEqual(evidence['top10_scores'],[9.5-i*.5 for i in range(10)])
        self.assertEqual(len(evidence['top10_adjacent_gaps']),9)
        self.assertAlmostEqual(evidence['boundary_gap'],.5)
        self.assertEqual(evidence['self_rank'],0)
        fingerprint=result['query_vector_fingerprint']
        self.assertEqual(fingerprint['dimension'],2)
        self.assertEqual(len(fingerprint['sha256']),64)

    def test_ranking_evidence_rejects_inconsistent_ranking(self):
        order,score='a b c d e f g h i j k'.split(),[10.-i for i in range(11)]
        with self.assertRaises(ValueError): e.ranking_evidence(order,score[:-1],'self')
        with self.assertRaises(ValueError): e.ranking_evidence(order,[0.,1.,*score[2:]],'self')
        with self.assertRaises(ValueError): e.ranking_evidence(order[:5],score[:5],'self')
        with self.assertRaises(ValueError): e.ranking_evidence(['a']*11,score,'self')
        with self.assertRaises(ValueError):
            e.ranking_evidence(order,[float('nan'),*score[1:]],'self')

    def test_schedule_has_unique_measured_keys_and_alternates(self):
        rows=e.schedule([query(i) for i in range(5)])
        measured=[x for x in rows if not x['warmup']]
        self.assertEqual(len(rows),32)
        self.assertEqual(len(measured),30)
        self.assertEqual(len({(x['qid'],x['strategy'],x['repeat']) for x in measured}),30)
        self.assertEqual([x['strategy'] for x in measured[:4]],['cosine','utility','utility','cosine'])

    def test_labels_and_holdout_rejected_before_runtime(self):
        for q in (dict(query(),answer='A'),dict(query(),split='internal_holdout')):
            with self.assertRaises(ValueError): e.schedule([q]*5)

    def test_partial_failure_preserves_warmup_and_never_retries(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'new'
            with self.assertRaises(RuntimeError):
                e.run([query(i) for i in range(5)],
                      {c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'},
                      out,Runtime(fail=True))
            receipt=json.loads((out/'receipt.json').read_text())
            self.assertEqual(receipt['status'],'failed_partial_no_retry')
            rows=[json.loads(x) for x in (out/'requests.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['error_type'],'RuntimeError')

    def test_success_excludes_warmups_and_does_not_invent_p95(self):
        corpus={c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'new'
            receipt=e.run([query(i) for i in range(5)],corpus,out,Runtime())
            self.assertEqual(receipt['completed_requests'],32)
            self.assertEqual(receipt['measured_requests'],30)
            self.assertIsNone(receipt['p95_seconds'])
            with self.assertRaises(FileExistsError):
                e.run([query(i) for i in range(5)],corpus,out,Runtime())

    def test_lease_counts_boot_and_fixed_preservation_reserve(self):
        lease=dict(execution_authorized=True,protocol_approved=True,shutdown_verified=True,
                   charge_start_epoch=1000,deadline_epoch=3700,quoted_rate_cny_hour=2.18,
                   max_rate_cny_hour=2.18,max_incremental_cny=3,incurred_cny=0,
                   storage_reserve_cny=.5)
        self.assertEqual(e.check_lease(lease,1100,1000),2000)
        for change in ({'execution_authorized':False},{'charge_start_epoch':1200},
                       {'deadline_epoch':1000+e.MAX_LEASE_SECONDS+1},{'max_incremental_cny':1}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                e.check_lease(dict(lease,**change),1100,1000)
        with self.assertRaises(ValueError): e.check_lease(lease,2500,1000)

    def test_consolidated_session_window_is_supported(self):
        lease=dict(execution_authorized=True,protocol_approved=True,shutdown_verified=True,
                   charge_start_epoch=1000,deadline_epoch=1000+3900,quoted_rate_cny_hour=1.48,
                   max_rate_cny_hour=2.18,max_incremental_cny=3,incurred_cny=0,
                   storage_reserve_cny=.5)
        self.assertEqual(e.check_lease(lease,1300,1200),1000+3900-1300-600)

    def test_shutdown_follows_verified_partial_archive_on_child_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);payload=root/'payload';payload.mkdir()
            events=[]
            result=guard.supervise([sys.executable,'-c',
                'from pathlib import Path; Path("partial").write_text("kept"); raise SystemExit(7)'],
                payload,root/'result.tar.gz',10,lambda:events.append('shutdown'))
            self.assertEqual(result['returncode'],7)
            self.assertEqual(events,['shutdown'])
            self.assertTrue(guard.verify_archive(root/'result.tar.gz'))

    def test_timeout_stops_child_and_preserves_results(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);payload=root/'payload';payload.mkdir();events=[]
            result=guard.supervise([sys.executable,'-c','import time; time.sleep(20)'],
                payload,root/'result.tar.gz',.05,lambda:events.append('shutdown'))
            self.assertTrue(result['timed_out'])
            self.assertEqual(events,['shutdown'])
            self.assertTrue(guard.verify_archive(root/'result.tar.gz'))

    def test_plan_rejects_drift_in_index_images_sources_and_order(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=root/'repo';repo.mkdir()
            for name in e.REQUIRED_SOURCES:
                p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'code')
            (root/'q.jpg').write_bytes(b'image');(root/'index.npy').write_bytes(b'index')
            ref=dict(path='q.jpg',sha256=e.file_sha(root/'q.jpg'),size=[1,1])
            queries=[dict(query(i),query_image=ref) for i in range(5)]
            plan=dict(queries=queries,corpus={c:ref for c in 'abcdefghijk'},corpus_order=list('abcdefghijk'),
                      index=dict(path='index.npy',sha256=e.file_sha(root/'index.npy')),
                      source_pins={name:e.file_sha(repo/name) for name in e.REQUIRED_SOURCES},
                      retriever=dict(e.RETRIEVER_SPEC),estimate_seconds=1000,cpu_threads=4,
                      entry=e.ENTRY,status='prepared_unexecuted',execution_authorized=False)
            self.assertEqual(e.validate_plan(plan,root,repo)['questions'],5)
            for mutation in ('index','image','source','order','holdout','threads_missing','threads_bad','entry'):
                changed=deepcopy(plan)
                if mutation=='index':changed['index']['sha256']='0'*64
                if mutation=='image':changed['queries'][0]['query_image']['sha256']='0'*64
                if mutation=='source':changed['source_pins'].pop(e.REQUIRED_SOURCES[0])
                if mutation=='order':changed['corpus_order'][0]='unknown'
                if mutation=='holdout':changed['queries'][0]['split']='internal_holdout'
                if mutation=='threads_missing':changed.pop('cpu_threads')
                if mutation=='threads_bad':changed['cpu_threads']=0
                if mutation=='entry':changed['entry']='b-side/e2e_cost.py'
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):e.validate_plan(changed,root,repo)

    def test_plan_accepts_affinity_thread_selection(self):
        plan=json.loads(json.dumps(dict(cpu_threads='affinity')))
        self.assertEqual(e.resolve_cpu_threads(plan['cpu_threads'],cpu_count=lambda:6,affinity=lambda:4),4)
        with self.assertRaises(ValueError): e.resolve_cpu_threads('auto')
        with self.assertRaises(ValueError): e.resolve_cpu_threads(True)


class ThreadConfiguration(unittest.TestCase):
    """The historical smoke inherited an unparsable OMP_NUM_THREADS and never recorded it."""

    def test_invalid_inherited_value_is_recorded_then_overridden(self):
        env=clean_env(OMP_NUM_THREADS='auto',MKL_NUM_THREADS='4')
        receipt=e.configure_cpu_threads(4,env)
        self.assertEqual(receipt['invalid_inherited'],{'OMP_NUM_THREADS':'auto'})
        self.assertEqual(receipt['inherited']['OMP_NUM_THREADS'],'auto')
        self.assertEqual(receipt['inherited']['MKL_NUM_THREADS'],'4')
        for name in e.THREAD_ENV_VARS:
            if name=='OMP_THREAD_LIMIT': continue
            self.assertEqual(env[name],'4')
        self.assertEqual(receipt['requested'],4)

    def test_empty_and_padded_values_count_as_invalid(self):
        for raw in ('','4 ',' 4','four','0','-2','4.0','+4'):
            with self.subTest(raw=raw):
                env=clean_env(OMP_NUM_THREADS=raw)
                receipt=e.configure_cpu_threads(2,env)
                self.assertIn('OMP_NUM_THREADS',receipt['invalid_inherited'])
                self.assertEqual(env['OMP_NUM_THREADS'],'2')

    def test_thread_limit_capping_the_request_is_rejected(self):
        with self.assertRaises(ValueError):
            e.configure_cpu_threads(4,clean_env(OMP_THREAD_LIMIT='2'))

    def test_invalid_thread_limit_is_removed_and_recorded(self):
        env=clean_env(OMP_THREAD_LIMIT='lots')
        receipt=e.configure_cpu_threads(3,env)
        self.assertNotIn('OMP_THREAD_LIMIT',env)
        self.assertEqual(receipt['removed_invalid'],{'OMP_THREAD_LIMIT':'lots'})

    def test_requested_threads_must_be_a_real_positive_integer(self):
        for value in (0,-1,True,4.0,'4',None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                e.configure_cpu_threads(value,clean_env())

    def test_vector_distance_detects_identical_and_shifted_vectors(self):
        same=e.vector_distance([1.,0.,-2.],[1.,0.,-2.])
        self.assertTrue(same['bitwise_equal'])
        self.assertEqual((same['l2'],same['linf']),(0.,0.))
        self.assertAlmostEqual(same['cosine'],1.)
        shifted=e.vector_distance([1.,0.],[1.,1.])
        self.assertFalse(shifted['bitwise_equal'])
        self.assertAlmostEqual(shifted['l2'],1.)
        self.assertAlmostEqual(shifted['linf'],1.)
        self.assertAlmostEqual(shifted['cosine'],2**-.5)
        for live,reference in (([1.],[1.,2.]),([float('nan')],[1.])):
            with self.subTest(live=live),self.assertRaises(ValueError):
                e.vector_distance(live,reference)

    def test_request_records_reference_vector_comparison(self):
        r=Runtime(); corpus={c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'}
        plain=e.request(query(),corpus,'cosine',r,clock=lambda:r.t)
        self.assertIsNone(plain['query_vector_vs_reference'])
        tagged=dict(query(),reference_vector=[1.,0.])
        compared=e.request(tagged,corpus,'cosine',r,clock=lambda:r.t)
        self.assertTrue(compared['query_vector_vs_reference']['bitwise_equal'])

    def test_plan_rejects_malformed_reference_vectors(self):
        plan=dict(reference_vectors={},queries=[{'qid':'a'},{'qid':'b'}])
        for references in ({'a':[1.]}, {'a':[1.],'b':[float('nan')]},
                           {'a':[1.],'b':[1.]}, {'a':[1.]*768,'b':[1.]*768,'c':[1.]*768}):
            with self.subTest(references=len(references)):
                with self.assertRaises(ValueError):
                    e.reference_vectors(dict(plan,reference_vectors=references))
        self.assertEqual(e.reference_vectors(dict(plan,reference_vectors={'a':[1.]*768,'b':[1.]*768})),
                         {'a':[1.]*768,'b':[1.]*768})

    def test_process_counters_return_measured_values_only(self):
        with tempfile.TemporaryDirectory() as d:
            status=Path(d)/'status'
            status.write_text('Name:\tpython\nVmRSS:\t  2048 kB\nVmHWM:\t  4096 kB\n')
            self.assertEqual(e.process_rss_bytes(str(status)),
                             {'current_bytes':2097152,'peak_bytes':4194304})
            self.assertEqual(e.process_rss_bytes(str(Path(d)/'absent')),None)
            status.write_text('Name:\tpython\n')
            self.assertEqual(e.process_rss_bytes(str(status)),
                             {'current_bytes':None,'peak_bytes':None})

    def test_cgroup_quota_is_read_from_v2_and_v1(self):
        def reader(files):
            def read(path):
                if path not in files:
                    raise OSError('missing')
                return files[path]
            return read
        self.assertEqual(e.cpu_quota_threads(reader({'/sys/fs/cgroup/cpu.max':'400000 100000'})),4)
        self.assertEqual(e.cpu_quota_threads(reader({'/sys/fs/cgroup/cpu.max':'150000 100000'})),1)
        self.assertIsNone(e.cpu_quota_threads(reader({'/sys/fs/cgroup/cpu.max':'max 100000'})))
        self.assertEqual(e.cpu_quota_threads(reader({
            '/sys/fs/cgroup/cpu/cpu.cfs_quota_us':'800000',
            '/sys/fs/cgroup/cpu/cpu.cfs_period_us':'100000'})),8)
        self.assertIsNone(e.cpu_quota_threads(reader({})))

    def test_affinity_resolution_is_capped_by_the_cgroup_quota(self):
        self.assertEqual(e.resolve_cpu_threads('affinity',cpu_count=lambda:128,
                                               affinity=lambda:128,quota=lambda:8),8)
        self.assertEqual(e.resolve_cpu_threads('affinity',cpu_count=lambda:128,
                                               affinity=lambda:128,quota=lambda:None),128)
        self.assertEqual(e.resolve_cpu_threads('affinity',cpu_count=lambda:128,
                                               affinity=lambda:4,quota=lambda:8),4)

    def test_thread_enforcement_happens_before_parallel_work(self):
        class Torch:
            def __init__(self, intra_ok=True): self.intra=None; self.inter=None; self.intra_ok=intra_ok
            def set_num_threads(self, value): self.intra=value if self.intra_ok else value+1
            def get_num_threads(self): return self.intra
            def set_num_interop_threads(self, value): self.inter=value
            def get_num_interop_threads(self): return self.inter
        class Limits:
            def __init__(self, limits): self.limits=limits; self.unregistered=False
            def unregister(self): self.unregistered=True
        torch=Torch()
        applied,handle=e.apply_cpu_threads(4,torch_module=torch,threadpool_limits=Limits)
        self.assertEqual(applied['torch_intra_op'],4)
        self.assertEqual(applied['torch_inter_op'],1)
        self.assertTrue(applied['threadpoolctl_applied'])
        self.assertEqual(handle.limits,4)
        e.release_thread_limits(handle)
        self.assertTrue(handle.unregistered)
        with self.assertRaises(ValueError):
            e.apply_cpu_threads(4,torch_module=Torch(intra_ok=False),threadpool_limits=Limits)
        with self.assertRaises(ValueError):
            e.apply_cpu_threads(0,torch_module=torch,threadpool_limits=Limits)

    def test_thread_configuration_verifier_rejects_any_mismatch(self):
        good=dict(torch_matches_requested=True,torch_inter_op_threads=1,
                  blas_matches_requested=True)
        self.assertTrue(e.verify_thread_configuration(good))
        for change in ({'torch_matches_requested':False},
                       {'torch_inter_op_threads':64},
                       {'blas_matches_requested':False}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                e.verify_thread_configuration(dict(good,**change))
        self.assertTrue(e.verify_thread_configuration(
            dict(good,blas_matches_requested=None,torch_inter_op_threads=None)))

    def test_observations_report_measured_values_only(self):
        observed=e.observed_parallel_evidence(requested=4,cpu_count=lambda:8,affinity=lambda:6,
                                              quota=lambda:4,torch_threads=lambda:4,
                                              torch_interop=lambda:1,
                                              blas=lambda:{'available':False,
                                                           'reason':'threadpoolctl unavailable'})
        self.assertEqual(observed['affinity_count'],6)
        self.assertEqual(observed['torch_intra_op_threads'],4)
        self.assertEqual(observed['torch_matches_requested'],True)
        self.assertEqual(observed['blas_threadpool']['available'],False)
        self.assertEqual(observed['cpu_quota'],4)
        self.assertIsNone(observed['blas_matches_requested'])
        self.assertEqual(observed['requested'],4)
        self.assertNotIn('assumed',json.dumps(observed).lower())

        available=e.observed_parallel_evidence(
            requested=4,cpu_count=lambda:8,affinity=lambda:6,quota=lambda:4,
            torch_threads=lambda:4,torch_interop=lambda:1,
            blas=lambda:{'available':True,'pools':[{'num_threads':4}]})
        self.assertTrue(available['blas_threadpool']['available'])
        self.assertEqual(available['blas_pool_threads'],[4])
        self.assertIs(available['blas_matches_requested'],True)


if __name__=='__main__': unittest.main()

class OfflineEnvironmentContracts(unittest.TestCase):
    def test_explicit_cache_environment_is_preserved(self):
        values=guard.offline_environment(Path('/data/session'), {'HF_HOME':'/cache/hf','HF_HUB_CACHE':'/cache/hub','PYTHONPATH':'/extra'})
        self.assertEqual(values['HF_HOME'],'/cache/hf')
        self.assertEqual(values['HF_HUB_CACHE'],'/cache/hub')
        self.assertEqual(values['HF_HUB_OFFLINE'],'1')
        self.assertIn('/extra', values['PYTHONPATH'])

    def test_cache_fallback_is_relative_to_supplied_root(self):
        values=guard.offline_environment(Path('/data/session'), {})
        self.assertEqual(values['HF_HOME'],'/data/session/cache/huggingface')
        self.assertEqual(values['HF_HUB_CACHE'],'/data/session/cache/huggingface/hub')
