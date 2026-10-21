"""Decompose shared-retrieval accuracy into retrieval ceiling, utilisation, parametric knowledge.

Acc = r*u + (1-r)*p, with r = P(gold in top-3), u = P(correct | hit), p = P(correct | miss).
Under shared retrieval r is model-invariant; u and p are model properties.
Descriptive only: question-level bootstrap, not the frozen cluster bootstrap.
"""
import argparse, csv, gzip, json, hashlib
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
JOIN = REPO / 'reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz'
SEED = 42
B = 10000


def load():
    rows = []
    with gzip.open(JOIN, 'rt', newline='') as f:
        for r in csv.DictReader(f):
            rows.append((r['model'], r['qid'],
                         r['top3_gt_hit'] == 'True',
                         r['S1_correct'] == 'True'))
    return rows


def stats(rows):
    n = len(rows)
    hit = np.array([r[2] for r in rows])
    ok = np.array([r[3] for r in rows])
    r = hit.mean()
    u = ok[hit].mean() if hit.any() else float('nan')
    p = ok[~hit].mean() if (~hit).any() else float('nan')
    acc = ok.mean()
    return dict(n=n, r=r, u=u, p=p, acc=acc,
                hit_correct=int(ok[hit].sum()), hit_n=int(hit.sum()),
                miss_correct=int(ok[~hit].sum()), miss_n=int((~hit).sum()),
                predicted=r * u + (1 - r) * p)


def boot(rows):
    rng = np.random.default_rng(SEED)
    n = len(rows)
    out = {k: [] for k in ('r', 'u', 'p', 'acc')}
    for _ in range(B):
        idx = rng.integers(0, n, n)
        s = stats([rows[i] for i in idx])
        for k in out:
            out[k].append(s[k])
    return {k: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    rows = load()
    by_model = {}
    for m, q, h, c in rows:
        by_model.setdefault(m, []).append((m, q, h, c))
    result = {'input': str(JOIN.relative_to(REPO)),
              'input_sha256': hashlib.sha256(JOIN.read_bytes()).hexdigest(),
              'seed': SEED, 'resamples': B,
              'interval': 'question-level percentile bootstrap; descriptive, not the frozen cluster bootstrap',
              'models': {}}
    for m, rs in sorted(by_model.items()):
        s = stats(rs)
        s['ci'] = boot(rs)
        result['models'][m] = s
    r_vals = {round(v['r'], 12) for v in result['models'].values()}
    result['r_model_invariant'] = len(r_vals) == 1
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({m: {k: round(v[k], 4) for k in ('r', 'u', 'p', 'acc', 'predicted')}
                      for m, v in result['models'].items()}, indent=1))
    print('r_invariant:', result['r_model_invariant'])


if __name__ == '__main__':
    main()
