"""Scenario-level out-of-sample check of the decomposition Acc = r*u + (1-r)*p.

Global u,p are estimated once per model; each scenario supplies its own r.
If u,p are scenario-invariant, predicted scenario accuracy matches observed.
Descriptive only; no cluster bootstrap here.
"""
import argparse, csv, gzip, json, hashlib
from pathlib import Path
import numpy as np

SEED = 42
B = 4000
REPO = Path(__file__).resolve().parents[2]
JOIN = REPO / 'reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz'
PRED = REPO / 'logs/B_predictions.jsonl.gz'


def scenario_map():
    m = {}
    with gzip.open(PRED, 'rt') as f:
        for line in f:
            d = json.loads(line)
            q, s = d.get('qid'), d.get('scenario')
            if q and s:
                m.setdefault(q, s)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    smap = scenario_map()
    rows = []
    with gzip.open(JOIN, 'rt', newline='') as f:
        for r in csv.DictReader(f):
            rows.append((r['model'], r['qid'], r['top3_gt_hit'] == 'True',
                         r['S1_correct'] == 'True'))
    by = {}
    for m, q, h, c in rows:
        by.setdefault(m, []).append((smap.get(q, 'UNKNOWN'), h, c))
    out = {'input_join': str(JOIN.relative_to(REPO)),
           'input_join_sha256': hashlib.sha256(JOIN.read_bytes()).hexdigest(),
           'input_predictions': str(PRED.relative_to(REPO)),
           'input_predictions_sha256': hashlib.sha256(PRED.read_bytes()).hexdigest(),
           'interval': 'per-scenario percentile bootstrap of u_s, 4000 resamples, seed 42; descriptive',
           'models': {}}
    for m, rs in sorted(by.items()):
        arr = np.array([[h, c] for _, h, c in rs])
        hit, ok = arr[:, 0], arr[:, 1]
        u, p = ok[hit].mean(), ok[~hit].mean()
        scen = {}
        for s in sorted({s for s, _, _ in rs}):
            sub = np.array([[h, c] for sc, h, c in rs if sc == s])
            hs, os_ = sub[:, 0], sub[:, 1]
            if len(sub) < 10:
                continue
            r_s = hs.mean()
            rng = np.random.default_rng(SEED)
            ub = []
            for _ in range(B):
                idx = rng.integers(0, len(sub), len(sub))
                h2, o2 = hs[idx], os_[idx]
                if h2.any(): ub.append(o2[h2].mean())
            ci = [float(np.percentile(ub, 2.5)), float(np.percentile(ub, 97.5))] if ub else None
            scen[s] = {'n': int(len(sub)), 'r': float(r_s), 'u_s_ci': ci,
                       'acc': float(os_.mean()),
                       'pred': float(r_s * u + (1 - r_s) * p),
                       'u_s': float(os_[hs].mean()) if hs.any() else None,
                       'p_s': float(os_[~hs].mean()) if (~hs).any() else None}
        resid = [v['acc'] - v['pred'] for v in scen.values()]
        out['models'][m] = {'u_global': float(u), 'p_global': float(p),
                            'scenarios': scen,
                            'rmse': float(np.sqrt(np.mean(np.square(resid)))),
                            'max_abs_resid': float(np.max(np.abs(resid))),
                            'u_spread': float(max(v['u_s'] for v in scen.values() if v['u_s'] is not None)
                                              - min(v['u_s'] for v in scen.values() if v['u_s'] is not None))}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(f"{'model':13s}{'u':>7s}{'p':>7s}{'RMSE':>8s}{'maxres':>8s}{'u_spread':>10s}")
    for m, v in sorted(out['models'].items()):
        print(f"{m:13s}{v['u_global']:7.3f}{v['p_global']:7.3f}{v['rmse']:8.4f}{v['max_abs_resid']:8.4f}{v['u_spread']:10.3f}")


if __name__ == '__main__':
    main()
