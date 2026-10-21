"""Independent CPU parent for one bounded smoke lease. Never boots a GPU."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tarfile
import time


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()


def verify_archive(path):
    with tarfile.open(path) as tar:
        names=tar.getnames()
        if len(set(names))!=len(names):raise ValueError('Duplicate archive entries')
        manifest=json.load(tar.extractfile('manifest.json'))
        if set(names)!={'manifest.json'}|set(manifest):raise ValueError('Archive inventory mismatch')
        for name,digest in manifest.items():
            with tar.extractfile(name) as f:
                if hashlib.sha256(f.read()).hexdigest()!=digest:raise ValueError('Archive hash mismatch')
    return True


def stop_platform():
    # Match the platform supervisor shutdown target without deleting Trash.
    found=[]
    for d in Path('/proc').glob('[0-9]*'):
        try:
            if ((d/'comm').read_text().strip()=='supervisord' and
                    b'/init/supervisor/supervisor.ini' in (d/'cmdline').read_bytes()):found.append(int(d.name))
        except OSError:pass
    if len(found)!=1:raise ValueError('Expected one AutoDL supervisor')
    os.sync();os.kill(found[0],signal.SIGTERM)


def supervise(command,payload,archive,seconds,shutdown):
    payload=Path(payload).resolve();archive=Path(archive).resolve()
    if archive.exists() or archive.is_relative_to(payload):raise ValueError('New external archive required')
    child=None;timed_out=False
    try:
        with (payload/'worker.log').open('x') as log:
            child=subprocess.Popen(command,cwd=payload,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try: child.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                timed_out=True
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        result={'returncode':child.returncode,'timed_out':timed_out,'epoch':time.time(),
                'status':'completed' if child.returncode==0 else 'failed_partial_no_retry'}
        (payload/'parent-receipt.json').write_text(json.dumps(result,indent=2))
        manifest={str(p.relative_to(payload)):sha(p) for p in sorted(payload.rglob('*')) if p.is_file()}
        data=json.dumps(manifest,indent=2).encode()
        with archive.open('xb') as raw,tarfile.open(fileobj=raw,mode='w:gz',compresslevel=1) as tar:
            for name in manifest:tar.add(payload/name,arcname=name)
            info=tarfile.TarInfo('manifest.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
        verify_archive(archive)
        (archive.parent/(archive.name+'.verified.json')).write_text(json.dumps(dict(result,sha256=sha(archive)),indent=2))
        return result
    finally:
        try:
            if child is not None and child.poll() is None:
                os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        finally:
            # Results remain on the persistent volume even if archive construction fails.
            if hasattr(os,'sync'):os.sync()
            shutdown()


def offline_environment(root, environ=None):
    """Honor operator cache settings; default under <SERVER_ROOT>/cache."""
    env = dict(os.environ if environ is None else environ)
    home = env.get('HF_HOME') or str(Path(root) / 'cache/huggingface')
    env.update(HF_HOME=home, HF_HUB_CACHE=env.get('HF_HUB_CACHE') or str(Path(home)/'hub'),
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    overlay = str(Path(root)/'retriever-overlay')
    env['PYTHONPATH'] = os.pathsep.join(filter(None, (overlay, env.get('PYTHONPATH'))))
    return env


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',required=True,type=Path);ap.add_argument('--root',required=True,type=Path)
    ap.add_argument('--lease',type=Path);ap.add_argument('--execute',action='store_true')
    ap.add_argument('--python',type=Path)
    a=ap.parse_args()
    import e2e_cost, e2e_smoke
    validators={'b-side/e2e_smoke.py':e2e_smoke.validate_plan,'b-side/e2e_cost.py':e2e_cost.validate_plan}
    check_lease,pool_digest=e2e_smoke.check_lease,e2e_smoke.pool_digest
    plan=json.loads(a.plan.read_text());root=a.root.resolve()
    if plan.get('entry') not in validators:raise ValueError('Plan entry is not an approved execution entry')
    validate_plan=validators[plan['entry']]
    if not a.execute:
        print(json.dumps(validate_plan(plan,root),indent=2));return
    if a.lease is None or a.python is None:raise ValueError('Explicit new lease and pinned Python required')
    lease=json.loads(a.lease.read_text())
    if lease.get('plan_sha256')!=sha(a.plan):raise ValueError('Lease plan binding mismatch')
    if lease.get('instance_id')!='678c4cb81e-857c90e4' or socket.gethostname()!='autodl-container-678c4cb81e-857c90e4':raise ValueError('Existing approved instance only')
    if not isinstance(lease.get('lease_id'),str) or not lease['lease_id']:raise ValueError('New unique lease id required')
    if Path(lease['data_root']).resolve()!=root:raise ValueError('Data root mismatch')
    check_lease(lease,time.time(),plan['estimate_seconds'])
    output=Path(lease['output_path']).resolve()
    if not output.is_relative_to(root) or output.exists():raise ValueError('New persistent output path required')
    claims=root/'e2e-claims';claims.mkdir(exist_ok=True)
    claim=claims/(pool_digest({'lease_id':lease['lease_id']})+'.json')
    with claim.open('x') as f:json.dump(lease,f);f.flush();os.fsync(f.fileno())
    delegated=False
    try:
        output.mkdir();(output/'plan.json').write_bytes(a.plan.read_bytes());(output/'lease.json').write_bytes(a.lease.read_bytes())
        # Validation and cold setup occur in the supervised child, inside the lease.
        repo=Path(__file__).resolve().parents[1]
        for name in plan['source_pins']:
            target=output/'code'/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((repo/name).read_bytes())
        os.environ.update(offline_environment(root))
        command=[str(a.python),str(output/'code'/plan['entry']),'--worker',
                 '--plan',str(output/'plan.json'),'--root',str(root),'--output',str(output/'results')]
        seconds=check_lease(lease,time.time(),plan['estimate_seconds'])
        # Platform hard timer must also be verified before this entry; parent does not depend on the Mac.
        delegated=True
        result=supervise(command,output,output.with_suffix('.private.tar.gz'),seconds,stop_platform)
    finally:
        if not delegated:stop_platform()
    print(json.dumps(result))


if __name__=='__main__':main()
