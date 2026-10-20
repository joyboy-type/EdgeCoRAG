"""Same-machine cost experiment entry. Preparation only until a new lease exists.

Reuses the smoke request path (live query encoding, resident CPU index, no-self
replenishment, three selection strategies) and adds the accounting the technical
smoke lacked: pinned CPU threads, sampled device-wide memory, process RSS and a
declared request/cluster structure for every reported statistic. This module
never boots an instance, downloads a model or writes into an archived directory.
"""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'b-side'))
sys.path.insert(0, str(REPO/'a-side/scripts'))
import e2e_smoke as smoke

STRATEGIES = ('cosine', 'random', 'utility')
ENTRY = 'b-side/e2e_cost.py'
COST_SOURCES = smoke.REQUIRED_SOURCES + (ENTRY,)
MIN_QUERIES, MAX_QUERIES = 5, 40
MIN_REPEATS, MAX_REPEATS = 2, 10
MAX_ESTIMATE_SECONDS = 2400
GENERATION_TIMING = ('preprocess_seconds', 'generate_seconds')
COMPONENTS = ('query_decode_encode_seconds', 'ranking_no_self_seconds',
              'selection_request_build_seconds', 'generation_decode_seconds')


def schedule(queries, strategies=STRATEGIES, repeats=5):
    """One warmup per strategy, then balanced strategy rotation across repeats."""
    smoke.no_labels(queries)
    strategies = tuple(strategies or ())
    if not isinstance(queries, list) or not MIN_QUERIES <= len(queries) <= MAX_QUERIES:
        raise ValueError('Fixed observed query set of bounded size required')
    if len({q['qid'] for q in queries}) != len(queries):
        raise ValueError('Duplicate query identity')
    if any(q.get('split') not in ('smoke_20', 'dev') for q in queries):
        raise ValueError('Observed splits only; no holdout evaluation')
    if strategies != STRATEGIES:
        raise ValueError('cosine, random and utility are all required')
    if type(repeats) is not int or not MIN_REPEATS <= repeats <= MAX_REPEATS:
        raise ValueError('Repeat count out of bound')
    rows = [dict(qid=queries[0]['qid'], strategy=s, repeat=-1, warmup=True) for s in strategies]
    for repeat in range(repeats):
        for index, query in enumerate(queries):
            offset = (index + repeat) % len(strategies)
            rotation = strategies[offset:] + strategies[:offset]
            rows.extend(dict(qid=query['qid'], strategy=s, repeat=repeat, warmup=False)
                        for s in rotation)
    return rows


def cover_plan(plan, root, repo=REPO):
    """Shared plan checks: authorization state, threads, pins, retriever, inputs, order."""
    smoke.no_labels(plan)
    root, repo = Path(root).resolve(), Path(repo).resolve()
    if plan.get('status') != 'prepared_unexecuted' or plan.get('execution_authorized') is not False:
        raise ValueError('Prepared, unexecuted plan required; a separate new lease authorizes execution')
    if plan.get('entry') != ENTRY:
        raise ValueError('Cost plan must name its own execution entry')
    smoke.resolve_cpu_threads(plan.get('cpu_threads'))
    smoke.reference_vectors(plan)
    if (set(plan['source_pins']) != set(COST_SOURCES)
            or any(smoke.file_sha(repo/name) != digest for name, digest in plan['source_pins'].items())):
        raise ValueError('Source pin mismatch')
    if any(plan['retriever'].get(k) != v for k, v in smoke.RETRIEVER_SPEC.items()):
        raise ValueError('Pinned EG768 required')
    ids, corpus = plan['corpus_order'], plan['corpus']
    if len(ids) < 11 or len(ids) != len(set(ids)) or set(ids) != set(corpus):
        raise ValueError('Corpus/index order mismatch')
    if type(plan.get('estimate_seconds')) not in (int, float) or not 0 < plan['estimate_seconds'] <= MAX_ESTIMATE_SECONDS:
        raise ValueError('Bounded estimate required before any paid run')
    checked = {}

    def verify(ref):
        path = (root/ref['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Input missing or outside root')
        if path not in checked:
            checked[path] = smoke.file_sha(path)
        if checked[path] != ref['sha256']:
            raise ValueError('Input hash mismatch')
    verify(plan['index'])
    for query in plan['queries']:
        if set(query) != {'qid', 'split', 'question', 'choices', 'query_image'} or set(query['choices']) != set('ABCD'):
            raise ValueError('Unexpected query metadata')
        verify(query['query_image'])
    for ref in corpus.values():
        verify(ref)
    rows = schedule(plan['queries'], plan.get('strategies'), plan.get('repeats'))
    measured = [row for row in rows if not row['warmup']]
    if len(measured) != len(plan['queries']) * len(STRATEGIES) * plan['repeats']:
        raise ValueError('Schedule does not match the declared sample structure')
    return rows


def validate_plan(plan, root, repo=REPO):
    rows = cover_plan(plan, root, repo)
    return dict(status='validated_no_model_loaded', queries=len(plan['queries']),
                strategies=list(plan['strategies']), repeats=plan['repeats'],
                planned_requests=len(rows), measured_requests=len(rows)-len(STRATEGIES),
                cpu_threads=plan['cpu_threads'], synthetic=False, gpu_execution_performed=False)


def request(query, corpus, strategy, runtime, clock=time.perf_counter):
    """Smoke request plus boundary-sampled device and process counters."""
    device_before, rss_before = runtime.device_memory(), smoke.process_rss_bytes()
    record = smoke.request(query, corpus, strategy, runtime, clock,
                           splits=('smoke_20', 'dev'), strategies=STRATEGIES)
    # New-run recording comes from smoke.request; the legacy boundary samples stay explicit.
    record['resources'] = dict(device_before=device_before, device_after=runtime.device_memory(),
                               rss_before=rss_before, rss_after=smoke.process_rss_bytes(),
                               scope=('device-wide CUDA sample at request boundaries and /proc process '
                                      'counters; sampled, not peaks, and the device value is not system RAM'))
    return record


def p95(values):
    ordered = sorted(values)
    if len(ordered) < 20:
        return None
    return ordered[max(0, math.ceil(.95 * len(ordered)) - 1)]


def aggregate(rows, strategies=STRATEGIES):
    result = {}
    for strategy in strategies:
        selected = [row for row in rows if row['strategy'] == strategy]
        if not selected:
            raise ValueError('No measurements for ' + strategy)
        values = [row['end_to_end_seconds'] for row in selected]
        per_query = {}
        for qid in sorted({row['qid'] for row in selected}):
            per_query[qid] = statistics.median(row['end_to_end_seconds'] for row in selected if row['qid'] == qid)
        device = [max(row['resources']['device_before']['used_bytes'],
                      row['resources']['device_after']['used_bytes']) for row in selected]
        rss = [row['resources']['rss_after']['peak_bytes'] for row in selected
               if row['resources']['rss_after'] and row['resources']['rss_after']['peak_bytes']]
        result[strategy] = dict(
            n=len(values), n_queries=len(per_query),
            requests_per_query=len(values) / len(per_query),
            median_seconds=statistics.median(values), p95_seconds=p95(values),
            p95_method='nearest-rank over request values; requires at least 20 requests',
            min_seconds=min(values), max_seconds=max(values),
            component_medians={name: statistics.median(row['components'][name] for row in selected)
                               for name in COMPONENTS},
            generation_timing_medians={name: statistics.median(
                row['generation']['timing'][name] for row in selected
                if (row.get('generation') or {}).get('timing') and name in row['generation']['timing'])
                for name in GENERATION_TIMING
                if any((row.get('generation') or {}).get('timing')
                       and name in row['generation']['timing'] for row in selected)},
            per_query_medians=per_query,
            device_used_bytes_max_sampled=max(device),
            process_rss_peak_bytes=max(rss) if rss else None)
    return result


def run(queries, corpus, output, runtime, strategies=STRATEGIES, repeats=5):
    jobs = schedule(queries, strategies, repeats)
    lookup = {query['qid']: query for query in queries}
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    receipt = dict(status='running', synthetic=runtime.synthetic, queries=len(queries),
                   strategies=list(strategies), repeats=repeats,
                   planned_requests=len(jobs), completed_requests=0, measured_requests=0,
                   p95_seconds=None,
                   sample_structure=dict(requests_per_query_per_strategy=repeats, query_clusters=len(queries),
                                         note=('Repeated requests to one question are not independent questions; '
                                               'report request-level and per-question statistics separately')))
    smoke.save(out/'receipt.json', receipt)
    measured = []
    try:
        with (out/'requests.jsonl').open('x') as stream:
            for job in jobs:
                try:
                    record = dict(job, **{k: v for k, v in request(lookup[job['qid']], corpus,
                                                                   job['strategy'], runtime).items()
                                          if k not in job})
                except BaseException as error:
                    stream.write(json.dumps(dict(job, error_type=type(error).__name__, error=str(error), recording=getattr(runtime,'last_recording',{}))) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                    raise
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
                receipt['completed_requests'] += 1
                if not job['warmup']:
                    measured.append(record)
                    receipt['measured_requests'] += 1
                smoke.save(out/'receipt.json', receipt)
        receipt['statistics'] = aggregate(measured, tuple(strategies))
        receipt['p95_seconds'] = {strategy: values['p95_seconds']
                                  for strategy, values in receipt['statistics'].items()}
        receipt['status'] = 'completed'
    except BaseException as error:
        receipt.update(status='failed_partial_no_retry', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        smoke.save(out/'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    root = args.root.resolve()
    if not args.worker:
        print(json.dumps(validate_plan(plan, root), indent=2))
        return
    if args.output is None:
        raise ValueError('New output required')
    lease = json.loads((args.output.parent/'lease.json').read_text())
    if (lease.get('plan_sha256') != smoke.file_sha(args.plan)
            or Path(lease['output_path']).resolve() != args.output.parent.resolve()):
        raise ValueError('Worker lease binding mismatch')
    smoke.check_lease(lease, time.time(), plan['estimate_seconds'])
    claim = root/'e2e-claims'/(smoke.pool_digest({'lease_id': lease['lease_id']}) + '.json')
    if json.loads(claim.read_text()) != lease:
        raise ValueError('Parent claim required')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    threads = smoke.resolve_cpu_threads(plan['cpu_threads'])
    configuration = smoke.configure_cpu_threads(threads)
    applied, thread_handle = smoke.apply_cpu_threads(threads)
    configuration['applied_threads'] = applied
    smoke.save(args.output.parent/'thread-configuration.json', configuration)
    started = time.perf_counter()
    validation = validate_plan(plan, root)
    smoke.save(args.output.parent/'validation.json', validation)
    runtime = smoke.NativeRuntime(plan, root)
    configuration['observed'] = smoke.observed_parallel_evidence(
        threads, torch_threads=runtime.torch.get_num_threads,
        torch_interop=runtime.torch.get_num_interop_threads)
    smoke.verify_thread_configuration(configuration['observed'])
    smoke.save(args.output.parent/'thread-configuration.json', configuration)
    smoke.save(args.output.parent/'setup.json', dict(
        cold_setup_seconds=runtime.cold_setup_seconds,
        validation_and_setup_seconds=time.perf_counter() - started,
        runtime=runtime.backend.runtime, cpu_threads=configuration,
        index_memory=dict(resident_vector_bytes=runtime.vectors.nbytes,
                          rss_before_index=runtime.rss_before_index,
                          rss_after_index=runtime.rss_after_index,
                          scope='resident float32 index array plus measured /proc counters'),
        device_memory_at_setup=runtime.device_memory(),
        topology='EG768 plus Gemma E2B co-resident on one CUDA GPU; same E2B reused for utility/generation',
        online_corpus_encoding=False, live_query_encoding=True))
    smoke.attach_reference_vectors(plan)
    run(plan['queries'], plan['corpus'], args.output, runtime,
        tuple(plan['strategies']), plan['repeats'])


if __name__ == '__main__':
    main()
