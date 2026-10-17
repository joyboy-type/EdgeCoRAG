"""Offline analysis of the published, compressed run records. No model or network calls."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import json
from pathlib import Path
import random
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'b-side'))
from score_minimal import parse_choice

MODELS = ['qwen3vl_4b','qwen3vl_8b','gemma4_e2b','gemma4_e4b','qwen35_4b']
LABELS = dict(zip(MODELS,['Qwen3-VL 4B','Qwen3-VL 8B','Gemma4 E2B','Gemma4 E4B','Qwen3.5 4B']))

def quantile(values, p):
    xs=sorted(values);i=(len(xs)-1)*p;lo=int(i);hi=min(lo+1,len(xs)-1)
    return xs[lo]+(xs[hi]-xs[lo])*(i-lo)

def paired(a, b, repetitions=2000, seed=42):
    """Explicit cross-model descriptive comparison; never changes runtime's same-model guard."""
    assert a and set(a)==set(b)
    strata=defaultdict(list)
    for q in a:
        assert a[q]['scenario']==b[q]['scenario']
        assert a[q]['condition']==b[q]['condition'] and a[q]['split']==b[q]['split']
        assert a[q]['protocol_version']==b[q]['protocol_version']
        assert a[q]['evidence_version']==b[q]['evidence_version']
        strata[a[q]['scenario']].append(q)
    delta={q:int(a[q]['correct'])-int(b[q]['correct']) for q in a}
    rng=random.Random(seed)
    draws=[sum(delta[rng.choice(qs)] for qs in strata.values() for _ in qs)/len(a) for _ in range(repetitions)]
    return {'n':len(a),'delta_pp':100*sum(delta.values())/len(a),
            'ci_low_pp':100*quantile(draws,.025),'ci_high_pp':100*quantile(draws,.975),
            'improvements':sum(v==1 for v in delta.values()),'regressions':sum(v==-1 for v in delta.values()),
            'resamples':repetitions,'seed':seed,'method':'paired_scenario_stratified_bootstrap',
            'source_clustering':False,'multiplicity_correction':False,'noninferiority_margin_preregistered':False}

def csv_write(path, rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def compute(log):
    with gzip.open(log,'rt',encoding='utf-8') as f: rows=[json.loads(s) for s in f]
    assert len(rows)==len({tuple(p['row_key']) for p in rows})==21927
    assert sum(p['parse_status']!='ok' for p in rows)==132
    assert {p['task_id'] for p in rows} and len({p['task_id'] for p in rows})==161
    for p in rows:
        assert (p['parsed_choice'],p['parse_status'])==parse_choice(p['final_output'])
        assert p['correct']==(p['parse_status']=='ok' and p['parsed_choice']==p['answer'])
        assert p['attempt']==1 and not p['generation_error'] and not p['final_extraction_error']
    quality=defaultdict(dict);performance=defaultdict(list)
    for p in rows:
        if p['stage']=='quality':
            k=(p['split'],p['model_key'],p['condition']);assert p['qid'] not in quality[k];quality[k][p['qid']]=p
        elif p['stage']=='performance':performance[p['model_key'],p['condition']].append(p)
    qtable=[]
    for (split,model,cond),values in quality.items():
        ps=list(values.values());n=len(ps);correct=sum(p['correct'] for p in ps)
        assert n==({'internal_holdout':150,'frozen_test':1033}[split] if cond!='S3-pure' else {'internal_holdout':2,'frozen_test':29}[split])
        qtable.append({'model_key':model,'split':split,'condition':cond,'n':n,'correct':correct,'accuracy':correct/n,
                       'format_failures':sum(p['parse_status']!='ok' for p in ps)})
    cross=[]
    for split in ['internal_holdout','frozen_test']:
        for cond in ['S0','S1','S2']:
            for small in ['gemma4_e2b','gemma4_e4b']:
                for baseline in ['qwen3vl_4b','qwen3vl_8b']:
                    a,b=quality[split,small,cond],quality[split,baseline,cond]
                    cross.append({'split':split,'condition':cond,'model':small,'baseline':baseline,
                                  'model_revision':next(iter(a.values()))['model_revision'],
                                  'baseline_revision':next(iter(b.values()))['model_revision'],**paired(a,b)})
    transitions=[];examples=[]
    for split in ['internal_holdout','frozen_test']:
        for model in MODELS:
            for left,right in [('S0','S1'),('S1','S2'),('S0','S2')]:
                a,b=quality[split,model,left],quality[split,model,right];assert set(a)==set(b)
                c=Counter((a[q]['correct'],b[q]['correct']) for q in a)
                transitions.append({'split':split,'model_key':model,'left':left,'right':right,'n':len(a),
                    'wrong_to_right':c[False,True],'right_to_wrong':c[True,False],
                    'right_to_right':c[True,True],'wrong_to_wrong':c[False,False],
                    'right_to_wrong_rate_full_denominator':c[True,False]/len(a),
                    'right_to_wrong_rate_among_left_correct':c[True,False]/sum(p['correct'] for p in a.values())})
                # Deterministic first qids, not selected to support a preferred conclusion.
                for transition in [(True,False),(False,True)]:
                    ids=sorted(q for q in a if (a[q]['correct'],b[q]['correct'])==transition)[:3]
                    for q in ids:examples.append({'split':split,'model_key':model,'left':left,'right':right,'qid':q,
                        'observed_transition':'right_to_wrong' if transition[0] else 'wrong_to_right',
                        'gold':a[q]['answer'],'left_raw':a[q]['final_output'],'right_raw':b[q]['final_output'],
                        'mechanism_adjudicated':False,'selection_rule':'first 3 lexicographic qids per transition group'})
    costs=[]
    for model in MODELS:
        for cond in ['S0','S1','S2']:
            ps=performance[model,cond];assert len(ps)==100 and len({p['qid'] for p in ps})==20
            q=quality['frozen_test',model,cond]
            costs.append({'model_key':model,'model':LABELS[model],'condition':cond,'quality_split':'frozen_test','quality_n':1033,
                'accuracy':sum(p['correct'] for p in q.values())/1033,'performance_split':'smoke_20','performance_observations':100,
                'performance_unique_questions':20,'offline_p50_ms':quantile([p['timing']['end_to_end_seconds']*1000 for p in ps],.5),
                'offline_p95_ms':quantile([p['timing']['end_to_end_seconds']*1000 for p in ps],.95),
                'performance_peak_reserved_gib':max(p['cuda_memory']['process_allocator_peak_reserved'] for p in ps)/2**30,
                'full_system_cost':False,'quality_and_cost_workloads_identical':False})
    for row in costs:
        group=[x for x in costs if x['condition']==row['condition']]
        for metric in ['offline_p95_ms','performance_peak_reserved_gib']:
            row['descriptive_nondominated_'+metric]=not any(
                other[metric]<=row[metric] and other['accuracy']>=row['accuracy'] and
                (other[metric]<row[metric] or other['accuracy']>row['accuracy']) for other in group)
    with gzip.open(log.with_name('B_input_contexts.jsonl.gz'),'rt',encoding='utf-8') as f:
        contexts={r['context_key']:r['input'] for r in map(json.loads,f)}
    overlap={};overlap_detail=[]
    for split in ['internal_holdout','frozen_test']:
        for qid,p in quality[split,MODELS[0],'S1'].items():
            a=contexts[p['context_key']]['evidence']
            b=contexts[quality[split,MODELS[0],'S2'][qid]['context_key']]['evidence']
            ah={x['sha256'] for x in a};bh={x['sha256'] for x in b};assert len(a)==3 and bh
            hits=bool(ah&bh);overlap[split,qid]=hits
            overlap_detail.append({'split':split,'qid':qid,'scenario':p['scenario'],'top3_any_gt_exact_hash_hit':hits,
                                   'gt_count':len(b),'matched_gt_hashes':len(ah&bh),'all_gt_hashes_covered':bh<=ah,
                                   'basis':'SHA256 of supplied JPEG95 bytes; not semantic support or independent retrieval recall'})
    overlap_strata=[]
    for split in ['internal_holdout','frozen_test']:
        for model in MODELS:
            for cond in ['S0','S1','S2']:
                for hit in [False,True]:
                    subset=[p for qid,p in quality[split,model,cond].items() if overlap[split,qid]==hit]
                    overlap_strata.append({'split':split,'model_key':model,'condition':cond,'top3_any_gt_exact_hash_hit':hit,
                        'n':len(subset),'correct':sum(p['correct'] for p in subset),'accuracy':sum(p['correct'] for p in subset)/len(subset),
                        'group_defined_using_scoring_gt':True,'selection_for_generation_used_this_group':False})
    groups=defaultdict(list)
    for row in overlap_detail:groups[row['split'],row['scenario']].append(row)
    overlap_scenarios=[{'split':split,'scenario':scenario,'n':len(rs),
        'any_gt_hash_hit_questions':sum(r['top3_any_gt_exact_hash_hit'] for r in rs),
        'any_gt_hash_hit_rate':sum(r['top3_any_gt_exact_hash_hit'] for r in rs)/len(rs),
        'all_gt_hashes_covered_questions':sum(r['all_gt_hashes_covered'] for r in rs)} for (split,scenario),rs in groups.items()]
    return {'quality_recomputed':qtable,'cross_model_paired':cross,'answer_transitions':transitions,'failure_examples':examples,
            'quality_cost':costs,'gt_overlap_strata':overlap_strata,'gt_overlap_by_question':overlap_detail,
            'gt_overlap_by_scenario':overlap_scenarios}

def figures(result, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=dict(zip(MODELS,['#206095','#7A5195','#D78521','#BA493A','#36765A']))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','pdf.fonttype':42})
    for metric,label,name in [('offline_p95_ms','P95 preprocessing + generation (ms)','quality_latency_pareto'),
                              ('performance_peak_reserved_gib','Maximum allocator reserved in performance runs (GiB)','quality_memory_pareto')]:
        fig,axes=plt.subplots(1,3,figsize=(13.5,4.7),sharey=True)
        for ax,cond in zip(axes,['S0','S1','S2']):
            rs=[r for r in result['quality_cost'] if r['condition']==cond]
            for n,r in enumerate(rs):
                ax.scatter(r[metric],r['accuracy']*100,color=colors[r['model_key']],s=46,marker=['o','s','^','D','v'][n],label=r['model'])
                ax.annotate(['Q4','Q8','E2','E4','Q3.5'][n],(r[metric],r['accuracy']*100),xytext=(4,5),textcoords='offset points',fontsize=8)
            frontier=sorted((r for r in rs if r['descriptive_nondominated_'+metric]),key=lambda r:r[metric])
            ax.plot([r[metric] for r in frontier],[r['accuracy']*100 for r in frontier],ls='--',color='#888888',lw=.8,zorder=0)
            ax.set_title(cond+' (S2 is oracle)' if cond=='S2' else cond)
            ax.set_xlabel(label,fontsize=8);ax.set_ylim(0,85);ax.set_xlim(left=0,right=max(r[metric] for r in result['quality_cost'])*1.3)
            ax.grid(alpha=.15)
        axes[0].set_ylabel('Frozen-test strict accuracy (%)')
        fig.suptitle('Descriptive quality and measured generation cost by condition',x=.06,ha='left',fontsize=13)
        fig.legend(*axes[0].get_legend_handles_labels(),ncol=5,loc='lower center',bbox_to_anchor=(.5,.065),frameon=False)
        fig.text(.06,.02,'Quality: 1,033 frozen questions. Cost: 20 smoke questions x 5 repeats. Single RTX 4090; retrieval excluded; workloads differ.',fontsize=9)
        fig.tight_layout(rect=(0,.16,1,.93))
        for ext in ['png','svg','pdf']:fig.savefig(out/(name+'.'+ext),dpi=180,bbox_inches='tight')
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(9.5,4.8))
    rs=[r for r in result['answer_transitions'] if r['split']=='frozen_test' and r['left']=='S0' and r['right']=='S1']
    for k,field,color in [(0,'wrong_to_right','#206095'),(1,'right_to_wrong','#BA493A')]:
        bars=ax.bar([n+(k-.5)*.34 for n in range(5)],[r[field] for r in rs],width=.32,label=field.replace('_',' '),color=color)
        ax.bar_label(bars,padding=3)
    ax.set_xticks(range(5),[LABELS[r['model_key']] for r in rs]);ax.set_ylim(bottom=0,top=max(max(r['wrong_to_right'],r['right_to_wrong']) for r in rs)*1.22)
    ax.set_ylabel('Questions (full denominator = 1,033 each)');ax.legend(frameon=False)
    ax.set_title('Answer transitions after adding published top-3 evidence',loc='left',pad=20)
    fig.text(.1,.015,'Observed paired outcomes; right-to-wrong does not establish a causal failure mechanism.',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1))
    for ext in ['png','svg','pdf']:fig.savefig(out/('evidence_harm_transitions.'+ext),dpi=180,bbox_inches='tight')
    plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,default=REPO/'logs/B_predictions.jsonl.gz')
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--figures',action='store_true')
    args=p.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):p.error('Use a new empty output directory')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    result=compute(args.log)
    for name,rows in result.items():csv_write(args.output_dir/(name+'.csv'),rows)
    if args.figures:figures(result,args.output_dir)
    print(json.dumps({'status':'PASS','unique_question_runs':21927,'format_failures_wrong':132,
                      'cross_model_contrasts':len(result['cross_model_paired']),'transition_groups':len(result['answer_transitions']),
                      'source_clustered_intervals':False,'inference_or_network':False}))
