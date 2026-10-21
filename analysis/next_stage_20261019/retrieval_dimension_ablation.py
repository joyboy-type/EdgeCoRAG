"""Post-hoc CPU analysis of pinned real retrieval ranks, excluding query SHA self matches."""
import csv
import hashlib
import json
import pathlib
import time

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=False)

COHORTS = {'smoke_20': 20, 'dev': 150, 'frozen_test': 1033}

def analysis_queries(rows):
    if any(r['split'] not in {*COHORTS, 'internal_holdout'} for r in rows):
        raise ValueError('Unknown split; do not guess evaluation scope')
    return [r for r in rows if r['split'] in COHORTS]

def score_ranking(order, targets, gold_count, query_index, corpus_size, ks=(1, 5, 10)):
    if (type(corpus_size) is not int or corpus_size < 1
            or len(order) != corpus_size or any(type(i) is not int for i in order)
            or set(order) != set(range(corpus_size))):
        raise ValueError('Complete unique in-range ranking required')
    if (type(gold_count) is not int or gold_count < 1 or not isinstance(targets, set)
            or len(targets) > gold_count or any(type(i) is not int or not 0 <= i < corpus_size for i in targets)
            or (query_index is not None and (type(query_index) is not int or not 0 <= query_index < corpus_size))
            or not ks or any(type(k) is not int or k < 1 for k in ks)):
        raise ValueError('Invalid gold, self identity or k')
    filtered = [i for i in order if i != query_index]
    first = next((i + 1 for i, candidate in enumerate(filtered) if candidate in targets), None)
    result = {'mrr': 1 / first if first else 0, 'top10': filtered[:10],
              'self_removed': query_index is not None, 'self_is_gold': query_index in targets,
              'no_indexed_gt_after_exclusion': not bool(targets - {query_index})}
    for k in ks:
        hits = len(set(filtered[:k]) & targets)
        result['hit_at_' + str(k)] = int(hits > 0)
        result['recall_at_' + str(k)] = hits / gold_count
    return result

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()

def main():
    import numpy as np
    here = PATHS.work_dir
    project = PATHS.project_root
    source = PATHS.archive_root
    ranks_root = source / 'results/formal-retrieval-embeddinggemma2'
    private = here / 'dimension-ablation-private'
    if private.exists():
        raise ValueError('Preserve existing analysis; no overwrite')
    protocol = json.loads((here / 'dimension-ablation-protocol.json').read_text())
    assert protocol['gpu_execution_authorized'] is False
    manifest = json.loads((source / 'backup-manifest.json').read_text())
    assert manifest['status'] == 'complete_stage_backup' and manifest['model'] == 'embeddinggemma2'
    pins = {r['path']: r for r in manifest['files']}
    relevant = ['controls/retrieval-formal.approved.json', 'results/formal-retrieval-embeddinggemma2/receipt.json']
    relevant += [f'results/formal-retrieval-embeddinggemma2/rank_indices_{d}.npy' for d in protocol['dimensions']]
    for name in relevant:
        p = source / name
        assert p.stat().st_size == pins[name]['bytes'] and sha(p) == pins[name]['sha256'], name
    package = json.loads((source / relevant[0]).read_text())
    assert sha(source / relevant[0]) == 'c766f7d381063ca2c935f3982de7ac72f18437a1f5889a8701181d11697fe740'
    receipt = json.loads((ranks_root / 'receipt.json').read_text())
    spec = package['models']['embeddinggemma2']
    assert receipt['status'] == 'completed' and receipt['model'] == 'embeddinggemma2'
    assert receipt['revision'] == spec['revision'] == '914f7f89142e33e77833254d9c9b90c3cef7303b'
    queries = analysis_queries(package['queries'])
    assert {co: sum(q['split'] == co for q in queries) for co in COHORTS} == COHORTS
    assert len({q['qid'] for q in queries}) == len(queries) == 1203
    corpus = [r['id'] for r in package['corpus']]
    assert len(corpus) == len(set(corpus)) == 18955
    lookup = {key: i for i, key in enumerate(corpus)}
    query_positions = {q['qid']: i for i, q in enumerate(package['queries'])}
    prepared = {}
    for co in COHORTS:
        rows = [json.loads(s) for s in (here / 'prepared' / ('no-self-' + co + '-ranks.jsonl')).read_text().splitlines()]
        assert {r['qid'] for r in rows} == {q['qid'] for q in queries if q['split'] == co}
        prepared.update({r['qid']: r['corpus_ids'] for r in rows})
    private.mkdir()
    started = time.time()
    metrics, details = [], []
    for dim in protocol['dimensions']:
        matrix = np.load(ranks_root / f'rank_indices_{dim}.npy', mmap_mode='r', allow_pickle=False)
        assert matrix.shape == (1353, 18955) and matrix.dtype == np.dtype('int32')
        values = {co: [] for co in COHORTS}
        for q in queries:
            gold = package['gold'][q['qid']]
            assert gold and len(gold) == len(set(gold))
            target = {lookup[g] for g in gold if g in lookup}
            query_index = lookup.get('image:' + q['sha256'])
            order = matrix[query_positions[q['qid']]].tolist()
            r = score_ranking(order, target, len(gold), query_index, len(corpus))
            if dim == 768:
                assert [corpus[i] for i in r['top10']] == prepared[q['qid']], q['qid']
            values[q['split']].append(r)
            details.append({'qid': q['qid'], 'cohort': q['split'], 'dimension': dim,
                            **{k: v for k, v in r.items() if k != 'top10'}})
        for co, rows in values.items():
            n = COHORTS[co]
            assert len(rows) == n
            metrics.append({'cohort': co, 'dimension': dim, 'questions': n,
                **{'hit_at_' + str(k) + '_questions': sum(r['hit_at_' + str(k)] for r in rows) for k in (1, 5, 10)},
                **{'hit_at_' + str(k) + '_percent': 100 * sum(r['hit_at_' + str(k)] for r in rows) / n for k in (1, 5, 10)},
                **{'mean_recall_at_' + str(k): sum(r['recall_at_' + str(k)] for r in rows) / n for k in (1, 5, 10)},
                'mrr': sum(r['mrr'] for r in rows) / n,
                'queries_with_self_removed': sum(r['self_removed'] for r in rows),
                'queries_whose_gt_contains_self': sum(r['self_is_gold'] for r in rows),
                'queries_without_indexed_gt_after_exclusion': sum(r['no_indexed_gt_after_exclusion'] for r in rows),
                'dense_float32_vector_payload_mib': len(corpus) * dim * 4 / 1024**2})
        del matrix
    result = {'status': 'completed_offline_no_self_dimension_ablation', 'method': 'posthoc filtering of real cached full rankings; no new embeddings or model calls',
              'dimensions': protocol['dimensions'], 'cohorts': COHORTS, 'rank_rows_analyzed': len(details),
              'holdout_evaluated': False, 'gpu_started': False, 'generation_calls': 0,
              'source_revision': spec['revision'], 'source_files': {name: pins[name]['sha256'] for name in relevant},
              'source_manifest_sha256': sha(source / 'backup-manifest.json'),
              'protocol_sha256': sha(here / 'dimension-ablation-protocol.json'),
              'code_sha256': sha(pathlib.Path(__file__).resolve()),
              '768_top10_matches_verified_generation_inputs_all1203': True,
              'gold_denominator_unchanged_when_query_is_gt': True,
              'elapsed_cpu_analysis_wall_seconds': time.time() - started, 'metrics': metrics}
    (private / 'per-query.private.json').write_text(json.dumps(details, ensure_ascii=False, indent=2))
    (private / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    out = PATHS.output_dir or here / "dimension-public"
    out.mkdir(parents=True, exist_ok=True)
    with (out / '无自匹配检索_维度消融.csv').open('x', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(metrics[0])); w.writeheader(); w.writerows(metrics)
    print(json.dumps({k: v for k, v in result.items() if k != 'source_files'}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
