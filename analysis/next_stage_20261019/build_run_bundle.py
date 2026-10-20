"""Build the two upload bundles for the round-2 runs. Nothing is authorized here.

Each bundle is self-contained: pinned sources, the server plan, its local
validation, an unapproved lease template and a signed-by-hash manifest. The
operator extracts one bundle per run and lets `b-side/e2e_lease.py` verify it.
"""
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=False)

PROJECT = PATHS.project_root
REPO = PATHS.repo
WORK = PATHS.work_dir
OUT = PATHS.output_dir or WORK / 'run-bundles-20261021'
SMOKE = WORK / 'smoke-recheck'
COST = WORK / 'cost'
SERVER_ROOT = str(PATHS.server_root) if PATHS.server_root else ''

sys.path.insert(0, str(REPO / 'b-side'))
import e2e_smoke as smoke
import e2e_cost as cost

EXTRA = ('b-side/boot_watchdog.py','b-side/session_runner.py','b-side/retrieval_comparison.py')  # safety machinery, shipped but not part of the plan pins

RUNS = {
    'smoke': dict(dir=SMOKE, sources=smoke.REQUIRED_SOURCES,
                  output=SERVER_ROOT + '/results/' + PATHS.run_id + '-smoke'),
    'cost': dict(dir=COST, sources=cost.COST_SOURCES,
                 output=SERVER_ROOT + '/results/' + PATHS.run_id + '-cost'),
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 8388608), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_member(info):
    info.mtime=0;info.uid=0;info.gid=0;info.uname='';info.gname=''
    info.mode=0o644;info.pax_headers={}
    return info


def build(name, spec):
    plan=json.loads((spec['dir']/'plan.private.json').read_text())
    if set(plan['source_pins'])!=set(spec['sources']) or any(sha(REPO/source)!=digest for source,digest in plan['source_pins'].items()):
        raise ValueError('Bundle sources disagree with prepared plan pins')
    payload = OUT / name
    if payload.exists():
        raise SystemExit(f'Refusing to overwrite {payload}')
    payload.mkdir(parents=True)
    for source in list(spec['sources'])+list(EXTRA):
        target = payload / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / source, target)
    shutil.copy2(spec['dir'] / 'plan.private.json', payload / 'plan.json')
    shutil.copy2(spec['dir'] / 'validation.json', payload / 'validation.json')
    template = json.loads((spec['dir'] / 'lease.proposed.json').read_text())
    template = dict(template, output_path=spec['output'],
                    note_authorization='Template only. A new lease must be written after explicit approval.')
    (payload / 'lease.template.json').write_text(json.dumps(template, ensure_ascii=False, indent=2))
    if PATHS.interface_freeze:
        shutil.copy2(PATHS.interface_freeze, payload/'A_retrieval_interface_freeze.json')
    if name=='cost' and PATHS.dimension_inputs:
        from build_dimension_inputs import verify_manifest
        verify_manifest(PATHS.dimension_inputs)
        shutil.copytree(PATHS.dimension_inputs, payload/'dimension-inputs')
    manifest = {str(path.relative_to(payload)): sha(path)
                for path in sorted(payload.rglob('*')) if path.is_file()}
    (payload / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    archive = OUT / f'{name}-20261021.private.tar.gz'
    with archive.open('xb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0,compresslevel=1) as compressed, tarfile.open(fileobj=compressed,mode='w|') as tar:
        for member in manifest:
            tar.add(payload / member, arcname=member, filter=canonical_member)
        data = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        info = tarfile.TarInfo('manifest.json')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    # verify like the remote side will
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        shipped = json.load(tar.extractfile('manifest.json'))
        if set(names) != {'manifest.json'} | set(shipped):
            raise SystemExit('Inventory mismatch for ' + str(archive))
        for member, expected in shipped.items():
            if hashlib.sha256(tar.extractfile(member).read()).hexdigest() != expected:
                raise SystemExit('Member hash mismatch: ' + member)
    return dict(name=name, archive=str(archive), bytes=archive.stat().st_size,
                sha256=sha(archive), members=len(manifest),
                plan_sha256=sha(payload / 'plan.json'), output_path=spec['output'])


def main():
    if not SERVER_ROOT and "--help" not in sys.argv: raise ValueError("--server-root required; no server is contacted")
    OUT.mkdir(exist_ok=False)
    summary = {name: build(name, spec) for name, spec in RUNS.items()}
    summary['note'] = ('Bundles contain no authorization. Execution needs a new lease with explicit budget '
                       'approval, a verified shutdown path and a fresh rate quote.')
    (OUT / 'bundles.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
