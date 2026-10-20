"""Q3-Q6 derived artifacts from frozen archives. No inference or reparsing.

Use --work-dir for private archived inputs and a NEW --out directory. Public
outputs contain aggregate counts, numeric comparisons, source digests and limits.
"""
import argparse
from collections import Counter
import csv
from itertools import combinations
import json
from pathlib import Path
import sys

from quality_data import MODELS,STRATEGIES,SPLITS,STATUSES,load,sha,read,write_json,write_csv
from quality_stats import choose_fixed,paired_family,mechanism

REPO=Path(__file__).resolve().parents[2]


def concept_rows():
    scenes=('Angle','Partial','Temporal','Others','Obstruction','Scope','Deformation','Biological','Incomplete')
    return [dict(official_scenario=scene,concept='跨图' if scene in ('Temporal','Incomplete') else '其他',
        reason=('时序/不完整视野可能需要跨图证据，场景名不足以确认，暂定映射' if scene in ('Temporal','Incomplete') else '官方场景描述视角/可见性/生物等因素，不能据此认定OCR或图表'),
        needs_manual_review=True,scope='概念映射，未经独立标注审定') for scene in scenes]


def build(repo,work,out):
    repo=Path(repo);out=Path(out)
    if out.exists():raise ValueError('Preserve existing derived artifacts; choose a new output directory')
    contract=read(repo/'analysis/next_stage_20261019/stats_contract.json')
    if contract['bootstrap']['resamples']!=10000 or contract['bootstrap']['seed']!=42:
        raise ValueError('Frozen resampling contract differs')
    data=load(repo,work);out.mkdir(parents=True)
    dev=data['splits']['dev'];selected={}
    selection=[]
    for model in MODELS:
        vectors={strategy:[dev['outcomes'][model,strategy][q] for q in dev['qids']] for strategy in STRATEGIES}
        selected[model]=choose_fixed(vectors)
        selection.append(dict(model=model,selection_split='dev',n=150,selected=selected[model],
            cosine_correct=sum(vectors['cosine']),random_correct=sum(vectors['random']),utility_correct=sum(vectors['utility']),
            tie_rule='cosine,random,utility',frozen_test_used=False))
    write_csv(out/'dev_fixed_selection.csv',selection)
    matrix=[];vectors={};status_rows=[]
    for split,n in SPLITS.items():
        part=data['splits'][split];qids=part['qids']
        for model in MODELS:
            for path in ('P1','P2','P3','P4'):
                strategy={'P1':'cosine','P2':'utility','P3':selected[model]}.get(path)
                choices={q:strategy if path!='P4' else next((s for s in STRATEGIES if part['outcomes'][model,s][q]),'cosine') for q in qids}
                values=[part['outcomes'][model,choices[q]][q] for q in qids];vectors[split,model,path]=values
                statuses=Counter(part['scored'][model,choices[q]][q]['parse_status'] for q in qids)
                if sum(statuses.values())!=n:raise ValueError('Failure denominator lost')
                matrix.append(dict(model=model,path=path,split=split,selected_strategy=strategy or 'per_question_post_hoc',
                    correct=sum(values),n=n,percent=100*sum(values)/n,post_hoc_oracle=path=='P4',
                    **{status:statuses[status] for status in STATUSES}))
    write_csv(out/'fixed_rag_matrix.csv',matrix)
    comparisons=[];part=data['splits']['frozen_test'];qids=part['qids']
    group_ids=[data['groups'][q]['query_or_GT_image_component'] for q in qids]
    for model in MODELS:
        for left,right in combinations(('P1','P2','P3','P4'),2):
            comparisons.append(dict(model=model,left_path=left,right_path=right,split='frozen_test',
                post_hoc_oracle=right=='P4',left=vectors['frozen_test',model,left],right=vectors['frozen_test',model,right]))
    paired=paired_family(comparisons,group_ids)
    write_csv(out/'paired_differences.csv',paired)
    write_csv(out/'oracle_paired_differences.csv',[r for r in paired if r['post_hoc_oracle']])
    source_family=[]
    for model in MODELS:
        for left,right in combinations(STRATEGIES,2):
            source_family.append(dict(comparison='within_model_strategy',left_model=model,right_model=model,
                left_strategy=left,right_strategy=right,split='frozen_test',
                left=[part['outcomes'][model,left][q] for q in qids],right=[part['outcomes'][model,right][q] for q in qids]))
    for left,right in contract['model_comparisons']:
        source_family.append(dict(comparison='cross_model_dev_fixed_P3',left_model=left,right_model=right,
            left_strategy=selected[left],right_strategy=selected[right],split='frozen_test',
            left=vectors['frozen_test',left,'P3'],right=vectors['frozen_test',right,'P3']))
    source_intervals=paired_family(source_family,group_ids)
    write_csv(out/'source_cluster_ci.csv',source_intervals)
    mechanisms=[];concepts=[];mapping=concept_rows();lookup={r['official_scenario']:r['concept'] for r in mapping}
    write_csv(out/'concept_mapping.csv',mapping)
    for split,n in SPLITS.items():
        part=data['splits'][split]
        for model in MODELS:
            for strategy in STRATEGIES:
                classification=Counter();pool_hits=0;selected_hits=0
                for q in part['qids']:
                    gold=set(data['gold'][q]);pool_hit=bool(gold&set(part['ranks'][q]['corpus_ids']))
                    selected_hit=bool(gold&set(part['selected'][model,strategy][q]));pool_hits+=pool_hit;selected_hits+=selected_hit
                    label=mechanism(data['s0'][split,model,q],part['outcomes'][model,strategy][q],pool_hit)
                    classification[label]+=1
                if sum(classification.values())!=n:raise ValueError('Mechanism partition denominator drift')
                for label in contract['mechanism']['priority']:
                    mechanisms.append(dict(model=model,strategy=strategy,category=label,split=split,count=classification[label],
                        n=n,percent=100*classification[label]/n,pool_exact_gt_hit_questions=pool_hits,
                        selected_exact_gt_hit_questions=selected_hits,scope='operational exact identity/outcome proxy; no causal/semantic inference'))
                for version in ('tentative','conservative_all_other'):
                    for concept in ('OCR','图表','跨图','其他'):
                        ids=[q for q in part['qids'] if (lookup[part['scenes'][q]] if version=='tentative' else '其他')==concept]
                        correct=sum(part['outcomes'][model,strategy][q] for q in ids)
                        errors=Counter(part['scored'][model,strategy][q]['parse_status'] for q in ids)
                        concepts.append(dict(model=model,strategy=strategy,split=split,mapping=version,concept=concept,
                            n=len(ids),correct=correct,percent=None if not ids else 100*correct/len(ids),
                            strict_failures=sum(value for status,value in errors.items() if status!='ok'),
                            scope='概念映射，未经独立标注审定；空类别不估计准确率'))
    write_csv(out/'mechanism_breakdown.csv',mechanisms);write_csv(out/'concept_sensitivity.csv',concepts)
    # Q5: preserve all inherited entries; unverified values remain unavailable.
    with (repo/'source_manifest.csv').open(encoding='utf-8-sig',newline='') as f:papers=list(csv.DictReader(f))
    with (repo/'reports/next_stage_20261017/B_paper_table_evidence.csv').open(encoding='utf-8-sig',newline='') as f:cells=list(csv.DictReader(f))
    key_names={'utility_mrag':'Utility-Oriented Visual Evidence Selection','mrag_bench':'MRAG-Bench','mmdocrag':'MMDocRAG','visdom':'VisDoM'}
    methods={'utility_mrag':'fixed-pool surrogate utility evidence selection','mrag_bench':'vision-centric multiple-choice benchmark; no-RAG/retrieved/GT protocols',
        'mmdocrag':'document multimodal QA; citation metrics and five-dimension judge','visdom':'visual/text multi-document retrieval and generation',
        'ragrouter':'text RAG routing; visual adaptation unexecuted','vqpp':'visual query preprocessing robustness; unexecuted'}
    paper_rows=[]
    for paper in papers:
        evidence=[c for c in cells if c['paper']==key_names.get(paper['key'])]
        values='; '.join(f"{c['evidence_id']} {c['model']} {c['setting']} {c['metric']}={c['reported_value']} {c['unit']}" for c in evidence)
        paper_rows.append(dict(paper=paper['paper_title'],method=methods.get(paper['key'],'not independently verified'),
            reported_values=values or '未核验；不填数字',measurement_scope='; '.join(sorted({c['denominator_status'] for c in evidence})) or '原文数值与分母尚未独立核验',
            license=paper['license'],license_source=paper['repo_url']+' ; '+paper['paper_url'],
            reproduction_status=paper.get('our_reproduction','')+'; author experiments not fully reproduced',
            differences='our frozen no-self top3 strict_choice_v1, dev150 selection/frozen1033 evaluation; incomparable pools/parsers/metrics; no cross-paper ranking',
            source=paper['paper_url'],pdf=paper['pdf_url'],source_sha256=paper['pdf_sha256'],
            verified_numeric_cells=len(evidence),numeric_verification='archived selected original-table audit' if evidence else 'blocked: original numeric/denominator audit absent'))
    write_csv(out/'papers_matrix.csv',paper_rows)
    write_csv(out/'papers_numeric_evidence.csv',cells)
    # Q6: no empirical judge runtime exists. Do not invent a numeric interval.
    registry=read(repo/'b-side/configs/model_registry.json');judge=registry['models']['qwen3vl_8b']
    mmdoc=next(r for r in papers if r['key']=='mmdocrag')
    proposal=dict(status='draft_unexecuted',semantic_accuracy=None,semantic_accuracy_citable=False,
        judge=dict(model_id=judge['model_id'],revision=judge['revision'],dtype=judge['dtype'],
            weights_required=['pinned configuration/tokenizer/processor files','all safetensors shards and index'],
            cache_verified_for_judge=False,download_performed=False,self_judge_bias='judge also appears among generators; human/external adjudication needed'),
        scope=dict(existing_evaluation_queries=200,generators=5,possible_ratings=1000,repeats=1),
        protocol=dict(input='private question, reference, fixed evidence and unchanged generated answer; hide generator identity',
            output='five bounded ordinal ratings plus evidence-grounded reasons and uncertainty; no binary semantic accuracy until independently calibrated',
            dimensions=['correctness','completeness','faithfulness','relevance','coherence'],dimension_scale=[0,5],
            temperature=0,max_new_tokens=512,failures='record missing/parse/generation errors separately; retain fixed 200 denominator per generator; no repair/retry',
            comparison='document/source components for MMDocRAG require separate validated grouping; MRAG564 groups cannot be transplanted'),
        cost=dict(gpu_minutes_interval=None,cny_interval=None,reason='No measured judge throughput or approved live quote; generation times from a different task cannot bound judge runtime.',
            formulas=dict(gpu_minutes='(1000 * measured_seconds_per_rating + measured_setup_seconds)/60',
                          compute_cny='gpu_minutes/60 * approved_cny_per_hour'),
            fee_not_authorized=True,Q7_65min_3CNY_does_not_authorize_judge=True),
        license_issues=[mmdoc['license'],'README research/noncommercial versus HF Apache-2.0 conflict remains unresolved',
            'code license does not confer image/PDF redistribution rights; no raw data/public responses','model license and derivative judge distribution require separate review'],
        sources=[mmdoc['repo_url'],mmdoc['paper_url']],limitations='未执行、不得引用语义准确率；无可辩护的数值费用区间，需获批后先做独立吞吐标定')
    write_json(out/'mmdocrag_judge_feasibility.json',proposal)
    source_codes=('quality_closure.py','quality_data.py','quality_stats.py','stats_contract.json')
    pins=dict(data['pins'])
    for name in source_codes:pins['code_'+name]=dict(sha256=sha(repo/'analysis/next_stage_20261019'/name),bytes=(repo/'analysis/next_stage_20261019'/name).stat().st_size)
    for name in ('source_manifest.csv','reports/next_stage_20261017/B_paper_table_evidence.csv','b-side/configs/model_registry.json'):
        pins['reference_'+name]=dict(sha256=sha(repo/name),bytes=(repo/name).stat().st_size)
    receipt=dict(status='completed_new_offline_derivations_only',source_pins=pins,denominators=SPLITS,
        archived_predictions=18045,failure_counts=dict(Counter(row['parse_status'] for part in data['splits'].values() for scores in part['scored'].values() for row in scores.values())),
        components=564,resamples=10000,seed=42,dev_selection=selected,fixed_matrix_rows=len(matrix),path_pairs=len(paired),
        source_cluster_pairs=len(source_intervals),mechanism_rows=len(mechanisms),concept_sensitivity_rows=len(concepts),
        paper_rows=len(paper_rows),verified_papers=sum(bool(row['verified_numeric_cells']) for row in paper_rows),verified_paper_numeric_cells=len(cells),
        Q5_status='partial: RAGRouter/VQQP original numeric and license audits incomplete',Q6_status='feasibility draft only; numeric budget unidentifiable',
        gpu_started=False,server_connected=False,old_scores_reparsed=False,old_artifacts_modified=False)
    report='# 固定RAG与四路径（描述性）\n\nP3只用dev150选择，平局cosine→random→utility；冻结1033题仅评估。固定20/150/1033分母，79条归档格式失败保留计错，未重解析。\n\n'
    report+='| 模型 | dev所选策略 | frozen P1 | frozen P2 | frozen P3 |\n|---|---|---:|---:|---:|\n'
    for model in MODELS:
        rows={r['path']:r for r in matrix if r['split']=='frozen_test' and r['model']==model}
        report+=f"| {model} | {selected[model]} | {rows['P1']['correct']}/1033 | {rows['P2']['correct']}/1033 | {rows['P3']['correct']}/1033 |\n"
    report+='\nOracle（P4）逐题取已归档三策略正确性的最大值，仅为post hoc上界，不可部署，见矩阵post_hoc_oracle列与单列Oracle配对表。\n\n区间为564图像关联分量、10000次、seed42的描述性basic bootstrap；Holm联合接受域反演置信矩形的投影数值等同Bonferroni。Holm step-down校正p值另列，不能将它们混为未经定义的更窄区间。\n\n'
    for row in paired:
        if row['left_path']=='P1' and row['right_path']=='P3':
            report+=f"- {row['model']} P3−P1：{row['delta_pp']:.3f}pp；未校正[{row['ci_low_pp']:.3f},{row['ci_high_pp']:.3f}]；Holm联合区间[{row['holm_ci_low_pp']:.3f},{row['holm_ci_high_pp']:.3f}]。{row['interpretation']}。\n"
    report+='\n最佳固定仅限本次三策略，不是全体可选RAG系统的全局最优。已观察数据，不是新盲测。\n'
    (out/'C_fixed_rag_and_paths.md').write_text(report)
    (out/'D_mechanisms_and_concepts.md').write_text('# 机制与概念分层\n\n四类按stats_contract优先级形成固定分母的互斥分区；检索伤害是S0正确→策略错误的关联代理，不是因果。精确GT图像身份命中不等于语义支持。20项配对区间沿用既有564图像关联分量，不冒称文档来源。\n\n概念映射，未经独立标注审定。Temporal/Incomplete暂归跨图；其余暂归其他，同时给全部归其他的敏感性表。没有由场景名编造OCR或图表标签，两类为空，分母0时不报准确率。\n')
    (out/'E_papers.md').write_text('# 逐论文对照\n\n六篇逐行列方法、数值口径、许可、复现状态、差异及原始链接；四篇36个原表单元来自既有带哈希的全文核验。RAGRouter/VQQP原文数字和适配许可仍未独立核验，不填估算数值。各论文候选池、解析、F1/judge/准确率分母不同，不并列成排名；作者报告不当成本项目复现。R05保持部分完成。\n')
    (out/'F_judge_feasibility.md').write_text('# MMDocRAG judge可行性\n\n未执行、不得引用语义准确率。仅提出固定200题×5生成器的盲化评级草案和所需已注册Qwen3-VL8B权重身份，未下载、未验机。尚无judge吞吐实测，不能用生成耗时假定judge分钟数；GPU分钟与金额区间明确为null，只给代入实测后的公式。许可冲突、模型许可与自评偏差未解决；R06不能因草案关闭。\n')
    write_json(out/'analysis_receipt.json',receipt)
    files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()}
    write_json(out/'manifest.json',dict(files=files,contract_sha256=sha(repo/'analysis/next_stage_20261019/stats_contract.json')))
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO);parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();receipt=build(args.repo,args.work_dir,args.out)
    print(json.dumps({key:value for key,value in receipt.items() if key!='source_pins'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
