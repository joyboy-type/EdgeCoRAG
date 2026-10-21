"""Real-data check of the new ranking-evidence recorder (CPU only, no model).

Rebuilds the live ranking code path over the archived 18,955 x 768 index, feeds it
through `e2e_smoke.ranking_evidence` and cross-checks the numbers against the
independent offline diagnostic. No GPU, no network, no model weights.
"""
import json
import sys
from pathlib import Path

import numpy as np

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=False)

PROJECT = PATHS.project_root
REPO = PATHS.repo
WORK = PATHS.work_dir
SMOKE = WORK / 'e2e-smoke-prepared'
ARCHIVE = PATHS.archive_root
RETRIEVAL = ARCHIVE / 'results/formal-retrieval-embeddinggemma2'
OUT = PATHS.output_dir or WORK / 'ranking-evidence-realcheck-20261021.json'

sys.path.insert(0, str(REPO / 'b-side'))
sys.path.insert(0, str(REPO / 'a-side/scripts'))
import e2e_smoke as smoke
from independent_retrieval import normalize


def main():
    plan = json.loads((SMOKE / 'local-plan.private.json').read_text())
    retrieval = json.loads((ARCHIVE / 'controls/retrieval-formal.approved.json').read_text())
    positions = {q['qid']: i for i, q in enumerate(retrieval['queries'])}
    vectors = normalize(np.load(PROJECT / plan['index']['path']), 768)
    queries = np.load(RETRIEVAL / 'query_embeddings.npy')
    ids = np.asarray(plan['corpus_order'])
    diagnostic = json.loads((WORK / 'retrieval-order-diagnostic-20261021/diagnostic.json').read_text())
    history = {row['qid']: row['corpus_ids'] for row
               in map(json.loads, (WORK / 'prepared/no-self-smoke_20-ranks.jsonl').read_text().splitlines())}

    rows = []
    for query in plan['queries']:
        qid = query['qid']
        vector = normalize(queries[positions[qid]:positions[qid] + 1], 768)[0]
        similarity = vectors @ vector
        order = ids[np.lexsort((ids, -similarity))].tolist()
        pool = smoke.no_self_pool(order, query['query_image']['sha256'])
        evidence = smoke.ranking_evidence(order, similarity[np.lexsort((ids, -similarity))],
                                          query['query_image']['sha256'], pool)
        reference = diagnostic['per_query'][qid]
        if pool != history[qid]:
            raise ValueError('Recorded ranking disagrees with archived history: ' + qid)
        if abs(evidence['boundary_gap'] - reference['boundary_margin']) > 1e-12:
            raise ValueError('Boundary gap disagrees with the diagnostic: ' + qid)
        if abs(min(evidence['top10_adjacent_gaps']) - reference['adjacent_gap_min']) > 1e-12:
            raise ValueError('Adjacent gap disagrees with the diagnostic: ' + qid)
        if evidence['self_rank'] is not None and evidence['self_rank'] < 0:
            raise ValueError('Invalid self rank: ' + qid)
        fingerprint = smoke.vector_fingerprint(vector)
        rows.append(dict(qid=qid, self_rank=evidence['self_rank'],
                         boundary_gap=evidence['boundary_gap'],
                         boundary_candidate=evidence['boundary_candidate'],
                         top10_adjacent_gap_min=min(evidence['top10_adjacent_gaps']),
                         self_inside_top10=(evidence['self_rank'] is not None
                                            and evidence['self_rank'] < 10),
                         query_vector_sha256=fingerprint['sha256'],
                         cross_check='boundary_gap and adjacent_gap_min match the offline diagnostic'))
    result = dict(status='real_archived_data_check_passed', model_loaded=False, gpu_used=False,
                  corpus_shape=list(vectors.shape), queries=rows,
                  code_under_test=smoke.file_sha(REPO / 'b-side/e2e_smoke.py'),
                  note=('The recorder stores per-request scores, adjacent gaps, boundary gap and a '
                        'query-vector fingerprint, so a future live run measures live-vs-cached '
                        'consistency directly instead of inferring it from candidate order.'))
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
