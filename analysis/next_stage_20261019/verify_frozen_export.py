"""Replay original export validators with explicit frozen source and private inputs.
Reproduce: $PY analysis/next_stage_20261019/verify_frozen_export.py --snapshot 61fe155 --metadata-dir <METADATA> --export-dir <ORIGINAL_PRIVATE_EXPORT> --official-source <PINNED_SCORE_PY>
The old export predates choices/option_count fields; today's format is checked
separately. This executes only frozen read-only CPU validators, never a scorer.
"""
import argparse,hashlib,json,os,re,subprocess,sys,tempfile
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
ART=REPO/'reports/next_stage_20261019/quality_closure_20261021'
def check(args):
    if not re.fullmatch('[0-9a-f]{7,40}',args.snapshot):raise ValueError('Immutable snapshot required')
    pins={}
    with tempfile.TemporaryDirectory(prefix='B-frozen-export-') as d:
        scripts=Path(d)/'analysis/next_stage_20261019';scripts.mkdir(parents=True)
        for name in ('quality_data.py','export_official.py','verify_official_export.py','verify_official_schema.py'):
            data=subprocess.check_output(['git','show',args.snapshot+':analysis/next_stage_20261019/'+name],cwd=REPO)
            (scripts/name).write_bytes(data);pins[name]=hashlib.sha256(data).hexdigest()
        receipt=args.export_dir/'export_receipt.json'
        if receipt.read_bytes()!=(ART/'official_export_receipt.json').read_bytes():raise ValueError('Original receipt binding mismatch')
        calls=[]
        for script,artifact in [('verify_official_export.py','official_export_validation.json'),('verify_official_schema.py','official_schema_validation.json')]:
            command=[sys.executable,str(scripts/script),'--repo',str(REPO),'--metadata-dir',str(args.metadata_dir),'--export-dir',str(args.export_dir)]
            if script=='verify_official_schema.py':command+=['--official-source',str(args.official_source)]
            r=subprocess.run(command,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True)
            if r.returncode:raise ValueError('Frozen validator failed: '+r.stderr[-300:])
            value=json.loads(r.stdout)
            if value!=json.loads((ART/artifact).read_text()):raise ValueError('Frozen validation result differs')
            calls.append(dict(script=script,returncode=r.returncode,files=value['files'],rows=value['full_export_rows']))
    return dict(status='verified_original_export_with_pinned_original_validators',snapshot=args.snapshot,source_sha256=pins,
        calls=calls,artifacts=3,official_scorer_executed=False,limitation='Original format lacks later choices/option_count fields; current format has separate validation, no historical files rewritten')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',required=True)
    for key in ('metadata-dir','export-dir','official-source'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();print(json.dumps(check(args),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
