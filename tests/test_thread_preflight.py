import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
try:import thread_preflight as t
except ImportError:t=None
class ThreadPreflight(unittest.TestCase):
 def setUp(self):self.assertIsNotNone(t)
 def test_hostile_strings_and_eight(self):
  for v in ['abc','','0','-1','4.0',' 4']:self.assertTrue(t.invalid(v))
  self.assertFalse(t.invalid('8'))
 def test_quota_is_cap(self):self.assertEqual(t.bounded(8,64,32,2),2)
 def test_apply_or_blas_mismatch_aborts(self):
  for observed,intra,inter,pools in [(4,8,1,[8]),(8,4,1,[8]),(8,8,1,[4]),(8,8,2,[8])]:
   with self.assertRaises(ValueError):t.enforce(8,observed,intra,inter,pools)
 def test_unavailable_is_explicit_not_default(self):
  t.enforce(8,8,'unavailable','unavailable','unavailable')
