"""D7 additive extension; verify every historical key against unchanged P1 commit.

Reproduce: $PY analysis/next_stage_20261019/b_append_archive.py
 --archive <ROUND1_TAR> --verify
Never changes a pin or warning. No archive extraction to filesystem.
"""
import argparse,copy,hashlib,json,subprocess,tarfile
from pathlib import Path
from append_source_provenance import pin_rows
from b_offline_closure import write_csv,sha,save,REPO,REPORT

RECEIPT=Path('provenance/results_20261020/e2e_smoke_public_receipt.json')
def append_only(old,extension):
 result=copy.deepcopy(old)
 if 'source_archive' in result and result['source_archive']!=extension:raise ValueError('Existing archive pointer must not be replaced')
 result['source_archive']=extension
 return result
def run(repo,archive,verify=False):
 repo=Path(repo);archive=Path(archive)
 frozen=subprocess.check_output(['git','show','34a7e6a:'+str(RECEIPT)],cwd=repo)
 old=json.loads(frozen);current=json.loads((repo/RECEIPT).read_text())
 if sha(archive)!=old['archive_sha256'] or archive.stat().st_size!=old['archive_bytes']:raise ValueError('Archive identity mismatch')
 with tarfile.open(archive) as tar:rows=pin_rows(old['source_pins'],repo,tar)
 extension=dict(sha256=sha(archive),bytes=archive.stat().st_size,
  original_receipt_sha256=hashlib.sha256(frozen).hexdigest(),
  members={r['path']:r['source_archive_member'] for r in rows},
  note='Round-1 source snapshots; historical pins and cpu_thread_warning retain original values')
 expected=append_only(old,extension)
 if {k:v for k,v in current.items() if k!='source_archive'}!=old:raise ValueError('Historical receipt fields changed')
 if current.get('source_archive') not in (None,extension):raise ValueError('Conflicting archive pointer')
 report=dict(status='verified_append_only',archive_sha256=sha(archive),pins_verified=len(rows),
   a_side_pin_count=sum(r['path'].startswith('a-side/') for r in rows),
   requested_a_side_pin_count=4,discrepancy='Receipt contains 2 A script pins, not4; additional2 not invented',
   b_side_four=[r['path'] for r in rows if r['path'] in ['b-side/e2e_smoke.py','b-side/e2e_lease.py','b-side/model_adapters.py','b-side/run_candidate.py']],
   old_keys_unchanged=True,cpu_thread_warning=current['cpu_thread_warning'],
   original_receipt_sha256=hashlib.sha256(frozen).hexdigest())
 out=repo/REPORT
 if verify:
  if current!=expected:raise ValueError('Archive extension absent')
  if json.loads((out/'B_source_archive_validation.json').read_text())!=report:raise ValueError('Validation report drift')
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'pins.csv';write_csv(p,rows)
   if p.read_bytes()!=(out/'B_pin_reproducibility.csv').read_bytes():raise ValueError('Pin table drift')
 else:
  save(repo/RECEIPT,expected);write_csv(out/'B_pin_reproducibility.csv',rows);save(out/'B_source_archive_validation.json',report)
 return report
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=REPO)
 p.add_argument('--archive',type=Path,required=True);p.add_argument('--verify',action='store_true');args=p.parse_args()
 print(json.dumps(run(args.repo,args.archive,args.verify),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
