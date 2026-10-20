"""Ordered, fail-stop leases in one rental; default is validation only.

Each stage uses the existing pinned worker and independent verified archive.
The session owns one final shutdown; an independent process guards the deadline.
Only existing approved E2E worker protocols are dispatched. No retry or download.
"""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import boot_watchdog
import e2e_lease as guard
import e2e_smoke as smoke

REPO=Path(__file__).resolve().parents[1]


def approved_validators():
    import e2e_cost
    return {smoke.ENTRY:smoke.validate_plan,e2e_cost.ENTRY:e2e_cost.validate_plan}


def validate_stages(stages,root,deadline,now,*,repo=REPO,hostname=None,validators=None,validate_inputs=True):
    root=Path(root).resolve();repo=Path(repo).resolve()
    validators=approved_validators() if validators is None else validators
    hostname=socket.gethostname() if hostname is None else hostname
    if (type(deadline) not in (int,float) or not math.isfinite(deadline)
            or not 0<deadline-now<=smoke.MAX_LEASE_SECONDS):
        raise ValueError('Session deadline must be future and within 7200 seconds')
    if not isinstance(stages,list) or not stages:
        raise ValueError('Nonempty ordered stage list required')
    prepared=[];labels=set();lease_ids=set();outputs=[];total=0
    shared=None
    for row in stages:
        if not isinstance(row,dict) or set(row)!={'label','plan','lease','entry'}:
            raise ValueError('Each stage requires exactly label/plan/lease/entry')
        label=row['label']
        if not isinstance(label,str) or not label or label in labels:
            raise ValueError('Unique nonempty stage labels required')
        labels.add(label)
        if row['entry'] not in validators:raise ValueError('Unknown execution entry')
        plan_path=Path(row['plan']).resolve();lease_path=Path(row['lease']).resolve()
        plan=json.loads(plan_path.read_text());lease=json.loads(lease_path.read_text())
        if plan.get('entry')!=row['entry'] or lease.get('plan_sha256')!=guard.sha(plan_path):
            raise ValueError('Stage/plan/lease identity mismatch')
        if Path(lease['data_root']).resolve()!=root:raise ValueError('Stage data root mismatch')
        instance=lease.get('instance_id')
        if not isinstance(instance,str) or not instance or hostname!='autodl-container-'+instance:
            raise ValueError('Lease must match the current approved instance')
        lease_id=lease.get('lease_id')
        if not isinstance(lease_id,str) or not lease_id or lease_id in lease_ids:
            raise ValueError('Unique new stage lease required')
        lease_ids.add(lease_id)
        if lease.get('deadline_epoch')!=deadline:
            raise ValueError('Every stage must share the session hard deadline')
        # A stage cannot reset accrued cost or restart the charging clock.
        binding={k:lease.get(k) for k in ('instance_id','charge_start_epoch','deadline_epoch',
            'quoted_rate_cny_hour','max_rate_cny_hour','max_incremental_cny','incurred_cny','storage_reserve_cny')}
        if shared is None:shared=binding
        elif shared!=binding:raise ValueError('Stages must share one whole-rental budget')
        smoke.check_lease(lease,now,plan['estimate_seconds'])
        if validate_inputs:validators[row['entry']](plan,root,repo)
        output=Path(lease['output_path']).resolve()
        archive=output.parent/(output.name+'.private.tar.gz')
        if (not output.is_relative_to(root) or output==root or output.exists() or archive.exists()
                or Path(str(archive)+'.verified.json').exists()):
            raise ValueError('Each output/archive must be new and on the persistent root')
        if any(output.is_relative_to(x) or x.is_relative_to(output) for x in outputs):
            raise ValueError('Stage outputs must not overlap')
        outputs.append(output)
        claim=root/'e2e-claims'/(smoke.pool_digest({'lease_id':lease_id})+'.json')
        if claim.exists():raise ValueError('Lease was already claimed; no retry')
        total+=plan['estimate_seconds']
        prepared.append(dict(row,plan_data=plan,lease_data=lease,plan_path=plan_path,
            lease_path=lease_path,output=output,archive=archive,claim=claim))
    if deadline-now-600<=total*1.25:
        raise ValueError('Combined estimates exceed session window with preservation and margin')
    return prepared


def start_watchdog(deadline,receipt,python,root):
    command=[str(python),str(REPO/'b-side/boot_watchdog.py'),'--deadline-epoch',str(deadline),
             '--receipt',str(receipt),'--poll-seconds','1']
    log=Path(receipt).with_suffix('.log')
    with log.open('x') as stream:
        child=subprocess.Popen(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    until=time.monotonic()+10
    while time.monotonic()<until:
        if Path(receipt).exists() and json.loads(Path(receipt).read_text()).get('status')=='armed':return child
        if child.poll() is not None:raise RuntimeError('Independent watchdog exited before arming')
        time.sleep(.05)
    # Leave a live watchdog running when acknowledgement is uncertain.
    raise RuntimeError('Independent watchdog did not acknowledge arming')


def run_session(stages,root,python,deadline,session_dir,*,shutdown_fn=None,supervise_fn=None,
                watchdog_fn=None,clock=None,repo=REPO,hostname=None,validators=None):
    clock=time.time if clock is None else clock
    shutdown_fn=guard.stop_platform if shutdown_fn is None else shutdown_fn
    supervise_fn=guard.supervise if supervise_fn is None else supervise_fn
    watchdog_fn=start_watchdog if watchdog_fn is None else watchdog_fn
    root=Path(root).resolve();session_dir=Path(session_dir).resolve();repo=Path(repo).resolve()
    prepared=validate_stages(stages,root,deadline,clock(),repo=repo,hostname=hostname,validators=validators,validate_inputs=False)
    if not session_dir.is_relative_to(root) or session_dir==root or session_dir.exists():
        raise ValueError('New persistent session directory required')
    if any(session_dir.is_relative_to(p['output']) or p['output'].is_relative_to(session_dir) for p in prepared):
        raise ValueError('Session metadata must not overlap stage outputs')
    session_dir.mkdir(parents=True)
    receipt_path=session_dir/'session-receipt.json';watchdog=None
    receipt=dict(status='started',deadline_epoch=deadline,started_epoch=clock(),
        stages=[dict(label=p['label'],status='skipped') for p in prepared],
        watchdog_status='not_started',shutdown_calls=0)
    try:
        watchdog=watchdog_fn(deadline,session_dir/'watchdog-receipt.json',Path(python),root)
        receipt['watchdog_status']='armed';boot_watchdog.save(receipt_path,receipt)
        validate_stages(stages,root,deadline,clock(),repo=repo,hostname=hostname,validators=validators)
        for index,p in enumerate(prepared):
            record=receipt['stages'][index];record.update(status='started',started_epoch=clock())
            boot_watchdog.save(receipt_path,receipt)
            try:
                # Recheck immutable bytes and remaining budget immediately before claiming.
                if guard.sha(p['plan_path'])!=p['lease_data']['plan_sha256'] or json.loads(p['lease_path'].read_text())!=p['lease_data']:
                    raise ValueError('Stage inputs changed since session validation')
                seconds=smoke.check_lease(p['lease_data'],clock(),p['plan_data']['estimate_seconds'])
                p['claim'].parent.mkdir(exist_ok=True)
                with p['claim'].open('x') as stream:
                    json.dump(p['lease_data'],stream);stream.flush();os.fsync(stream.fileno())
                output=p['output'];output.mkdir()
                (output/'plan.json').write_bytes(p['plan_path'].read_bytes())
                (output/'lease.json').write_bytes(p['lease_path'].read_bytes())
                for name,digest in p['plan_data']['source_pins'].items():
                    source=repo/name
                    if not source.resolve().is_relative_to(repo) or guard.sha(source)!=digest:
                        raise ValueError('Pinned source changed or escaped repository')
                    target=output/'code'/name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(source.read_bytes())
                command=[str(python),str(output/'code'/p['entry']),'--worker','--plan',str(output/'plan.json'),
                    '--root',str(root),'--output',str(output/'results')]
                previous=dict(os.environ)
                try:
                    os.environ.update(guard.offline_environment(root))
                    result=supervise_fn(command,output,p['archive'],seconds,lambda:None)
                finally:
                    os.environ.clear();os.environ.update(previous)
                guard.verify_archive(p['archive'])
                verified=json.loads(Path(str(p['archive'])+'.verified.json').read_text())
                digest=guard.sha(p['archive'])
                if verified.get('sha256')!=digest:raise ValueError('Stage verification receipt hash mismatch')
                record.update(result,archive=p['archive'].name,sha256=digest,bytes=p['archive'].stat().st_size,
                    completed_epoch=clock())
                if result.get('returncode')!=0 or result.get('timed_out') or result.get('status')!='completed':
                    raise RuntimeError('Stage failed; later stages skipped without retry')
            except BaseException as error:
                record.update(status='failed_partial_no_retry',error_type=type(error).__name__,error=str(error),completed_epoch=clock())
                raise
            finally:boot_watchdog.save(receipt_path,receipt)
        receipt['status']='completed'
    except BaseException as error:
        receipt.update(status='failed_partial_no_retry',error_type=type(error).__name__,error=str(error))
    finally:
        receipt['completed_epoch']=clock();receipt['shutdown_calls']=1
        try:boot_watchdog.save(receipt_path,receipt)
        except OSError as error:
            receipt.update(status='failed_partial_no_retry',receipt_write_error=str(error))
        try:
            try:
                if hasattr(os,'sync'):os.sync()
            finally:shutdown_fn()
            receipt['shutdown_status']='signalled'
        except BaseException as error:
            # The independent watchdog stays armed if the final signal failed.
            receipt.update(status='failed_partial_no_retry',shutdown_status='failed_watchdog_retained',
                           shutdown_error=str(error))
        else:
            if watchdog is not None:
                try:
                    if watchdog.poll() is None:
                        watchdog.terminate();watchdog.wait(timeout=5)
                except (OSError,subprocess.TimeoutExpired):pass
        try:boot_watchdog.save(receipt_path,receipt)
        except OSError as error:receipt.update(receipt_write_error=str(error))
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stages',type=Path,required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--python',type=Path,required=True)
    parser.add_argument('--deadline-epoch',type=float,required=True)
    parser.add_argument('--session-output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();stages=json.loads(args.stages.read_text())
    # Relative plan/lease names belong to the stages file's directory.
    for row in stages:
        for key in ('plan','lease'):row[key]=str((args.stages.parent/row[key]).resolve())
    if args.execute:
        receipt=run_session(stages,args.root,args.python.resolve(),args.deadline_epoch,args.session_output)
        print(json.dumps(receipt,indent=2));return 0 if receipt['status']=='completed' else 1
    prepared=validate_stages(stages,args.root,args.deadline_epoch,time.time())
    print(json.dumps(dict(status='validated_only',stages=len(prepared),execution_authorized=False)))
    return 0

if __name__=='__main__':sys.exit(main())
