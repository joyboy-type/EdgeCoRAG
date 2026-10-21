import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019/error_crosstab.py'
spec=importlib.util.spec_from_file_location('error_crosstab',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def row(model,qid,hit,s0,s1):
    return dict(model=model,qid=qid,joinable='True',missing_reason='',top3_gt_hit=str(hit),S0_correct=str(s0),S1_correct=str(s1))

class CrosstabTests(unittest.TestCase):
    def test_four_cells_and_harm_overlap(self):
        rows=[row('a',str(i),h,s0,s1) for i,(h,s0,s1) in enumerate([(False,False,True),(False,True,False),(True,True,False),(True,False,True)])]
        result=m.summarize(rows,models=('a',),denominator=4)[0]
        self.assertEqual([result[k] for k in m.CELLS],[1,1,1,1])
        self.assertEqual(result['检索伤害'],2)
        self.assertEqual(result['检索伤害占比'],50)
        self.assertEqual(result['命中数'],2)
        self.assertEqual(result['未命中数'],2)
    def test_equal_counts_different_query_hits_rejected(self):
        rows=[row('a','1',True,True,True),row('a','2',False,True,True),row('b','1',False,True,True),row('b','2',True,True,True)]
        with self.assertRaisesRegex(ValueError,'Shared retrieval'):m.summarize(rows,models=('a','b'),denominator=2)
    def test_missing_or_duplicate_rejected(self):
        r=row('a','1',True,True,False)
        with self.assertRaises(ValueError):m.summarize([r,r],models=('a',),denominator=2)
        r['joinable']='False'
        with self.assertRaises(ValueError):m.summarize([r],models=('a',),denominator=1)
