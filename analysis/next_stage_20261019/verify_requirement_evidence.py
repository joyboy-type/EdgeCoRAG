"""Reproduce historical evidence identities for one authoritative requirement.

Historical delivery verification checks the frozen bytes/inventory, not a rerun of
model generation or a new scientific claim. New Q analyses have their own numeric
reproduction commands in the registry. No model is loaded and no score is parsed.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

REPO=Path(__file__).resolve().parents[2]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(repo,evidence):
    repo=Path(repo).resolve();files={}
    for rel in evidence:
        path=(repo/rel).resolve()
        if not path.is_relative_to(repo) or not path.exists():raise ValueError('Missing/outside evidence: '+rel)
        paths=[path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        if not paths:raise ValueError('Evidence directory is empty')
        for item in paths:
            name=str(item.relative_to(repo));files[name]=dict(sha256=sha(item),bytes=item.stat().st_size)
    return files


def verify(repo,qid):
    repo=Path(repo);registry=json.loads((repo/'analysis/next_stage_20261019/requirement_reproduction_registry.json').read_text())
    with (repo/'reports/v1.10.1/requirements_matrix.csv').open(encoding='utf-8-sig',newline='') as stream:
        row=next(row for row in csv.DictReader(stream) if row['id']==qid)
    spec=registry['requirements'][qid];evidence=[s.strip() for s in row['evidence'].split(';') if s.strip()]
    if row['status']!=spec['status'] or evidence!=spec['evidence']:raise ValueError('Authoritative requirement changed')
    actual=inventory(repo,evidence)
    if actual!=spec['files']:raise ValueError('Historical evidence bytes/inventory changed')
    summary=dict(id=qid,status='verified_historical_artifact_identity',evidence_files=len(actual),
        inventory_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        scope='same archived delivery bytes, not scientific recalculation or model rerun')
    if qid=='R35':
        frozen=json.loads((repo/'reports/next_stage_20261019/A_retrieval_interface_freeze.json').read_text())
        for name,pin in frozen['source_files'].items():
            content=subprocess.check_output(['git','show','frozen-20261021-session:'+name],cwd=repo)
            if hashlib.sha256(content).hexdigest()!=pin['sha256']:raise ValueError('Tagged session source pin mismatch')
        summary['session_tag']='frozen-20261021-session'
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--id',required=True);args=parser.parse_args()
    print(json.dumps(verify(args.repo,args.id),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
