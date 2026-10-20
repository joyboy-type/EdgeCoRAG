"""B5 native A recorder dry-run. NO model loading or GPU execution in CLI.

Reproduce: $PY -B b-side/a_interface_runner.py --dry-run --a-repo <A_WORKTREE>
 --thread-evidence <B4_JSON> --out <NEW_B_OUTPUT>
Without a current pinned G1 proof, A CSVs remain provisional. Never rewrites A files.
"""
import argparse,csv,hashlib,importlib.util,json,math,sys
from pathlib import Path
from next_interface_bridge import build_fp32_encoder
PROVISIONAL='provisional: manifest 行尾口径待 A 修复'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def interface_status(a_repo,verification):
 if verification is None:return False,PROVISIONAL
 a_repo=Path(a_repo).resolve();proof=json.loads(Path(verification).read_text())
 calls=proof.get('commands',[]);checks=proof.get('checks',{})
 if proof.get('B1_passed') is not True or len(calls)!=4 or any(c.get('returncode')!=0 for c in calls):raise ValueError('Incomplete current G1 proof')
 if proof.get('A_commit')!='c77e91c07a288b719683c51258324c11431c12d5':raise ValueError('Unpinned G1 version')
 for name in ('a17_default','a17_strict'):
  if checks.get(name,{}).get('artifacts_checked')!=36 or checks.get(name,{}).get('fail_count')!=0:raise ValueError('G1 native verification did not pass')
 if proof.get('artifact_manifest_sha256')!=sha(a_repo/'a-side/retrieval_if_v1/artifacts.json'):raise ValueError('G1 manifest binding changed')
 pins=proof.get('source_sha256',{})
 if len(pins)<36:raise ValueError('G1 source pins absent')
 for name,pin in pins.items():
  path=(a_repo/name).resolve()
  if not path.is_relative_to(a_repo) or sha(path)!=pin:raise ValueError('G1 source changed after verification')
 return True,'verified A c77e91c; current native G1 CLI rc=0'
def read_pool(path):
 result={}
 with Path(path).open(newline='') as f:
  for row in csv.DictReader(f):result.setdefault(row['qid'],[]).append(row)
 for q,rows in result.items():
  if [int(r['rank']) for r in rows]!=list(range(1,11)):raise ValueError('CSV rank/file order mismatch; no silent sorting')
  if len({r['sha256'] for r in rows})!=10:raise ValueError('Duplicate candidate')
 return result
def require_scores(path,pools):
 if path is None:raise ValueError('utility scores missing; B must not invent or select top3')
 with Path(path).open() as f:
  reader=csv.DictReader(f)
  if reader.fieldnames!=['qid','sha256','score']:raise ValueError('Only qid,sha256,score allowed')
  rows=list(reader)
 by={}
 for r in rows:
  key=(r['qid'],r['sha256'])
  if key in by or not math.isfinite(float(r['score'])):raise ValueError('Duplicate/nonfinite utility score')
  by[key]=float(r['score'])
 expected={(q,r['sha256'] if isinstance(r,dict) else r) for q,pool in pools.items() for r in pool}
 if set(by)!=expected:raise ValueError('Utility must cover every candidate exactly')
 return rows
def export_utility_scores(path,qid,pool,raw_logits,*,batch_size):
 if len(pool)!=10 or len(raw_logits)!=10 or len({r['sha256'] for r in pool})!=10:raise ValueError('Exactly10 ordered candidates/logits required')
 if type(batch_size) is not int or batch_size<=0:raise ValueError('Pinned utility batch size required')
 if any(type(v) not in (int,float) or not math.isfinite(v) for v in raw_logits):raise ValueError('Finite raw logits required')
 with Path(path).open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['qid','sha256','score']);w.writeheader()
  for row,value in zip(pool,raw_logits):w.writerow(dict(qid=qid,sha256=row['sha256'],score=value))
 return dict(utility_input_order=[r['sha256'] for r in pool],utility_batch_size=batch_size,
  score_kind='ell(True) raw last-token logit; no softmax',selected_by='A a15 only')

def thread_value(evidence):
 rows=evidence.get('rows',[])
 if not rows:raise ValueError('Missing thread evidence; refuse before recorder construction')
 values={r['observed'] for r in rows}
 if len(values)!=1 or any(type(r['observed']) is not int or r['observed']<=0 or r['observed']!=r['applied'] for r in rows):
  raise ValueError('Thread mismatch')
 return next(iter(values))
def encode_fp32(model,images,torch,*,authorized=False):
 if authorized is not True:raise ValueError('Future approved session required')
 torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 if any(p.dtype!=torch.float32 for p in model.parameters()):raise ValueError('Encoder parameter is not float32')
 import numpy as np
 values=np.asarray(model.encode([{'image':image} for image in images],batch_size=1,normalize_embeddings=False,convert_to_numpy=True,show_progress_bar=False),dtype=np.float32)
 norms=np.linalg.norm(values,axis=1,keepdims=True)
 if not np.isfinite(values).all() or (norms<=0).any():raise ValueError('Invalid vectors')
 return values/np.maximum(norms,np.float32(1e-12))
def true_logits(model,inputs,true_token_id,*,authorized=False):
 if authorized is not True:raise ValueError('No utility forward without approval')
 # Raw last-token logit, never sigmoid/softmax/True-False normalization.
 return model(**inputs).logits[:,-1,true_token_id].detach().float().cpu().tolist()
def load_a12(path):
 old=sys.dont_write_bytecode;sys.dont_write_bytecode=True
 try:
  spec=importlib.util.spec_from_file_location('edgecorag_readonly_a12',path)
  module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
  return module
 finally:sys.dont_write_bytecode=old
def dry_run(a_repo,evidence_path,out,cohort='smoke_20',dimension=768,strategy='cosine',scores=None,interface_verification=None):
 a_repo,out=Path(a_repo).resolve(),Path(out).resolve()
 if out.is_relative_to(a_repo) or out.exists():raise ValueError('New output outside A worktree required')
 if cohort!='smoke_20':raise ValueError('Dry-run uses observed smoke only; no frozen selection')
 b1_passed,source_status=interface_status(a_repo,interface_verification)
 iface=a_repo/'a-side/retrieval_if_v1';poolfile=iface/'pools'/f'{cohort}__dim{dimension}__top10.csv'
 pools=read_pool(poolfile)
 if strategy=='utility':
  require_scores(scores,pools)
  raise ValueError('Scores validated; A a15 must select/materialize utility before B request assembly')
 if strategy not in ('cosine','random'):raise ValueError('Unknown strategy')
 with (iface/'select3'/f'{cohort}__dim{dimension}__cosine+random.csv').open() as f:selections=list(csv.DictReader(f))
 chosen={}
 for row in selections:
  if row['strategy']==strategy:chosen.setdefault(row['qid'],[]).append(row)
 query={}
 with (iface/'corpus/occurrences.csv').open() as f:
  for row in csv.DictReader(f):
   if row['role']=='query' and row['qid'] in pools:query[row['qid']]=row['sha256']
 evidence=json.loads(Path(evidence_path).read_text());env_cpu=thread_value(evidence)
 cpu=env_cpu if evidence.get('formal_backend_ready') is True else 'unfixed'
 a12=load_a12(a_repo/'a-side/scripts/a12_cost_recorder.py')
 prov=dict(hardware=dict(cpu_thread_env=cpu),
  encoder=dict(encoder_dtype='float32',observed=False,model_loaded=False,note='与 round-1 的 bf16 不可比'),
  corpus=dict(source='A frozen CSV',provisional=source_status),
  protocol='a-side/retrieval-interface-v1',warm_state='CPU_dry_run_not_GPU',
  thread_evidence=dict(preflight_sha256=sha(evidence_path),preflight_observed=env_cpu,a12_observed=cpu,
    torch_intra=evidence['rows'][0]['torch_intra'],torch_inter=evidence['rows'][0]['torch_inter'],
    blas_matches_requested=evidence['rows'][0]['blas_matches_requested']))
 out.mkdir(parents=True);rec=a12.CostRecorder(out/'a12_dry_records.jsonl','B_native_A_dry',prov)
 hashes=[]
 try:
  with (out/'requests.jsonl').open('x') as stream:
   for q,pool in pools.items():
    rows=chosen.get(q,[])
    if [int(r['slot']) for r in rows]!=[1,2,3]:raise ValueError('A select3 slot mismatch')
    selected=[r['sha256'] for r in rows];order=[r['sha256'] for r in pool]
    if not set(selected)<=set(order):raise ValueError('A selected evidence not from A pool')
    order_sha=hashlib.sha256(('\n'.join(order)+'\n').encode()).hexdigest()
    with rec.request(q,strategy=strategy,dry_run=True,pool_order_sha256=order_sha,source_status=source_status,
       resource_status={k:'unmeasured' for k in ('device_memory','system_ram','energy')}):
     rec.unmeasured('query_decode_encode_seconds','ranking_no_self_seconds','generation_decode_seconds','utility_scoring_seconds','switch_seconds')
     with rec.segment('selection_request_build_seconds'):
      request=dict(qid=q,images=[dict(role='query',sha256=query[q])]+[dict(role='evidence',slot=i,sha256=s) for i,s in enumerate(selected,1)],
        candidate_order=order,selected_by='A_select3_file',dry_run=True,source_status=source_status)
      if len(request['images'])!=4 or [r['sha256'] for r in request['images'][1:]]!=selected:raise ValueError('4-image order mismatch')
      stream.write(json.dumps(request)+'\n')
    hashes.append(dict(qid=q,source_order_sha256=order_sha,consumed_order_sha256=order_sha,matches=True))
 finally:rec.close()
 with (out/'pool_order_hashes.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(hashes[0]));w.writeheader();w.writerows(hashes)
 receipt=dict(status='CPU_native_a12_dry_run_only_'+('verified_A_manifest' if b1_passed else 'provisional_A_manifest'),requests=len(hashes),images_per_request=4,
  A_pool_file_sha256=sha(poolfile),A_a12_source_sha256=sha(a_repo/'a-side/scripts/a12_cost_recorder.py'),
  A_select3_sha256=sha(iface/'select3'/f'{cohort}__dim{dimension}__cosine+random.csv'),
  thread_evidence=prov['thread_evidence'],encoder_dtype='float32',encoder_executed=False,
  no_new_ranking=True,no_model_loaded=True,utility='unmeasured; only raw score export, selection/materialization delegated to A15',
  resources='unmeasured',B1_passed=b1_passed,provisional=source_status)
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 return receipt
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dry-run',action='store_true',required=True)
 p.add_argument('--a-repo',type=Path,required=True);p.add_argument('--thread-evidence',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True);p.add_argument('--strategy',default='cosine');p.add_argument('--scores',type=Path)
 p.add_argument('--interface-verification',type=Path)
 args=p.parse_args();print(json.dumps(dry_run(args.a_repo,args.thread_evidence,args.out,strategy=args.strategy,scores=args.scores,interface_verification=args.interface_verification),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
