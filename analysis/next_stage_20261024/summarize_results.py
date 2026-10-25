"""Read preserved raw outcomes and apply preregistered summaries; no GPU execution."""
import json,gzip,hashlib,random,math,statistics,sys,subprocess
from pathlib import Path
from supplement_core import transition_counts,retention_status,cost_status,extra100
REPO=Path(__file__).resolve().parents[2];RAW=Path(sys.argv[1]);OUT=REPO/'reports/paper_20261021'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def loadlines(p):return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
def qhash(qs):return hashlib.sha256(''.join(x+'\n' for x in sorted(qs)).encode()).hexdigest()
def percentile(xs,p):
 xs=sorted(xs);i=(len(xs)-1)*p;a=int(i);b=min(a+1,len(xs)-1);return xs[a]+(xs[b]-xs[a])*(i-a)
models=['qwen3vl_4b','gemma4_e2b','gemma4_e4b','qwen3vl_8b','qwen35_4b']
with gzip.open(REPO/'logs/B_predictions.jsonl.gz','rt') as f:
 old=[json.loads(x) for x in f]
old=[r for r in old if r['stage']=='quality' and r['split']=='frozen_test' and r['condition'] in ('S1','S2')]
lookup={(r['model_key'],r['condition'],r['qid']):r for r in old};assert len(lookup)==len(old)==10330
registration=OUT/'PREREGISTRATION_20261024.md'
# Execution results may be appended later; cite the immutable pre-execution blob.
registration_sha=hashlib.sha256(subprocess.check_output(['git','show','f5a3f12:reports/paper_20261021/PREREGISTRATION_20261024.md'],cwd=REPO)).hexdigest()
assert registration_sha=='8046e99b4c2c82064e3e9263043929c570f1af95dd49e393dfff363f41f39391'
result={'registration_commit':'f5a3f12','registration_sha256':registration_sha,'source':{'existing_predictions':'logs/B_predictions.jsonl.gz','existing_sha256':sha(REPO/'logs/B_predictions.jsonl.gz'),'new_raw_archive':str(RAW),'archive_manifest_sha256':sha(RAW/'file_sha256.json')},'ci_method':{'unit':'question-level scenario-stratified paired bootstrap','replicates':2000,'seed':42,'rng':'random.Random, reset per model and analysis set','percentile':'95%, linear interpolation','descriptive':True,'not_frozen_564_cluster_bootstrap':True},'models':{}}
for model in models:
 new=loadlines(RAW/model/'predictions.jsonl');assert len(new)==1033 and len({r['qid'] for r in new})==1033;assert not any(r.get('generation_error') for r in new)
 assert qhash(r['qid'] for r in new)=='2a102ea80297f371dbe793125ac98c084880168929cf8a0781aac315c485d9bc'
 z={'new_predictions_source':str(RAW/model/'predictions.jsonl'),'new_sha256':sha(RAW/model/'predictions.jsonl'),'runtime':json.loads((RAW/model/'runtime.json').read_text()),'groups':{}}
 for group,rs in [('primary956',[r for r in new if r['primary956']]),('secondary1033',new),('single77',[r for r in new if not r['primary956']])]:
  rs=sorted(rs,key=lambda r:r['qid']);n=len(rs);assert n=={'primary956':956,'secondary1033':1033,'single77':77}[group];groups={}
  for r in rs:
   before=lookup[(model,'S1',r['qid'])];prior=lookup[(model,'S2',r['qid'])]
   # Independently score against the same existing gold; don't trust the new correct flag alone.
   now=r.get('parsed_choice')==before['answer'];assert now==r['correct'];assert before['scenario']==r['scenario'];assert prior['answer']==before['answer']
   a,b=bool(before['correct']),bool(now);c=transition_counts([(a,b)])
   value={'delta':int(b)-int(a),'rescue':c['rescue'],'harm':c['harm'],'unchanged':c['unchanged'],'same_correct':c['same_correct'],'same_wrong':c['same_wrong']}
   groups.setdefault(r['scenario'],[]).append(value)
  counts=transition_counts([(bool(lookup[(model,'S1',r['qid'])]['correct']),bool(r['correct'])) for r in rs]);metrics=['delta','rescue','harm','unchanged','same_correct','same_wrong'];samples={k:[] for k in metrics};rng=random.Random(42)
  for _ in range(2000):
   totals={k:0 for k in metrics}
   for scenario in sorted(groups):
    g=groups[scenario]
    for _j in range(len(g)):
     v=g[rng.randrange(len(g))]
     for k in metrics:totals[k]+=v[k]
   for k in metrics:samples[k].append(totals[k]/n)
  ci={k:[percentile(samples[k],.025),percentile(samples[k],.975)] for k in metrics}
  old_delta=sum(int(lookup[(model,'S2',r['qid'])]['correct'])-int(lookup[(model,'S1',r['qid'])]['correct']) for r in rs)/n
  a=sum(bool(lookup[(model,'S1',r['qid'])]['correct']) for r in rs);b=sum(bool(r['correct']) for r in rs)
  z['groups'][group]={'n':n,'qid_sha256':qhash(r['qid'] for r in rs),'S1_correct':a,'S2_at3_correct':b,'S1_accuracy':a/n,'S2_at3_accuracy':b/n,'counts':counts,'proportions':{k:counts[k]/n for k in ('rescue','harm','unchanged','same_correct','same_wrong')},'delta':(b-a)/n,'ci95':ci,'reference_S2_at5_minus_S1_same_set':old_delta,'retained_ratio':((b-a)/n/old_delta) if old_delta>0 else None,'lower_bound_reference_ratio':ci['delta'][0]/old_delta if old_delta>0 else None,'criterion':retention_status(ci['delta'][0],old_delta) if group=='primary956' else 'not_primary_no_pass_label','scenario_n':{k:len(v) for k,v in sorted(groups.items())}}
 result['models'][model]=z
(OUT/'r1_equal_count_20261024.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
lines=['# 同张数正确证据对照（2026-10-24）','','五模型均完成1,033题新生成，技术失败0；主分析严格限于956道原有5张GT的题，S1与S2@3均提供3张证据。另77道单图题及全量1,033题只作次要报告，非同张数，不引用为主结论。','','来源：`logs/B_predictions.jsonl.gz`（stage=quality、split=frozen_test、S1/S2）及JSON内逐模型`new_predictions_source`。原始文件SHA256、题单摘要与运行栈见同名JSON。预注册提交`f5a3f12`；未改冻结表。','','|模型|S1答对/956|S2@3答对/956|净增益pp [95%区间]|原S2−S1，同956题pp|预设保留判据|','|---|---:|---:|---|---:|---|']
for m,z in result['models'].items():
 g=z['groups']['primary956'];lo,hi=g['ci95']['delta'];lines.append(f"|{m}|{g['S1_correct']}|{g['S2_at3_correct']}|{100*g['delta']:+.2f} [{100*lo:+.2f}, {100*hi:+.2f}]|{100*g['reference_S2_at5_minus_S1_same_set']:+.2f}|{'满足' if g['criterion']=='meets_retention' else '未满足'}|")
lines+=['','预设判据：净增益区间下界>0且≥原同956题净增益的70%。判据未满足不等于没有净增益，也不是因果机制判断。','','### 70%规则的逐模型读数（分母956；S1三张、S2@3三张，原S2五张）','','|模型|点估计比 Delta3/Delta5|判定比 L3/Delta5|严格保留标准|','|---|---:|---:|---|']
for m,z in result['models'].items():
 g=z['groups']['primary956'];lines.append(f"|{m}|{100*g['retained_ratio']:.2f}%|{100*g['lower_bound_reference_ratio']:.2f}%|{'满足' if g['criterion']=='meets_retention' else '未满足'}|")
lines+=['','只有判定比≥70%且L3>0才满足标准；五模型净增益区间全>0，严格标准2/5。点估计比不是通过判据；超过100%是两个净差的描述性比值，不是因果贡献。','','## 转换构成（956题；两条件均3张证据；题数、比例与95%区间）','','|模型|救回|伤害|不变|不变：同对/同错|','|---|---|---|---|---|']
for m,z in result['models'].items():
 g=z['groups']['primary956'];cells=[]
 for k in ('rescue','harm','unchanged'):
  lo,hi=g['ci95'][k];cells.append(f"{g['counts'][k]}，{100*g['proportions'][k]:.2f}% [{100*lo:.2f}, {100*hi:.2f}]")
 lines.append('|'+m+'|'+'|'.join(cells)+f"|{g['counts']['same_correct']}/{g['counts']['same_wrong']}|")
lines+=['','每行救回+伤害+不变=956；同对+同错=不变。区间为题级、场景分层配对bootstrap，2,000次，seed 42，描述性95% percentile（线性插值）；与冻结表564分量聚类口径不同。','','## 次要报告（非同张数；不作主结论引用）','','|模型|全量1,033答对|全量净差pp|单图77答对|单图净差pp|','|---|---:|---:|---:|---:|']
for m,z in result['models'].items():
 a=z['groups']['secondary1033'];b=z['groups']['single77'];lines.append(f"|{m}|{a['S2_at3_correct']}|{100*a['delta']:+.2f}|{b['S2_at3_correct']}|{100*b['delta']:+.2f}|")
lines+=['','全量条件实际为956×3张+77×1张。区间、各格计数及单图层完整数据见JSON的`models.*.groups`。','','边界：仅描述同题、同数量条件的表现差异；没有随机化图像内容，未做机制归因。新运行使用RTX 4090，原S1沿用历史正式记录；新旧硬件/栈差异见runtime，不能声称跨栈逐位相同。']
(OUT/'r1_equal_count_20261024.md').write_text('\n'.join(lines)+'\n')
# Preserve dimension result; annotate archival paths rather than change its raw numbers.
dim=json.loads((RAW/'r2_dimension_compress_20261024.json').read_text());dim['local_raw_archive']=str(RAW);dim['registration_sha256']=registration_sha
(OUT/'r2_dimension_compress_20261024.json').write_text(json.dumps(dim,indent=2)+'\n')
lines=['# 当前池维度压缩（2026-10-24）','','当前4,712唯一身份池，分母1,203题；GT标注通常5张、Incomplete为1张；这是纯检索排序，不设置生成输入的3/5张条件，top1/5/10的k为评估截断位次。复用V，全部Q新补编码FP32。按截断→float32逐行L2重归一化→FP32点积→score降序/identity升序排序，并排除query精确自匹配。不是历史18,955索引的复跑。','','|维度|top1命中|top5命中|top10命中|宏Recall@5|完整MRR|V载荷MiB|判定|','|---|---:|---:|---:|---:|---:|---:|---|']
for d,z in dim['dimensions'].items():
 g=z['groups']['all'];n=g['n'];c=g['any_hit_counts'];lines.append(f"|{d}|{c['hit_at_1']}/{n}|{c['hit_at_5']}/{n}|{c['hit_at_10']}/{n}|{g['recall_at_5']:.6f}|{g['mrr']:.6f}|{z['V_payload_bytes']/1048576:.4f}|未超过3 pp损失阈值|")
lines+=['','128/256/512维的五项指标下降均未严格超过预设3 pp容差。此为本题单的容差判定，不代表统计等价或其他语料泛化。256维V理论载荷为768维的1/3；top5为819/1,203 vs 815/1,203，top1下降1.50 pp，完整MRR下降0.006667。不能只报告top5而隐去其他指标。','','来源：同名JSON `dimensions.*.groups.all`；split分别见`groups.smoke_20/dev/frozen_test`，V/Q路径及摘要见`sources`。新Q编码回执`'+str(RAW/'encoding_receipt.json')+'`。载荷仅为矩阵元素字节数，不是完整索引文件体积、显存或端到端成本；不与历史384/383混比。']
lines+=['','## 256维对768维：五项完整比较（分母1,203；纯检索、无生成3/5张条件）','','|指标|256维|768维|差值（概率×100；MRR为百分制单位）|','|---|---:|---:|---:|']
for k in ('hit_at_1','hit_at_5','hit_at_10','recall_at_5','mrr'):
 a=dim['dimensions']['256']['groups']['all'][k];b=dim['dimensions']['768']['groups']['all'][k];lines.append(f'|{k}|{a:.9f}|{b:.9f}|{100*(a-b):+.6f}|')
(OUT/'r2_dimension_compress_20261024.md').write_text('\n'.join(lines)+'\n')
# Cost: check locked jobs and independently recompute sampled energy.
from supplement_core import cost_jobs,sample_energy
cost={'registration_commit':'f5a3f12','registration_sha256':registration_sha,'inputs':str(RAW/'cost/inputs.json'),'inputs_sha256':sha(RAW/'cost/inputs.json'),'models':{},'limitations':['fixed_cosine E3 pipeline differs from official S1','20 hot requests per model/cap; descriptive P95','energy includes power-sampling boundary overhead; e2e excludes that boundary overhead','GPU energy only; sampled device maximum is not true continuous peak','old pilot archived only; no cross-card comparison']}
inputs=json.loads((RAW/'cost/inputs.json').read_text());device=loadlines(RAW/'cost/device_samples.jsonl')
for m in models[:3]:
 rs=loadlines(RAW/'cost'/(m+'_requests.jsonl'));assert len(rs)==46;assert [(r['qid'],r['cap'],r['warmup']) for r in rs]==cost_jobs(inputs['qids']);assert not any(r.get('generation_error') for r in rs)
 z={'source':str(RAW/'cost'/(m+'_requests.jsonl')),'sha256':sha(RAW/'cost'/(m+'_requests.jsonl')),'caps':{}}
 for cap in (2,256):
  a=[r for r in rs if r['cap']==cap and not r['warmup']];assert len(a)==20
  for r in a:
   en=sample_energy(device,r['start_epoch'],r['end_epoch']);assert en['full_request_covered'];assert math.isclose(en['trapezoidal_Wh'],r['energy']['trapezoidal_Wh'],rel_tol=1e-12)
  g={'n':20,'warmups':3,'mean_generated_tokens':statistics.mean(r['generated_tokens'] for r in a),'budget_exhausted':sum(r['budget_exhausted'] for r in a),'end_before_budget_count':sum(not r['budget_exhausted'] for r in a),'sampled_device_peak_bytes':max(r['device_peak_bytes_sampled'] for r in a),'allocator_peak_allocated_bytes':max(r['cuda_memory']['process_allocator_peak_allocated'] for r in a),'energy_trapezoidal_Wh':sum(r['energy']['trapezoidal_Wh'] for r in a),'energy_mean_power_times_duration_Wh':sum(r['energy']['mean_power_times_duration_Wh'] for r in a),'summed_sample_window_s':sum(r['energy']['sample_window_s'] for r in a),'raw_output_examples':[r['raw_output_with_special_tokens'] for r in a[:3]]}
  for k in ('e2e_ms','encoder_ms','generation_ms'):
   vs=[r[k] for r in a];g[k]={'mean':statistics.mean(vs),'p50':percentile(vs,.5),'p95':percentile(vs,.95)}
  z['caps'][str(cap)]=g
 a,b=z['caps']['2'],z['caps']['256'];status=cost_status(a['mean_generated_tokens'],b['mean_generated_tokens']);z['length_status']=status
 z['generation_ms_per_extra100_tokens']=extra100(a['mean_generated_tokens'],b['mean_generated_tokens'],a['generation_ms']['mean'],b['generation_ms']['mean']);z['e2e_ms_per_extra100_tokens']=extra100(a['mean_generated_tokens'],b['mean_generated_tokens'],a['e2e_ms']['mean'],b['e2e_ms']['mean']);z['marginal_result_use']='main_descriptive' if status=='effective' else 'appendix_arithmetic_only_not_long_answer_cost'
 cost['models'][m]=z
(OUT/'r3_normal_output_cost_20261024.json').write_text(json.dumps(cost,indent=2,ensure_ascii=False)+'\n')
lines=['# 同卡两档输出预算成本（2026-10-24）','','三模型×固定20题×两档，各档3次预热；每档分母20题、均3张cosine证据（另加1张query），不使用5张GT条件；共120条正式请求+18条预热；均完整，无技术生成异常。题单与输入哈希见同名JSON。新运行在同一RTX 4090上，保持相同greedy提示词与原生EOS，仅将max_new_tokens从2改为256。','','|模型|cap|平均生成token|E2E P50/P95 ms|encoder均值ms|generation均值ms|采样显存峰GiB|GPU电量Wh（梯形）|','|---|---:|---:|---|---:|---:|---:|---:|']
for m,z in cost['models'].items():
 for cap,g in z['caps'].items():lines.append(f"|{m}|{cap}|{g['mean_generated_tokens']:.2f}|{g['e2e_ms']['p50']:.2f}/{g['e2e_ms']['p95']:.2f}|{g['encoder_ms']['mean']:.2f}|{g['generation_ms']['mean']:.2f}|{g['sampled_device_peak_bytes']/1073741824:.3f}|{g['energy_trapezoidal_Wh']:.6f}|")
lines+=['','## 长度判定','','|模型|256档/2档平均长度|判定|每增100 token生成耗时ms|','|---|---:|---|---|']
for m,z in cost['models'].items():
 a,b=z['caps']['2'],z['caps']['256'];v=z['generation_ms_per_extra100_tokens'];lines.append(f"|{m}|{b['mean_generated_tokens']/a['mean_generated_tokens']:.2f}倍|{'长度档位生效' if z['length_status']=='effective' else '长度未生效'}|{'不可估计' if v is None else f'{v:.2f}（仅算术读数）'}|")
lines+=['','未超过3倍长度的模型按预注册判为“长度未生效”，不能据此声称测得正常长回答的边际成本。原提示要求单个选项字母；保留原生EOS，未强制续写。结束前预算未耗尽次数及原始特殊token输出示例见JSON，支持对短答终止现象的检查。','','能耗按各正式请求的采样窗口梯形积分，另列均功率×时长，不取平均。同步边界采样包含于能耗窗口，而不包含于E2E计时；仅GPU功耗。峰值为nvidia-smi采样到的最大值；allocator峰值另列JSON。P95采用线性插值，20题仅作描述；组件含IPC/预处理等差异，不能将均值相加冒充E2E。','','这是fixed_cosine E3管线：在线编码查询+驻留CPU V点积+消费固定选图，不重排候选池，不是主实验官方S1。旧pilot为另一张卡与另一批题，仅存档，不合并或比较。','','来源：同名JSON `models.*.caps`与`models.*.length_status`；逐请求路径、SHA256、原始采样文件及题单见`inputs`及`source`。']
(OUT/'r3_normal_output_cost_20261024.md').write_text('\n'.join(lines)+'\n')
for m,z in result['models'].items():
 g=z['groups']['primary956'];print('R1',m,g['S1_correct'],g['S2_at3_correct'],g['delta'],g['ci95']['delta'],g['criterion'])
for m,z in cost['models'].items():print('R3',m,z['caps']['2']['mean_generated_tokens'],z['caps']['256']['mean_generated_tokens'],z['length_status'])
