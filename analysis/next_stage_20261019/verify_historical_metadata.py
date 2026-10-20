"""Reproduce frozen status metadata from an explicit immutable Git snapshot.
Reproduce: $PY analysis/next_stage_20261019/verify_historical_metadata.py --snapshot 61fe155 --artifact <NAME>
The historical audit receipt is conserved, not replayed with today's inputs.
"""
import argparse,csv,io,json,subprocess,tempfile
from pathlib import Path
from report_completion_counts import report
REPO=Path(__file__).resolve().parents[2]
ART=REPO/'reports/next_stage_20261019/quality_closure_20261021'
def contents(snapshot,path):return subprocess.check_output(['git','show',snapshot+':'+path],cwd=REPO)
def validate(snapshot,name):
    rel='reports/next_stage_20261019/quality_closure_20261021/'+name
    if contents(snapshot,rel)!=(ART/name).read_bytes():raise ValueError('Frozen metadata bytes changed')
    if name=='Q_requirement_evidence_audit.json':return dict(status='blocked',returncode=2,
        reason='Historical audit receipt is immutable; original session registry/environment not fully versioned for exact replay. Current explicit-input audit is reported separately, not retrofitted into old receipt.')
    path='reports/v1.10.1/requirements_matrix.csv'
    frozen=contents(snapshot,path)
    if name=='Q_completion_counts.json':
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'matrix.csv';p.write_bytes(frozen);result=report(p)
        if result!=json.loads((ART/name).read_text()):raise ValueError('Frozen completion counts do not reproduce')
    elif name=='status_changes.json':
        def rows(data):return {r['id']:r for r in csv.DictReader(io.StringIO(data.decode('utf-8-sig')))}
        old=rows(contents('34a7e6a',path));new=rows(frozen);saved=json.loads((ART/name).read_text())
        diffs={k for k in old if old[k]['status']!=new[k]['status']}
        if diffs!={r['id'] for r in saved}:raise ValueError('Status transition inventory differs')
        for r in saved:
            if r['old_status']!=old[r['id']]['status'] or r['new_status']!=new[r['id']]['status'] or r['reason']!=new[r['id']]['limit_or_next_action']:
                raise ValueError('Status transition differs from frozen matrix')
    else:raise ValueError('Unsupported frozen metadata artifact')
    return dict(status='verified_from_frozen_status_inputs',returncode=0,snapshot=snapshot,artifact=name)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',required=True);p.add_argument('--artifact',required=True);a=p.parse_args()
    value=validate(a.snapshot,a.artifact);print(json.dumps(value,ensure_ascii=False,indent=2));return value['returncode']
if __name__=='__main__':raise SystemExit(main())
