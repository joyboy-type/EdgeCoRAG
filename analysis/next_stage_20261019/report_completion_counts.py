"""Count the authoritative status column; limit text is never inspected.

Rules, in order: status starting 已完成/已交付/已披露/已执行 -> 完成;
部分 -> 部分; 后置 -> 后置; 未测或不适用本轮 -> 后置; 待/未 -> 待补.
R26 已执行 is historical executed scope, so 完成; it does not certify all future
research. R18 未测或不适用本轮 is explicitly outside this round, so 后置.
已交付 部分核验 remains 完成 for its qualified delivery, not full verification.
Unknown/empty statuses fail instead of being silently assigned. No limit parsing.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]


def bucket(status):
    status=status.strip()
    if status.startswith(('已完成','已交付','已披露','已执行')):return '完成'
    if status.startswith('部分'):return '部分'
    if status.startswith('后置') or status=='未测或不适用本轮':return '后置'
    if status.startswith(('待','未')):return '待补'
    raise ValueError('Unknown authoritative status: '+status)


def report(matrix):
    matrix=Path(matrix);groups={name:[] for name in ('完成','部分','待补','后置')};seen=set();rows=[]
    with matrix.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            qid=row['id']
            if qid in seen:raise ValueError('Duplicate requirement: '+qid)
            seen.add(qid);name=bucket(row['status']);groups[name].append(qid)
            rows.append(dict(id=qid,status=row['status'],group=name))
    return dict(groups=groups,counts={name:len(ids) for name,ids in groups.items()},rows=rows,
        rule='status-prefix-only; 已完成/已交付/已披露/已执行=完成; 部分=部分; 后置 or 未测或不适用本轮=后置; 待/未=待补',
        input_sha256={'requirements_matrix.csv':hashlib.sha256(matrix.read_bytes()).hexdigest()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix',type=Path,default=REPO/'reports/v1.10.1/requirements_matrix.csv')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=report(args.matrix)
    data=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.out:
        with args.out.open('x') as stream:stream.write(data)
    print(data,end='')

if __name__=='__main__':main()
