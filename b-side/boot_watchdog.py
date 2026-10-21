"""Independent boot watchdog: shut the platform down at a hard deadline.

Defence in depth on top of `e2e_lease.supervise`, which already shuts the platform
down in a `finally` block and on child timeout. This watchdog covers the cases the
parent cannot: the upload or validation step never reaches the parent, the SSH
session dies, or the parent itself is killed. It is started detached right after
boot, writes a receipt to the persistent disk before acting, and never relies on
the local machine.

It refuses to guess: if the platform supervisor cannot be identified uniquely it
raises instead of signalling an arbitrary process.
"""
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path


def supervisor_pid(proc_root=Path('/proc')):
    found = []
    for entry in Path(proc_root).glob('[0-9]*'):
        try:
            if ((entry/'comm').read_text().strip() == 'supervisord'
                    and b'/init/supervisor/supervisor.ini' in (entry/'cmdline').read_bytes()):
                found.append(int(entry.name))
        except OSError:
            pass
    if len(found) != 1:
        raise ValueError('Expected exactly one platform supervisor, found %d' % len(found))
    return found[0]


def shutdown(proc_root=Path('/proc'), kill=None, sync=True, attempts=40, pause=0.5, sleep=None):
    """SIGTERM the platform supervisor and wait for it to disappear."""
    kill = os.kill if kill is None else kill
    sleep = time.sleep if sleep is None else sleep
    pid = supervisor_pid(proc_root)
    if sync and hasattr(os, 'sync'):
        os.sync()
    kill(pid, signal.SIGTERM)
    for _ in range(attempts):
        if not (Path(proc_root)/str(pid)).exists():
            return pid
        sleep(pause)
    return pid


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.next.json')
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def watch(deadline_epoch, receipt_path, poll_seconds=30., clock=None, sleep=None,
          shutdown_fn=None, proc_root=Path('/proc')):
    """Block until the deadline, then shut down once and record what happened."""
    clock = time.time if clock is None else clock
    sleep = time.sleep if sleep is None else sleep
    shutdown_fn = (lambda: shutdown(proc_root)) if shutdown_fn is None else shutdown_fn
    started = clock()
    receipt = dict(status='armed', deadline_epoch=deadline_epoch, started_epoch=started,
                   arm_epoch=None, poll_seconds=poll_seconds,
                   note='independent of the parent lease; acts even if the caller session died')
    save(receipt_path, receipt)
    while True:
        now = clock()
        if now >= deadline_epoch:
            break
        sleep(min(poll_seconds, deadline_epoch-now))
    receipt.update(status='firing', fired_epoch=now)
    save(receipt_path, receipt)
    try:
        pid = shutdown_fn()
        receipt.update(status='shut_down', supervisor_pid=pid, completed_epoch=clock())
    except BaseException as error:
        receipt.update(status='shutdown_failed_no_retry', error_type=type(error).__name__,
                       error=str(error), completed_epoch=clock())
        save(receipt_path, receipt)
        raise
    save(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deadline-epoch', type=float, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--poll-seconds', type=float, default=30.)
    parser.add_argument('--arm-epoch', type=float)
    args = parser.parse_args()
    now = time.time()
    if args.deadline_epoch <= now:
        parser.exit(2, 'ERROR: deadline must be in the future\n')
    if args.arm_epoch is not None and args.deadline_epoch < args.arm_epoch:
        parser.exit(2, 'ERROR: deadline precedes the arm epoch\n')
    receipt = watch(args.deadline_epoch, args.receipt, args.poll_seconds)
    receipt['armed_from_boot_epoch'] = args.arm_epoch
    save(args.receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
