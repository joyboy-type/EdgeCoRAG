"""One-command offline verification of new private preparation, never an experiment.

Checks source pins, frozen contracts, every dimension artifact, archive inventory,
member hashes, proposed/non-authorizing leases, and plan identity. Emits only
counts and digests; fixed output is suitable for repeat comparison or publication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'b-side'))
import e2e_lease
from build_dimension_inputs import verify_manifest,sha
from freeze_retrieval_interface import canonical,bytes_sha,reject_paths


def verify_bundle(record):
    archive=Path(record['archive'])
    if archive.stat().st_size!=record['bytes'] or sha(archive)!=record['sha256']:
        raise ValueError('Package digest/size mismatch')
    e2e_lease.verify_archive(archive)
    with tarfile.open(archive) as tar:
        plan_bytes=tar.extractfile('plan.json').read();plan=json.loads(plan_bytes)
        lease=json.load(tar.extractfile('lease.template.json'))
        if plan.get('execution_authorized') is not False or lease.get('execution_authorized') is not False:
            raise ValueError('Prepared package must contain no execution authorization')
        digest=hashlib.sha256(plan_bytes).hexdigest()
        if digest!=record['plan_sha256']:raise ValueError('Packaged plan identity mismatch')
        for name,pin in plan['source_pins'].items():
            if hashlib.sha256(tar.extractfile(name).read()).hexdigest()!=pin:
                raise ValueError('Packaged source pin mismatch')
        return dict(sha256=record['sha256'],bytes=record['bytes'],plan_sha256=digest,
                    plan_bytes=len(plan_bytes),members=len(tar.getmembers())-1,execution_authorized=False)


def verify(manifest,dimensions,freeze_path,repo=REPO):
    records=json.loads(Path(manifest).read_text());dimension=verify_manifest(dimensions)
    frozen=json.loads(Path(freeze_path).read_text());reject_paths(frozen)
    if bytes_sha(canonical(frozen['interface']))!=frozen['interface_sha256'] or bytes_sha(canonical(frozen['source_files']))!=frozen['source_files_sha256']:
        raise ValueError('Frozen interface internal identity mismatch')
    for name,pin in frozen['source_files'].items():
        path=Path(repo)/name
        if path.stat().st_size!=pin['bytes'] or sha(path)!=pin['sha256']:
            raise ValueError('Frozen source no longer matches: '+name)
    bundles={name:verify_bundle(records[name]) for name in ('smoke','cost')}
    for name in ('smoke','cost'):
        with tarfile.open(records[name]['archive']) as tar:
            if hashlib.sha256(tar.extractfile('A_retrieval_interface_freeze.json').read()).hexdigest()!=sha(freeze_path):
                raise ValueError('Packaged interface freeze identity mismatch')
            if name=='cost' and hashlib.sha256(tar.extractfile('dimension-inputs/manifest.json').read()).hexdigest()!=sha(Path(dimensions)/'manifest.json'):
                raise ValueError('Packaged dimension manifest identity mismatch')
    return dict(status='verified_local_preparation_only',execution_authorized=False,gpu_started=False,
        packages=bundles,dimension_manifest_sha256=sha(Path(dimensions)/'manifest.json'),
        dimensions=dimension['dimensions'],interface_sha256=frozen['interface_sha256'],
        interface_artifact_sha256=sha(freeze_path),source_files=len(frozen['source_files']),
        scope='Input preparation and CPU contract tests only; no new quality or cost measurement')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundles',type=Path,required=True)
    parser.add_argument('--dimensions',type=Path,required=True)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=verify(args.bundles,args.dimensions,args.freeze,args.repo)
    if args.out:
        with args.out.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
