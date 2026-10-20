"""Public-only Gate A1 and error derivatives; no generation/reparsing/selection.
Reproduce: $PY analysis/next_stage_20261019/gate_error_analysis.py --out "$NEW_ROOT"
Writes gate_a1_20261021/ and error_partition_20261021/ inside a NEW root.
--verify compares a temporary rebuild to an existing root; never overwrites.
"""
import argparse,csv,gzip,hashlib,io,json,tempfile
from pathlib import Path
from collections import Counter
from itertools import combinations
from quality_stats import paired_family
from quality_data import MODELS

REPO=Path(__file__).resolve().parents[2]
CLASSES=['未检索到','检索到但答错','检索伤害','无关但未伤害','不可判定']
STAGE={'smoke_20':'smoke','dev':'development','frozen_test':'quality'}

def error_type(r):
 if r.get('input_error'):return 'input_error'
 if r.get('generation_error'):return 'generation_error'
 status=r.get('parse_status')
 if status in ('empty_output','parse_failure','missing_prediction','generation_error'):return status
 if status!='ok':return 'other_parse_status'
 return 'none' if r['correct'] else 'incorrect_choice'

def partition(s0,s1,gt_hit):
 if s0 and not s1:return '检索伤害'
 if gt_hit is None:return '不可判定'
 if not gt_hit and not s1:return '未检索到'
 if gt_hit and not s1:return '检索到但答错'
 if not gt_hit and s1:return '无关但未伤害'
 return '不可判定' # correct/relevant is outside error labels, not invented error

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_csv(p):
 with Path(p).open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def jrows(p):
 with gzip.open(p,'rt') as f:return [json.loads(s) for s in f]
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def table(p,rows):
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def compressed_table(p,rows):
 text=io.StringIO();w=csv.DictWriter(text,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 p.write_bytes(gzip.compress(text.getvalue().encode(),mtime=0))
def success(r):return bool(r['correct'] and r.get('parse_status')=='ok' and not r.get('generation_error') and not r.get('input_error'))

def build(repo,out):
 repo=Path(repo);out=Path(out)
 if out.exists():raise FileExistsError(out)
 gate=out/'gate_a1_20261021';err=out/'error_partition_20261021';gate.mkdir(parents=True);err.mkdir()
 base_path=repo/'logs/B_predictions.jsonl.gz';no_path=repo/'logs/results_20261020/no_self_scored_outcomes.jsonl.gz'
 group_path=repo/'logs/results_20261020/frozen1033_image_groups_and_transitions.csv'
 qroot=repo/'reports/next_stage_20261019/quality_closure_20261021'
 selection_path=qroot/'dev_fixed_selection.csv';interval_path=qroot/'paired_differences.csv'
 budget_path=repo/'reports/next_stage_20261019/p2_p5_20261021/P5_budget/budget_options.csv'
 base=jrows(base_path);no=jrows(no_path);group_rows=load_csv(group_path)
 assert len(base)==21927 and len(no)==18045 and len(group_rows)==1033
 qids=[r['qid'] for r in group_rows];groups=[r['query_or_GT_image_component'] for r in group_rows]
 assert len(set(qids))==1033 and len(set(groups))==564
 selected={r['model']:r['selected'] for r in load_csv(selection_path)}
 # Check existing dev choices only; never choose/revise on frozen outcomes.
 for r in load_csv(selection_path):assert r['selection_split']=='dev' and int(r['n'])==150 and r['frozen_test_used']=='False'
 primary={}
 for line,r in enumerate(base,1):
  if r['split'] in STAGE and r['stage']==STAGE[r['split']] and r['condition'] in ('S0','S1','S2'):
   key=(r['model_key'],r['condition'],r['split'],r['qid'])
   if key in primary:raise ValueError('Duplicate primary row')
   primary[key]=(line,r)
 public={(r['model'],r['strategy'],r['cohort'],r['qid']):r for r in no}
 vec={};comparisons=[]
 for m in MODELS:
  paths={s:[bool(public[m,s,'frozen_test',q]['correct'] and public[m,s,'frozen_test',q]['parse_status']=='ok' and not public[m,s,'frozen_test',q]['generation_error_present']) for q in qids] for s in ('cosine','random','utility')}
  vec[m]={'P1':paths['cosine'],'P2':paths['utility'],'P3':paths[selected[m]],'P4':[any(paths[s][i] for s in paths) for i in range(1033)]}
  for left,right in combinations(('P1','P2','P3','P4'),2):comparisons.append(dict(model=m,left_path=left,right_path=right,left=vec[m][left],right=vec[m][right]))
 paired=paired_family(comparisons,groups)
 archived={(r['model'],r['left_path'],r['right_path']):r for r in load_csv(interval_path)}
 for r in paired:
  ref=archived[r['model'],r['left_path'],r['right_path']]
  for field in ('delta_pp','ci_low_pp','ci_high_pp','holm_ci_low_pp','holm_ci_high_pp'):
   if abs(r[field]-float(ref[field]))>1e-9:raise ValueError('R03 archive mismatch '+field)
 oracle=[r for r in paired if r['left_path']=='P3' and r['right_path']=='P4']
 complement=[];flags={};examples=[]
 for m in MODELS:
  s={c:[success(primary[m,c,'frozen_test',q][1]) for q in qids] for c in ('S0','S1','S2')}
  flags[m]={'a_S1_rescues_S0':[not x and y for x,y in zip(s['S0'],s['S1'])],
            'b_S2_rescues_S1':[not x and y for x,y in zip(s['S1'],s['S2'])],
            'c_S1_harms_S0':[x and not y for x,y in zip(s['S0'],s['S1'])]}
  flags[m]['rescue_union']=[a or b for a,b in zip(flags[m]['a_S1_rescues_S0'],flags[m]['b_S2_rescues_S1'])]
  for name,v in flags[m].items():complement.append(dict(model=m,metric=name,left=[False]*1033,right=v))
  harm=next((i for i,v in enumerate(flags[m]['c_S1_harms_S0']) if v),None)
  allwrong=next((i for i,v in enumerate(vec[m]['P4']) if not v),None)
  for kind,i in [('S0_right_S1_wrong',harm),('all_no_self_strategies_wrong_even_oracle',allwrong)]:
   if i is not None:examples.append(dict(model=m,qid=qids[i],kind=kind,S0=s['S0'][i],S1=s['S1'][i],S2=s['S2'][i],P3=vec[m]['P3'][i],P4_post_hoc=vec[m]['P4'][i],baseline_source_lines={c:primary[m,c,'frozen_test',qids[i]][0] for c in s}))
 comp=paired_family(complement,groups);table(gate/'complementarity.csv',comp)
 # Cost assumptions copied from P5; not technical-smoke measured performance.
 budget=load_csv(budget_path);gen=next(r for r in budget if r['option']=='A_cap5' and r['stage']=='E3' and r['operation'].startswith('generation-only'))
 route=next(r for r in budget if r['option']=='A_cap5' and r['operation']=='smoke request IO')
 unit=float(gen['assumed_unit_seconds']);overhead=float(route['assumed_unit_seconds']);rate=2.18
 costs=[dict(assumed_skip_fraction=f,queries=1033,assumed_generation_seconds=unit,assumed_route_seconds=overhead,
   routing_seconds=1033*overhead,net_saved_seconds=1033*(f*unit-overhead),routing_cny=1033*overhead*rate/3600,
   net_saved_cny=1033*(f*unit-overhead)*rate/3600,nonmeasured=True) for f in (0,.25,.5,.75,1)]
 sources={str(p.relative_to(repo)):sha(p) for p in [base_path,no_path,group_path,selection_path,interval_path,budget_path]}
 numbers=dict(verdict='insufficient_evidence',reason='Post hoc complementarity is not an evaluated deployable router; matched end-to-end routing cost absent.',
   n=1033,components=564,resamples=10000,seed=42,statistics='描述性、未预注册；配对单位qid，整组重采样564个query/GT图像关联分量，按题加权；basic区间，Holm兼容联合矩形=Bonferroni；非独立题bootstrap。',
   oracle_minus_dev_selected_fixed=oracle,complementarity=comp,cost_scenarios=costs,cost_assumptions={'routing_proxy_source':"P5 CSV option=A_cap5 AND operation='smoke request IO', assumed_unit_seconds=0.03; IO proxy, NOT trained router time",'generation_source':"option=A_cap5 AND stage=E3 AND operation startswith generation-only; assumed_unit_seconds=3",'assumed_rate_cny_hour':rate,'exclusions':'load, retrieval, utility, network and storage excluded; no measured saving claim'},
   counterexamples=examples,source_sha256=sources,filters={'baseline':"split='frozen_test' AND stage='quality' AND condition IN ('S0','S1','S2'); each model/condition 1033 unique qids",'R03':"cohort='frozen_test', model=m, strategy=dev_fixed_selection[m]; P4=max(correct over cosine/random/utility), never deployable",'complementarity':'a=!S0&S1; b=!S1&S2; c=S0&!S1; a/b/c may overlap, cannot sum to1033; rescue_union=a|b'},reconsideration='复议条件（区间下界>0 且互补率≥15%）系事后设定的写作形态规则，不作统计推断。')
 save(gate/'numbers.json',numbers)
 md=['# Gate A1 裁决：insufficient_evidence','', '复验：`$PY analysis/next_stage_20261019/gate_error_analysis.py --verify --out "$DERIVED_ROOT"`','',numbers['reason'],'',numbers['statistics'],'','## (i) post hoc Oracle − dev150最佳固定（frozen1033只评估）','']
 for r in oracle:md.append(f"- {r['model']}: {r['right_correct']}-{r['left_correct']} /1033 = {r['delta_pp']:.4f}pp；95% [{r['ci_low_pp']:.4f},{r['ci_high_pp']:.4f}]；30对家族校正矩形 [{r['holm_ci_low_pp']:.4f},{r['holm_ci_high_pp']:.4f}]。")
 md+=['','Oracle为三种no-self策略的post hoc上界，不是S2 GT路径，也不是可部署路由。dev150选择原样核对，未改动。','', '## (ii) S0/S1/S2互补','',numbers['filters']['complementarity'],'这与R03的三策略路径是不同条件，不混成一项实验。逐模型计数/1033与区间见numbers.json、complementarity.csv。失败计错，未重parse。','', '## (iii) 假设路由成本/节省','',f'1033题×{overhead}s = {1033*overhead:.2f}s路由开销；假设跳过25%且每次生成{unit}s，净节省{costs[1]["net_saved_seconds"]:.2f}s（{costs[1]["net_saved_cny"]:.6f}元，假设2.18元/时）。均非实测，0%跳过时反而损失30.99秒。IO代理不等于真实路由器耗时。','', '反例：counterexamples列出S0正确但S1错误的题，以及三种策略均错、Oracle仍失败的题；每例带源JSONL物理行号。互补并不证明有可学习且省成本的部署策略。','', '文件、SHA及精确筛选条件见numbers.json.source_sha256/filters。校正区间跨零一律“不能排除无差异”；不写显著、因果或普遍替代。','',numbers['reconsideration']]
 (gate/'verdict.md').write_text('\n'.join(md)+'\n')
 # Derived row table retains source status/flags and never copies raw outputs/gold.
 derived=[];ledger=[];errorcounts=Counter();allcounts=Counter()
 for line,r in enumerate(base,1):
  et=error_type(r);errorcounts[et]+=1
  derived.append(dict(source_line=line,row_key=r.get('row_key',''),qid=r['qid'],model=r['model_key'],split=r['split'],stage=r['stage'],condition=r['condition'],input_error_json=json.dumps(r.get('input_error')),generation_error_json=json.dumps(r.get('generation_error')),parse_status=r['parse_status'],correct=r['correct'],error_type=et))
  key=(r['model_key'],'S0',r['split'],r['qid']);eligible=r['split'] in STAGE and r['stage']==STAGE[r['split']] and r['condition']=='S1' and key in primary
  label=partition(success(primary[key][1]),success(r),None) if eligible else '不可判定'
  allcounts[label]+=1
  ledger.append(dict(source_line=line,qid=r['qid'],model=r['model_key'],split=r['split'],stage=r['stage'],condition=r['condition'],category=label,limit='S0/S1关联伤害代理，无因果' if label=='检索伤害' else ('无精确GT/top10身份联接，不能从槽位名称推断' if eligible else '不是主分析S1行；重复/性能/holdout及S0/S2不充作检索错误题'),ability_replacement='model_level_unestablished_not_a_partition'))
 compressed_table(err/'error_types.csv.gz',derived);compressed_table(err/'partition_rows.csv.gz',ledger)
 partcomps=[];assignment={}
 for m in MODELS:
  labels=[partition(success(primary[m,'S0','frozen_test',q][1]),success(primary[m,'S1','frozen_test',q][1]),None) for q in qids];assignment[m]=Counter(labels)
  for label in CLASSES:partcomps.append(dict(model=m,category=label,left=[False]*1033,right=[x==label for x in labels]))
 partci=paired_family(partcomps,groups)
 for r in partci:
  r['count']=r['right_correct'];r['percent']=100*r['count']/1033;r['ability_replacement']='unestablished: no matched-load cost/noninferiority evidence'
  r['limit']='Assigned-label fraction only; zero identified != true event prevalence zero. Slot IDs cannot establish exact GT hit.'
 table(err/'partition_summary.csv',partci)
 mapping=[dict(old='a_not_retrieved',new='未检索到',rule='Exact GT absent from top10 AND S1 wrong after harm priority; unknown without GT join'),dict(old='b_present_but_wrong',new='检索到但答错',rule='GT hit AND S1 wrong after harm priority'),dict(old='c_S0_right_S1_wrong',new='检索伤害',rule='S0 right AND S1 wrong; priority first; associative only'),dict(old='d_ability_replacement',new='model-level attribute only',rule='Not a per-query partition; unavailable without cost/noninferiority'),dict(old='other/unknown',new='无关但未伤害 / 不可判定',rule='No exact GT AND S1 right = no-harm proxy; otherwise missing GT or outside error labels -> unknown')]
 table(err/'old_to_new_mapping.csv',mapping)
 save(err/'summary.json',dict(source_rows=21927,error_type_counts=dict(errorcounts),all_row_assigned_counts=dict(allcounts),primary_frozen_per_model={m:dict(assignment[m]) for m in MODELS},per_model_denominator=1033,components=564,resamples=10000,seed=42,source_sha256={str(base_path.relative_to(repo)):sha(base_path),str(group_path.relative_to(repo)):sha(group_path)},error_type_priority=['input_error truthy','generation_error truthy','parse_status in empty_output/parse_failure/missing_prediction/generation_error','parse_status != ok -> other_parse_status','correct false -> incorrect_choice','else none'],original_fields_unchanged=True,original_logs_unchanged=True,CI_scope='paired S0/S1 qids, marginal assigned-category fractions via zero-reference paired component bootstrap; not model-accuracy differences. Full21927 repeated/holdout rows have no defensible shared564-component CI, so no pooled CI fabricated.',missing='No public exact GT/top10 identity join for original S1; assigned0 means not identified, not proven absent. Unknown contains those and non-S1/out-of-scope rows.'))
 (err/'README.md').write_text('# 五类互斥操作分区与error_type\n\n复验：`$PY analysis/next_stage_20261019/gate_error_analysis.py --verify --out "$DERIVED_ROOT"`\n\n全部21927源行各落一个标签，见partition_rows.csv.gz；主分析为stage=quality/split=frozen_test/condition=S1，每模型1033，按564关联分量配对bootstrap10000次seed42，见partition_summary.csv。主分析5类和=1033。全21927行包含性能重复、holdout与S0/S2，不伪称21927个独立问题，不对它们移植564组CI。\n\n优先级：先S0对S1错→检索伤害代理；其后top10不含GT且S1错→未检索到；含GT且S1错→检索到但答错；不含GT且S1对→无关但未伤害的操作代理；缺身份联接/配对、非主S1或正确且有证据→不可判定（包括非错误项，不能硬塞错误类）。公开S1 official_retrieved*与S2 gt*是角色槽位名，不能比较字符串推断图像命中；本批所有非伤害主S1都未知，前三个无法识别类别的0只是已识别计数，不是其真实率为0。\n\n区间是同一配对问题集中的标签占比区间，以全False参考计算；不是模型间准确率差。未校正与25格家族Holm兼容保守矩形=Bonferroni均报告，描述性、未预注册。跨零只能说不能排除无差异。能力替代单列模型级属性，缺同负载成本/非劣效证据，不能由跨零推出。\n\nerror_types.csv.gz逐条保留源行号、原input_error/generation_error的JSON值、parse_status、correct，额外派生error_type；优先级见summary.json，重叠失败另有原始字段可查，不改变任何原状态、分数或日志。未重新parse；wrong-answer与parse_failure分开计数。\n')
 for folder in (gate,err):save(folder/'manifest.json',{p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(folder.iterdir())})
 return numbers

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=REPO);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.verify:
  with tempfile.TemporaryDirectory() as d:
   tmp=Path(d)/'fresh';numbers=build(a.repo,tmp)
   for f in tmp.rglob('*'):
    if f.is_file() and f.read_bytes()!=(a.out/f.relative_to(tmp)).read_bytes():raise ValueError('Reproduction mismatch: '+str(f.relative_to(tmp)))
 else:numbers=build(a.repo,a.out)
 print(json.dumps({'verdict':numbers['verdict'],'oracle_minus_fixed':[{k:r[k] for k in ('model','delta_pp','ci_low_pp','ci_high_pp')} for r in numbers['oracle_minus_dev_selected_fixed']]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
