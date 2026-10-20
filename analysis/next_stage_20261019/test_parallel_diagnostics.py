import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unittest
from parallel_diagnostics import clusters, cluster_interval, transition, paired_counts

class DiagnosticsTests(unittest.TestCase):
    def test_graph_connects_transitive_image_reuse_but_not_missing_gt(self):
        rows=[dict(qid='a',sha='one',gold=['x']),dict(qid='b',sha='two',gold=['x','y']),
              dict(qid='c',sha='three',gold=['y']),dict(qid='d',sha='four',gold=[]),
              dict(qid='e',sha='four',gold=[]),dict(qid='f',sha='five',gold=[])]
        got=clusters(rows,include_gold=True)
        self.assertEqual(got['a'],got['c']);self.assertEqual(got['d'],got['e'])
        self.assertNotEqual(got['a'],got['d']);self.assertNotEqual(got['d'],got['f'])
        self.assertNotEqual(clusters(rows,include_gold=False)['a'],clusters(rows,include_gold=False)['b'])

    def test_cluster_interval_uses_question_weighted_ratio(self):
        got=cluster_interval([1,1,-1],['x','x','y'],1000,42)
        self.assertAlmostEqual(got['delta_pp'],100/3)
        self.assertEqual(got['ci_low_pp'],-100);self.assertEqual(got['ci_high_pp'],100)
        self.assertEqual(got['clusters'],2)

    def test_shared_cluster_is_not_resampled_as_independent_questions(self):
        got=cluster_interval([1,0,-1],['x','x','x'],1000,42)
        self.assertEqual((got['ci_low_pp'],got['ci_high_pp']),(0,0))
        self.assertEqual(got['clusters'],1)

    def test_transitions_are_exact_identity_not_semantics(self):
        self.assertEqual(transition(['x'],['y'],{'y'}),'gain_exact_hit')
        self.assertEqual(transition(['y'],['x'],{'y'}),'lose_exact_hit')
        self.assertEqual(transition(['x'],['z'],{'y'}),'neither_exact_hit')
        self.assertEqual(transition(['x'],['y'],set()),'neither_exact_hit')

    def test_wins_losses_reconcile_without_dropping_failures(self):
        result=paired_counts([False,True,False,True],[True,False,False,True])
        self.assertEqual(result,dict(n=4,left_correct=2,right_correct=2,wins=1,losses=1,unchanged=2,delta_pp=0.))
        with self.assertRaises(ValueError):paired_counts([True],[True,False])

if __name__=='__main__':unittest.main()
