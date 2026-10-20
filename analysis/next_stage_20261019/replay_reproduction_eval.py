"""Offline reproduction audit of the fixed pipeline, before any paid GPU run.

Replays the live request path with archived inputs only: cached query vectors stand
in for live encoding, archived Gemma E2B True logits stand in for live utility
scores, and generation is stubbed. That separates "does the pipeline reproduce the
history" from "does the GPU encoder reproduce the cached vectors", which is the
only part a new paid run can answer.

No model is loaded, no GPU is used, nothing is written into archived directories.
"""
import json
import statistics
import sys
import tarfile
import time
from pathlib import Path

import numpy as np

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=False)

PROJECT = PATHS.project_root
REPO = PATHS.repo
WORK = PATHS.work_dir
SMOKE = WORK / 'e2e-smoke-prepared'
UTILITY = WORK / 'continuous-complete-backup/smoke_20/results/utility-gemma4_e2b/utility_scores.json'
ARCHIVE = PATHS.archive_root
RETRIEVAL = ARCHIVE / 'results/formal-retrieval-embeddinggemma2'
OUT = PATHS.output_dir or WORK / 'reproduction-eval-20261021'
SPLITS = ('smoke_20', 'dev', 'frozen_test')
ROUND_ONE = ('mragb:10', 'mragb:1049', 'mragb:1051', 'mragb:1062', 'mragb:1117')
SEED = 20261017

sys.path.insert(0, str(REPO / 'b-side'))
sys.path.insert(0, str(REPO / 'a-side/scripts'))
import e2e_cost as cost
import e2e_smoke as smoke
from independent_retrieval import normalize


class ReplayRuntime:
    """Same interface as NativeRuntime, fed by archived inputs only."""
    synthetic = True

    def __init__(self, plan, vectors, cached, positions, utility):
        self.ids = np.asarray(plan['corpus_order'])
        self.vectors = vectors
        self.np = np
        self.cached = {qid: cached[index] for qid, index in positions.items()}
        self.utility_scores = utility
        self.calls = {'encode': 0, 'rank': 0, 'utility': 0, 'infer': 0}

    def sync(self): pass
    def reset_peak(self): pass
    def peak(self): return {'allocated_bytes': 0, 'reserved_bytes': 0}
    def device_memory(self):
        return dict(free_bytes=None, total_bytes=None, used_bytes=0,
                    scope='replay: no device exists; this value is a stand-in and is not reported')

    def encode(self, query):
        self.calls['encode'] += 1
        return self.cached[query['qid']]

    def rank(self, vector):
        self.calls['rank'] += 1
        return rank_with(rank_inputs(self.ids, self.vectors), vector)

    def search(self, vector): return self.rank(vector)[0]

    def utility(self, query, pool):
        self.calls['utility'] += 1
        scores = self.utility_scores[query['qid']]
        if set(scores) != set(pool):
            raise ValueError('Archived utility scores do not cover the replayed pool for ' + query['qid'])
        return {cid: scores[cid] for cid in pool}

    def infer(self, row):
        self.calls['infer'] += 1
        return dict(final_output='REPLAY_NO_GENERATION', final_extraction_error=None,
                    synthetic=True, cuda_memory=None, input_image_count=1+len(row['evidence']))


def rank_inputs(ids, vectors):
    return ids, vectors


def rank_with(inputs, vector):
    ids, vectors = inputs
    similarity = vectors @ vector
    permutation = np.lexsort((ids, -similarity))
    return ids[permutation].tolist(), similarity[permutation]


def load_inputs():
    plan = json.loads((WORK / 'e2e-cost-proposed/local-plan.private.json').read_text())
    retrieval = json.loads((ARCHIVE / 'controls/retrieval-formal.approved.json').read_text())
    positions = {query['qid']: index for index, query in enumerate(retrieval['queries'])}
    vectors = normalize(np.load(PROJECT / plan['index']['path']), 768)
    cached = normalize(np.load(RETRIEVAL / 'query_embeddings.npy'), 768)
    raw = json.loads(UTILITY.read_text())
    if raw.get('synthetic') is not False or len(raw['scores']) != 200:
        raise ValueError('Archived utility scores are not the expected real 200 rows')
    utility = {}
    for row in raw['scores']:
        utility.setdefault(row['qid'], {})[row['candidate_id']] = row['raw_true_logit']
    return plan, retrieval, positions, vectors, cached, utility


def live_round_one():
    with tarfile.open(SMOKE / 'e2e-smoke-results-20261020.private.tar.gz') as tar:
        rows = [json.loads(line) for line
                in tar.extractfile('results/requests.jsonl').read().decode().splitlines()]
    pools = {}
    for row in rows:
        if pools.setdefault(row['qid'], row['candidate_ids']) != row['candidate_ids']:
            raise ValueError('Round-one live pool was not stable within a query')
    selected = {(row['qid'], row['strategy']): row['selected_ids'] for row in rows if not row['warmup']}
    return pools, selected


def history_ranks(split):
    return {row['qid']: row['corpus_ids'] for row
            in map(json.loads, (WORK / f'prepared/no-self-{split}-ranks.jsonl').read_text().splitlines())}


def ranking_reproduction(plan, retrieval, positions, vectors, cached):
    ids = np.asarray(plan['corpus_order'])
    shas = {query['qid']: query['sha256'] for query in retrieval['queries']}
    started = time.perf_counter()
    splits, total, matched = {}, 0, 0
    for split in SPLITS:
        ranks = history_ranks(split)
        mismatches = []
        for qid, expected in ranks.items():
            sha = shas[qid]
            order, scores = rank_with((ids, vectors), cached[positions[qid]])
            pool = smoke.no_self_pool(order, sha)
            evidence = smoke.ranking_evidence(order, scores, sha, pool)
            if evidence['candidate_ids'] != pool:
                raise ValueError('Recorded evidence disagrees with the pool: ' + qid)
            if pool != expected:
                mismatches.append(qid)
        splits[split] = dict(queries=len(ranks), top10_order_matches=len(ranks)-len(mismatches),
                             mismatches=mismatches)
        total += len(ranks)
        matched += len(ranks)-len(mismatches)
    return dict(splits=splits, total_queries=total, top10_order_matches=matched,
                elapsed_seconds=time.perf_counter()-started)


def main():
    if OUT.exists():
        raise SystemExit('Refusing to overwrite an existing evaluation directory')
    plan, retrieval, positions, vectors, cached, utility = load_inputs()
    references = smoke.attach_reference_vectors(plan)
    if set(references) != {query['qid'] for query in plan['queries']}:
        raise ValueError('Plans must carry archived reference vectors for every query')
    runtime = ReplayRuntime(plan, vectors, cached, positions, utility)
    live_pools, live_selected = live_round_one()
    history = {split: history_ranks(split) for split in SPLITS}
    OUT.mkdir(parents=True)

    ranking = ranking_reproduction(plan, retrieval, positions, vectors, cached)

    queries = [query for query in plan['queries'] if query['split'] == 'smoke_20']
    if len(queries) != 20:
        raise ValueError('Expected the twenty observed smoke questions')
    corpus = plan['corpus']
    replay = {}
    for query in queries:
        for strategy in cost.STRATEGIES:
            replay[(query['qid'], strategy)] = smoke.request(
                query, corpus, strategy, runtime,
                splits=('smoke_20', 'dev'), strategies=cost.STRATEGIES)
    # B2. the exact lease-A entry (fixed smoke) on the same five questions
    smoke_out = OUT / 'smoke-entry-replay'
    smoke_receipt = smoke.run([query for query in queries if query['qid'] in ROUND_ONE],
                              corpus, smoke_out, runtime)
    smoke_rows = [json.loads(line) for line in (smoke_out/'requests.jsonl').read_text().splitlines()]
    cost_out = OUT / 'cost-entry-replay'
    receipt = cost.run(queries, corpus, cost_out, runtime, cost.STRATEGIES, 2)

    parity, generation = [], []
    for qid in ROUND_ONE:
        query = next(q for q in queries if q['qid'] == qid)
        recorded = history['smoke_20'][qid]
        historical_cosine = recorded[:3]
        historical_utility = smoke.select(qid, recorded, 'utility', 3, SEED, utility[qid])
        row = dict(
            qid=qid,
            replay_pool_matches_history=replay[(qid, 'cosine')]['candidate_ids'] == recorded,
            replay_pool_matches_live=replay[(qid, 'cosine')]['candidate_ids'] == live_pools[qid],
            replay_pool_same_set_as_live=set(replay[(qid, 'cosine')]['candidate_ids']) == set(live_pools[qid]),
            replay_cosine_selection=' '.join(replay[(qid, 'cosine')]['selected_ids']),
            historical_cosine_selection=' '.join(historical_cosine),
            live_cosine_selection=' '.join(live_selected.get((qid, 'cosine'), ['-'])),
            replay_utility_selection=' '.join(replay[(qid, 'utility')]['selected_ids']),
            historical_utility_selection=' '.join(historical_utility),
            live_utility_selection=' '.join(live_selected.get((qid, 'utility'), ['-'])))
        row['cosine_selection_all_three_agree'] = (
            replay[(qid, 'cosine')]['selected_ids'] == historical_cosine
            == live_selected.get((qid, 'cosine')))
        row['utility_selection_all_three_agree'] = (
            replay[(qid, 'utility')]['selected_ids'] == historical_utility
            == live_selected.get((qid, 'utility')))
        parity.append(row)
        for strategy in ('cosine', 'utility'):
            selected = (historical_cosine if strategy == 'cosine' else historical_utility)
            historical_row = smoke.generation_row(query, corpus, selected, strategy,
                                                  smoke.pool_digest(recorded), SEED)
            live_row = smoke.generation_row(query, corpus, live_selected[(qid, strategy)], strategy,
                                            smoke.pool_digest(live_pools[qid]), SEED)
            generation.append(dict(
                qid=qid, strategy=strategy,
                evidence_order_identical=[ref['sha256'] for ref in historical_row['evidence']]
                                        == [ref['sha256'] for ref in live_row['evidence']],
                evidence_set_identical={ref['sha256'] for ref in historical_row['evidence']}
                                       == {ref['sha256'] for ref in live_row['evidence']},
                prompt_text_identical=historical_row['model_request'] == live_row['model_request']))

    timings = {'bare_rank': [], 'rank_with_pool': [], 'rank_with_evidence': []}
    for query in queries:
        vector = runtime.cached[query['qid']]
        for _ in range(3):
            started = time.perf_counter(); rank_with((np.asarray(plan['corpus_order']), vectors), vector)
            timings['bare_rank'].append(time.perf_counter()-started)
            started = time.perf_counter()
            order, scores = rank_with((np.asarray(plan['corpus_order']), vectors), vector)
            smoke.no_self_pool(order, query['query_image']['sha256'])
            timings['rank_with_pool'].append(time.perf_counter()-started)
            started = time.perf_counter()
            order, scores = rank_with((np.asarray(plan['corpus_order']), vectors), vector)
            pool = smoke.no_self_pool(order, query['query_image']['sha256'])
            smoke.ranking_evidence(order, scores, query['query_image']['sha256'], pool)
            timings['rank_with_evidence'].append(time.perf_counter()-started)

    result = dict(
        status='offline_replay_audit_completed', model_loaded=False, gpu_used=False,
        note='replayed encode and utility come from archived artefacts; generation is a stub',
        ranking_reproduction=ranking,
        request_replay=dict(requests=len(replay), queries=len(queries),
                            strategies=list(cost.STRATEGIES),
                            every_pool_matches_history=all(
                                replay[(query['qid'], 'cosine')]['candidate_ids'] == history['smoke_20'][query['qid']]
                                for query in queries),
                            every_cosine_top3_matches_history=all(
                                replay[(query['qid'], 'cosine')]['selected_ids'] == history['smoke_20'][query['qid']][:3]
                                for query in queries),
                            utility_selections_matching_history=sum(
                                replay[(query['qid'], 'utility')]['selected_ids']
                                == smoke.select(query['qid'], history['smoke_20'][query['qid']],
                                                'utility', 3, SEED, utility[query['qid']])
                                for query in queries)),
        smoke_entry_replay=dict(status=smoke_receipt['status'],
                                completed_requests=smoke_receipt['completed_requests'],
                                measured_requests=smoke_receipt['measured_requests'],
                                warmups=sum(1 for row in smoke_rows if row['warmup']),
                                pools_match_history=all(row['candidate_ids'] == history['smoke_20'][row['qid']]
                                                        for row in smoke_rows),
                                cosine_selections_match_history=all(
                                    row['selected_ids'] == history['smoke_20'][row['qid']][:3]
                                    for row in smoke_rows if row['strategy'] == 'cosine'),
                                utility_selections_match_history=all(
                                    row['selected_ids'] == smoke.select(row['qid'], history['smoke_20'][row['qid']],
                                                                        'utility', 3, SEED, utility[row['qid']])
                                    for row in smoke_rows if row['strategy'] == 'utility'),
                                timings_are_replay_only=True),
        cost_entry_replay=dict(status=receipt['status'], measured_requests=receipt['measured_requests'],
                               statistics={name: {key: value for key, value in values.items()
                                                   if key != 'per_query_medians'}
                                           for name, values in receipt['statistics'].items()},
                               timing_scope='replay plumbing only; these seconds are not latency measurements'),
        reference_vector_comparison=dict(
            queries=len(replay),
            comparisons=sum(1 for record in replay.values()
                            if record['query_vector_vs_reference'] is not None),
            bitwise_equal=sum(1 for record in replay.values()
                              if record['query_vector_vs_reference']
                              and record['query_vector_vs_reference']['bitwise_equal']),
            max_l2=max(record['query_vector_vs_reference']['l2'] for record in replay.values()
                       if record['query_vector_vs_reference']),
            note='replay feeds the archived vector itself, so equality is a plumbing check, not an encoder result'),
        round_one_parity=parity, generation_input_equivalence=generation,
        recording_overhead_ms=dict(
            bare_rank_median=1000*statistics.median(timings['bare_rank']),
            rank_plus_no_self_pool_median=1000*statistics.median(timings['rank_with_pool']),
            with_evidence_median=1000*statistics.median(timings['rank_with_evidence']),
            round_one_definition_delta=1000*(statistics.median(timings['rank_with_pool'])
                                             - statistics.median(timings['bare_rank'])),
            added_by_evidence_recording=1000*(statistics.median(timings['rank_with_evidence'])
                                              - statistics.median(timings['rank_with_pool'])),
            samples=len(timings['bare_rank']),
            definitions=['bare: matmul + lexsort',
                         'round one: bare + no-self replenishment (was the timed component)',
                         'round two: round one + ranking evidence and vector fingerprint'],
            note='measured on this Mac against the 768-d index; server CPU differs'))
    (OUT / 'evaluation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    header = list(parity[0])
    with (OUT / 'round_one_parity.csv').open('w') as stream:
        stream.write(','.join(header)+'\n')
        for row in parity:
            stream.write(','.join(str(row[key]) for key in header)+'\n')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('round_one_parity',)}, indent=2, ensure_ascii=False)[:5000])
    print('generation inputs identical:', sum(row['prompt_text_identical'] for row in generation),
          'of', len(generation))


if __name__ == '__main__':
    main()
