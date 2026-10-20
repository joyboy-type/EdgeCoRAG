"""Offline diagnostics of observed outputs; no model, server or holdout evaluation."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=True)

HERE=PATHS.work_dir
PROJECT=PATHS.project_root
REPO=PATHS.repo
OUT=PATHS.output_dir or HERE/'parallel-diagnostics-20261020'
MODELS=['qwen3vl_4b','qwen3vl_8b','gemma4_e2b','gemma4_e4b','qwen35_4b']
STRATEGIES=['cosine','random','utility']
PAIRS=[('cosine','random'),('cosine','utility'),('random','utility')]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())

def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

def csvwrite(path,rows):
    with Path(path).open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def clusters(rows,include_gold=False):
    parent={r['qid']:r['qid'] for r in rows}
    if len(parent)!=len(rows):raise ValueError('Duplicate query identity')
    def find(q):
        while parent[q]!=q:parent[q]=parent[parent[q]];q=parent[q]
        return q
    seen={}
    for r in rows:
        tokens=[r['sha']]+(r['gold'] if include_gold else [])
        for token in tokens:
            if not isinstance(token,str) or not token:raise ValueError('Nonempty image identity required')
            if token in seen:parent[find(r['qid'])]=find(seen[token])
            else:seen[token]=r['qid']
    return {q:find(q) for q in parent}


def paired_counts(left,right):
    if not left or len(left)!=len(right) or any(type(x) is not bool for x in left+right):
        raise ValueError('Nonempty, aligned boolean outcomes required')
    wins=sum(b and not a for a,b in zip(left,right));losses=sum(a and not b for a,b in zip(left,right))
    return dict(n=len(left),left_correct=sum(left),right_correct=sum(right),wins=wins,losses=losses,
                unchanged=len(left)-wins-losses,delta_pp=100*(wins-losses)/len(left))


def cluster_interval(differences,groups,repetitions=10000,seed=42):
    import numpy as np
    if not differences or len(differences)!=len(groups) or any(d not in (-1,0,1) for d in differences):
        raise ValueError('Aligned paired differences and groups required')
    names=sorted(set(groups));lookup={name:i for i,name in enumerate(names)}
    sums=np.zeros(len(names));sizes=np.zeros(len(names),dtype=int)
    for d,g in zip(differences,groups):sums[lookup[g]]+=d;sizes[lookup[g]]+=1
    rng=np.random.default_rng(seed);bootstrap=[]
    for start in range(0,repetitions,250):
        draws=rng.integers(0,len(names),size=(min(250,repetitions-start),len(names)))
        bootstrap.extend((100*sums[draws].sum(axis=1)/sizes[draws].sum(axis=1)).tolist())
    low,high=np.quantile(bootstrap,[.025,.975],method='linear')
    return dict(delta_pp=100*sum(differences)/len(differences),ci_low_pp=float(low),ci_high_pp=float(high),
                clusters=len(names),largest_cluster=int(sizes.max()),resamples=repetitions,seed=seed,
                method='unstratified paired cluster percentile bootstrap; ratio of sums; question-weighted estimand',
                multiplicity='unadjusted descriptive 95% interval')


def transition(left,right,gold):
    a=bool(set(left)&set(gold));b=bool(set(right)&set(gold))
    return {(False,False):'neither_exact_hit',(False,True):'gain_exact_hit',
            (True,False):'lose_exact_hit',(True,True):'both_exact_hit'}[a,b]


def load():
    validation=read(HERE/'corrected-protocol-scoring/validation.json');pins={}
    def bound(path,expected=None):
        path=Path(path);digest=sha(path)
        if expected is not None and expected!=digest:raise ValueError('Source hash drift: '+str(path))
        pins[str(path)]=digest;return read(path)
    package=bound(HERE/'prepared/selection-frozen_test.proposed.json')
    qids=[q['qid'] for q in package['queries']]
    assert len(qids)==len(set(qids))==1033 and all(q['split']=='frozen_test' for q in package['queries'])
    answers=bound(validation['answer_sources']['frozen_test']['answers_path'],validation['answer_sources']['frozen_test']['answers_sha256'])
    answers={r['qid']:r for r in answers};assert set(answers)==set(qids)
    ret_path=PROJECT/'work/instance394-preflight/formal-retrieval-embeddinggemma2-backup/controls/retrieval-formal.approved.json'
    ret=bound(ret_path,'c766f7d381063ca2c935f3982de7ac72f18437a1f5889a8701181d11697fe740')
    gold={q:set(ret['gold'][q]) for q in qids}
    sys.path.insert(0,str(REPO/'b-side'));import score_minimal as scorer
    assert sha(REPO/'b-side/score_minimal.py')==validation['parser_sha256']
    pins[str(REPO/'b-side/score_minimal.py')]=validation['parser_sha256']
    manifest=read(HERE/'continuous-complete-backup/closeout-manifest.json')
    archive_pins={r['path']:r['sha256'] for r in manifest['files']}
    selected={};outcomes={};scenes={};raw={};parse_failures=0
    for model in MODELS:
        path=HERE/'continuous-complete-backup/frozen_test/results'/('generate-'+model)/'predictions.jsonl'
        digest=sha(path);assert digest==archive_pins[str(path.relative_to(HERE/'continuous-complete-backup'))]
        pins[str(path)]=digest;rows=[json.loads(s) for s in path.read_text().splitlines()]
        assert [(r['qid'],r['selection_strategy']) for r in rows]==[(q,s) for q in qids for s in STRATEGIES]
        for s in STRATEGIES:
            score=bound(HERE/'corrected-protocol-scoring'/('frozen_test__'+model+'__'+s+'.private.json'))
            assert score['source_predictions_sha256']==digest and score['source_answers_sha256']==validation['answer_sources']['frozen_test']['answers_sha256']
            scored={r['qid']:r for r in score['per_question']};assert set(scored)==set(qids)
            outcome={};choice={};output={}
            for r in (r for r in rows if r['selection_strategy']==s):
                q=r['qid'];parsed,status=scorer.parse_choice(r['final_output'])
                correct=(parsed==answers[q]['answer_choice'] and not r.get('final_extraction_error'))
                assert bool(correct)==scored[q]['correct'] and r['final_output']==scored[q]['raw_output']
                assert answers[q]['scenario']==scored[q]['scenario']
                outcome[q]=bool(correct);choice[q]=tuple(r['selected_ids']);output[q]=r['final_output']
                assert len(choice[q])==len(set(choice[q]))==3
                parse_failures+=status!='ok' or bool(r.get('final_extraction_error'))
                scenes[q]=answers[q]['scenario']
            if s in selected:assert selected[s]==choice
            selected[s]=choice;outcomes[model,s]=outcome;raw[model,s]=output
            assert sum(outcome.values())==score['overall']['correct']
    cluster_rows=[]
    for q in package['queries']:
        refs=['sha:'+package['corpus'][cid]['sha256'] if cid in package['corpus'] else 'unindexed:'+cid for cid in gold[q['qid']]]
        cluster_rows.append(dict(qid=q['qid'],sha='sha:'+q['query_image']['sha256'],gold=refs))
    return dict(qids=qids,gold=gold,selected=selected,outcomes=outcomes,scenes=scenes,raw=raw,
                cluster_rows=cluster_rows,pins=pins,strict_failures=parse_failures)


def robustness(data):
    qids=data['qids'];rows=[];jackknife=[];groups={}
    for name,include in [('query_image_sha',False),('query_or_shared_GT_image_component',True)]:
        mapping=clusters(data['cluster_rows'],include);sizes=Counter(mapping.values())
        groups[name]=dict(n_clusters=len(sizes),largest_cluster=max(sizes.values()),singleton_clusters=sum(n==1 for n in sizes.values()))
        for m in MODELS:
            for a,b in PAIRS:
                left=data['outcomes'][m,a];right=data['outcomes'][m,b]
                delta=[int(right[q])-int(left[q]) for q in qids]
                stat=cluster_interval(delta,[mapping[q] for q in qids])
                rows.append(dict(model=m,left=a,right=b,grouping=name,n=len(qids),**stat))
    for m in MODELS:
        for a,b in PAIRS:
            for scene in sorted(set(data['scenes'].values())):
                keep=[q for q in qids if data['scenes'][q]!=scene]
                counts=paired_counts([data['outcomes'][m,a][q] for q in keep],[data['outcomes'][m,b][q] for q in keep])
                jackknife.append(dict(model=m,left=a,right=b,omitted_scenario=scene,omitted_n=len(qids)-len(keep),**counts))
    csvwrite(OUT/'cluster_intervals.csv',rows);csvwrite(OUT/'leave_one_scenario_out.csv',jackknife)
    result=dict(status='completed_descriptive_offline',groupings=groups,comparisons=len(rows),jackknife_cells=len(jackknife),
                utility_vs_cosine=[r for r in rows if r['left']=='cosine' and r['right']=='utility'])
    write(OUT/'robustness.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))


def evidence(data):
    rows=[];same=[];qids=data['qids']
    states={q:transition(data['selected']['cosine'][q],data['selected']['utility'][q],data['gold'][q]) for q in qids}
    for m in MODELS:
        for state in ('neither_exact_hit','gain_exact_hit','lose_exact_hit','both_exact_hit'):
            ids=[q for q in qids if states[q]==state]
            counts=paired_counts([data['outcomes'][m,'cosine'][q] for q in ids],[data['outcomes'][m,'utility'][q] for q in ids])
            rows.append(dict(model=m,transition=state,**counts))
        ids=[q for q in qids if data['selected']['cosine'][q]==data['selected']['utility'][q]]
        same.append(dict(model=m,n_identical_selected_order=len(ids),
            different_final_output=sum(data['raw'][m,'cosine'][q]!=data['raw'][m,'utility'][q] for q in ids),
            different_correctness=sum(data['outcomes'][m,'cosine'][q]!=data['outcomes'][m,'utility'][q] for q in ids)))
        total=paired_counts([data['outcomes'][m,'cosine'][q] for q in qids],[data['outcomes'][m,'utility'][q] for q in qids])
        cells=[r for r in rows if r['model']==m]
        for key in ('n','left_correct','right_correct','wins','losses','unchanged'):assert sum(r[key] for r in cells)==total[key]
    counts=Counter(states.values());assert sum(counts.values())==1033
    assert counts['gain_exact_hit']-counts['lose_exact_hit']==293-281
    csvwrite(OUT/'evidence_transitions.csv',rows);csvwrite(OUT/'identical_inputs_check.csv',same)
    result=dict(status='completed_descriptive_offline',transition_question_counts=dict(counts),identical_selection=same,
                interpretation='post-treatment strata; association only; exact GT identity is not semantic relevance or sufficiency')
    write(OUT/'evidence.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','robustness','evidence']);args=ap.parse_args()
    if args.mode=='prepare':
        OUT.mkdir(exist_ok=False);data=load()
        write(OUT/'input-validation.json',dict(status='passed',source_pins=data['pins'],questions=1033,
            scored_predictions=15495,strict_failures_preserved=data['strict_failures'],
            holdout_evaluated=False,inference_performed=False,parameters_changed=False,
            analysis_script_sha256=sha(__file__)))
        print('INPUTS_BOUND_15495_PREDICTIONS_RECOUNTED');return
    validation=read(OUT/'input-validation.json')
    assert sha(__file__)==validation['analysis_script_sha256']
    data=load();assert data['pins']==validation['source_pins']
    (robustness if args.mode=='robustness' else evidence)(data)

if __name__=='__main__':main()
