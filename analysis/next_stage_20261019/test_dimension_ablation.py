import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unittest
try:
    from retrieval_dimension_ablation import score_ranking, analysis_queries
except ImportError:
    score_ranking = analysis_queries = None

class DimensionAblationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(score_ranking, 'Offline no-self ranking analysis is not implemented')

    def test_exclusion_replenishes_without_reordering(self):
        r = score_ranking([2, 0, 1, 3], {3}, 1, 2, 4, (1, 3))
        self.assertEqual(r['top10'], [0, 1, 3])
        self.assertAlmostEqual(r['mrr'], 1 / 3)
        self.assertEqual(r['hit_at_1'], 0)
        self.assertEqual(r['hit_at_3'], 1)

    def test_removing_gt_self_does_not_shrink_gold_denominator(self):
        r = score_ranking([2, 0, 1, 3], {2, 3}, 2, 2, 4, (3,))
        self.assertEqual(r['recall_at_3'], .5)
        self.assertEqual(r['self_is_gold'], True)

    def test_unindexed_gt_retains_zero_question(self):
        r = score_ranking([0, 1, 2], set(), 2, None, 3, (1, 3))
        self.assertEqual(r['mrr'], 0)
        self.assertEqual(r['recall_at_3'], 0)
        self.assertTrue(r['no_indexed_gt_after_exclusion'])

    def test_duplicate_or_incomplete_full_ranking_rejected(self):
        for order in [[0, 0, 2], [0, 1], [0, 1, 3]]:
            with self.subTest(order=order), self.assertRaises(ValueError):
                score_ranking(order, {1}, 1, None, 3)

    def test_unknown_query_index_and_invalid_gold_count_rejected(self):
        for query, count in [(4, 1), (None, 0), (None, True)]:
            with self.subTest(query=query,count=count), self.assertRaises(ValueError):
                score_ranking([0, 1, 2], {1}, count, query, 3)

    def test_holdout_is_not_selected_for_analysis(self):
        rows = [{'qid': 's', 'split': 'smoke_20'}, {'qid': 'h', 'split': 'internal_holdout'}, {'qid': 'f', 'split': 'frozen_test'}]
        self.assertEqual([r['qid'] for r in analysis_queries(rows)], ['s', 'f'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
