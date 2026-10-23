"""Synthetic checks; no archived outcomes are loaded by this test module."""
import hashlib
import math
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extrapolation_test as subject


def record(qid, hit, correct, scenario='A'):
    return dict(qid=qid, hit=hit, correct=correct, scenario=scenario)


class ExtrapolationTests(unittest.TestCase):
    def test_hash_split_is_order_independent_disjoint_and_balanced(self):
        qids=['q5', 'q1', 'q3', 'q2', 'q4']
        left, right=subject.split_questions(qids)
        self.assertEqual((left, right), subject.split_questions(list(reversed(qids))))
        self.assertEqual((len(left), len(right)), (2, 3))
        self.assertFalse(set(left) & set(right))
        self.assertEqual(set(left) | set(right), set(qids))

    def test_qid_hash_uses_sorted_utf8_with_final_newline(self):
        self.assertEqual(subject.qid_hash(['b', 'a']), hashlib.sha256(b'a\nb\n').hexdigest())

    def test_estimation_pools_counts_instead_of_averaging_strategy_rates(self):
        # Strategy 1 hit rate of correctness 1/1; strategy 2 0/3.
        # Pooled u is 1/4, not the mean conditional rate 1/2.
        rows=[record('a', True, True), record('b', False, False),
              record('a', True, False), record('b', True, False),
              record('c', True, False), record('d', False, True)]
        result=subject.estimate(rows)
        self.assertEqual((result['hit_n'], result['hit_correct'], result['u']), (4, 1, .25))
        self.assertEqual((result['miss_n'], result['miss_correct'], result['p']), (2, 1, .5))

    def test_zero_estimation_denominator_is_undefined_without_smoothing(self):
        result=subject.estimate([record('a', False, True)])
        self.assertIsNone(result['u'])
        self.assertEqual(result['p'], 1)
        self.assertIsNone(subject.predict(result, [record('v', False, True)])['predicted'])

    def test_hit_uses_selected_three_not_candidate_pool(self):
        self.assertFalse(subject.selected_hit(['a','b','c'], ['gold']))
        self.assertTrue(subject.selected_hit(['a','gold','c'], ['gold','other']))
        with self.assertRaises(ValueError):subject.selected_hit(['a','a','c'], ['gold'])
        with self.assertRaises(ValueError):subject.selected_hit(['a','b','c'], None)

    def test_required_coverage_rejects_duplicates_and_missing_records(self):
        with self.assertRaises(ValueError):subject.keyed([{'qid':'a'}, {'qid':'a'}], 'qid')
        with self.assertRaises(ValueError):subject.require_coverage({'a'}, {'a','b'}, 'fixture')

    def test_prediction_uses_validation_r_and_observed_minus_predicted(self):
        result=subject.predict({'u':.8,'p':.2},
            [record('a', True, True), record('b', False, False),
             record('c', False, False), record('d', False, False)])
        self.assertAlmostEqual(result['r'], .25)
        self.assertAlmostEqual(result['predicted'], .35)
        self.assertAlmostEqual(result['observed'], .25)
        self.assertAlmostEqual(result['residual'], -.1)

    def test_scenario_errors_are_equal_weighted_and_thresholds_are_inclusive(self):
        result=subject.error_metrics([.02, -.08])
        self.assertAlmostEqual(result['rmse'], math.sqrt(.0034))
        self.assertEqual(result['max_abs_residual'], .08)
        self.assertFalse(result['passes'])
        self.assertTrue(subject.within_threshold(.05, .10))
        self.assertFalse(subject.within_threshold(.050000001, .10))
        self.assertFalse(subject.within_threshold(.05, .100000001))

    def test_empty_validation_scene_does_not_turn_into_pass(self):
        result=subject.error_metrics([.01, None])
        self.assertEqual(result['status'], 'not_estimable')
        self.assertIsNone(result['passes'])

    def test_strategy_estimation_never_reads_random_outcomes(self):
        data={'cosine':[record('a', True, True),record('b', False,False)],
              'utility':[record('a', True, False),record('b', False,True)],
              'random':[record('a', True, False)]}
        before=subject.strategy_estimate(data)
        data['random']=[record('different', False, True)]
        self.assertEqual(before, subject.strategy_estimate(data))


if __name__ == '__main__':unittest.main()
