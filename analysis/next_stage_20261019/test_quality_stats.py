import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from quality_stats import holm, paired_family, choose_fixed, mechanism

class QualityStatsTests(unittest.TestCase):
    def test_holm_is_stepdown_and_keeps_original_order(self):
        self.assertEqual(holm([.2,.01,.03]),[.2,.03,.06])

    def test_identical_paths_keep_zero_interval_and_fixed_denominator(self):
        result=paired_family([dict(left=[True,False,True],right=[True,False,True])],['a','a','b'],resamples=10000,seed=42)[0]
        self.assertEqual(result['n'],3);self.assertEqual(result['delta_pp'],0)
        self.assertEqual((result['ci_low_pp'],result['ci_high_pp']),(0,0))
        self.assertEqual(result['holm_p'],1)

    def test_cluster_weighting_uses_ratio_of_sums(self):
        result=paired_family([dict(left=[False,False,True],right=[True,True,False])],['a','a','b'],resamples=10000,seed=42)[0]
        self.assertAlmostEqual(result['delta_pp'],100/3)
        self.assertEqual(result['components'],2)
        # Enumerating the four two-cluster resamples gives means -100, 100/3, 100/3, 100.
        self.assertAlmostEqual(result['ci_low_pp'],-100/3)
        self.assertEqual(result['ci_high_pp'],100)
        self.assertLessEqual(result['holm_ci_low_pp'],result['ci_low_pp'])
        self.assertGreaterEqual(result['holm_ci_high_pp'],result['ci_high_pp'])

    def test_fixed_selection_only_reads_dev_and_tie_order(self):
        dev={'utility':[True,False],'random':[True,False],'cosine':[True,False]}
        self.assertEqual(choose_fixed(dev),'cosine')
        dev['utility']=[True,True];self.assertEqual(choose_fixed(dev),'utility')

    def test_mechanism_classes_have_explicit_priority(self):
        self.assertEqual(mechanism(True,False,False),'retrieval_harm_proxy')
        self.assertEqual(mechanism(False,True,False),'not_retrieved')
        self.assertEqual(mechanism(False,False,True),'present_but_wrong')
        self.assertEqual(mechanism(False,True,True),'other')
