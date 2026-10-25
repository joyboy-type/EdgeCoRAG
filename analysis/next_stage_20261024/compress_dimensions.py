"""Registered four-dimensional retrieval metrics, reusing V and complete new Q."""
import os
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
import csv,json,hashlib,time
from pathlib import Path
import numpy as np
from supplement_core import score_rank,dimension_status
O=Path('/root/autodl-tmp/registered-20261024');E=Path('/root/autodl-tmp/session/encoded')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
V=np.load(E/'V.npy',allow_pickle=False);Q=np.load(O/'Q_1203.npy',allow_pickle=False);rows=json.loads((O/'query_inputs.json').read_text());pool=list(csv.DictReader((E/'pool.csv').open()));ids=np.asarray([r['identity'] for r in pool]);assert len(set(ids))==4712
assert V.shape==(4712,768) and Q.shape==(1203,768) and V.dtype==Q.dtype==np.float32
assert sha(E/'V.npy')=='31a3e122be53f528d59b5ece290b0814461027d7792a0dd1ff6c2841bab827ce'
occ=list(csv.DictReader(open('/root/autodl-tmp/corpus_v1/occurrences.csv')));gold={}
for r in occ:
 if r['role']=='gt':gold.setdefault(r['qid'],set()).add('image:'+r['sha256'])
def normalized(a,d):
 a=a[:,:d].copy();norm=np.linalg.norm(a,axis=1,keepdims=True);assert a.dtype==np.float32 and np.isfinite(a).all() and (norm>0).all();a/=norm;return a
metrics=['hit_at_1','hit_at_5','hit_at_10','recall_at_5','mrr'];result={'sources':{'V':str(E/'V.npy'),'V_sha256':sha(E/'V.npy'),'Q':str(O/'Q_1203.npy'),'Q_sha256':sha(O/'Q_1203.npy'),'pool_sha256':sha(E/'pool.csv'),'gold': '/root/autodl-tmp/corpus_v1/occurrences.csv','gold_sha256':sha('/root/autodl-tmp/corpus_v1/occurrences.csv'),'registration_commit':'f5a3f12','script_sha256':sha(__file__)},'numpy':np.__version__,'dimensions':{},'notes':['V reused; all Q newly encoded FP32, separate generation batch','exact query identity excluded; score desc then identity asc','macro Recall@5 denominator includes out-of-pool gold; full MRR']}
for d in (128,256,512,768):
 t=time.time();v=normalized(V,d);q=normalized(Q,d);records=[]
 for i,r in enumerate(rows):
  scores=v@q[i];assert scores.dtype==np.float32 and np.isfinite(scores).all();order=np.lexsort((ids,-scores));g=gold[r['qid']];assert g
  z=score_rank(ids[order].tolist(),g,len(g),'image:'+r['sha256']);records.append({'qid':r['qid'],'split':r['split'],**z,'gold_unique_count':len(g)})
 groups={}
 for split in ('all','smoke_20','dev','frozen_test'):
  rs=[r for r in records if split=='all' or r['split']==split];groups[split]={'n':len(rs),**{k:float(np.mean([r[k] for r in rs])) for k in metrics},'any_hit_counts':{k:sum(r[k] for r in rs) for k in metrics[:3]}}
 result['dimensions'][str(d)]={'groups':groups,'V_payload_bytes':4712*d*4,'Q_payload_bytes':1203*d*4,'payload_ratio':d/768,'elapsed_s':time.time()-t}
 with (O/f'dimension_{d}_rows.jsonl').open('x') as f:
  for r in records:f.write(json.dumps(r)+'\n')
 print(json.dumps({'dimension':d,**groups['all']}),flush=True)
for d,r in result['dimensions'].items():
 b=result['dimensions']['768']['groups']['all'];a=r['groups']['all'];r['delta_vs_768']={k:a[k]-b[k] for k in metrics};r['classification']=dimension_status([b[k]-a[k] for k in metrics])
(O/'r2_dimension_compress_20261024.json').write_text(json.dumps(result,indent=2))
