"""Compose the phase manuscript and evidence ledger from already saved tables.

No model calls, networking, bootstrap reruns, or changes to experiment inputs.
The companion HTML is packaged separately by the canonical portable reader.
"""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/next_stage_20261017'
BASE = ROOT / 'reports/v1.10.1'
MODELS = ['qwen3vl_4b', 'qwen3vl_8b', 'gemma4_e2b', 'gemma4_e4b', 'qwen35_4b']
LABEL = dict(zip(MODELS, ['Qwen3-VL 4B', 'Qwen3-VL 8B', 'Gemma 4 E2B', 'Gemma 4 E4B', 'Qwen3.5 4B']))
SOURCE_COMMIT = 'c249fadb757fa64c08a677b77d7489ff7e05fa9a'


def read_csv(name):
    with (ROOT / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def table(rows, columns):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(label for _, label in columns) + ' |',
                      '| ' + ' | '.join('---' for _ in columns) + ' |'] +
                     ['| ' + ' | '.join(cell(row[key]) for key, _ in columns) + ' |' for row in rows])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    quality_path = 'reports/v1.10.1/quality.csv'
    cross_path = 'reports/v1.10.1/cross_model_paired.csv'
    cost_path = 'reports/v1.10.1/quality_cost.csv'
    transition_path = 'reports/v1.10.1/answer_transitions.csv'
    s3_path = 'reports/v1.10.1/s3_subsets.csv'
    gt_path = 'reports/v1.10.1/diagnostics/gt_decomposition.csv'
    errors_path = 'reports/v1.10.1/diagnostics/condition_errors.csv'
    format_path = 'reports/v1.10.1/diagnostics/format_decomposition.csv'
    registry_path = 'b-side/configs/model_registry.json'
    receipt_path = 'provenance/v1.10.1/execution_receipt.json'
    protocol_path = 'b-side/configs/protocol_main_v1.json'
    audit_path = 'reports/v1.10.1/diagnostics/validation_receipt.json'
    quality, cross, cost = [read_csv(p) for p in [quality_path, cross_path, cost_path]]
    transitions, s3, gt, errors, formats = [read_csv(p) for p in [transition_path, s3_path, gt_path, errors_path, format_path]]
    registry = json.loads((ROOT / registry_path).read_text())
    receipt = json.loads((ROOT / receipt_path).read_text())
    protocol = json.loads((ROOT / protocol_path).read_text())
    audit = json.loads((ROOT / audit_path).read_text())
    assert (receipt['tasks'], receipt['question_runs'], receipt['format_failures_including_performance']) == (161, 21927, 132)
    assert sum(int(r['n']) for r in quality) == 17807
    assert sum(int(r['n']) for r in quality if r['condition'] != 'S3-pure') == 17745
    assert sum(int(r['n']) for r in quality if r['condition'] == 'S3-pure') == 62
    assert all(int(r['generation_errors']) == int(r['missing']) == 0 for r in quality)
    assert audit['sql_reconciled'] and audit['main_quality_format_failures'] == 99
    assert protocol['max_new_tokens'] == 64 and protocol['seed'] == 42 and not protocol['do_sample']
    q = {(r['split'], r['model_key'], r['condition']): r for r in quality}
    for r in quality:
        assert abs(float(r['accuracy']) - int(r['correct']) / int(r['n'])) < 1e-12
    for r in cross:
        a, b = [q[r['split'], model, r['condition']] for model in [r['model'], r['baseline']]]
        assert abs(float(r['delta_pp']) - 100 * (int(a['correct']) - int(b['correct'])) / int(r['n'])) < 1e-10
        assert r['source_clustering'] == r['multiplicity_correction'] == r['noninferiority_margin_preregistered'] == 'False'
    perf = {(r['model_key'], r['condition']): r for r in read_csv('reports/v1.10.1/performance.csv')}
    for r in cost:
        assert abs(float(r['accuracy']) - float(q['frozen_test', r['model_key'], r['condition']]['accuracy'])) < 1e-12
        # Two CSV writers round the final binary-float digit differently (max 1.14e-13 ms).
        assert abs(float(r['offline_p95_ms']) - float(perf[r['model_key'], r['condition']]['end_to_end_p95_ms'])) < 1e-9
        assert r['full_system_cost'] == r['quality_and_cost_workloads_identical'] == 'False'
        if r['condition'] == 'S1':
            assert int(r['performance_observations']) == 100 and int(r['performance_unique_questions']) == 20

    # Queries select and reshape saved facts. They do not re-estimate confidence intervals.
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    input_tables = {'quality': (quality_path, quality), 'comparisons': (cross_path, cross), 'cost': (cost_path, cost),
                    'transitions': (transition_path, transitions), 's3': (s3_path, s3), 'gt': (gt_path, gt),
                    'errors': (errors_path, errors), 'format_groups': (format_path, formats)}
    for name, (_, rows) in input_tables.items():
        fields = list(rows[0])
        conn.execute(f'CREATE TABLE "{name}" (' + ','.join('"' + f + '" TEXT' for f in fields) + ')')
        conn.executemany(f'INSERT INTO "{name}" VALUES (' + ','.join('?' for _ in fields) + ')',
                         [tuple(row[f] for f in fields) for row in rows])
    model_rows = [{'model_key': k, 'model': LABEL[k], 'model_id': registry['models'][k]['model_id'],
                   'revision': registry['models'][k]['revision']} for k in MODELS]
    conn.execute('CREATE TABLE registry(model_key TEXT,model TEXT,model_id TEXT,revision TEXT)')
    conn.executemany('INSERT INTO registry VALUES (:model_key,:model,:model_id,:revision)', model_rows)
    order = 'CASE model_key ' + ' '.join(f"WHEN '{m}' THEN {i}" for i, m in enumerate(MODELS)) + ' END'
    queries = {
        'frozen_long': f"SELECT model_key,model,condition,CAST(n AS INTEGER) AS n,CAST(correct AS INTEGER) AS correct,CAST(accuracy AS REAL) AS accuracy FROM quality WHERE split='frozen_test' AND condition IN ('S0','S1','S2') ORDER BY {order},condition;",
        'frozen_wide': "SELECT model_key,MAX(model) AS model,MAX(CAST(n AS INTEGER)) AS n," + ','.join(f"MAX(CASE WHEN condition='{c}' THEN printf('%d/1033 (%.2f%%)',CAST(correct AS INTEGER),100*CAST(accuracy AS REAL)) END) AS {c}" for c in ['S0','S1','S2']) + f" FROM quality WHERE split='frozen_test' AND condition IN ('S0','S1','S2') GROUP BY model_key ORDER BY {order};",
        'holdout_wide': "SELECT model_key,MAX(model) AS model,MAX(CAST(n AS INTEGER)) AS n," + ','.join(f"MAX(CASE WHEN condition='{c}' THEN printf('%d/150 (%.2f%%)',CAST(correct AS INTEGER),100*CAST(accuracy AS REAL)) END) AS {c}" for c in ['S0','S1','S2']) + f" FROM quality WHERE split='internal_holdout' AND condition IN ('S0','S1','S2') GROUP BY model_key ORDER BY {order};",
        'cross': "SELECT model,baseline,CAST(n AS INTEGER) AS n,printf('%.2f',CAST(delta_pp AS REAL)) AS delta,printf('[%.2f, %.2f]',CAST(ci_low_pp AS REAL),CAST(ci_high_pp AS REAL)) AS interval FROM comparisons WHERE split='frozen_test' AND condition='S1';",
        'cost': f"SELECT model_key,model,CAST(quality_n AS INTEGER) AS quality_n,CAST(accuracy AS REAL) AS accuracy,CAST(performance_observations AS INTEGER) AS observations,CAST(offline_p50_ms AS REAL) AS p50_ms,CAST(offline_p95_ms AS REAL) AS p95_ms,CAST(performance_peak_reserved_gib AS REAL) AS reserved_gib FROM cost WHERE condition='S1' ORDER BY {order};",
        'registry': f'SELECT * FROM registry ORDER BY {order};',
        'transitions': f"SELECT model_key,CAST(n AS INTEGER) AS n,CAST(wrong_to_right AS INTEGER) AS improved,CAST(right_to_wrong AS INTEGER) AS regressed,CAST(wrong_to_right AS INTEGER)-CAST(right_to_wrong AS INTEGER) AS net FROM transitions WHERE split='frozen_test' AND left='S0' AND right='S1' ORDER BY {order};",
        'gt': f"SELECT model_key,gt_hash_hit,CAST(n AS INTEGER) AS n,CAST(net_correct_change AS INTEGER) AS net FROM gt WHERE split='frozen_test' ORDER BY {order},gt_hash_hit;",
        'errors': f"SELECT model_key,CAST(n AS INTEGER) AS n,CAST(correct AS INTEGER) AS correct,CAST(valid_choice_wrong AS INTEGER) AS valid_wrong,CAST(format_failures AS INTEGER) AS formats FROM errors WHERE split='frozen_test' AND condition='S2' ORDER BY {order};",
        's3': "SELECT model_key,CAST(parent_n AS INTEGER) AS parent_n,CAST(paired_n AS INTEGER) AS n,CAST(coverage AS REAL) AS coverage,CAST(s1_subset_accuracy AS REAL) AS s1,CAST(s3_subset_accuracy AS REAL) AS s3 FROM s3 WHERE split='frozen_test';",
        'format_groups': "SELECT format_group,CAST(n AS INTEGER) AS n,CAST(net_correct_change AS INTEGER) AS net FROM format_groups WHERE split='frozen_test' AND model_key='qwen35_4b' AND left='S1' AND right='S2';"
    }
    data = {name: [dict(row) for row in conn.execute(sql)] for name, sql in queries.items()}
    assert len(data['frozen_long']) == 15 and len(data['frozen_wide']) == len(data['holdout_wide']) == 5
    assert sum(r['net'] for r in data['gt'] if r['model_key'] == 'qwen3vl_4b') == -26
    assert {r['gt_hash_hit']: r['net'] for r in data['gt'] if r['model_key'] == 'qwen3vl_4b'} == {'False': -30, 'True': 4}
    e = {r['model_key']: r for r in data['errors']}
    assert e['gemma4_e2b']['valid_wrong'] == 592 and e['gemma4_e4b']['valid_wrong'] == 540
    assert e['gemma4_e2b']['formats'] == e['gemma4_e4b']['formats'] == 0
    assert e['qwen35_4b']['correct'] + e['qwen35_4b']['formats'] == 656
    assert sum(r['net'] for r in data['format_groups']) == 38 and sum(r['n'] for r in data['format_groups']) == 1033

    claims = []
    def claim(text, cohort, denominator, sources, filters, kind='descriptive', limit='固定记录上的描述，非因果或普遍替代结论。'):
        cid = f'C{len(claims)+1:03d}'
        claims.append(dict(claim_id=cid, claim=text, cohort=cohort, denominator=denominator,
                           source_file=sources, filter_or_row=filters, claim_type=kind,
                           limitation=limit, review_status='checked_against_saved_sources'))
        return cid
    execution_id = claim('161任务；119正式任务；21927次问答；132格式失败；25份阶段回执完整；0重试；483次warmup不评分。', '全部批准执行', '161 tasks;21927 question-runs;25 receipts', receipt_path, 'tasks,formal_tasks,question_runs,format_failures_including_performance,worker_phase_receipts,retries,warmups_excluded', limit='运行数含阶段与性能重复观测，不是独立问题数；技术通过不等于准确率假设成立。')
    scope_id = claim('正式quality17807条＝S0/S1/S2主条件17745条＋S3 62条；性能1550条单列。', '正式执行', '17807 quality;1550 performance', quality_path+';'+receipt_path, 'sum(n) by condition; performance_question_runs', limit='内部留出与冻结分开，不将性能及warmup并入质量。')
    quality_ids = {}
    for split, n in [('frozen_test',1033),('internal_holdout',150)]:
        for m in MODELS:
            text = LABEL[m] + '：' + '；'.join(f"{c}={q[split,m,c]['correct']}/{n} ({100*float(q[split,m,c]['accuracy']):.2f}%)" for c in ['S0','S1','S2']) + '。'
            quality_ids[split,m] = claim(text, split+' / '+m, str(n)+' questions per condition', quality_path, json.dumps({'split':split,'model_key':m,'condition':['S0','S1','S2']},ensure_ascii=False))
    for r in cross:
        if r['split'] != 'frozen_test' or r['condition'] != 'S1': continue
        claim(f"{LABEL[r['model']]}−{LABEL[r['baseline']]}：{float(r['delta_pp']):.2f} pp；描述性95%区间[{float(r['ci_low_pp']):.2f}, {float(r['ci_high_pp']):.2f}]。", 'frozen_test / S1 / paired models', '1033 paired questions', cross_path, json.dumps({k:r[k] for k in ['split','condition','model','baseline']}), kind='descriptive_interval', limit='沿用场景分层题级配对bootstrap2000次seed42；未重估区间，无来源聚类、多重校正或预注册非劣效界值。')
    for r in data['cost']:
        claim(f"{LABEL[r['model_key']]} S1：预处理＋生成P50={r['p50_ms']:.1f} ms，P95={r['p95_ms']:.1f} ms，性能阶段reserved峰值={r['reserved_gib']:.2f} GiB。", 'performance / S1 / '+r['model_key'], '20 smoke questions x5 repeats=100 observations', cost_path+';reports/v1.10.1/performance.csv', json.dumps({'condition':'S1','model_key':r['model_key']}), limit='不含检索、加载与warmup；reserved不是整卡峰值；质量用另一批1033题，不是同负载端到端前沿。')
    for r in data['transitions']:
        claim(f"{LABEL[r['model_key']]} S0→S1：错转对{r['improved']}题，对转错{r['regressed']}题，净变化{r['net']:+d}题。", 'frozen_test / paired S0,S1', '1033 questions', transition_path, json.dumps({'split':'frozen_test','model_key':r['model_key'],'left':'S0','right':'S1'}), limit='回答转移不等于已审定检索伤害机制。')
    claim('Qwen3-VL 4B的S1−S0净−26题：GT哈希未命中组−30题，命中组+4题；两组分别517与516题。', 'frozen_test / qwen3vl_4b', '1033=517+516', gt_path, 'model_key=qwen3vl_4b;split=frozen_test;gt_hash_hit=False/True', limit='JPEG95字节哈希重叠不等于语义支持、R@k或因果效应。')
    claim('Gemma E2B/E4B的S2分别592/540题有效选项答错，格式失败均0。', 'frozen_test / S2 / Gemma', '1033 questions per model', errors_path, 'split=frozen_test;condition=S2;model_key=gemma4_e2b/gemma4_e4b', limit='未看正式原图，不能把有效选项答错全归为纯推理不足。')
    claim('Qwen3.5 S2原正确601题、格式失败55题；全部格式失败假定正确时656/1033=63.50%，仍比Qwen3-VL 4B的717题少61题。', 'frozen_test / S2', '1033 questions', errors_path, 'model_key=qwen35_4b/qwen3vl_4b;split=frozen_test;condition=S2', kind='fixed_record_extreme_bound', limit='仅假设修复格式错误且其余回答不变；非恢复分数、非预算调整预测，不改变原始评分。')
    claim('Qwen3.5 S1→S2格式互斥组贡献：均有效+56题、仅S2失败−25题、仅S1失败+7题、均失败0题，合计+38题。', 'frozen_test / qwen35_4b / S1,S2', '1033 paired questions', format_path, 'split=frozen_test;model_key=qwen35_4b;left=S1;right=S2', limit='按观测格式状态事后分组，仅可加描述。')
    claim('正式主条件99次格式失败中98次记录预算耗尽。', 'internal_holdout+frozen_test / S0,S1,S2', '99 format failures /17745 outputs', audit_path, 'main_quality_format_failures;format_failures_at_token_limit', limit='同时发生不证明增加预算必然改善；全部132格式失败属于更大执行总体。')
    for r in data['s3']:
        claim(f"{LABEL[r['model_key']]}冻结S3子集{r['n']}/{r['parent_n']} ({100*r['coverage']:.2f}%)，同题S1={100*r['s1']:.2f}%，S3={100*r['s3']:.2f}%。", 'frozen_test / S1,S3 paired subset', '29 paired questions of1033', s3_path, 'split=frozen_test;model_key='+r['model_key'], limit='AI图像辅助、label-aware选定子集；非人工盲审、非完整基准代表性；内部留出仅2题，不解释其区间。')
    claim('五模型固定revision；统一BF16、无量化、无offload、greedy、seed42、64token、SDPA、TF32关闭。', 'runtime-v1.10.1', '5 models', registry_path+';'+protocol_path+';'+receipt_path, 'models[*].revision and execution protocol', kind='protocol_fact', limit='原生视觉tokenizer与图像预处理不同，不声称等视觉token预算；冻结registry旧状态不代表当前未实跑。')
    claim('精确图像连通审计最大组1338/1353题；切分采用逐题回退，跨split相关性未隔离。', 'MRAG-Bench original test', '1353 questions', 'a-side/data/entity_connectivity.json', 'exact_only_connectivity.largest_group;questions', kind='inherited_audit', limit='不是官方文档来源分组；split_manifest另有1331旧值，口径/版本差异未统一，不合并估计。')

    selected = read_csv('reports/v1.10.1/diagnostics/selected_cases.csv')
    with gzip.open(ROOT/'reports/v1.10.1/diagnostics/case_ledger.csv.gz', 'rt', encoding='utf-8-sig') as f:
        ledger = {(r['model_key'],r['qid']):r for r in csv.DictReader(f) if r['split']=='frozen_test'}
    case_rows=[]
    for r in selected:
        assert ledger[r['model_key'],r['qid']]['pattern'] == r['pattern']
        assert r['visual_review_completed'].lower() == r['mechanism_adjudicated'].lower() == 'false'
        case_rows.append(dict(case_id=r['case_id'],model_key=r['model_key'],qid=r['qid'],record_pattern=r['pattern'],record_checked='true',image_available='unknown_pending_A01',visual_review_completed='false',mechanism_adjudicated='false',dependency='A-01 existing-image availability; later image review separately arranged'))
    assert len(case_rows)==20 and len({r['case_id'] for r in case_rows})==20
    claim('20条事后案例卡已对照逐题台账核验记录模式，0条完成视觉机制审定。', 'deterministic post hoc selected case cards', '20 case cards;not representative sampling', 'reports/v1.10.1/diagnostics/selected_cases.csv;reports/v1.10.1/diagnostics/case_ledger.csv.gz', 'all selected case_ids matched by model_key,qid;visual_review_completed=false', kind='audit_fact', limit='已暴露答案与输出，不是盲审；图像可获得性待A-01回传。')
    split_paths = ['a-side/splits/'+n+'.v2.txt' for n in ['smoke_20','dev','internal_holdout','frozen_test']]
    split_counts = [len([s for s in (ROOT/p).read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]) for p in split_paths]
    assert split_counts == [20,150,150,1033] and sum(split_counts) == 1353
    claim('固定题单划分为20/150/150/1033，共1353题；内部留出与冻结集同源。', 'MRAG-Bench split v2', '1353 questions', ';'.join(split_paths), 'count nonempty noncomment lines per fixed split file', kind='protocol_fact', limit='不是来源隔离或独立外部验证；后续审计暴露另行披露。')
    write_csv(OUT/'B_claim_evidence.csv', claims)
    write_csv(OUT/'B_case_review_status.csv',case_rows)

    for row in data['cross']:
        row['model'],row['baseline']=LABEL[row['model']],LABEL[row['baseline']]
    for row in data['transitions']:row['model']=LABEL[row['model_key']]
    cost_display=[{**r,'p50':f"{r['p50_ms']:.1f}",'p95':f"{r['p95_ms']:.1f}",'reserved':f"{r['reserved_gib']:.2f}"} for r in data['cost']]
    conditions=[{'condition':'S0','input':'查询图＋问题','evidence':'0','use':'无外部证据基线'},
                {'condition':'S1','input':'查询图＋发布候选原顺序top3','evidence':'3（含Incomplete）','use':'共享候选基线，非自主重检索'},
                {'condition':'S2','input':'查询图＋实际GT','evidence':'常规5／Incomplete1','use':'Oracle诊断，非部署性能'},
                {'condition':'S3','input':'查询图＋D1干扰','evidence':'3','use':'仅Gemma批准子集'}]
    sections=[]
    def section(key,text,tab=None):sections.append((key,text,tab))
    title='EdgeCoRAG阶段论文：共享视觉证据下的五模型能力边界'
    section('summary', '## 摘要：相同候选证据仍未填平Gemma与Qwen的质量差距\n\n我们在MRAG-Bench的固定题单和证据下比较五个原生视觉模型，冻结测试每条件1033题，严格评分。S0只给查询图，S1加入发布候选top3，S2提供真实GT证据。Gemma E2B/E4B的S1准确率为35.43%/41.34%，Qwen3-VL 4B/8B为57.60%/56.15%。即使在GT条件下，Gemma仍有明显错误。部分生成时延较低，但不能由此认定在同等完整系统预算下实现替代。\n\n全部批准的161任务、21927次运行完成，132次格式失败全部计错；技术完成不构成研究假设成立的证据。记录诊断将Qwen3-VL 4B的检索条件净退步分解为GT哈希未命中组−30题与命中组+4题；未进行正式原图的视觉机制审定。本阶段支持共享证据下的描述性能力边界与负结果，尚未建立非劣效、普遍替代或独立外部验证结论。')
    section('question', '## 1 研究问题与相关工作定位\n\n研究问题是：同一视觉证据能在多大程度上缩小模型的质量差距；观测收益或退步与证据哈希重叠、输出格式及生成成本有什么关系？共享证据比较避免只让小模型拿GT、却让大模型无证据作答的不对等对照。\n\n[MRAG-Bench](https://arxiv.org/abs/2410.08182)面向视觉知识增强问答；[Utility-MRAG](https://aclanthology.org/2026.acl-long.1620/)以证据效用而非单纯相似性进行选择。本轮没有复现自主效用选择器，S1是官方发布候选，不是EmbeddingGemma 2自主检索结果。[MMDocRAG](https://arxiv.org/abs/2505.16470)与[VisDoM](https://aclanthology.org/2025.naacl-long.310/)用于规划跨文档、跨域验证，目前均无本项目新推理结果。文献作者的增益不作为本项目成绩；这些方法定位以已核对摘要和项目说明为限，未宣称复现全部原论文表格。')
    section('scope', f'## 2 数据、分母与评价单位\n\nMRAG-Bench原始test共1353题，本项目固定切分为smoke20、development150、internal_holdout150、frozen_test1033。内部留出与冻结集同源，不能称外部验证。正式quality为17807条，其中五模型S0/S1/S2共17745条、Gemma S3共62条；性能1550条及483次warmup分别记录。5915个主条件问题×模型配对单元不是5915道独立问题。\n\n准确率定义为严格正确题数除以固定题单分母，格式失败和缺失均不得剔除。此次主质量记录没有技术错误或缺失。主要表格以冻结集为主，内部留出单独报告；性能重复观测不进入质量分母。百分点差值以pp表示，时延以ms、显存以GiB表示。执行总体和分母对应{execution_id}、{scope_id}，全部主要数字在论断证据表中逐项定位。')
    section('design', '## 3 实验设计与预算控制\n\n所有模型在同一RTX4090 24GB上使用BF16、无量化、无offload、SDPA、thinking关闭、greedy解码、seed42、max_new_tokens64、TF32关闭。按冒烟、开发、内部留出、冻结测试、性能顺序执行，正常格式失败计错且不自动重试。v1.10.1修复的是格式失败与技术故障的门禁区分并补足依赖，不改变提示词或科学设置。\n\n共享原始图片字节和顺序；Qwen的像素上限与Gemma的soft-token限制、原生视觉预处理不同，因此不声称实际视觉token完全等价。S1与S2图片数不同，特别是Incomplete的3与1，不能将两者差值完全归为证据质量。S3的语义状态来自AI辅助且label-aware审阅，只代表批准的小型补充子集。', ('conditions',conditions,[('condition','条件'),('input','模型输入'),('evidence','证据图数'),('use','解释范围')]))
    section('models', '### 3.1 模型身份与执行来源\n\n模型全名和权重revision如下。Gemma的E2B/E4B有效参数标签不等于全部权重参数量，跨模型成本以实测表为准。冻结注册表中的旧GPU未验证状态是历史字段；当前执行状态以独立实跑回执为准。', ('registry',data['registry'],[('model','模型'),('model_id','模型ID'),('revision','权重revision')]))
    section('statistics', '### 3.2 配对比较与不确定性\n\n同模型条件比较与同条件跨模型比较均按相同split、qid和版本配对。沿用已保存的场景分层题级配对bootstrap：2000次重采样、seed42；本次写作未重估区间。未进行来源聚类、多重比较校正或预注册非劣效检验，故将区间标为描述性95%区间，不以包含0解释等价。\n\n来源审计显示图片跨题复用并形成大连通组，逐题切分未隔离相关性。后续分组方案不得按模型表现拆组。检索、格式和案例分解是结果后的探索性描述，不能转写成因果效应。')
    section('main', '## 4 共享候选条件下，两款Gemma仍保留明显质量差距\n\n下表和图按固定1033题比较S0/S1/S2，格式失败始终留在分母。S1下Gemma E2B/E4B为35.43%/41.34%，均低于Qwen3-VL 4B的57.60%和8B的56.15%；Qwen3.5为54.50%。这批共享证据没有建立普遍替代结论。\n\nS2是GT诊断：Qwen3-VL 4B为69.41%，Gemma E2B/E4B为42.69%/47.73%。五模型的冻结S2均高于S1，但这不是自主检索系统成绩。GT集合、证据数量和问题难度同时限制机制解释。', ('frozen_wide',data['frozen_wide'],[('model','模型'),('S0','S0：正确/n（%）'),('S1','S1：正确/n（%）'),('S2','S2：正确/n（%）')]))
    section('gap', '### 4.1 同S1证据的配对差距\n\n差值为Gemma减Qwen的准确率百分点。四个观察差距介于−22.17与−14.81pp，描述性区间整体为负。来源相关性与多重比较限制仍在，不能据此声称对所有数据域或预算都成立，也没有找到经过预注册验证的可替代子群。', ('cross',data['cross'],[('model','模型'),('baseline','对照'),('delta','差值pp'),('interval','描述性95%区间pp')]))
    section('holdout', '### 4.2 内部留出单列，不与冻结集混合\n\n每模型每条件分母150。Qwen3-VL 4B/8B在S1均为59.33%，Gemma E2B/E4B为36.00%/38.00%，Qwen3.5为50.00%。这些结果来自同一基准的内部切分，只作单独检查，不能充当外部验证或通过合并分母提高置信。', ('holdout_wide',data['holdout_wide'],[('model','模型'),('S0','S0：正确/n（%）'),('S1','S1：正确/n（%）'),('S2','S2：正确/n（%）')]))
    section('cost', '## 5 部分生成时延更低，不代表同预算系统替代\n\nS1性能每模型使用20道smoke题各重复5次，共100观测，先warmup。下表P50/P95覆盖预处理和生成，不含编码检索、索引驻留、模型加载或切换。文件中的end_to_end字段只在该runner边界内使用，正文不将其称作完整检索端到端。\n\nGemma E2B/E4B的P95为413.5/501.6ms，Qwen3-VL 4B/8B为694.8/986.4ms；但E2B的S1性能阶段reserved峰值9.77GiB仍高于Qwen3-VL 4B的8.75GiB。不能仅凭参数标签或较短时延推断更省显存。质量来自1033道冻结题，成本来自另一批smoke工作负载，二者不是同负载完整系统前沿。', ('cost',cost_display,[('model','模型'),('p50','预处理＋生成P50 ms'),('p95','P95 ms'),('reserved','性能阶段reserved峰值GiB')]))
    section('diagnosis', '## 6 记录诊断定位了现象，尚未审定具体机制\n\nS0→S1的错转对与对转错在同一题单上计数，净变化分别为−26、−3、−9、+30、+10题。Qwen3-VL 4B的−26题来自GT哈希未命中组−30题、命中组+4题；冻结分组为517与516题。哈希未命中不排除语义有用证据，命中也不保证GT充分、位置或干扰内容一致，不能直接贴检索失败或不会利用标签。\n\nGT条件下Gemma E2B/E4B仍错592/540题，全部是有效选项答错。Qwen3.5在S2原正确601题、55次格式失败；假定这55次全部正确而其余回答不变，上限为656/1033=63.50%，仍比Qwen3-VL 4B的717题少61题。这个固定记录极端上限不是重评分或增加预算的效果预测。\n\nQwen3.5由S1到S2净多答对38题，格式互斥组贡献为均有效+56、仅S2失败−25、仅S1失败+7、均失败0。主条件99次格式失败中98次记录预算耗尽；该同时发生关系不证明增大预算必然改善。20条按固定SHA规则事后选出的案例卡已核对记录模式，0条完成视觉机制审定，不代表总体，也不是盲审。', ('transitions',data['transitions'],[('model','模型'),('improved','错转对'),('regressed','对转错'),('net','净正确变化')]))
    section('s3', '## 7 S3只支持小型选定子集上的描述\n\n冻结S3为29/1033题（2.81%）：同题S1→S3，Gemma E2B从51.72%降到31.03%，E4B均为34.48%。内部留出仅2/150题，不解释其退化的区间或方向；开发S3为5题。主条件全量结果始终保留，不能用子集分数代替总体。\n\nS3接受AI图像辅助、label-aware审阅，预览分辨率有限，服务模型revision不可得；不是全基准代表性或纯干扰普遍语义独立性的证明。本轮新增20例记录诊断与此前S3审核是不同工作，不能将前者标为已看图。')
    section('limits', '## 8 局限与结论边界\n\n第一，数据同源且跨split图片相关性未隔离，冻结集有已披露审计暴露；当前分层题级区间未处理来源依赖，也未校正多重比较。第二，S1发布候选的产生过程未完全公开；本轮没有独立检索指标、效用选择器或最佳固定RAG的实跑对照。第三，各模型原生视觉预处理不等价，S1/S2图片数不同，S2属于Oracle。\n\n第四，质量和成本使用不同固定负载，缺少完整检索、切换、整卡峰值、整机能耗与真实边缘设备评测。第五，格式失败严格计错，未尝试事后放宽解析或预算补救；有效选项错误也没有完成视觉语义机制审查。第六，最终processor-rendered chat-template字符串未保存，不能事后伪造；输入上下文、顺序与哈希已保存，但不等同于全部运行内存状态。\n\n最后，文献逐表数值与部分许可仍有缺口，MMDocRAG/VisDoM尚无本项目实测结果。精确实跑源码与绑定保留，旧依赖pin存在两阶段重建限制；本阶段未声称图像全链路重新部署已验证。这些限制允许分享阶段发现，但不支持课题结题或跨域普遍结论。')
    section('next', '## 9 下一步与待回答问题\n\n当前最有依据的成果是共享视觉证据下的能力边界，而非检索后普遍超越更大模型。下一步先保留原分数并完善论文论证，等待A回传案例图片可获得性、独立语料与来源分组依据；再预先冻结第二数据集和完整系统的独立协议、预算与验收条件。现阶段无需新增GPU推理。\n\n仍需回答：GT未命中的图片是否语义有用？GT命中但答错是否与读取、证据充分性、数量或干扰有关？在真正同硬件、同工作负载和完整系统成本下，是否存在可验证的替代范围？这些问题不能仅凭本轮记录给出机制或因果答案。')
    markdown=['# '+title]
    for _,text,tab in sections:
        markdown.append(text)
        if tab:markdown.append(table(tab[1],tab[2]))
    markdown.append('## 配套证据\n\n主要定量论断见[B_claim_evidence.csv](B_claim_evidence.csv)，逐条案例状态见[B_case_review_status.csv](B_case_review_status.csv)。模型主结果、配对区间、成本分别来自[quality.csv](../v1.10.1/quality.csv)、[cross_model_paired.csv](../v1.10.1/cross_model_paired.csv)、[quality_cost.csv](../v1.10.1/quality_cost.csv)。本稿是基于已保存结果的阶段论文初稿，不是新实验或已发表论文。')
    (OUT/'B_phase_report.md').write_text('\n\n'.join(markdown)+'\n')

    now=datetime.now(timezone.utc).isoformat()
    sources=[{'id':'claims','label':'阶段论文论断与原始证据定位','path':'reports/next_stage_20261017/B_claim_evidence.csv','query':{'engine':'Python standard library','language':'python','description':'Saved-source claim register; includes original file and row filters, denominator, claim type and limitations. No new inference or interval estimation.','executed_at':now}}]
    query_sources={'frozen_long':(quality_path,['quality']),'frozen_wide':(quality_path,['quality']),'holdout_wide':(quality_path,['quality']), 'cross':(cross_path,['comparisons']),'cost':(cost_path,['cost']),'registry':(registry_path,['registry']),'transitions':(transition_path,['transitions'])}
    for name,(path,tables) in query_sources.items():
        sources.append({'id':name,'label':name,'path':path,'query':{'engine':'SQLite in memory','language':'sql','sql':queries[name],'tables_used':tables,'executed_at':now,'description':'Actually executed selection/reshape of existing saved tables; numeric casts and displayed rounding only. Original intervals are reused, not re-estimated.'}})
    blocks=[{'id':'title','type':'markdown','body':'# '+title}]
    tables=[]
    for key,text,tab in sections:
        blocks.append({'id':key,'type':'markdown','body':text,'sourceId':'claims'})
        if key=='main':blocks.append({'id':'quality_chart_block','type':'chart','chartId':'quality_chart'})
        if key=='cost':blocks.append({'id':'latency_chart_block','type':'chart','chartId':'latency_chart'})
        if tab:
            name,rows,cols=tab
            if name=='conditions':
                # This categorical protocol table is prose in the portable version, not a fake SQL source.
                blocks.append({'id':'condition_definition','type':'markdown','body':table(rows,cols),'sourceId':'claims'})
            else:
                ds='cost_display' if name=='cost' else name
                tables.append({'id':name+'_table','title':{'registry':'模型与权重版本','frozen_wide':'冻结集严格准确率','holdout_wide':'内部留出严格准确率','cross':'同S1模型差距','cost':'S1预处理与生成成本','transitions':'S0到S1逐题变化'}[name], 'dataset':ds,'sourceId':name,'columns':[{'field':f,'label':l} for f,l in cols], 'density':'spacious'})
                blocks.append({'id':name+'_table_block','type':'table','tableId':name+'_table'})
    charts=[{'id':'quality_chart','title':'五模型三条件严格准确率','description':'冻结集每模型每条件1033题；格式失败计错；S2为GT诊断。','showDescription':True,'type':'horizontalBar','intent':'comparison','question':'相同证据条件下模型差距是否保留？','rationale':'Grouped horizontal bars compare three conditions within each model; zero baseline, no causal inference.','dataset':'frozen_long','sourceId':'frozen_long','valueFormat':'percent','encodings':{'x':{'field':'model'},'y':{'field':'accuracy'},'color':{'field':'condition'}},'options':{'grouping':'grouped'},'legend':{'show':True,'position':'bottom'},'palette':{'kind':'categorical'}},
            {'id':'latency_chart','title':'S1预处理与生成P95','description':'单张4090；每模型20道smoke题×5次；单位ms；不含检索或加载。','showDescription':True,'type':'horizontalBar','intent':'comparison','question':'在已测生成边界内哪些模型时延较低？','rationale':'One bar per model for an absolute cost; paired quality interpretation remains in adjacent narrative and table.','dataset':'cost','sourceId':'cost','encodings':{'x':{'field':'model'},'y':{'field':'p95_ms'}},'legend':{'show':False},'palette':{'kind':'categorical'}}]
    datasets={k:data[k] for k in ['frozen_long','frozen_wide','holdout_wide','cross','cost','registry','transitions']}
    datasets['cost_display']=cost_display
    artifact={'surface':'report','manifest':{'version':1,'surface':'report','title':title,'description':'基于runtime-v1.10.1已保存实验的阶段论文与证据；没有新增推理。','generatedAt':now,'blocks':blocks,'charts':charts,'tables':tables,'sources':sources},'snapshot':{'version':1,'generatedAt':now,'status':'ready','datasets':datasets}}
    (OUT/'B_phase_artifact.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
    (OUT/'B_phase_queries.json').write_text(json.dumps(queries,ensure_ascii=False,indent=2)+'\n')
    inputs=set([p for p,_ in input_tables.values()]+split_paths+[registry_path,receipt_path,protocol_path,audit_path,'reports/v1.10.1/performance.csv','reports/v1.10.1/diagnostics/selected_cases.csv','reports/v1.10.1/diagnostics/case_ledger.csv.gz','a-side/data/entity_connectivity.json','analysis/v1.10.1/build_phase_report.py'])
    notes={'delivery_mode':'portable_html_with_markdown_manuscript_source','audience':'technical','source_commit':SOURCE_COMMIT,'structure_mapping':{'summary':'摘要','definitions':'数据与分母、实验设计','visual_findings':'共享证据结果、成本','methodology':'模型身份、配对统计','limitations':'局限','next_steps_and_questions':'最后一节'},'chart_contracts':[{'id':'quality_chart','family':'grouped horizontal bars','grain':'15 model x condition rows','zero_baseline':True,'denominator':1033,'claim':'shared-condition quality gap remains'},{'id':'latency_chart','family':'horizontal bars','grain':'5 model rows','zero_baseline':True,'unit':'ms','claim':'generation-boundary cost only'}],'repeated_chart_family_reason':'Two absolute category comparisons with different units; separate rows and labels avoid suggesting a temporal trend or unsupported correlation.','source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(inputs)},'no_new_inference':True,'no_interval_reestimation':True,'public_source_web_checks_handled_separately_in_B03':True}
    (OUT/'B_phase_source_notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2)+'\n')
    validation={'status':'PASS_saved_source_checks','quality_rows':len(quality),'formal_main_outputs':17745,'formal_s3_outputs':62,'quality_denominators_and_accuracy_checked':True,'cross_model_point_differences_recomputed_from_correct_counts':True,'cost_p95_reconciled_with_performance':True,'sql_queries_executed':len(queries),'claim_rows':len(claims),'selected_case_cards_checked':len(case_rows),'visual_reviews_completed':0,'new_model_inference':False,'intervals_reestimated':False,'html_qa':'pending separate canonical packaging','readiness':'share with scientific and rendering caveats; phase manuscript, not full-project closeout'}
    (OUT/'B_phase_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(validation,ensure_ascii=False))


if __name__ == '__main__':
    main()
