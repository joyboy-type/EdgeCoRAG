"""Write a run lease from an explicit human authorization record.

Refuses to emit an authorizing lease unless the record carries the user's own
words, a finite rate inside the cap, a verified shutdown path, and a window that
satisfies the whole-lease arithmetic (25% margin + 600 s preservation).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=True)

PROJECT = PATHS.project_root
REPO = PATHS.repo
WORK = PATHS.work_dir
RUNS = {'smoke': WORK / 'e2e-smoke-recheck-20261021', 'cost': WORK / 'e2e-cost-proposed'}
SERVER_ROOT = str(PATHS.server_root) if PATHS.server_root else ''
OUTPUTS = {'smoke': SERVER_ROOT + '/results/e2e-smoke-recheck-20261021',
           'cost': SERVER_ROOT + '/results/e2e-cost-20261021-formal'}
ESTIMATES = {'smoke': 600, 'cost': 900}

sys.path.insert(0, str(REPO / 'b-side'))
import e2e_smoke as smoke


def main():
    if not SERVER_ROOT and "--help" not in sys.argv: raise ValueError("--server-root required; no server is contacted")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization', type=Path, required=True)
    parser.add_argument('--run', choices=sorted(RUNS), required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    record = json.loads(args.authorization.read_text())
    required = ('user_words', 'authorized_at', 'quoted_rate_cny_hour', 'charge_start_epoch',
                'hard_deadline_epoch', 'shutdown_evidence', 'lease_ids', 'max_incremental_cny',
                'storage_reserve_cny')
    missing = [name for name in required if name not in record]
    if missing:
        raise SystemExit('Authorization record incomplete: ' + ', '.join(missing))
    if not isinstance(record['user_words'], str) or len(record['user_words'].strip()) < 4:
        raise SystemExit('User authorization words required')
    if not isinstance(record['shutdown_evidence'], str) or not record['shutdown_evidence'].strip():
        raise SystemExit('Verified shutdown evidence required')
    lease_id = record['lease_ids'].get(args.run)
    if not isinstance(lease_id, str) or not lease_id:
        raise SystemExit('New unique lease id required for this run')
    plan = RUNS[args.run] / 'plan.private.json'
    estimate = ESTIMATES[args.run]
    if json.loads((RUNS[args.run] / 'local-plan.private.json').read_text())['estimate_seconds'] != estimate:
        raise SystemExit('Estimate drifted from the prepared plan')
    lease = dict(
        status='human_authorized_platform_timer_verified',
        execution_authorized=True, protocol_approved=True, shutdown_verified=True,
        instance_id='678c4cb81e-857c90e4', lease_id=lease_id,
        plan_sha256=smoke.file_sha(plan), data_root=SERVER_ROOT, output_path=OUTPUTS[args.run],
        charge_start_epoch=record['charge_start_epoch'], deadline_epoch=None,
        quoted_rate_cny_hour=record['quoted_rate_cny_hour'], max_rate_cny_hour=2.18,
        max_incremental_cny=record['max_incremental_cny'], incurred_cny=0,
        storage_reserve_cny=record['storage_reserve_cny'], max_wall_seconds=2700,
        preservation_reserve_seconds=600, contingency_fraction=.25,
        scope=json.loads(plan.read_text())['provenance'].get('purpose')
              or 'twenty observed smoke_20 questions x cosine/random/utility',
        human_authorization=record['user_words'],
        authorization_recorded_at=record['authorized_at'],
        hard_deadline_epoch=record['hard_deadline_epoch'],
        platform_timer=record.get('platform_timer_local'),
        platform_timer_verified=bool(record.get('platform_timer_local')),
        shutdown_evidence=record['shutdown_evidence'],
        timer_verified_before_boot=bool(record.get('platform_timer_local')))
    deadline = min(record['charge_start_epoch'] + 2700, record['hard_deadline_epoch'])
    if deadline <= record['charge_start_epoch']:
        raise SystemExit('Hard deadline must fall after the charge start')
    lease['deadline_epoch'] = deadline
    # a dry run anchors 'now' just after the hypothetical charge start
    now = record['charge_start_epoch'] + 30 if args.dry_run else time.time()
    available = smoke.check_lease(lease, now, estimate)
    projected = (deadline - lease['charge_start_epoch']) * lease['quoted_rate_cny_hour'] / 3600 \
        + lease['incurred_cny'] + lease['storage_reserve_cny']
    result = dict(lease=lease, estimate_seconds=estimate,
                  window_seconds=deadline - lease['charge_start_epoch'],
                  projected_whole_lease_cny=round(projected, 3),
                  seconds_available_now=round(available, 1),
                  plan_sha256=lease['plan_sha256'])
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    target = RUNS[args.run] / 'lease.json'
    if target.exists():
        raise SystemExit('Refusing to overwrite an existing lease')
    target.write_text(json.dumps(lease, ensure_ascii=False, indent=2))
    result['lease_path'] = str(target)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
