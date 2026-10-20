"""Independent persisted B5 request/A CSV order and a12-field check, no models.
Reproduce: $PY analysis/next_stage_20261019/verify_a_interface_dry_run.py
 --a-repo <A_WORKTREE> --output <B5_OUTPUT>
"""
import argparse,csv,hashlib,json,sys
from pathlib import Path
def check(a_repo,out,interface_verification=None):
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'b-side'))
 from a_interface_runner import interface_status
 passed,label=interface_status(a_repo,interface_verification)
 a_repo,out=Path(a_repo),Path(out);iface=a_repo/'a-side/retrieval_if_v1'
 with (iface/'pools/smoke_20__dim768__top10.csv').open() as f:pool_rows=list(csv.DictReader(f))
 pools={}
 for r in pool_rows:pools.setdefault(r['qid'],[]).append(r['sha256'])
 chosen={}
 with (iface/'select3/smoke_20__dim768__cosine+random.csv').open() as f:
  for r in csv.DictReader(f):
   if r['strategy']=='cosine':chosen.setdefault(r['qid'],[]).append(r['sha256'])
 requests=[json.loads(s) for s in (out/'requests.jsonl').read_text().splitlines()]
 records=[json.loads(s) for s in (out/'a12_dry_records.jsonl').read_text().splitlines()]
 if len(requests)!=len(records) or len(requests)!=20 or len({r['qid'] for r in requests})!=20:raise ValueError('Fixed dry count mismatch')
 for row,record in zip(requests,records):
  if row['source_status']!=label or record['attrs']['source_status']!=label:raise ValueError('G1 availability label mismatch')
  q=row['qid']
  if row['candidate_order']!=pools[q]:raise ValueError('Persisted candidate order differs from A')
  if len(row['images'])!=4 or [v['sha256'] for v in row['images'][1:]]!=chosen[q]:raise ValueError('Persisted4 image/A select3 order mismatch')
  if record['req_id']!=q or not record['attrs']['dry_run']:raise ValueError('a12 request binding')
  prov=record['provenance'];hw=prov['hardware'];ev=prov['thread_evidence']
  if hw['cpu_thread_env']!=ev['a12_observed'] or (hw['cpu_thread_env']!='unfixed' and (type(hw['cpu_thread_env']) is not int or hw['cpu_thread_env']<=0)):
   raise ValueError('a12 thread provenance missing')
  if hw['cpu_thread_env']=='unfixed' and not record['unmeasured_provenance']:raise ValueError('Unfixed must flag technical-only')
  if set(record['segments'])!={'selection_request_build_seconds'}:raise ValueError('CPU dry segments differ')
  if not {'query_decode_encode_seconds','ranking_no_self_seconds','generation_decode_seconds','utility_scoring_seconds'}<=set(record['unmeasured_segments']):
   raise ValueError('Unperformed segments not marked')
  if any(record[k] is not None for k in ('device_memory','system_ram','energy')):raise ValueError('Dry-run resources must not claim GPU measurements')
  if not all(record['attrs']['resource_status'][k]=='unmeasured' for k in ('device_memory','system_ram','energy')):raise ValueError('Resource availability missing')
 return dict(status='verified_CPU_only_'+('G1_passed' if passed else 'provisional_A_manifest'),requests=20,images_per_request=4,
  source_file_sha256=hashlib.sha256((iface/'pools/smoke_20__dim768__top10.csv').read_bytes()).hexdigest(),
  persisted_order_matches_source=True,B1_passed=passed,provisional=label)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--a-repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--interface-verification',type=Path);a=p.parse_args()
 print(json.dumps(check(a.a_repo,a.output,a.interface_verification),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
