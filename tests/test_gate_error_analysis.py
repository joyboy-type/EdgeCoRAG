import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
import gate_error_analysis as a
class DerivedEvidenceTests(unittest.TestCase):
 def test_error_priority_retains_failure_flags_without_reparsing(self):
  r=dict(input_error=None,generation_error=None,parse_status='ok',correct=True)
  self.assertEqual(a.error_type(r),'none')
  self.assertEqual(a.error_type(dict(r,correct=False)),'incorrect_choice')
  self.assertEqual(a.error_type(dict(r,parse_status='parse_failure',correct=False)),'parse_failure')
  self.assertEqual(a.error_type(dict(r,generation_error='boom',parse_status='parse_failure')),'generation_error')
  self.assertEqual(a.error_type(dict(r,input_error='bad',generation_error='boom')),'input_error')
 def test_unknown_gt_is_not_inferred_from_slot_ids(self):
  self.assertEqual(a.partition(True,False,None),'检索伤害')
  self.assertEqual(a.partition(False,True,None),'不可判定')
  self.assertEqual(a.partition(False,False,None),'不可判定')
  self.assertEqual(a.partition(False,False,False),'未检索到')
  self.assertEqual(a.partition(False,False,True),'检索到但答错')
  self.assertEqual(a.partition(False,True,False),'无关但未伤害')
  self.assertEqual(a.partition(False,True,True),'不可判定')
