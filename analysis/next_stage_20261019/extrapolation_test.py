"""Execute conditional_extrapolation_20261023_v1; no inference or answer reparsing."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess

MODELS=('qwen3vl_4b','qwen3vl_8b','gemma4_e2b','gemma4_e4b','qwen35_4b')
STRATEGIES=('cosine','random','utility')
SCENARIOS=('Angle','Biological','Deformation','Incomplete','Obstruction','Others','Partial','Scope','Temporal')
SALT='EdgeCoRAG-extrapolation-20261023:a:'
REGISTRATION_SHA='e7f754c4622356600d8e3b201d596102a3661df257cb399060788321ba3cf978'
PAPER=Path('reports/paper_20261021')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def jsonl(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def keyed(rows, key):
    result={}
    for row in rows:
        k=key(row) if callable(key) else row[key]
        if k in result:
            raise ValueError('Duplicate record: '+str(k))
        result[k]=row
    return result


def require_coverage(actual, expected, label):
    if set(actual)!=set(expected):
        raise ValueError(f'{label}: missing={sorted(set(expected)-set(actual))}; extra={sorted(set(actual)-set(expected))}')


def qid_hash(qids):
    items=sorted(qids)
    if len(items)!=len(set(items)):
        raise ValueError('Duplicate qids in list hash')
    return hashlib.sha256(''.join(q+'\n' for q in items).encode('utf-8')).hexdigest()


def split_questions(qids):
    if len(qids)!=len(set(qids)):
        raise ValueError('Duplicate split qid')
    order=sorted(qids,key=lambda q:(hashlib.sha256((SALT+q).encode('utf-8')).hexdigest(),q))
    middle=len(order)//2
    return sorted(order[:middle]), sorted(order[middle:])


def selected_hit(selected, gold):
    if (not isinstance(selected,list) or len(selected)!=3 or len(set(selected))!=3
            or not all(isinstance(x,str) for x in selected)):
        raise ValueError('Expected three distinct ordered selected_ids')
    if not isinstance(gold,list) or not gold or not all(isinstance(x,str) for x in gold):
        raise ValueError('Missing/invalid original gold mapping')
    return bool(set(selected)&set(gold))


def estimate(rows):
    hits=[r for r in rows if r['hit']]
    misses=[r for r in rows if not r['hit']]
    hc=sum(r['correct'] for r in hits)
    mc=sum(r['correct'] for r in misses)
    return dict(n_records=len(rows),n_unique_qids=len({r['qid'] for r in rows}),
                hit_n=len(hits),miss_n=len(misses),hit_correct=hc,miss_correct=mc,
                u=hc/len(hits) if hits else None,p=mc/len(misses) if misses else None)


def strategy_estimate(data):
    return estimate(data['cosine']+data['utility'])


def predict(parameters, rows):
    n=len(rows)
    h=sum(r['hit'] for r in rows)
    c=sum(r['correct'] for r in rows)
    r=h/n if n else None
    observed=c/n if n else None
    predicted=(r*parameters['u']+(1-r)*parameters['p']
               if n and parameters['u'] is not None and parameters['p'] is not None else None)
    return dict(n=n,hit_n=h,correct_n=c,r=r,observed=observed,predicted=predicted,
                residual=observed-predicted if predicted is not None else None)


def within_threshold(rmse, maximum):
    return rmse<=.05 and maximum<=.10


def error_metrics(residuals):
    if not residuals or any(x is None for x in residuals):
        return dict(status='not_estimable',rmse=None,max_abs_residual=None,passes=None)
    rmse=math.sqrt(sum(x*x for x in residuals)/len(residuals))
    maximum=max(abs(x) for x in residuals)
    return dict(status='evaluable',rmse=rmse,max_abs_residual=maximum,
                passes=within_threshold(rmse,maximum))


def load_sources(repo, work, registration_commit):
    catalog={}
    def pin(label,path):
        path=Path(path).resolve()
        catalog[label]=dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size)
        return path
    reg=pin('registration',repo/PAPER/'PREREGISTRATION.md')
    committed=subprocess.check_output(['git','show',f'{registration_commit}:{PAPER}/PREREGISTRATION.md'],cwd=repo)
    if hashlib.sha256(committed).hexdigest()!=REGISTRATION_SHA or sha(reg)!=REGISTRATION_SHA:
        raise ValueError('Registered document changed or wrong registration commit')
    pin('implementation',Path(__file__))
    pin('frozen_numbers',repo/'reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json')
    pin('fixed_rag_matrix',repo/'reports/next_stage_20261019/quality_closure_20261021/fixed_rag_matrix.csv')
    legacy=read(pin('legacy_S1',repo/PAPER/'decomposition_20261021.json'))
    public_rows=jsonl(pin('public_outcomes',repo/'logs/results_20261020/no_self_scored_outcomes.jsonl.gz'))
    public=keyed([r for r in public_rows if r['cohort']=='frozen_test'],lambda r:(r['model'],r['strategy'],r['qid']))
    package=read(pin('package',work/'prepared/selection-frozen_test.proposed.json'))
    queries=package['queries'];qids=[q['qid'] for q in queries]
    if len(qids)!=1033 or len(set(qids))!=1033 or any(q['split']!='frozen_test' for q in queries):
        raise ValueError('Frozen qid universe differs from registered 1033 questions')
    ret_path=pin('gold',work.parent/'instance394-preflight/formal-retrieval-embeddinggemma2-backup/controls/retrieval-formal.approved.json')
    if package['retrieval_package_sha256']!=sha(ret_path):
        raise ValueError('Gold/retrieval package binding differs')
    gold=read(ret_path)['gold']
    if not set(qids)<=set(gold):
        raise ValueError('Missing gold qid mappings')
    ranks=keyed(jsonl(pin('ranks',work/'prepared/no-self-frozen_test-ranks.jsonl')),'qid')
    require_coverage(ranks,qids,'top10 ranks')
    full=work/'continuous-complete-backup'
    manifest=read(pin('raw_manifest',full/'closeout-manifest.json'))
    manifest_map={r['path']:r for r in manifest['files']}
    data={};scenes={};evidence={};record_sources={}
    expected_public={(m,s,q) for m in MODELS for s in STRATEGIES for q in qids}
    require_coverage(public,expected_public,'public frozen outcomes')
    for model in MODELS:
        rel=f'frozen_test/results/generate-{model}/predictions.jsonl'
        raw_label='raw_'+model
        raw_path=pin(raw_label,full/rel)
        if sha(raw_path)!=manifest_map[rel]['sha256']:
            raise ValueError('Raw archive SHA mismatch: '+rel)
        raw=keyed(jsonl(raw_path),lambda r:(r['selection_strategy'],r['qid']))
        require_coverage(raw,{(s,q) for s in STRATEGIES for q in qids},model+' raw')
        data[model]={}
        for strategy in STRATEGIES:
            score_label=f'score_{model}_{strategy}'
            scored=read(pin(score_label,work/'corrected-protocol-scoring'/f'frozen_test__{model}__{strategy}.private.json'))
            if scored['source_predictions_sha256']!=sha(raw_path):
                raise ValueError('Scored source hash mismatch')
            per=keyed(scored['per_question'],'qid')
            require_coverage(per,qids,score_label)
            result=[]
            for qid in sorted(qids):
                row=raw[strategy,qid];score=per[qid];published=public[model,strategy,qid]
                if row.get('split')!='frozen_test' or row.get('synthetic') is not False:
                    raise ValueError('Wrong split or synthetic prediction')
                if type(score['correct']) is not bool:
                    raise ValueError('Correctness must be an archived boolean')
                if score['parse_status']!='ok' and score['correct']:
                    raise ValueError('Failure incorrectly excluded')
                for field in ('correct','scenario','parse_status'):
                    if score[field]!=published[field]:
                        raise ValueError('Public/private outcome mismatch')
                if score['raw_output']!=row['final_output']:
                    raise ValueError('Raw/scored answer binding differs')
                scenario=score['scenario']
                if scenario not in SCENARIOS or (qid in scenes and scenes[qid]!=scenario):
                    raise ValueError('Scenario identity differs')
                scenes[qid]=scenario
                selected=row['selected_ids'];pool=ranks[qid]['corpus_ids']
                if len(pool)!=10 or len(set(pool))!=10 or not set(selected)<=set(pool):
                    raise ValueError('Selected IDs not in bound top10 pool')
                hit=selected_hit(selected,gold[qid])
                if selected!=[i for i in pool if i in set(selected)]:
                    raise ValueError('Presentation order differs')
                ek=(strategy,qid)
                if ek in evidence and evidence[ek]!=selected:
                    raise ValueError('Evidence differs across models')
                evidence[ek]=selected
                result.append(dict(qid=qid,scenario=scenario,hit=hit,correct=score['correct']))
            data[model][strategy]=result
            record_sources[model,strategy]=[raw_label,score_label,'public_outcomes','gold','package','ranks','raw_manifest']
    return data,scenes,catalog,legacy,record_sources


def evaluate(parameters, validation, qid_lists, list_id):
    overall=predict(parameters,validation)
    by_scenario={}
    for scenario in SCENARIOS:
        rows=[r for r in validation if r['scenario']==scenario]
        qid_lists[list_id+'.'+scenario]=list_record([r['qid'] for r in rows])
        by_scenario[scenario]={**predict(parameters,rows),'qid_list_id':list_id+'.'+scenario}
    metrics=error_metrics([r['residual'] for r in by_scenario.values()])
    return dict(overall=overall,scenarios=by_scenario,metrics=metrics)


def list_record(qids):
    return dict(qids=sorted(qids),n_unique_qids=len(qids),sha256=qid_hash(qids),
                encoding='sorted UTF-8 qid + newline, final newline included')


def build_results(repo,work,registration_commit):
    data,scenes,sources,legacy,record_sources=load_sources(repo,work,registration_commit)
    all_qids=sorted(scenes)
    train,valid=split_questions(all_qids)
    lists={'all':list_record(all_qids),'a.estimate':list_record(train),'a.validation':list_record(valid)}
    tests={name:dict(rows=[]) for name in ('a','b')}
    for name in ('a','b'):
        for model in MODELS:
            targets=STRATEGIES if name=='a' else ('random',)
            for strategy in targets:
                full=data[model][strategy]
                if name=='a':
                    estimation=[r for r in full if r['qid'] in set(train)]
                    validation=[r for r in full if r['qid'] in set(valid)]
                    parameters=estimate(estimation)
                    estimate_strategies=[strategy];elist='a.estimate';vlist='a.validation'
                else:
                    validation=full;parameters=strategy_estimate(data[model])
                    estimate_strategies=['cosine','utility'];elist=vlist='all'
                scene_list='a.validation' if name=='a' else 'b.validation'
                measurement=evaluate(parameters,validation,lists,scene_list)
                baselines={}
                for baseline in ('full_sample_target_strategy','legacy_S1_full_sample'):
                    if baseline=='full_sample_target_strategy':
                        bp=estimate(full);bs=record_sources[model,strategy]
                        definition='all frozen target-strategy outcomes; validation contamination'
                    else:
                        old=legacy['models'][model]
                        bp={k:old[k] for k in ('u','p','hit_n','miss_n','hit_correct','miss_correct')}
                        bp.update(n_records=old['n'],n_unique_qids=old['n']);bs=['legacy_S1']
                        definition='legacy S1 full-sample parameters; different evidence condition'
                    bresult=evaluate(bp,validation,lists,scene_list)
                    baselines[baseline]=dict(estimate=bp,estimate_qid_list_id='all',source_ids=bs,
                                            definition=definition,**bresult)
                metrics=measurement['metrics']
                comparisons={k:dict(
                    rmse_difference=(metrics['rmse']-b['metrics']['rmse'] if metrics['rmse'] is not None and b['metrics']['rmse'] is not None else None),
                    max_abs_residual_difference=(metrics['max_abs_residual']-b['metrics']['max_abs_residual'] if metrics['max_abs_residual'] is not None and b['metrics']['max_abs_residual'] is not None else None))
                    for k,b in baselines.items()}
                estimate_sources=sorted({i for s in estimate_strategies for i in record_sources[model,s]})
                tests[name]['rows'].append(dict(model=model,validation_strategy=strategy,
                    estimation_strategies=estimate_strategies,estimate=parameters,**measurement,
                    provenance=dict(estimate_qid_list_id=elist,validation_qid_list_id=vlist,
                        estimate_source_ids=estimate_sources,validation_source_ids=record_sources[model,strategy],
                        gold_source_id='gold',raw_selection_fields=['qid','selection_strategy','selected_ids'],
                        correctness_fields=['per_question[].qid','per_question[].correct','per_question[].scenario']),
                    baselines=baselines,primary_minus_baseline=comparisons))
        results=[r['metrics']['passes'] for r in tests[name]['rows']]
        tests[name]['status']='not_estimable' if any(x is None for x in results) else ('pass' if all(results) else 'fail')
        tests[name]['failed_rows']=[dict(model=r['model'],strategy=r['validation_strategy'],
            rmse=r['metrics']['rmse'],max_abs_residual=r['metrics']['max_abs_residual'])
            for r in tests[name]['rows'] if r['metrics']['passes'] is False]
    tests['a']['definition']='hashed question holdout; separate parameters per model/strategy'
    tests['b']['definition']='cosine+utility pooled estimation; random-only validation on same questions'
    tests['b']['non_validation_strategies']={'cosine':'estimation_only','utility':'estimation_only'}
    failed=[name for name in ('a','b') if tests[name]['status']=='fail']
    if failed:
        conclusion='条件比例不可外推，只能作区间描述'
    elif all(tests[n]['status']=='pass' for n in ('a','b')):
        conclusion='条件比例在同一模型内可跨题、跨策略外推'
    else:
        conclusion='证据不完整，未能完成预注册外推检验'
    return dict(schema='conditional_extrapolation/20261023/v1',protocol_id='conditional_extrapolation_20261023_v1',
        created_at_utc=datetime.now(timezone.utc).isoformat(),registration_commit=registration_commit,
        registration_sha256=REGISTRATION_SHA,implementation_sha256=sha(__file__),python=platform.python_version(),
        thresholds=dict(rmse=.05,max_abs_residual=.10,units='probability',inclusive=True,
                        aggregation='equal-weight original validation scenarios; observed minus predicted'),
        source_catalog=sources,qid_lists=lists,tests=tests,conclusion=conclusion,failed_dimensions=failed,
        scope='retrospective, previously observed benchmark; descriptive operational tolerance check, not causal/independent confirmation',
        no_new_confidence_intervals=True,no_inference=True,no_reparsing=True,
        protected_sources_unchanged=all(sha(sources[k]['path'])==sources[k]['sha256'] for k in ('frozen_numbers','fixed_rag_matrix','legacy_S1','registration')))


def fmt(value):
    return 'NA' if value is None else f'{value:.6f}'


def render_report(result):
    lines=['# 条件表现模型外推检验（2026-10-23）','',
        '**固定结论：'+result['conclusion']+'。**','',
        '本结论仅适用于本次已观察MRAG题单、模型、策略和预设容差。不是因果解释，也不是新的未暴露验证。',
        '“只能作区间描述”沿用预注册结论标签；本次没有新增置信区间，旧零成功样本的退化区间不因此变得可靠。','',
        f"预注册提交：`{result['registration_commit']}`；SHA256：`{result['registration_sha256']}`。",
        f"实现SHA256：`{result['implementation_sha256']}`。",'',
        '误差使用概率单位；有符号残差=观测−预测；RMSE为九场景等权，最大残差为绝对值最大。',
        '判定：RMSE≤0.05且最大绝对残差≤0.10；未四舍五入即判定。','',
        '数值主文件：[extrapolation_test_20261023.json](extrapolation_test_20261023.json)。下列每行按tests/a或tests/b的rows索引对应；',
        '其provenance给出估计/验证题号清单ID、原预测文件、评分文件及gold来源，清单内容和SHA256位于qid_lists。','',
        '## 划分和来源','',
        '| 清单 | 题数 | 题号清单SHA256 |','|---|---:|---|']
    for key in ('all','a.estimate','a.validation'):
        row=result['qid_lists'][key];lines.append(f"| {key} | {row['n_unique_qids']} | `{row['sha256']}` |")
    lines+=['','(a) 同一哈希划分用于全部模型与策略；(b) 同题留出random，cosine与utility仅作估计，不报告它们的策略留出验证成绩。',
        'P3为dev选定策略；618/615/623分别是Qwen3-VL-4B三策略归档计数，711属于Oracle；Oracle不参与拟合或验证。','']
    for test in ('a','b'):
        group=result['tests'][test]
        lines += [f"## ({test}) {'按题留出' if test=='a' else '按策略留出'}：{group['status']}",'',
            '| 模型 | 验证策略 | 估计u | 估计p | 验证r | 观测Acc | 预测Acc | 观测−预测 | 场景RMSE | 最大绝对残差 | 判定 |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
        for row in group['rows']:
            e=row['estimate'];v=row['overall'];m=row['metrics']
            vals=[e['u'],e['p'],v['r'],v['observed'],v['predicted'],v['residual'],m['rmse'],m['max_abs_residual']]
            decision='可外推' if m['passes'] is True else ('不可外推' if m['passes'] is False else '缺口/不可估计')
            lines.append('| '+row['model']+' | '+row['validation_strategy']+' | '+' | '.join(fmt(x) for x in vals)+' | '+decision+' |')
        lines+=['','### 与全样本基线比较','',
            'Target-full包含验证结局，属于回顾性污染对照；Legacy-S1使用上一版全样本S1参数。二者均不影响主判定。',
            '| 模型 | 策略 | 主检验RMSE / Max | Target-full RMSE / Max | Legacy-S1 RMSE / Max |',
            '|---|---|---|---|---|']
        for row in group['rows']:
            methods=[row['metrics'],row['baselines']['full_sample_target_strategy']['metrics'],row['baselines']['legacy_S1_full_sample']['metrics']]
            lines.append('| '+row['model']+' | '+row['validation_strategy']+' | '+' | '.join(fmt(x['rmse'])+' / '+fmt(x['max_abs_residual']) for x in methods)+' |')
        lines+=['','### 逐场景预测与观测','']
        for i,row in enumerate(group['rows']):
            est=row['estimate'];prov=row['provenance']
            lines += [f"#### {row['model']} / {row['validation_strategy']}（JSON: tests.{test}.rows[{i}]）",'',
                f"估计：{est['n_records']}条、{est['n_unique_qids']}题；命中{est['hit_correct']}/{est['hit_n']}；未命中{est['miss_correct']}/{est['miss_n']}。",
                f"题号清单：估计 `{prov['estimate_qid_list_id']}`；验证 `{prov['validation_qid_list_id']}`。",'',
                '| 场景 | 验证题数 | 命中数 | 答对数 | r | 观测 | 主预测 | 主残差 | Target-full预测 | Target-full残差 | Legacy-S1预测 | Legacy-S1残差 |',
                '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
            for s,v in row['scenarios'].items():
                b=row['baselines']['full_sample_target_strategy']['scenarios'][s]
                old=row['baselines']['legacy_S1_full_sample']['scenarios'][s]
                vals=[v['r'],v['observed'],v['predicted'],v['residual'],b['predicted'],b['residual'],old['predicted'],old['residual']]
                lines.append(f"| {s} | {v['n']} | {v['hit_n']} | {v['correct_n']} | "+' | '.join(fmt(x) for x in vals)+' |')
    lines+=['','## 结论与边界','',result['conclusion']+'。',
        '失效维度：'+(', '.join('题' if x=='a' else '策略' for x in result['failed_dimensions']) or '无已观察超阈值维度')+'。',
        '所有通过、未通过和小样本场景均保留；不改划分、不重选策略、不调整阈值。跨题与跨策略不能合并解释。',
        '跨题划分未隔离图像关联分量；跨策略验证使用相同题目。既有结果暴露与场景样本量限制独立泛化结论。',
        'MMDocRAG固定候选未加入本次拟合；本结果不构成跨数据集验证。','',
        '## 源文件（JSON source_catalog）','']
    for key,source in result['source_catalog'].items():
        lines.append(f"- `{key}`：`{source['path']}`；SHA256 `{source['sha256']}`。")
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--registration-commit',required=True)
    args=parser.parse_args()
    repo=args.repo.resolve();out=repo/PAPER
    targets=[out/'extrapolation_test_20261023.json',out/'EXTRAPOLATION_TEST.md']
    if any(p.exists() for p in targets):
        parser.error('Preserve prior outputs; no overwrite or result-dependent rerun')
    try:
        result=build_results(repo,args.work_dir.resolve(),args.registration_commit)
    except (ValueError,KeyError,FileNotFoundError) as error:
        parser.exit(2,'Data gap/protocol mismatch: '+str(error)+'\n')
    if not result['protected_sources_unchanged']:
        parser.exit(2,'Protected source changed during analysis\n')
    report=render_report(result)
    with targets[0].open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    with targets[1].open('x',encoding='utf-8') as f:
        f.write(report)
    print(json.dumps(dict(conclusion=result['conclusion'],failed_dimensions=result['failed_dimensions'],
        tests={k:dict(status=v['status'],failed_rows=v['failed_rows']) for k,v in result['tests'].items()},
        outputs=[str(p) for p in targets]),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
