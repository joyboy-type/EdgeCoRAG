"""Build the reviewable round-2 plan, lease proposal and budget by local validation.

Nothing here authorizes execution: the plan stays `prepared_unexecuted`, the lease
stays `proposed_not_authorized`, and no instance is contacted. Run with the NumPy
runtime because it builds and validates the real 18,955 x 768 index inputs.
"""
import json
import sys
from pathlib import Path

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=False)

PROJECT = PATHS.project_root
REPO = PATHS.repo
WORK = PATHS.work_dir
SMOKE = WORK / 'e2e-smoke-prepared'
OUT = PATHS.output_dir or WORK / 'e2e-cost-proposed'
ARCHIVE = PATHS.archive_root
PACKAGE = WORK / 'prepared/selection-smoke_20.proposed.json'
SERVER_ROOT = str(PATHS.server_root) if PATHS.server_root else ''

sys.path.insert(0, str(REPO / 'b-side'))
import e2e_smoke as smoke
import e2e_cost as cost
sys.path.insert(0, str(REPO / 'a-side/scripts'))

REPEATS = 6
QUERY_LIMIT = 20
RATE_QUOTE_CNY_HOUR = 1.48
RATE_CAP_CNY_HOUR = 2.18
BUDGET_CAP_CNY = 3
WINDOW_SECONDS = 3900  # one consolidated rental session, 65 minutes
PRESERVATION_SECONDS = 600


def measured_medians():
    """Medians of the archived round-1 measured requests, read from the sealed archive."""
    import statistics, tarfile
    with tarfile.open(SMOKE / 'e2e-smoke-results-20261020.private.tar.gz') as tar:
        rows = [json.loads(line) for line
                in tar.extractfile('results/requests.jsonl').read().decode().splitlines()]
    return {strategy: statistics.median(row['end_to_end_seconds'] for row in rows
                                        if row['strategy'] == strategy and not row['warmup'])
            for strategy in ('cosine', 'utility')}


def main():
    if not SERVER_ROOT and "--help" not in sys.argv: raise ValueError("--server-root required; no server is contacted")
    if OUT.exists() or (OUT.parent / "smoke-recheck").exists():
        raise SystemExit('Refusing to overwrite an existing proposal directory')
    package = json.loads(PACKAGE.read_text())
    retrieval = json.loads((ARCHIVE / 'controls/retrieval-formal.approved.json').read_text())
    medians = measured_medians()
    # The random path shares the cosine retrieval and generation shape; its selection
    # does not call the utility model, so the cosine median is used as the estimate.
    per_triple = medians['cosine'] + medians['cosine'] + medians['utility']
    queries = package['queries'][:QUERY_LIMIT]
    runs = len(queries) * REPEATS
    formal_seconds = runs * per_triple
    estimate = 900
    if formal_seconds > 600:
        raise SystemExit('Formal run no longer fits the bounded estimate; re-derive it')
    index_entry = next(row for row in json.loads((ARCHIVE / 'backup-manifest.json').read_text())['files']
                       if row['path'] == 'results/formal-retrieval-embeddinggemma2/corpus_embeddings.npy')
    # Archived reference vectors make the live encoding measurable per request.
    import numpy as np
    from independent_retrieval import normalize
    cached = normalize(np.load(ARCHIVE / 'results/formal-retrieval-embeddinggemma2/query_embeddings.npy'), 768)
    positions = {q['qid']: i for i, q in enumerate(retrieval['queries'])}
    references = {q['qid']: cached[positions[q['qid']]].tolist() for q in queries}
    ids = [row['id'] for row in retrieval['corpus']]
    if len(ids) != 18955 or ids != list(package['corpus']):
        raise SystemExit('Corpus order identity check failed')
    plan = dict(status='prepared_unexecuted', execution_authorized=False,
                entry=cost.ENTRY,
                queries=queries, corpus=package['corpus'], corpus_order=ids,
                strategies=list(cost.STRATEGIES), repeats=REPEATS, cpu_threads='affinity',
                retriever=retrieval['models']['embeddinggemma2'],
                reference_vectors=references,
                estimate_seconds=estimate,
                index=dict(path=str((ARCHIVE / 'results/formal-retrieval-embeddinggemma2/corpus_embeddings.npy')
                                    .relative_to(PROJECT)),
                           sha256=index_entry['sha256']),
                source_pins={name: smoke.file_sha(REPO / name) for name in cost.COST_SOURCES},
                provenance=dict(
                    observed_query_package_sha256=smoke.file_sha(PACKAGE),
                    retrieval_controls_sha256=smoke.file_sha(ARCHIVE / 'controls/retrieval-formal.approved.json'),
                    index_path_note='Local path for validation; the server plan maps only the index path',
                    query_scope='The 20 already-observed smoke_20 questions; no new blind evaluation'))
    if smoke.file_sha(PROJECT / plan['index']['path']) != index_entry['sha256']:
        raise SystemExit('Index hash mismatch against the archive manifest')
    validation = cost.validate_plan(plan, PROJECT)
    OUT.mkdir(parents=True)
    (OUT / 'local-plan.private.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    server_plan = dict(plan, index=dict(path='results/formal-retrieval-embeddinggemma2/corpus_embeddings.npy',
                                        sha256=index_entry['sha256']))
    (OUT / 'plan.private.json').write_text(json.dumps(server_plan, ensure_ascii=False, indent=2))
    (OUT / 'validation.json').write_text(json.dumps(dict(validation,
        index_sha256=index_entry['sha256'],
        local_plan_sha256=smoke.file_sha(OUT / 'local-plan.private.json'),
        server_plan_sha256=smoke.file_sha(OUT / 'plan.private.json'),
        cpu_threads_note='affinity resolves to the container CPU count and is recorded at run time'), ensure_ascii=False, indent=2))
    lease = dict(status='proposed_not_authorized', execution_authorized=False,
                 protocol_approved=False, shutdown_verified=False,
                 instance_id='678c4cb81e-857c90e4', lease_id=None,
                 plan_sha256=smoke.file_sha(OUT / 'plan.private.json'),
                 data_root=SERVER_ROOT,
                 output_path=SERVER_ROOT + '/results/e2e-cost-20261021-formal',
                 charge_start_epoch=None, deadline_epoch=None,
                 quoted_rate_cny_hour=None, max_rate_cny_hour=RATE_CAP_CNY_HOUR,
                 max_incremental_cny=BUDGET_CAP_CNY, incurred_cny=0,
                 storage_reserve_cny=.5, max_wall_seconds=WINDOW_SECONDS,
                 preservation_reserve_seconds=PRESERVATION_SECONDS, contingency_fraction=.25,
                 scope=(f'{len(queries)} observed smoke_20 queries x cosine/random/utility x {REPEATS} repeats; '
                        'live EG768 query encoding over the resident 18,955 x 768 index; Gemma E2B for '
                        'utility scores and generation; sampled device-wide memory and process RSS'))
    (OUT / 'lease.proposed.json').write_text(json.dumps(lease, ensure_ascii=False, indent=2))
    recheck = dict(status='prepared_unexecuted', execution_authorized=False,
                   entry=smoke.ENTRY,
                   queries=queries[:5], corpus=plan['corpus'], corpus_order=plan['corpus_order'],
                   cpu_threads=plan['cpu_threads'], retriever=plan['retriever'],
                   reference_vectors={q['qid']: references[q['qid']] for q in queries[:5]},
                   estimate_seconds=600, index=plan['index'],
                   source_pins={name: smoke.file_sha(REPO / name) for name in smoke.REQUIRED_SOURCES},
                   provenance=dict(plan['provenance'],
                       purpose='Fixed new-version smoke recheck on the same five round-1 questions'))
    recheck_dir = OUT.parent / 'smoke-recheck'
    recheck_validation = smoke.validate_plan(recheck, PROJECT)
    recheck_dir.mkdir(parents=True)
    (recheck_dir / 'local-plan.private.json').write_text(json.dumps(recheck, ensure_ascii=False, indent=2))
    recheck_server = dict(recheck, index=dict(server_plan['index']))
    (recheck_dir / 'plan.private.json').write_text(json.dumps(recheck_server, ensure_ascii=False, indent=2))
    (recheck_dir / 'validation.json').write_text(json.dumps(recheck_validation, ensure_ascii=False, indent=2))
    recheck_lease = dict(lease, plan_sha256=smoke.file_sha(recheck_dir / 'plan.private.json'),
                         output_path=SERVER_ROOT + '/results/e2e-smoke-recheck-20261021',
                         scope='5 round-1 questions x cosine/utility x 3 repeats; new-version recheck of CPU threads and ranking recording')
    (recheck_dir / 'lease.proposed.json').write_text(json.dumps(recheck_lease, ensure_ascii=False, indent=2))
    # Arithmetic simulation only: the proposal above stays unauthorized.
    trial = dict(lease, charge_start_epoch=0, deadline_epoch=WINDOW_SECONDS,
                 quoted_rate_cny_hour=RATE_QUOTE_CNY_HOUR,
                 execution_authorized=True, protocol_approved=True, shutdown_verified=True)
    available = smoke.check_lease(trial, 300, estimate)
    budget = dict(
        status='proposed_not_authorized', currency='CNY', budget_cap=BUDGET_CAP_CNY,
        rate_quote_cny_hour=RATE_QUOTE_CNY_HOUR, rate_cap_cny_hour=RATE_CAP_CNY_HOUR,
        window_seconds=WINDOW_SECONDS, preservation_reserve_seconds=PRESERVATION_SECONDS,
        contingency_fraction=.25, storage_reserve_cny=.5,
        measured_request_medians_seconds=medians,
        estimate_assumption='random path uses the cosine median; utility includes ten live candidate scores',
        planned=dict(queries=len(queries), strategies=list(cost.STRATEGIES), repeats=REPEATS,
                     requests_per_strategy=runs, measured_requests=runs * len(cost.STRATEGIES),
                     warmup_requests=len(cost.STRATEGIES),
                     formal_seconds_estimate=round(formal_seconds, 1),
                     recheck_requests=32, recheck_seconds_estimate=60,
                     steps=['boot and index/plan verification', 'fixed new-version smoke recheck (separate lease)',
                            'formal three-strategy cost run', 'archive verify then platform shutdown']),
        expected_wall_seconds=2400,
        expected_compute_cny=round(2400 / 3600 * RATE_QUOTE_CNY_HOUR + .01, 2),
        worst_case_cny=round(WINDOW_SECONDS / 3600 * RATE_CAP_CNY_HOUR + .5, 3),
        worst_case_note=('Worst case is the full window at the rate cap plus the storage reserve; it stays '
                         'below the 3 CNY cap but is only reached if every optional step overruns'),
        lease_precheck=dict(arithmetic_simulation_only=True, hypothetical_boot_delay_seconds=300,
                            projected_whole_lease_cny=round(WINDOW_SECONDS / 3600 * RATE_QUOTE_CNY_HOUR + .5, 3),
                            seconds_available_after_boot_and_preservation=available,
                            required_seconds_with_margin=round(estimate * 1.25, 1),
                            passes=available > estimate * 1.25,
                            timer_must_be_reverified_at_launch=True),
        claims_permitted=['per-strategy end-to-end latency distribution on this instance',
                          'component medians with the outer-timer caveat',
                          'sampled device-wide memory and measured process RSS',
                          'live-vs-cached ranking boundary margins'],
        claims_forbidden=['edge-device cost', 'device-wide peak from allocator counters',
                          'independent-question P95', 'accuracy from timing runs',
                          'generalisable speedup from one instance'])
    (OUT / 'budget.proposed.json').write_text(json.dumps(budget, ensure_ascii=False, indent=2))
    print(json.dumps(dict(validation=validation, formal_seconds=round(formal_seconds, 1),
                          recheck_validation=recheck_validation, lease_precheck=budget['lease_precheck'],
                          expected_compute_cny=budget['expected_compute_cny'],
                          worst_case_cny=budget['worst_case_cny']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
