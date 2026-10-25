"""Registered transformations and metric definitions, without model imports."""
import copy

def equal_count(row):
 r=copy.deepcopy(row)
 if len(r['evidence']) not in (1,5): raise ValueError('Unexpected original gold count')
 r['evidence']=r['evidence'][:3];n=1+len(r['evidence'])
 for m in r.get('model_request',{}).get('messages',[]):
  m['content']=[x for x in m['content'] if x['type']!='image' or x['image_index']<n]
 if 'image_order' in r:r['image_order']=r['image_order'][:n]
 r['expected_num_evidence']=len(r['evidence']);r['condition']='S2@3'
 return r

def check_query_ids(expected,actual):
 if len(actual)!=len(set(actual)) or set(expected)!=set(actual):raise ValueError('Missing or duplicate qids')

def cost_status(short,long):return 'effective' if long>3*short else 'length_not_effective'
def extra100(short,long,tshort,tlong):return 100*(tlong-tshort)/(long-short) if long>short else None

def score_rank(order_ids,gold_set,gold_count,query_identity):
 order=[x for x in order_ids if x!=query_identity];ranks=[i+1 for i,x in enumerate(order) if x in gold_set]
 return {'hit_at_1':int(any(x<=1 for x in ranks)),'hit_at_5':int(any(x<=5 for x in ranks)),'hit_at_10':int(any(x<=10 for x in ranks)),'recall_at_5':len(set(order[:5])&gold_set)/gold_count,'mrr':1/min(ranks) if ranks else 0.}
def dimension_status(losses):return 'not_compressible' if any(x>.03 for x in losses) else 'within_tolerance'

def cost_jobs(qids):
 return [(qids[0],cap,True) for cap in (2,256) for _ in range(3)]+[(qid,cap,False) for i,qid in enumerate(qids) for cap in ((2,256) if i%2==0 else (256,2))]

def sample_energy(samples,t0,t1):
 import math
 rows=[]
 for r in samples:
  try:p=float(r.get('power_W'));t=float(r['epoch'])
  except (TypeError,ValueError,KeyError):continue
  if t0<=t<=t1 and math.isfinite(p):rows.append((t,p))
 rows.sort();n=len(rows)
 if n<2:return {'n':n,'trapezoidal_Wh':None,'mean_power_times_duration_Wh':None,'sample_window_s':None,'full_request_covered':False}
 duration=rows[-1][0]-rows[0][0];trap=sum((a[1]+b[1])*.5*(b[0]-a[0]) for a,b in zip(rows,rows[1:]))/3600
 return {'n':n,'trapezoidal_Wh':trap,'mean_power_times_duration_Wh':sum(x[1] for x in rows)/n*duration/3600,'sample_window_s':duration,'full_request_covered':rows[0][0]<=t0 and rows[-1][0]>=t1}

def transition_counts(pairs):
 counts={k:0 for k in ('rescue','harm','same_correct','same_wrong')}
 for old,new in pairs:counts[('same_correct' if new else 'harm') if old else ('rescue' if new else 'same_wrong')]+=1
 return {**counts,'unchanged':counts['same_correct']+counts['same_wrong'],'n':len(pairs),'net':counts['rescue']-counts['harm']}

def retention_status(lower,reference):
 if reference<=0:return 'not_applicable'
 return 'meets_retention' if lower>0 and lower>=.7*reference else 'does_not_meet_retention'
