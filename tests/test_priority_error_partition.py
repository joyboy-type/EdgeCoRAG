import importlib.util
import itertools
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019/priority_error_partition.py'
spec=importlib.util.spec_from_file_location('priority_partition',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PriorityPartitionTests(unittest.TestCase):
    def test_all_complete_combinations(self):
        for s0,s1,hit in itertools.product((False,True),repeat=3):
            expected=('检索伤害' if s0 and not s1 else '未检索到' if not hit and not s1 else '检索到但答错' if hit and not s1 else '无关但未伤害')
            self.assertEqual(m.classify(True,s0,s1,hit),expected)
    def test_missing_is_separate(self):
        self.assertEqual(m.classify(False,None,None,None),'不可判定')
    def test_malformed_complete_rejected(self):
        for value in ('False',None,0):
            with self.assertRaises(ValueError):m.classify(True,value,False,True)
        with self.assertRaises(ValueError):m.boolean('false')
