"""Negative contracts: failure flags cannot score; resource gaps cannot look measured."""
import sys,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'b-side'))
try:
    import b_offline_closure as b
except ImportError:
    b=None
try:
    import recording_policy as p
except ImportError:
    p=None
import e2e_smoke as smoke
from test_e2e_smoke import Runtime,query

class PublicStatistics(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(b, "Public-only closure not implemented")
    def test_generation_or_parse_failure_overrides_correct_without_dropping(self):
        self.assertFalse(b.scored(dict(correct=True,parse_status='ok',generation_error_present=True)))
        self.assertFalse(b.scored(dict(correct=True,parse_status='parse_failure',generation_error_present=False)))
        self.assertTrue(b.scored(dict(correct=True,parse_status='ok',generation_error_present=False)))
    def test_duplicate_or_missing_cluster_join_fails(self):
        with self.assertRaises(ValueError): b.align_groups(['q1','q1'],{'q1':'a'})
        with self.assertRaises(ValueError): b.align_groups(['q1','q2'],{'q1':'a'})

class RecordingPolicy(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(p, "Recording policy not implemented")
    def test_text_is_redacted_and_fingerprint_binds_actual_rendering(self):
        import hashlib
        messages=[{'role':'user','content':[{'type':'text','text':'Private answer A'}, {'type':'image','image':'/private/x.jpg'}]}]
        actual='<user>Private answer A /private/x.jpg<assistant>'
        r=p.redacted_prompt(actual,messages)
        self.assertNotIn('Private answer A',r['text']);self.assertNotIn('/private/',r['text'])
        self.assertEqual(r['original_sha256'],hashlib.sha256(actual.encode()).hexdigest())
        self.assertEqual(r['status'],'recorded_redacted')
    def test_device_is_sampled_peak_and_system_is_host_not_rss(self):
        read=lambda name:'MemTotal: 1000 kB\nMemAvailable: 400 kB\n'
        sampler=p.ResourceSampler(lambda:{'used_bytes':2*1024**3,'total_bytes':8*1024**3},meminfo=read)
        sampler.sample();r=sampler.finish()
        self.assertEqual(r['peak_vram_gb']['value'],2.)
        self.assertEqual(r['peak_vram_gb']['status'],'sampled')
        self.assertEqual(r['system_ram']['max_used_bytes'],600*1024)
        self.assertEqual(r['energy']['status'],'not_measured');self.assertIsNone(r['energy']['value'])
    def test_unavailable_is_not_zero_or_observed(self):
        r=p.ResourceSampler(None,meminfo=lambda name: (_ for _ in ()).throw(OSError())).finish()
        for field in ['peak_vram_gb','system_ram','energy']:
            self.assertEqual(r[field]['status'],'not_measured')
        self.assertNotIn('value',r['peak_vram_gb'])
    def test_successful_smoke_adds_new_fields_without_relabelling_allocator(self):
        runtime=Runtime();corpus={c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'}
        result=smoke.request(query(),corpus,'cosine',runtime,clock=lambda:runtime.t)
        self.assertEqual(result['recording']['rendered_prompt']['status'],'not_recorded')
        self.assertEqual(result['recording']['peak_vram_gb']['status'],'not_measured')
        self.assertEqual(result['memory']['allocated_bytes'],31)

    def test_failed_request_keeps_new_field_availability_and_partial_output(self):
        runtime=Runtime(fail=True);corpus={c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'failed'
            with self.assertRaises(RuntimeError):smoke.run([query(i) for i in range(5)],corpus,out,runtime)
            row=json.loads((out/'requests.jsonl').read_text().splitlines()[0])
            self.assertIn('recording',row)
            self.assertEqual(row['recording']['energy']['status'],'not_measured')
            self.assertEqual(row['recording']['rendered_prompt']['status'],'not_recorded')
