"""Verify a retrieved cost-run archive locally, without trusting the server.

Checks the archive manifest, the request inventory and per-request invariants, then
recomputes the reported statistics from the raw rows. It never writes into the
archive and never invents a number that is absent from the data.
"""
import argparse
import json
import statistics
import tarfile
from pathlib import Path

STRATEGIES = ('cosine', 'random', 'utility')
COMPONENTS = ('query_decode_encode_seconds', 'ranking_no_self_seconds',
              'selection_request_build_seconds', 'generation_decode_seconds')


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def p95(values):
    ordered = sorted(values)
    return ordered[max(0, -(-95 * len(ordered) // 100) - 1)] if len(ordered) >= 20 else None


def check_archive(archive):
    failures = []
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        manifest = json.load(tar.extractfile('manifest.json'))
        if len(names) != len(set(names)):
            failures.append('duplicate archive members')
        if set(names) != {'manifest.json'} | set(manifest):
            failures.append('archive inventory mismatch')
        for name, digest in manifest.items():
            if sha(tar.extractfile(name).read()) != digest:
                failures.append('hash mismatch: ' + name)
        readers = {name: tar.extractfile(name).read() for name in manifest}
    return failures, manifest, readers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--history', type=Path,
                        help='optional no-self ranks jsonl used for candidate-pool comparison')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    failures, manifest, readers = check_archive(args.archive)
    plan = json.loads(readers['plan.json'])
    lease = json.loads(readers['lease.json'])
    setup = json.loads(readers['setup.json'])
    threads = json.loads(readers['thread-configuration.json'])
    receipt = json.loads(readers['results/receipt.json'])
    rows = [json.loads(line) for line in readers['results/requests.jsonl'].decode().splitlines()]
    measured = [row for row in rows if not row['warmup']]
    warmups = [row for row in rows if row['warmup']]

    if receipt.get('status') != 'completed':
        failures.append('receipt is not completed: %r' % receipt.get('status'))
    if len(rows) != len(warmups) + len(measured):
        failures.append('row inventory inconsistent')
    if len(measured) != plan['repeats'] * len(plan['queries']) * len(STRATEGIES):
        failures.append('measured request count does not match the plan')
    keys = {(row['qid'], row['strategy'], row['repeat']) for row in measured}
    if len(keys) != len(measured):
        failures.append('duplicate measured request keys')

    qids = {query['qid'] for query in plan['queries']}
    self_ids = {'image:' + query['query_image']['sha256'] for query in plan['queries']}
    pools, selection_violations, timing_violations, thread_rows = {}, 0, 0, []
    distances = []
    for row in rows:
        candidates = row.get('candidate_ids') or []
        ranking = row.get('ranking') or {}
        if len(candidates) != 10 or len(set(candidates)) != 10:
            selection_violations += 1
        if set(candidates) & self_ids:
            selection_violations += 1
        if ranking.get('candidate_ids') != candidates:
            selection_violations += 1
        if any(cid not in candidates for cid in row.get('selected_ids') or []):
            selection_violations += 1
        if len(row.get('selected_ids') or []) != 3:
            selection_violations += 1
        pools.setdefault(row['qid'], set()).add(tuple(candidates))
        if not row['warmup']:
            total = sum(row['components'][name] for name in COMPONENTS)
            if row['end_to_end_seconds'] < total - 1e-9:
                timing_violations += 1
        if row.get('query_vector_vs_reference') is None:
            distances.append(row['qid'])
        if row['qid'] not in qids:
            failures.append('unknown qid ' + row['qid'])
    if any(len(found) != 1 for found in pools.values()):
        failures.append('candidate pool was not stable across repeats within a query')
    if selection_violations:
        failures.append('%d selection/ranking invariant violations' % selection_violations)
    if timing_violations:
        failures.append('%d outer-timer violations' % timing_violations)
    if distances:
        failures.append('missing live-vs-reference distance for %d requests' % len(distances))

    observed = (threads.get('observed') or {})
    if threads.get('invalid_inherited'):
        failures.append('invalid inherited thread value: %r' % threads['invalid_inherited'])
    if observed.get('torch_intra_op_threads') != observed.get('requested'):
        failures.append('pinned thread count was not applied')
    blas = [pool.get('num_threads') for pool in (observed.get('blas_threadpool') or {}).get('pools', [])]
    if not blas:
        failures.append('no BLAS thread evidence recorded')

    stats, recomputed = receipt.get('statistics') or {}, {}
    for strategy in STRATEGIES:
        selected = [row for row in measured if row['strategy'] == strategy]
        values = [row['end_to_end_seconds'] for row in selected]
        recomputed[strategy] = dict(
            n=len(values), median_seconds=statistics.median(values), p95_seconds=p95(values),
            min_seconds=min(values), max_seconds=max(values),
            component_medians={name: statistics.median(row['components'][name] for row in selected)
                               for name in COMPONENTS})
        reported = stats.get(strategy) or {}
        if reported.get('n') != len(values):
            failures.append('n mismatch for ' + strategy)
        if abs((reported.get('median_seconds') or -1) - recomputed[strategy]['median_seconds']) > 1e-9:
            failures.append('median mismatch for ' + strategy)
        if reported.get('p95_seconds') != recomputed[strategy]['p95_seconds']:
            failures.append('p95 mismatch for ' + strategy)

    history_check = None
    if args.history:
        history = {row['qid']: row['corpus_ids'] for row
                   in map(json.loads, args.history.read_text().splitlines())}
        compared = [qid for qid in history if qid in pools]
        history_check = dict(
            compared=len(compared),
            same_set=sum(set(history[qid]) == set(next(iter(pools[qid]))) for qid in compared),
            same_order=sum(history[qid] == list(next(iter(pools[qid]))) for qid in compared))

    result = dict(
        status='passed' if not failures else 'failed', failures=failures,
        archive=str(args.archive), archive_sha256=sha(args.archive.read_bytes()),
        members=len(manifest), plan_sha256=sha(readers['plan.json']),
        lease=dict(lease_id=lease.get('lease_id'), plan_sha256=lease.get('plan_sha256'),
                   deadline_epoch=lease.get('deadline_epoch'),
                   shutdown_evidence=lease.get('shutdown_evidence'),
                   platform_timer_verified=lease.get('platform_timer_verified')),
        requests=dict(total=len(rows), warmups=len(warmups), measured=len(measured),
                      queries=len(pools), strategies=list(STRATEGIES)),
        threads=dict(requested=observed.get('requested'), cpu_count=observed.get('cpu_count'),
                     affinity=observed.get('affinity_count'),
                     torch_intra=observed.get('torch_intra_op_threads'),
                     torch_inter=observed.get('torch_inter_op_threads'),
                     blas_threads=blas, inherited=threads.get('inherited'),
                     invalid_inherited=threads.get('invalid_inherited')),
        setup=dict(cold_setup_seconds=setup.get('cold_setup_seconds'),
                   validation_and_setup_seconds=setup.get('validation_and_setup_seconds'),
                   index_memory=setup.get('index_memory'),
                   device_memory_at_setup=setup.get('device_memory_at_setup')),
        statistics=recomputed, receipt_statistics_match=not any('mismatch' in f for f in failures),
        live_vs_reference=dict(requests=len(rows),
                              recorded=len(rows) - len(distances),
                              max_l2=max(row['query_vector_vs_reference']['l2'] for row in rows),
                              median_l2=statistics.median(row['query_vector_vs_reference']['l2'] for row in rows),
                              bitwise_equal=sum(row['query_vector_vs_reference']['bitwise_equal'] for row in rows),
                              max_cosine=min(row['query_vector_vs_reference']['cosine'] for row in rows)),
        history_check=history_check,
        scope=('single RTX3090 instance; repeated requests to twenty observed questions; '
               'not an edge-device or independent-question measurement'))
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text)
    print(text)
    raise SystemExit(0 if result['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
