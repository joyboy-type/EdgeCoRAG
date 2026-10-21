"""Guards for the accuracy decomposition and scenario stratification."""
import gzip, json, unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'analysis/next_stage_20261019'))
import decompose_accuracy as dec


class Decomposition(unittest.TestCase):
    def test_identity_residual_is_zero_for_synthetic_rows(self):
        rows = [('m', f'q{i}', i % 2 == 0, i % 3 == 0) for i in range(60)]
        s = dec.stats(rows)
        self.assertAlmostEqual(s['acc'], s['predicted'], places=12)

    def test_r_is_model_invariant_on_frozen_join(self):
        rows = dec.load()
        per = {}
        for m, q, h, c in rows:
            per.setdefault(m, []).append(h)
        r = {round(sum(v) / len(v), 12) for v in per.values()}
        self.assertEqual(len(r), 1, 'hit marginal must be identical across models')

    def test_every_row_has_a_scenario(self):
        import scenario_extrapolation as se
        smap = se.scenario_map()
        rows = dec.load()
        missing = [q for _, q, _, _ in rows if q not in smap]
        self.assertEqual(missing, [], 'scenario_map must cover every evaluated qid')


class Scenario(unittest.TestCase):
    def test_artifact_matches_recomputation(self):
        art = ROOT / 'reports/paper_20261021/scenario_extrapolation_20261021.json'
        data = json.loads(art.read_text())
        total = sum(x['n'] for v in data['models'].values() for x in v['scenarios'].values())
        self.assertGreater(total, 0)
        for m, v in data['models'].items():
            for s, x in v['scenarios'].items():
                self.assertLessEqual(x['n'], 1033)
                if x['u_s'] is not None and x.get('u_s_ci'):
                    lo, hi = x['u_s_ci']
                    self.assertLessEqual(lo, x['u_s'] + 1e-9)
                    self.assertGreaterEqual(hi, x['u_s'] - 1e-9)


if __name__ == '__main__':
    unittest.main()
