"""Reproduce: $PY -m unittest discover -s analysis/next_stage_20261019 -p test_p2_p5.py"""
import hashlib,json,tempfile,unittest
from pathlib import Path
from round1_projection import measure_identity
from p5_budget_options import build
from p4_reproduce import specs,REPO,receipt_filename
class OfflineBatchTests(unittest.TestCase):
 def test_opaque_alias_does_not_get_relabelled_as_byte_hash(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'img').write_bytes(b'actual bytes');digest=hashlib.sha256(b'actual bytes').hexdigest()
   r=measure_identity([{'path':'img','id':'image:'+'0'*64,'sha256':digest}],p)
   self.assertEqual(r['id_suffix_not_raw_byte_sha256'],1);self.assertEqual(r['unique_raw_byte_sha256'],1)
 def test_changed_source_bytes_abort_projection(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'img').write_bytes(b'changed')
   with self.assertRaises(ValueError):measure_identity([{'path':'img','id':'image:'+'0'*64,'sha256':'0'*64}],p)
 def test_duplicate_content_count_is_measured(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'img').write_bytes(b'x');digest=hashlib.sha256(b'x').hexdigest()
   rows=[{'path':'img','id':'image:'+str(i)*64,'sha256':digest} for i in (0,1)]
   self.assertEqual(measure_identity(rows,p)['duplicate_content_rows'],1)
 def test_budget_options_reduce_scope_and_never_claim_authorization(self):
  with tempfile.TemporaryDirectory() as d:
   result=build(Path(d)/'new');self.assertGreaterEqual(result['slow_scope_reduction_fraction_B_vs_A'],.2)
   for r in result['options']:
    self.assertLessEqual(r['slow_scenario_seconds'],r['hard_window_seconds']);self.assertLessEqual(r['hard_window_seconds'],7200)
    self.assertFalse(r['total_cost_cap_verified']);self.assertFalse(r['ready_for_GPU_application']);self.assertEqual(r['preservation_seconds'],600)
    self.assertIn('跳过E0',r['E0']);self.assertIn('No verified',r['index_prerequisite'])
 def test_all_artifacts_have_explicit_command_templates(self):
  groups=specs(REPO);names=[]
  for _,files,command in groups:
   names.extend(files)
   self.assertTrue(command[0].endswith('.py'))
   self.assertFalse(any(Path(s).is_absolute() for s in command))
  self.assertEqual(len(names),30);self.assertEqual(len(set(names)),30)
  for label in ('Q_completion_counts.json','Q_requirement_evidence_audit.json','status_changes.json','quality'):
   result=receipt_filename(label);self.assertTrue(result.startswith('receipt_'));self.assertFalse(result.endswith('.json.json'))
