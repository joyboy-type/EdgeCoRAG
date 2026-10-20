"""Audit requirement/evidence consistency without re-evaluating any experiment.

This structural audit cannot certify scientific validity. It checks matching
Markdown/CSV rows, local evidence presence, limits, and reports four status groups.
Partial items stay partial, including missing evidence and statistical blockers.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

REPO=Path(__file__).resolve().parents[2]


def group(status):
    from report_completion_counts import bucket
    return bucket(status)


def audit(repo=REPO):
    repo=Path(repo).resolve();md=repo/'reports/Requirements.md';matrix=repo/'reports/v1.10.1/requirements_matrix.csv'
    parsed={}
    for line in md.read_text().splitlines():
        if re.match(r'^\| R\d+ \|',line):
            cells=[cell.strip() for cell in line.split('|')[1:-1]]
            if cells[0] in parsed:raise ValueError('Duplicate Markdown requirement')
            parsed[cells[0]]=cells
    with matrix.open(encoding='utf-8-sig',newline='') as stream:table=list(csv.DictReader(stream))
    errors=[];warnings=[];rows=[];seen=set()
    counts={name:dict(count=0,ids=[]) for name in ('完成','部分','待补','后置')}
    for record in table:
        cells=[record[key] for key in ('id','source','requirement','status','evidence','limit_or_next_action')]
        qid=cells[0];category=group(cells[3]);limit=cells[5]
        if qid in seen:errors.append(qid+': duplicate CSV id')
        seen.add(qid)
        if parsed.get(qid)!=cells:errors.append(qid+': Markdown/CSV mismatch')
        missing=[];pins={}
        for rel in filter(None,(part.strip().strip('`') for part in cells[4].split(';'))):
            path=(repo/rel).resolve()
            if not path.is_relative_to(repo) or not path.exists():missing.append(rel)
            elif path.is_file():pins[rel]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
            else:pins[rel]=dict(kind='directory')
        if not cells[4] or not limit.strip():errors.append(qid+': evidence and limit required')
        if category=='完成' and missing:errors.append(qid+': completed item has missing evidence '+','.join(missing))
        elif missing:warnings.append(qid+': partial/deferred evidence missing '+','.join(missing))
        counts[category]['count']+=1;counts[category]['ids'].append(qid)
        rows.append(dict(id=qid,status=cells[3],group=category,missing_evidence=missing,evidence=pins,limit=limit))
    if set(parsed)!=seen:errors.append('Markdown/CSV requirement inventory mismatch')
    return dict(status='failed' if errors else 'passed',scope='structural evidence audit; no metrics recomputed or statuses promoted',
        requirements=len(rows),completion=counts,counts={key:value['count'] for key,value in counts.items()},errors=errors,warnings=warnings,rows=rows,
        input_sha256={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in [('Requirements.md',md),('requirements_matrix.csv',matrix)]})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=audit(args.repo)
    if args.out:
        with args.out.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({key:value for key,value in result.items() if key!='rows'},ensure_ascii=False,indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
