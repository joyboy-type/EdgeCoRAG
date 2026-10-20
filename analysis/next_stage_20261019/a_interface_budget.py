"""B7 conditional arithmetic only, not an executable plan or GPU authorization.
Reproduce: $PY analysis/next_stage_20261019/a_interface_budget.py --verify
Request counts follow user E1-E5 queue; E5 assumes ONE generator, utility on all
quality questions as a conservative scenario. Unit times/rate are assumptions.
"""
import argparse,csv,io,json,math,tempfile
from pathlib import Path
from a_interface_evidence import sha,save,table
REPO=Path(__file__).resolve().parents[2]
OUT=Path('reports/next_stage_20261019/a_interface_review_20261021')
def build(repo,out):
 receipt=repo/'provenance/results_20261020/e2e_smoke_public_receipt.json'
 old=json.loads(receipt.read_text());rows=[]
 cases=[
 ('E0','conditional A fp32 corpus encode if no transferable verified index',4712,.5,1.),
 ('E1','1203 queries x batches16/1 sensitivity encodes',1203*2,.5,1.),
 ('E2','5 additional live fingerprint encodes',5,.5,1.),
 ('E3','20x3x6 +3 warmup generations',20*3*6+3,3.,6.),
 ('E3','live query encode per request',363,.5,1.),
 ('E3','ranking per request',363,.03,.06),
 ('E3','utility 20x6x10 +10 warmup forwards',1210,.25,.5),
 ('E4','smoke20 x4 paths generations',20*4,3.,6.),
 ('E4','shared utility once per20 queries x10',20*10,.25,.5),
 ('E5','one generator: smoke20x4 +dev150x4 +frozen1033x1',20*4+150*4+1033,3.,6.),
 ('E5','utility-all conditional upper workload',1713*10,.25,.5),
 ('E5','materialization/request IO conditional',1713,.03,.06),
 ('setup','one session load/validation allowance',1,900.,1800.),
 ('preservation','mandatory preservation reserve',1,600.,600.)]
 for stage,op,n,unit,worst in cases:
  rows.append(dict(stage=stage,operation=op,requests=n,unit_seconds=unit,unit_seconds_source='假设，非实测；不能由旧bf16移植到新fp32',
   point_seconds=n*unit,worst_unit_seconds=worst,worst_seconds=n*worst,
   count_source=('A corpus4712 reference; conditional new encoding' if stage=='E0' else 'user E1-E5 scope + explicit one-generator/shared-utility/cache assumptions')))
 for row in rows:
  if row['stage']=='preservation':row['unit_seconds_source']='user mandated600-second preservation, not measured duration'
 table(out/'B7_budget_derivation.csv',rows)
 total=sum(r['point_seconds'] for r in rows);worst=sum(r['worst_seconds'] for r in rows)
 rate=2.18;window=math.ceil(total/60);worst_window=math.ceil(worst/60)
 sources=dict(round1_receipt_sha256=sha(receipt),
  round1_bf16_cosine_full_request_median_seconds=old['stats']['cosine']['median_seconds'],
  round1_bf16_utility_full_request_median_seconds=old['stats']['utility']['median_seconds'],
  round1_utility_selection_build_median_seconds=old['stats']['utility']['component_medians']['selection_request_build_seconds'],
  limits='Historical medians are observed on round1 bf16; mixed selection includes utility and is NOT pure utility timing; no transfer as new fp32 benchmark.')
 save(out/'B7_budget_sources.json',sources)
 summary=dict(status='conditional_arithmetic_not_an_executable_plan',nonmeasured_assumptions=True,
  total_seconds=total,worst_scenario_seconds=worst,window_minutes=window,worst_window_minutes=worst_window,
  current_quote=None,assumed_rate_cap_cny_hour=rate,
  conditional_expected_cny=window/60*rate,conditional_worst_cny=worst_window/60*rate,
  rate_scope='assumption only, no live quote or user approval; no5h/7.4 reused',
  hard_stop='T0 + '+str(worst_window*60)+' seconds including600s preservation; actual UTC unknown until approved boot',
  stop_work='T0 + '+str(worst_window*60-600)+' seconds; preserve600s; independent platform hard-stop must be confirmed before running',
  preservation_seconds=600,
  failures=['B1 raw manifest verification fails -> do not begin','Index reconciliation unresolved -> no paired session',
   'Torch/BLAS effective counts unavailable/mismatch -> abort','Any source/hash/model/protocol mismatch -> abort',
   'First task error -> preserve partial, no retry','Insufficient remaining preservation reserve -> stop work'],
  cannot_apply_for_GPU_now=True,existing_runner_window_max_seconds=7200,
  proposed_window_within_existing_runner_limit=worst_window*60<=7200,
  runner_limit_source_sha256=sha(repo/'b-side/e2e_smoke.py'),
  limitations=['All unit times hypothetical, worst is a scenario not a probabilistic bound; hard stop bounds expenditure only after a quote and platform control are verified',
   'E5 one-generator scope must be confirmed; adding more models needs recomputation',
   'If transferred A fp32 index accepted, E0 could be omitted by a new preregistered scope; not silently removed here',
   'No3yuan/5yuan/65minute/100minute authorization inferred from prior sessions',
   'Conditional scope exceeds existing7200s runner limit; cannot execute this scenario without separate scope/protocol decision'])
 save(out/'B7_budget_summary.json',summary)
 return summary
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.verify:
  with tempfile.TemporaryDirectory() as d:
   result=build(REPO,Path(d))
   for f in Path(d).iterdir():
    if f.read_bytes()!=(REPO/OUT/f.name).read_bytes():raise ValueError('Budget arithmetic drift: '+f.name)
 else:result=build(REPO,REPO/OUT)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
