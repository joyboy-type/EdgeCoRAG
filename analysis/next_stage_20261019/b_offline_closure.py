"""Public-only D1 and honest D2 availability report; no generation or reparsing.

Reproduce: $PY analysis/next_stage_20261019/b_offline_closure.py --verify
Requires only the two published D1 files and logs/B_predictions.jsonl.gz.
D1 family is fixed at 15 strategy + 5 dev-selected P3 cross-model pairs.
Holm-compatible simultaneous rectangles equal conservative Bonferroni basic CIs;
Holm step-down p values are separately reported. Descriptive, not preregistered.
"""
import argparse,csv,gzip,hashlib,io,json,tempfile
from collections import Counter,defaultdict
from pathlib import Path
from quality_stats import paired_family,choose_fixed
from quality_data import MODELS

REPO=Path(__file__).resolve().parents[2]
REPORT=Path('reports/next_stage_20261019')
MODEL_PAIRS=[('qwen3vl_4b','gemma4_e2b'),('qwen3vl_8b','gemma4_e2b'),
 ('qwen3vl_4b','gemma4_e4b'),('qwen3vl_8b','gemma4_e4b'),('gemma4_e2b','gemma4_e4b')]
STRATEGY_PAIRS=[('cosine','utility'),('random','utility'),('random','cosine')]
SPLITS={'smoke_20':20,'dev':150,'frozen_test':1033}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def jsonl(path):
 with gzip.open(path,'rt') as stream:return [json.loads(s) for s in stream]
def scored(row):
 if type(row['correct']) is not bool or type(row['generation_error_present']) is not bool:
  raise ValueError('Expected archived boolean flags')
 return row['correct'] and row['parse_status']=='ok' and not row['generation_error_present']
def align_groups(qids,groups):
 if len(set(qids))!=len(qids) or set(qids)!=set(groups):raise ValueError('One-to-one query/component join required')
 return [groups[q] for q in qids]
def write_csv(path,rows):
 stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 path.write_text(stream.getvalue(),newline='')
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def build(repo,out):
 repo,out=Path(repo),Path(out);out.mkdir(parents=True,exist_ok=True)
 source=repo/'logs/results_20261020/no_self_scored_outcomes.jsonl.gz'
 component=repo/'logs/results_20261020/frozen1033_image_groups_and_transitions.csv'
 predictions=repo/'logs/B_predictions.jsonl.gz'
 rows=jsonl(source)
 if len(rows)!=18045:raise ValueError('Expected 18045 public no-self rows')
 with component.open() as f:component_rows=list(csv.DictReader(f))
 groups={r['qid']:r['query_or_GT_image_component'] for r in component_rows}
 if len(component_rows)!=1033 or len(groups)!=1033 or len(set(groups.values()))!=564:
  raise ValueError('Expected 1033 queries / 564 components')
 cohorts=defaultdict(dict);failures=Counter();overrides=0
 for row in rows:
  k=(row['model'],row['strategy'],row['cohort'])
  if row['qid'] in cohorts[k]:raise ValueError('Duplicate scored outcome')
  cohorts[k][row['qid']]=scored(row)
  failures[row['parse_status']]+=1
  overrides+=int(row['correct'] and not scored(row))
 if len(cohorts)!=45:raise ValueError('Incomplete model/strategy/split matrix')
 for (m,s,c),v in cohorts.items():
  if m not in MODELS or s not in ('cosine','random','utility') or c not in SPLITS or len(v)!=SPLITS[c]:
   raise ValueError('Unexpected cohort or fixed denominator')
 qids=list(groups);cluster=align_groups(qids,groups)
 def values(m,s):return [cohorts[m,s,'frozen_test'][q] for q in qids]
 selected={}
 for m in MODELS:
  devs=[cohorts[m,s,'dev'] for s in ('cosine','random','utility')]
  if any(set(v)!=set(devs[0]) for v in devs):raise ValueError('Dev cohort not aligned')
  selected[m]=choose_fixed({s:list(cohorts[m,s,'dev'].values()) for s in ('cosine','random','utility')})
 comparisons=[]
 for m in MODELS:
  for left,right in STRATEGY_PAIRS:
   comparisons.append(dict(kind='strategy',left_model=m,right_model=m,left_strategy=left,right_strategy=right,
     left=values(m,left),right=values(m,right)))
 for left,right in MODEL_PAIRS:
  comparisons.append(dict(kind='model_P3_dev_selected',left_model=left,right_model=right,left_strategy=selected[left],
    right_strategy=selected[right],left=values(left,selected[left]),right=values(right,selected[right])))
 estimates=paired_family(comparisons,cluster)
 write_csv(out/'B_source_cluster_ci.csv',estimates)
 nonzero=[{k:r[k] for k in ('kind','left_model','right_model','left_strategy','right_strategy','delta_pp','ci_low_pp',
 'ci_high_pp','holm_ci_low_pp','holm_ci_high_pp')} for r in estimates if not r['holm_ci_low_pp']<=0<=r['holm_ci_high_pp']]
 summary=dict(status='recomputed_public_only',description='描述性、未预注册',public_rows=len(rows),queries=1033,components=564,
  resamples=10000,seed=42,paired_comparisons=20,family_size=20,selected_on_dev=selected,parse_status_counts=dict(failures),
  generation_error_present=sum(r['generation_error_present'] for r in rows),true_correct_overridden_by_failure=overrides,
  estimand='ratio of resampled cluster difference sums to resampled question counts; percentage points',
  holm_p='step-down centered-bootstrap p values',holm_intervals='conservative full-family joint-acceptance rectangle projections = Bonferroni basic intervals; descriptive approximation',
  holm_nonzero=nonzero,strategy_holm_nonzero=sum(r['kind']=='strategy' for r in nonzero),
  cross_zero_wording='不能排除无差异',source_sha256={str(p.relative_to(repo)):sha(p) for p in [source,component]},
  cross_model_limit='P3 may select different strategies; not guaranteed shared selected evidence. Not a replacement or causal test.')
 save(out/'B_holm_summary.json',summary)
 # D2 original definitions are retained, never forced into an invalid partition.
 baseline=jsonl(predictions)
 if len(baseline)!=21927:raise ValueError('Expected 21927 historical prediction rows')
 by={}
 stage={'smoke_20':'smoke','dev':'development','frozen_test':'quality'}
 for r in baseline:
  if r['split'] not in stage or r['stage']!=stage[r['split']] or r['condition'] not in ('S0','S1'):continue
  k=(r['model_key'],r['condition'],r['split'],r['qid'])
  if k in by:raise ValueError('Duplicate primary S0/S1')
  by[k]=r
 cells=[]
 for m in MODELS:
  for cohort,n in SPLITS.items():
   qs={k[3] for k in by if k[:3]==(m,'S0',cohort)}
   if len(qs)!=n or qs!={k[3] for k in by if k[:3]==(m,'S1',cohort)}:raise ValueError('S0/S1 fixed cohort mismatch')
   def ok(c,q):
    r=by[m,c,cohort,q];return bool(r['correct'] and r['parse_status']=='ok' and not r.get('generation_error'))
   harm=sum(ok('S0',q) and not ok('S1',q) for q in qs)
   for category in ('a_not_retrieved','b_present_but_wrong','c_S0_right_S1_wrong','d_ability_replacement'):
    known=category.startswith('c_')
    cells.append(dict(model=m,category=category,cohort=cohort,denominator=n,count=harm if known else '',
      percent=100*harm/n if known else '',status='observed_overlap_possible' if known else 'blocked',
      limit='Original S1 published candidates, not D1 no-self path; may overlap a/b' if known else
      ('No A pools/ranks + exact GT identity in this public checkout' if not category.startswith('d_') else
       'Cross-zero is not equivalence; missing matched-load lower cost and shared-evidence comparison; group-level claim not question class')))
 write_csv(out/'B_mechanism_four_class.csv',cells)
 save(out/'B_mechanism_availability.json',dict(status='blocked_not_a_valid_partition',public_baseline_rows=21927,
  source_sha256=sha(predictions),D1_sha256=sha(out/'B_holm_summary.json'),queries_per_model_frozen=1033,
  original_definitions_retained=True,unknown_counts_are_blank=True,reason=['a,b,c can overlap','d is model-pair/cost property, not per-question complement',
  'No independent equivalence/noninferiority protocol','S1 and no-self D1 evidence policies differ','A pools/ranks + GT identities unavailable'],
  R21='部分完成',not_completed='four mutually exclusive original classes summing to1033 cannot be certified'))
 return summary
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=REPO)
 p.add_argument('--verify',action='store_true');args=p.parse_args();target=args.repo/REPORT
 if args.verify:
  with tempfile.TemporaryDirectory() as d:
   summary=build(args.repo,Path(d))
   for f in Path(d).iterdir():
    if f.read_bytes()!=(target/f.name).read_bytes():raise ValueError('Reproduction differs: '+f.name)
 else:summary=build(args.repo,target)
 print(json.dumps({k:summary[k] for k in ['status','public_rows','queries','components','paired_comparisons','strategy_holm_nonzero','holm_nonzero']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
