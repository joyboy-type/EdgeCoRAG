"""Append round-1 archive provenance without modifying any old pin or receipt.

Reproduce: $PY analysis/next_stage_20261019/append_source_provenance.py
 --archive <PRIVATE_ROUND1_TAR> --out <NEW_SUPPLEMENT_JSON> --table <NEW_CSV>
Use --verify-json/--verify-table to check prior artifacts. --source-snapshot
selects the old source bytes for legacy current_sha columns, never relabels them
as today's files and never changes historical pins or receipts.
"""
import argparse
import re,csv,io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from quality_data import sha,read,write_json,write_csv

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'b-side'))
import e2e_lease


def pin_rows(pins,repo,tar,source_snapshot=None):
    result=[]
    for name,pin in pins.items():
        member='code/'+name
        data=tar.extractfile(member).read();observed=hashlib.sha256(data).hexdigest()
        if observed!=pin:raise ValueError('Archive member does not reproduce historical pin: '+name)
        current=sha(Path(repo)/name) if source_snapshot is None else hashlib.sha256(subprocess.check_output(['git','show',source_snapshot+':'+name],cwd=repo)).hexdigest()
        result.append(dict(path=name,historical_pin_sha256=pin,source_archive_member=member,
            member_sha256=observed,current_sha256=current,archive_matches_pin=True,current_matches_pin=current==pin))
    return result


def supplement(repo,archive,receipt,source_snapshot=None):
    repo=Path(repo);receipt=Path(receipt);archive=Path(archive);old=read(receipt)
    if sha(archive)!=old['archive_sha256'] or archive.stat().st_size!=old['archive_bytes']:
        raise ValueError('Round-1 archive identity mismatch')
    e2e_lease.verify_archive(archive)
    with tarfile.open(archive) as tar:rows=pin_rows(old['source_pins'],repo,tar,source_snapshot)
    for row in rows:
        if row['path'].startswith('a-side/'):
            published=subprocess.check_output(['git','show','543de53:'+row['path']],cwd=repo)
            if hashlib.sha256(published).hexdigest()!=row['historical_pin_sha256'] or not row['current_matches_pin']:
                raise ValueError('Protected A file differs from published543de53/historical pin')
    changed=[row['path'] for row in rows if not row['current_matches_pin']]
    return dict(status='historical_pins_reproduced_from_round1_archive',
        historical_receipt_sha256=sha(receipt),historical_receipt_modified=False,
        source_archive=dict(sha256=old['archive_sha256'],bytes=old['archive_bytes'],
            members={row['path']:row['source_archive_member'] for row in rows}),
        pin_rows=rows,pins_verified=len(rows),current_files_differ=changed,
        cpu_thread_warning_unchanged=old['cpu_thread_warning'],
        limitation='Round-1 source pins identify archived snapshot bytes, not current source; no warning or historical field rewritten')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,default=REPO/'provenance/results_20261020/e2e_smoke_public_receipt.json')
    parser.add_argument('--out',type=Path);parser.add_argument('--table',type=Path);parser.add_argument('--verify-json',type=Path)
    parser.add_argument('--source-snapshot',help='Explicit immutable hex Git ref for legacy current_sha columns; never changes checkout')
    parser.add_argument('--verify-table',type=Path)
    args=parser.parse_args()
    if args.source_snapshot is not None and not re.fullmatch('[0-9a-f]{7,40}',args.source_snapshot):raise ValueError('Immutable hex snapshot required')
    value=supplement(args.repo,args.archive,args.receipt,args.source_snapshot)
    if args.verify_json and read(args.verify_json)!=value:raise ValueError('Supplement no longer matches archived/current identities')
    if args.verify_table:
        stream=io.StringIO(newline='');rows=value['pin_rows'];w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        if stream.getvalue().encode()!=args.verify_table.read_bytes():raise ValueError('Frozen pin table differs')
    if args.out:write_json(args.out,value)
    if args.table:write_csv(args.table,value['pin_rows'])
    print(json.dumps({k:v for k,v in value.items() if k not in ('pin_rows','source_archive')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
