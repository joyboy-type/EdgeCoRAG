#!/usr/bin/env python3
"""Recompute supplemental point results using public CSVs and existing frozen sources."""
import argparse,csv,gzip,hashlib,io,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REPORT=Path('reports/paper_20261026')
FIELDS=['raw_id','qid','choice','gold','correct','status']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def qhash(qids):return hashlib.sha256(''.join(q+'\n' for q in sorted(qids)).encode()).hexdigest()
def read_json(path):return json.loads(Path(path).read_text())
def validate_rows(path,n,expected_sha=None):
 if expected_sha is not None:assert sha(path)==expected_sha,'CSV byte hash mismatch: '+str(path)
 with Path(path).open(newline='') as f:
  reader=csv.DictReader(f);assert reader.fieldnames==FIELDS;rows=list(reader)
 assert len(rows)==len({r['qid'] for r in rows})==len({r['raw_id'] for r in rows})==n,'Missing/duplicate rows: '+str(path)
 for r in rows:
  assert r['gold'] in ('A','B','C','D') and r['choice'] in ('','A','B','C','D')
  assert r['correct'] in ('True','False') and (r['correct']=='True')==(r['choice']==r['gold'])
  assert r['status']=='ok','Unexpected technical failure in completed export'
 return rows
def csv_text(rows):
 s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows);return s.getvalue()
def recompute(root=ROOT):
 folder=root/REPORT;s3_receipt=read_json(folder/'receipt_s3_qwen3vl_8b.json');nine=read_json(folder/'receipt_qwen35_9b.json');cold=read_json(folder/'receipt_feasibility_cold.json');gate=read_json(folder/'receipt_warmed_feasibility.json')
 assert s3_receipt['complete'] and s3_receipt['return_code']==0 and s3_receipt['attempted']==36 and s3_receipt['failed']==0
 assert nine['complete'] and nine['return_code']==0 and nine['full_state']=={'attempted':3099,'failed':0,'stopped_reason':None}
 assert nine['runtime']['revision']=='c202236235762e1c871ad0ccb60c8ee5ba337b9a' and s3_receipt['runtime']['revision']=='0c351dd01ed87e9c1b53cbc748cba10e6187ff3b'
 for runtime in [nine['runtime'],s3_receipt['runtime']]:
  assert runtime['dtype']=='bfloat16' and runtime['quantization']=='none' and runtime['max_new_tokens']==64 and runtime['seed']==42 and runtime['do_sample'] is False
 assert not cold['passed'] and cold['return_code']==5 and len(cold['results'])==1 and cold['seconds_each'][0]>30
 assert gate['passed'] and gate['threshold_seconds']==30 and gate['warmup_limit_seconds']==600
 assert [r['qid'] for r in gate['warmup_results']]==[r['qid'] for r in gate['results']]==['mragb:6','mragb:11','mragb:12']
 assert all(r['status']=='ok' and r['end_to_end_seconds']<=30 for r in gate['results']);assert len(gate['results'])==3
 assert nine['preregistration_sha256']==sha(folder/'PREREGISTRATION_registered_46c8fd5.md')
 assert nine['cold_result']['sha256']==sha(folder/'receipt_feasibility_cold.json')
 sources=[REPORT/'PREREGISTRATION_registered_46c8fd5.md',REPORT/'receipt_s3_qwen3vl_8b.json',REPORT/'receipt_qwen35_9b.json',REPORT/'receipt_feasibility_cold.json',REPORT/'receipt_warmed_feasibility.json',Path('logs/B_predictions.jsonl.gz'),Path('reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz'),Path('reports/paper_20261021/PREREGISTRATION_20261026_completion.md')]
 nine_rows={};accuracy=[]
 assert {r['condition'] for r in nine['condition_receipts']}=={'S0','S1','S2'}
 for r in nine['condition_receipts']:
  cond=r['condition'];path=REPORT/('s0s1s2_qwen35_9b_'+cond+'.csv');rows=validate_rows(root/path,1033,r['csv_sha256']);assert qhash(r['qid'] for r in rows)==r['qid_sha256']=='2a102ea80297f371dbe793125ac98c084880168929cf8a0781aac315c485d9bc';nc=sum(x['correct']=='True' for x in rows);assert nc==r['n_correct'] and nc/1033==r['accuracy'];nine_rows[cond]={x['qid']:x for x in rows};accuracy.append({'condition':cond,'n':1033,'correct':nc,'accuracy':nc/1033,'source':str(path),'receipt_pointer':f'receipt_qwen35_9b.json#/condition_receipts/{len(accuracy)}'});sources.append(path)
 assert set(nine_rows['S0'])==set(nine_rows['S1'])==set(nine_rows['S2'])
 with gzip.open(root/'reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz','rt') as f:joined=list(csv.DictReader(f))
 maps={}
 for r in joined:
  assert r['joinable']=='True' and r['top3_gt_hit'] in ('True','False');bucket=maps.setdefault(r['model'],{});assert r['qid'] not in bucket;bucket[r['qid']]=r['top3_gt_hit']=='True'
 assert len(maps)==5 and all(len(m)==1033 and sum(m.values())==516 for m in maps.values());shared=next(iter(maps.values()));assert all(m==shared for m in maps.values());assert set(shared)==set(nine_rows['S1'])
 hit_correct=sum(row['correct']=='True' for q,row in nine_rows['S1'].items() if shared[q]);miss_correct=sum(row['correct']=='True' for q,row in nine_rows['S1'].items() if not shared[q]);assert hit_correct+miss_correct==next(x['correct'] for x in accuracy if x['condition']=='S1')
 conditioned={'model':'qwen35_9b','n':1033,'hit_n':516,'miss_n':517,'hit_correct':hit_correct,'miss_correct':miss_correct,'r':516/1033,'u':hit_correct/516,'p':miss_correct/517,'hit_qid_sha256':qhash(q for q in shared if shared[q]),'source':'join_v2.csv.gz: all five model/qid/top3_gt_hit maps validated identical; new S1 CSV: correct','intervals':'none; no additional bootstrap registered'}
 s3_rows={};s3_stats=[]
 for r in s3_receipt['split_receipts']:
  split=r['split'];name,n={'dev':('dev',5),'internal_holdout':('holdout',2),'frozen_test':('frozen',29)}[split];path=REPORT/('s3_qwen3vl_8b_'+name+'.csv');rows=validate_rows(root/path,n,r['csv_sha256']);assert qhash(x['qid'] for x in rows)==r['qid_sha256'];nc=sum(x['correct']=='True' for x in rows);assert nc==r['n_correct'];s3_rows[split]=rows;s3_stats.append({'split':split,'n':n,'correct':nc,'accuracy':nc/n,'source':str(path)});sources.append(path)
 assert set(s3_rows)=={'dev','internal_holdout','frozen_test'}
 wanted={r['qid'] for rows in s3_rows.values() for r in rows};old={};stage_by_split={'dev':'development','internal_holdout':'quality','frozen_test':'quality'}
 with gzip.open(root/'logs/B_predictions.jsonl.gz','rt') as f:
  for line in f:
   r=json.loads(line)
   if r.get('model_key')!='qwen3vl_8b' or r.get('condition')!='S1' or r.get('repeat_index')!=0 or r['qid'] not in wanted:continue
   split=r.get('split')
   if split not in stage_by_split or r.get('stage')!=stage_by_split[split]:continue
   key=(split,r['qid']);assert key not in old;old[key]=r
 paired=[]
 for split in ['dev','internal_holdout','frozen_test']:
  rows=s3_rows[split];cells={'both_correct':0,'S1_only_correct':0,'S3_only_correct':0,'both_wrong':0}
  for r in rows:
   prior=old[(split,r['qid'])];assert prior['answer']==r['gold'];a=prior['correct'];b=r['correct']=='True';assert isinstance(a,bool);cells['both_correct' if a and b else 'S1_only_correct' if a else 'S3_only_correct' if b else 'both_wrong']+=1
  paired.append({'split':split,'n':len(rows),'S1_source_stage':stage_by_split[split],'S1_source_split':split,'S1_correct':cells['both_correct']+cells['S1_only_correct'],'S3_correct':cells['both_correct']+cells['S3_only_correct'],**cells,'qid_sha256':qhash(x['qid'] for x in rows)})
 numbers={'schema':'completion_point_results_20261028/v1','source_file_sha256':{str(p):sha(root/p) for p in sources},'S3_8B':s3_stats,'S3_vs_existing_S1':paired,'Qwen35_9B':accuracy,'Qwen35_9B_conditioned_S1':conditioned,'feasibility':{'cold_passed':False,'cold_seconds':cold['seconds_each'],'cold_rc':5,'warmup_seconds':[r['end_to_end_seconds'] for r in gate['warmup_results']],'warmed_timed_seconds':[r['end_to_end_seconds'] for r in gate['results']],'warmed_passed':True,'full_rc':0},'technical_failures':{'S3_8B':0,'Qwen35_9B':0},'limits':['Point estimates only; no new confidence intervals or causal/equivalence claims.','S3 label-aware and AI-assisted; narrow 5/2/29 subsets.','9B is Qwen3.5 family and has no S2@3; no pure scale or matched-count A conclusion.','Cold and warmed feasibility are distinct; old failure is retained.']}
 return numbers,{'s3_qwen3vl_8b_S1_pairs.csv':csv_text(paired),'qwen35_9b_conditioned_S1.csv':csv_text([conditioned])}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--verify',action='store_true');ap.add_argument('--out',type=Path,default=ROOT/REPORT);args=ap.parse_args();numbers,csvs=recompute();text=json.dumps(numbers,ensure_ascii=False,indent=2)+'\n';files={'completion_numbers_20261028.json':text,**csvs}
 if args.verify:
  for name,content in files.items():assert (args.out/name).read_bytes()==content.encode(),name+' differs from recomputation'
  manifest=args.out/'final_receipt_20261026.json'
  if manifest.exists():
   for row in read_json(manifest)['files']:
    path=ROOT/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['path']+' manifest mismatch'
  print('Verified six CSVs, both feasibility regimes, conditioned S1, three S3/S1 pairs and publication hashes; no GPU required.')
 else:
  args.out.mkdir(exist_ok=True,parents=True)
  for name,content in files.items():(args.out/name).write_bytes(content.encode())
  print(json.dumps({'Qwen35_9B':numbers['Qwen35_9B'],'conditioned':numbers['Qwen35_9B_conditioned_S1'],'S3_pairs':numbers['S3_vs_existing_S1']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
