"""B6 copy unchanged prior projections into a NEW private export; enrich metadata.
No generation, scoring, reparsing or response repair. Third-party verifier remains
verify_official_export.py/verify_official_schema.py.
Reproduce: $PY analysis/next_stage_20261019/copy_official_export_receipt.py
 --source <VERIFIED_PRIVATE_EXPORT> --out <NEW_PRIVATE_EXPORT>
"""
import argparse,datetime,json,shutil
from pathlib import Path
from quality_data import sha
REPO=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.resolve().is_relative_to(REPO) or a.out.exists():raise ValueError('New private output outside repo required')
 receipt=json.loads((a.source/'export_receipt.json').read_text());a.out.mkdir(parents=True)
 for item in receipt['files']:
  source=(a.source/item['file']).resolve();target=(a.out/item['file']).resolve()
  if not source.is_relative_to(a.source.resolve()) or not target.is_relative_to(a.out.resolve()):raise ValueError('Unsafe member')
  if sha(source)!=item['sha256'] or source.stat().st_size!=item['bytes']:raise ValueError('Prior export identity drift')
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
 receipt.update(export_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),copy_only=True,
  original_export_time='not recorded; current timestamp describes unchanged re-export only',
  source_export_receipt_sha256=sha(a.source/'export_receipt.json'),code_sha256=sha(Path(__file__)),
  field_mapping={'raw_output':'output','answer':'gt_choice','context saved message text':'prompt',
                 'scenario':'scenario','official A/B/C/D nonempty fields':'choices and option_count',
                 'qid':'qid','archived strict_choice_v1 parse_status':'parse_status (unchanged)'})
 (a.out/'export_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:receipt[k] for k in ['export_time','copy_only','source_prediction_sha256','source_export_receipt_sha256','code_sha256','full_export_rows','failure_counts']},indent=2))
if __name__=='__main__':main()
