"""Offline diagnosis of live-vs-history top10 internal ordering.

Reads only archived artifacts: the historical corpus embeddings, the historical
cached query embeddings, the recorded historical ranks and the recorded live
(batch=1) smoke candidate orders. No model is loaded, no GPU is used and no
network access occurs. It does not write into any archived directory.
"""
import json
import statistics
from pathlib import Path

import numpy as np

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=False)

PROJECT = PATHS.project_root
WORK = PATHS.work_dir
SMOKE = WORK / 'e2e-smoke-prepared'
ARCHIVE = PATHS.archive_root
RETRIEVAL = ARCHIVE / 'results/formal-retrieval-embeddinggemma2'
OUT = PATHS.output_dir or WORK / 'retrieval-order-diagnostic-20261021'

# deterministic seeds; the sensitivity probe is an offline bound, not a new run
NOISE_TRIALS = 200
NOISE_SEED = 20261021
# dyadic relative perturbations around the float32/bf16 boundary of the encoder output
NOISE_LEVELS = tuple(2.0 ** -k for k in (18, 16, 14, 12, 10, 9, 8, 7, 6, 5))
SET_PRESERVED = 0.99


def normalize(vectors, dim):
    array = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(array[:, :dim], axis=1, keepdims=True)
    return array[:, :dim] / norms


def rank(vectors, ids, vector):
    similarity = vectors @ vector
    return ids[np.lexsort((ids, -similarity))].tolist(), similarity


def live_orders():
    import tarfile
    path = SMOKE / 'e2e-smoke-results-20261020.private.tar.gz'
    with tarfile.open(path) as tar:
        rows = [json.loads(line) for line
                in tar.extractfile('results/requests.jsonl').read().decode().splitlines()]
    orders, selected = {}, {}
    for row in rows:
        if row['warmup']:
            continue
        orders.setdefault(row['qid'], set()).add(tuple(row['candidate_ids']))
        selected.setdefault((row['qid'], row['strategy']), set()).add(tuple(row['selected_ids']))
    if any(len(v) != 1 for v in orders.values()):
        raise ValueError('Live candidate order was not stable within a query')
    if any(len(v) != 1 for v in selected.values()):
        raise ValueError('Live selected evidence was not stable within a strategy')
    return ({q: list(next(iter(v))) for q, v in orders.items()},
            {k: list(next(iter(v))) for k, v in selected.items()})


def noise_probe(vectors, ids, vector, self_sha, history, seed, relative):
    """Per-trial surrogates for 'the same image re-encoded with a different batch/kernel'.

    Counts how many in-top10 adjacent pairs a perturbation of this size displaces and
    how often the recorded live top10 membership survives it.
    """
    rng = np.random.default_rng(seed)
    swapped, same_set, same_top3 = [], 0, 0
    self_id = 'image:' + self_sha
    for _ in range(NOISE_TRIALS):
        trial = vector * (1. + rng.uniform(-relative, relative, vector.shape)).astype(np.float32)
        order, _ = rank(vectors, ids, (trial / np.linalg.norm(trial)).astype(np.float32))
        pool = [cid for cid in order if cid != self_id][:10]
        if len(pool) != 10:
            raise ValueError('Ten non-self candidates required')
        swapped.append(sum(1 for i, cid in enumerate(pool) if cid != history[i]))
        same_set += set(pool) == set(history)
        same_top3 += pool[:3] == history[:3]
    return dict(trials=NOISE_TRIALS, relative_perturbation=relative,
                median_displaced_positions=statistics.median(swapped),
                mean_displaced_positions=sum(swapped) / len(swapped),
                kept_recorded_top10_set=same_set / NOISE_TRIALS,
                kept_recorded_top3=same_top3 / NOISE_TRIALS)


def noise_sweep(vectors, ids, vector, self_sha, history, seed, history_reference):
    rows = [noise_probe(vectors, ids, vector, self_sha, history, seed, level) for level in NOISE_LEVELS]
    observed = 2 * len(history_reference)
    closest = min(rows, key=lambda r: abs(r['mean_displaced_positions'] - observed))
    preserved = [r['relative_perturbation'] for r in rows if r['kept_recorded_top10_set'] >= SET_PRESERVED]
    return dict(levels=rows, observed_displaced_positions=observed,
                closest_level=closest['relative_perturbation'],
                closest_level_mean_displaced=closest['mean_displaced_positions'],
                largest_set_preserving_level=max(preserved, default=None))


def implied_element_error(score_change, dimension=768):
    """Order-of-magnitude map from a cosine change to an elementwise relative error.

    For unit-norm vectors with roughly uniform components, an independent per-element
    relative error eps produces a similarity standard deviation of about
    eps / sqrt(3 * dimension). Reported in bf16 units (ulp = 2**-8 relative).
    """
    eps = score_change * (3 * dimension) ** .5
    return dict(score_change=score_change, relative_element_error=eps,
                bf16_ulp_units=eps / 2.0 ** -8)


def main():
    plan = json.loads((SMOKE / 'local-plan.private.json').read_text())
    retrieval = json.loads((ARCHIVE / 'controls/retrieval-formal.approved.json').read_text())
    positions = {q['qid']: i for i, q in enumerate(retrieval['queries'])}
    vectors = normalize(np.load(PROJECT / plan['index']['path']), 768)
    queries = np.load(RETRIEVAL / 'query_embeddings.npy')
    ids = np.asarray(plan['corpus_order'])
    history = {row['qid']: row['corpus_ids'] for row
               in map(json.loads, (WORK / 'prepared/no-self-smoke_20-ranks.jsonl').read_text().splitlines())}
    live, selected = live_orders()
    if vectors.shape != (len(ids), 768):
        raise ValueError('Index shape mismatch')

    OUT.mkdir(parents=True, exist_ok=False)
    rows, per_query = [], {}
    for query in plan['queries']:
        qid = query['qid']
        cached = normalize(queries[positions[qid]:positions[qid] + 1], 768)[0]
        order, similarity = rank(vectors, ids, cached)
        pool = [cid for cid in order if cid != 'image:' + query['query_image']['sha256']][:10]
        if pool != history[qid]:
            raise ValueError('Archived history could not be reproduced from cached vectors: ' + qid)
        observed = live[qid]
        if set(observed) != set(pool):
            raise ValueError('Live and history top10 membership differ: ' + qid)
        score = dict(zip(ids.tolist(), similarity.tolist()))
        rank_of = {cid: i for i, cid in enumerate(pool)}
        live_rank = {cid: i for i, cid in enumerate(observed)}
        inversions = [(a, b) for a in pool for b in pool
                      if rank_of[a] < rank_of[b] and live_rank[a] > live_rank[b]]
        # A score perturbation that reverses an inverted pair must exceed half its gap;
        # this bounds the per-candidate similarity change the live encoding introduced.
        bound = max(((score[a] - score[b]) / 2 for a, b in inversions), default=0.)
        full = [cid for cid in order if cid != 'image:' + query['query_image']['sha256']]
        margin = score[full[9]] - score[full[10]]
        adjacent = [score[full[i]] - score[full[i + 1]] for i in range(9)]
        sweep = noise_sweep(vectors, ids, cached, query['query_image']['sha256'], pool, NOISE_SEED + int(qid.split(':')[1]), inversions)
        per_query[qid] = dict(order_matches=observed == pool, inversions=inversions,
                              inversion_score_gap_lower_bound=bound, boundary_margin=margin,
                              inversion_is_tightest_adjacent=bool(inversions) and abs(bound - min(adjacent) / 2) < 1e-12,
                              implied_element_error=implied_element_error(bound),
                              adjacent_gap_min=min(adjacent), adjacent_gap_median=statistics.median(adjacent),
                              cosine_top3=selected[(qid, 'cosine')], history_top3=pool[:3],
                              noise_sweep=sweep)
        rows.append(dict(qid=qid, order_matches=observed == pool, inverse_pairs=len(inversions),
                         inversion_score_gap_lower_bound=bound,
                         inversion_is_tightest_adjacent=per_query[qid]['inversion_is_tightest_adjacent'],
                         implied_relative_element_error=per_query[qid]['implied_element_error']['relative_element_error'],
                         implied_bf16_ulp=per_query[qid]['implied_element_error']['bf16_ulp_units'],
                         top10_boundary_margin=margin,
                         adjacent_gap_min=min(adjacent), adjacent_gap_median=statistics.median(adjacent),
                         closest_noise_level=sweep['closest_level'],
                         closest_noise_level_mean_displaced=sweep['closest_level_mean_displaced'],
                         largest_set_preserving_noise_level=sweep['largest_set_preserving_level']))

    differing = [q for q, r in per_query.items() if not r['order_matches']]
    bound_max = max((r['inversion_score_gap_lower_bound'] for r in rows), default=0.)
    margin_min = min(r['top10_boundary_margin'] for r in rows)
    result = dict(
        status='offline_diagnostic_no_model_loaded',
        scope='archived historical embeddings, cached query vectors, recorded live candidate order',
        queries=len(per_query), order_mismatch_queries=differing,
        set_mismatch_queries=[],
        mismatches_are_single_tightest_adjacent_swap=all(
            len(per_query[q]['inversions']) == 1 and per_query[q]['inversion_is_tightest_adjacent'] for q in differing),
        note=('History was reproduced exactly from the cached query vectors with the same ranking code, '
              'so sorting, index normalization and no-self replenishment are not the difference; only the '
              'live batch=1 query embedding differs, and each reordered query differs by one adjacent swap '
              'at its tightest in-top10 tie.'),
        similarity_perturbation_interval=[bound_max, margin_min],
        implied_element_error_upper=implied_element_error(bound_max),
        implied_element_error_from_margin=implied_element_error(margin_min),
        noise_levels=list(NOISE_LEVELS), noise_trials=NOISE_TRIALS,
        noise_levels_preserving_all_recorded_sets=min(
            (r['largest_set_preserving_noise_level'] for r in rows
             if r['largest_set_preserving_noise_level'] is not None), default=None),
        scope_caveat=('An identical top10 membership bounds every boundary-straddling similarity change below the '
                      'smallest observed boundary margin; the inverted adjacent pairs bound it above half their gap. '
                      'The element-error conversion assumes independent, roughly uniform element errors and is an '
                      'order-of-magnitude reading only.'),
        per_query=per_query,
        limitation=('The live query vectors were not persisted, so no direct vector distance is available; '
                    'the gap bound and the noise sweep are indirect and do not identify a single kernel or '
                    'batch cause. No GPU or accuracy claim follows.'))
    (OUT / 'diagnostic.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    header = list(rows[0])
    with (OUT / 'per_query.csv').open('w') as f:
        f.write(','.join(header) + '\n')
        for row in rows:
            f.write(','.join(str(row[k]) for k in header) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('per_query',)}, indent=2, ensure_ascii=False))
    for row in rows:
        print(row)


if __name__ == '__main__':
    main()
