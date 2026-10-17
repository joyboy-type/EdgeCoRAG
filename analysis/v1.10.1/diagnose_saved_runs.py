"""Post hoc record diagnostics. Reads saved outputs only; never calls models or networks."""
from collections import Counter, defaultdict
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'b-side'))
from score_minimal import parse_choice

MODELS=['qwen3vl_4b','qwen3vl_8b','gemma4_e2b','gemma4_e4b','qwen35_4b']
LABELS=dict(zip(MODELS,['Qwen3-VL 4B','Qwen3-VL 8B','Gemma4 E2B','Gemma4 E4B','Qwen3.5 4B']))
PATTERNS={'000':'三条件均错','001':'仅GT条件答对','010':'仅检索条件答对','011':'两证据条件均答对',
          '100':'仅无证据条件答对','101':'检索条件独错','110':'GT条件独错','111':'三条件均对'}
CONTRASTS=[('S0','S1'),('S1','S2'),('S0','S2')]

SQL={
 'record_summary':"""SELECT split,model_key,COUNT(*) AS n,SUM(pattern='000') AS all_three_wrong,
 SUM(s1=0 AND s2=1) AS s1_wrong_s2_correct,
 SUM(s1=0 AND s2=1 AND s1_format=0) AS s1_valid_wrong_s2_correct,
 SUM(s1=0 AND s2=1 AND gt_hash_hit=0) AS s1_wrong_s2_correct_no_gt_hash_hit,
 SUM(s1=0 AND s2=1 AND gt_hash_hit=1) AS s1_wrong_s2_correct_with_gt_hash_hit,
 SUM(s2=0) AS s2_wrong,SUM(s0=1 AND s1=0) AS s0_right_s1_wrong
 FROM triples GROUP BY split,model_key ORDER BY split,model_key;""",
 'selected_cases':"""SELECT model_key,category,qid FROM review_candidates
 WHERE model_key=:model_key AND category=:category
 AND qid NOT IN (SELECT value FROM json_each(:excluded_qids))
 ORDER BY selection_hash LIMIT 1;""",
 'condition_errors':"""SELECT split,model_key,condition,COUNT(*) AS n,SUM(correct) AS correct,
 SUM(correct=0 AND format_failure=0) AS valid_choice_wrong,SUM(format_failure) AS format_failures,
 SUM(format_failure=1 AND budget_exhausted=1) AS format_failures_budget_exhausted
 FROM condition_runs GROUP BY split,model_key,condition ORDER BY split,model_key,condition;""",
 'patterns':"""SELECT split,model_key,pattern,COUNT(*) AS n FROM triples
 GROUP BY split,model_key,pattern ORDER BY split,model_key,pattern;""",
 'format_decomposition':"""SELECT split,model_key,left_condition,right_condition,
 CASE WHEN left_format=1 AND right_format=1 THEN 'both_format_failure'
      WHEN left_format=1 THEN 'left_only_format_failure'
      WHEN right_format=1 THEN 'right_only_format_failure'
      ELSE 'both_parse_ok' END AS format_group,
 COUNT(*) AS n,SUM(right_correct-left_correct) AS net_correct_change,
 SUM(left_correct=0 AND right_correct=1) AS improvements,
 SUM(left_correct=1 AND right_correct=0) AS regressions
 FROM contrasts GROUP BY split,model_key,left_condition,right_condition,format_group
 ORDER BY split,model_key,left_condition,right_condition,format_group;""",
 'gt_decomposition':"""SELECT split,model_key,gt_hash_hit,COUNT(*) AS n,
 SUM(s1-s0) AS net_correct_change,SUM(s0=0 AND s1=1) AS improvements,
 SUM(s0=1 AND s1=0) AS regressions,
 SUM(s1=0 AND s2=1) AS s1_wrong_s2_correct,
 SUM(s1=0 AND s2=1 AND s1_format=0) AS s1_valid_wrong_s2_correct
 FROM triples GROUP BY split,model_key,gt_hash_hit ORDER BY split,model_key,gt_hash_hit;"""
}

def jsonl_gz(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return [json.loads(s) for s in f]

def write_csv(path,rows):
    if not rows:return
    text=io.StringIO(newline='');w=csv.DictWriter(text,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    data=text.getvalue().encode('utf-8-sig')
    if path.suffix=='.gz':
        with gzip.GzipFile(filename=str(path),mode='wb',mtime=0) as f:f.write(data)
    else:path.write_bytes(data)

def compute(repo=REPO):
    rows=jsonl_gz(repo/'logs/B_predictions.jsonl.gz')
    assert len(rows)==len({tuple(p['row_key']) for p in rows})==21927
    contexts={r['context_key']:r['input'] for r in jsonl_gz(repo/'logs/B_input_contexts.jsonl.gz')}
    quality=[p for p in rows if p['stage']=='quality' and p['condition'] in ('S0','S1','S2')]
    assert len(quality)==17745
    groups=defaultdict(dict)
    for p in quality:
        assert parse_choice(p['final_output'])==(p['parsed_choice'],p['parse_status'])
        assert p['correct']==(p['parse_status']=='ok' and p['parsed_choice']==p['answer'])
        assert not p['generation_error'] and not p['final_extraction_error']
        key=(p['split'],p['model_key'],p['qid']);assert p['condition'] not in groups[key]
        groups[key][p['condition']]=p
    assert len(groups)==5915
    ledger=[];context_fingerprints={}
    for (split,model,qid),ps in sorted(groups.items()):
        assert set(ps)=={'S0','S1','S2'}
        assert len({p['model_revision'] for p in ps.values()})==1
        assert len({p['answer'] for p in ps.values()})==len({p['scenario'] for p in ps.values()})==1
        inputs={c:contexts[p['context_key']] for c,p in ps.items()}
        assert len({i['query_image']['sha256'] for i in inputs.values()})==1
        assert len(inputs['S0']['evidence'])==0 and len(inputs['S1']['evidence'])==3
        assert len(inputs['S2']['evidence'])==(1 if ps['S0']['scenario']=='Incomplete' else 5)
        hashes={c:[x['sha256'] for x in i['evidence']] for c,i in inputs.items()}
        for cond,values in hashes.items():
            k=(split,qid,cond)
            assert k not in context_fingerprints or context_fingerprints[k]==values
            context_fingerprints[k]=values
        s1,s2=set(hashes['S1']),set(hashes['S2']);hit=bool(s1&s2)
        pattern=''.join(str(int(ps[c]['correct'])) for c in ['S0','S1','S2'])
        r={'split':split,'model_key':model,'model':LABELS[model],'qid':qid,'scenario':ps['S0']['scenario'],
           'gold':ps['S0']['answer'],'pattern':pattern,'pattern_label':PATTERNS[pattern],
           'top3_any_gt_exact_hash_hit':hit,'matched_gt_hashes':len(s1&s2),'gt_image_count':len(hashes['S2']),
           's1_wrong_s2_correct':not ps['S1']['correct'] and ps['S2']['correct'],
           's0_right_s1_wrong':ps['S0']['correct'] and not ps['S1']['correct'],
           's2_wrong':not ps['S2']['correct'],'mechanism_adjudicated':False,'visual_review_completed':False}
        for c,p in ps.items():
            r.update({c+'_correct':p['correct'],c+'_choice':p['parsed_choice'],c+'_parse_status':p['parse_status'],
                      c+'_format_failure':p['parse_status']!='ok',c+'_generated_tokens':p['generated_tokens'],
                      c+'_budget_exhausted':p['budget_exhausted']})
        ledger.append(r)

    patterns=[];summary=[];gt=[];decomposition=[];conditions=[];scenario=[]
    bygroup=defaultdict(list)
    for r in ledger:bygroup[r['split'],r['model_key']].append(r)
    for (split,model),rs in bygroup.items():
        n={'internal_holdout':150,'frozen_test':1033}[split];assert len(rs)==n
        counts=Counter(r['pattern'] for r in rs)
        for pattern,label in PATTERNS.items():patterns.append({'split':split,'model_key':model,'model':LABELS[model],
            'pattern':pattern,'pattern_label':label,'n':counts[pattern],'denominator':n,'share':counts[pattern]/n})
        summary.append({'split':split,'model_key':model,'model':LABELS[model],'n':n,'all_three_wrong':counts['000'],
            's1_wrong_s2_correct':sum(r['s1_wrong_s2_correct'] for r in rs),
            's1_valid_wrong_s2_correct':sum(r['s1_wrong_s2_correct'] and not r['S1_format_failure'] for r in rs),
            's1_wrong_s2_correct_no_gt_hash_hit':sum(r['s1_wrong_s2_correct'] and not r['top3_any_gt_exact_hash_hit'] for r in rs),
            's1_wrong_s2_correct_with_gt_hash_hit':sum(r['s1_wrong_s2_correct'] and r['top3_any_gt_exact_hash_hit'] for r in rs),
            's2_wrong':sum(r['s2_wrong'] for r in rs),'s0_right_s1_wrong':sum(r['s0_right_s1_wrong'] for r in rs)})
        for hit in [False,True]:
            subset=[r for r in rs if r['top3_any_gt_exact_hash_hit']==hit]
            improve=sum(not r['S0_correct'] and r['S1_correct'] for r in subset)
            regress=sum(r['S0_correct'] and not r['S1_correct'] for r in subset)
            gt.append({'split':split,'model_key':model,'model':LABELS[model],'gt_hash_hit':hit,
                'group':'至少一个GT哈希命中' if hit else '无GT哈希命中','n':len(subset),'full_denominator':n,
                'improvements':improve,'regressions':regress,'net_correct_change':improve-regress,
                'contribution_pp_full_denominator':100*(improve-regress)/n,
                'within_group_delta_pp':100*(improve-regress)/len(subset),
                's1_wrong_s2_correct':sum(r['s1_wrong_s2_correct'] for r in subset),
                's1_valid_wrong_s2_correct':sum(r['s1_wrong_s2_correct'] and not r['S1_format_failure'] for r in subset)})
        for left,right in CONTRASTS:
            for lf,rf in [(False,False),(False,True),(True,False),(True,True)]:
                subset=[r for r in rs if r[left+'_format_failure']==lf and r[right+'_format_failure']==rf]
                improve=sum(not r[left+'_correct'] and r[right+'_correct'] for r in subset)
                regress=sum(r[left+'_correct'] and not r[right+'_correct'] for r in subset)
                group='both_format_failure' if lf and rf else 'left_only_format_failure' if lf else 'right_only_format_failure' if rf else 'both_parse_ok'
                decomposition.append({'split':split,'model_key':model,'left':left,'right':right,'format_group':group,'n':len(subset),
                    'full_denominator':n,'improvements':improve,'regressions':regress,'net_correct_change':improve-regress,
                    'contribution_pp_full_denominator':100*(improve-regress)/n})
        for c in ['S0','S1','S2']:
            correct=sum(r[c+'_correct'] for r in rs);formats=sum(r[c+'_format_failure'] for r in rs)
            validwrong=n-correct-formats
            conditions.append({'split':split,'model_key':model,'model':LABELS[model],'condition':c,'n':n,'correct':correct,
                'strict_accuracy':correct/n,'valid_choice_wrong':validwrong,'format_failures':formats,
                'valid_choice_wrong_rate':validwrong/n,'format_failure_rate':formats/n,
                'all_format_failures_assumed_correct_ceiling':(correct+formats)/n,
                'ceiling_is_not_recovered_or_expected_accuracy':True,
                'format_failures_budget_exhausted':sum(r[c+'_format_failure'] and r[c+'_budget_exhausted'] for r in rs)})
        for scene in sorted({r['scenario'] for r in rs}):
            subset=[r for r in rs if r['scenario']==scene]
            scenario.append({'split':split,'model_key':model,'model':LABELS[model],'scenario':scene,'n':len(subset),
                'S0_correct':sum(r['S0_correct'] for r in subset),'S1_correct':sum(r['S1_correct'] for r in subset),
                'S2_correct':sum(r['S2_correct'] for r in subset),
                'S1_minus_S0_net_correct':sum(r['S1_correct']-r['S0_correct'] for r in subset),
                'S2_minus_S1_net_correct':sum(r['S2_correct']-r['S1_correct'] for r in subset),
                'all_three_wrong':sum(r['pattern']=='000' for r in subset),
                's1_wrong_s2_correct':sum(r['s1_wrong_s2_correct'] for r in subset),
                'S1_format_failures':sum(r['S1_format_failure'] for r in subset),
                'S2_format_failures':sum(r['S2_format_failure'] for r in subset)})

    # Independent SQL aggregation from row-grain facts, not Python summary outputs.
    with sqlite3.connect(':memory:') as conn:
        conn.row_factory=sqlite3.Row
        conn.execute('CREATE TABLE condition_runs(split TEXT,model_key TEXT,qid TEXT,condition TEXT,correct INTEGER,format_failure INTEGER,budget_exhausted INTEGER,PRIMARY KEY(split,model_key,qid,condition))')
        conn.executemany('INSERT INTO condition_runs VALUES (?,?,?,?,?,?,?)',[(p['split'],p['model_key'],p['qid'],p['condition'],int(p['correct']),int(p['parse_status']!='ok'),int(p['budget_exhausted'])) for p in quality])
        conn.execute('CREATE TABLE triples(split TEXT,model_key TEXT,qid TEXT,pattern TEXT,gt_hash_hit INTEGER,s0 INTEGER,s1 INTEGER,s2 INTEGER,s1_format INTEGER,PRIMARY KEY(split,model_key,qid))')
        conn.executemany('INSERT INTO triples VALUES (?,?,?,?,?,?,?,?,?)',[(r['split'],r['model_key'],r['qid'],r['pattern'],int(r['top3_any_gt_exact_hash_hit']),int(r['S0_correct']),int(r['S1_correct']),int(r['S2_correct']),int(r['S1_format_failure'])) for r in ledger])
        conn.execute('CREATE TABLE contrasts(split TEXT,model_key TEXT,qid TEXT,left_condition TEXT,right_condition TEXT,left_format INTEGER,right_format INTEGER,left_correct INTEGER,right_correct INTEGER)')
        conn.executemany('INSERT INTO contrasts VALUES (?,?,?,?,?,?,?,?,?)',[(r['split'],r['model_key'],r['qid'],a,b,int(r[a+'_format_failure']),int(r[b+'_format_failure']),int(r[a+'_correct']),int(r[b+'_correct'])) for r in ledger for a,b in CONTRASTS])
        sql_results={name:[dict(r) for r in conn.execute(query)] for name,query in SQL.items() if name!='selected_cases'}
    py_patterns={(r['split'],r['model_key'],r['pattern']):r['n'] for r in patterns if r['n']}
    assert py_patterns=={(r['split'],r['model_key'],r['pattern']):r['n'] for r in sql_results['patterns']}
    keys=['n','net_correct_change','improvements','regressions']
    pd={(r['split'],r['model_key'],r['left'],r['right'],r['format_group']):tuple(r[k] for k in keys) for r in decomposition if r['n']}
    sd={(r['split'],r['model_key'],r['left_condition'],r['right_condition'],r['format_group']):tuple(r[k] for k in keys) for r in sql_results['format_decomposition']}
    assert pd==sd
    keys_summary=[k for k in summary[0] if k not in ['split','model_key','model']]
    assert {(r['split'],r['model_key']):tuple(r[k] for k in keys_summary) for r in summary}=={(r['split'],r['model_key']):tuple(r[k] for k in keys_summary) for r in sql_results['record_summary']}
    keys_error=['n','correct','valid_choice_wrong','format_failures','format_failures_budget_exhausted']
    assert {(r['split'],r['model_key'],r['condition']):tuple(r[k] for k in keys_error) for r in conditions}=={(r['split'],r['model_key'],r['condition']):tuple(r[k] for k in keys_error) for r in sql_results['condition_errors']}
    keys+=['s1_wrong_s2_correct','s1_valid_wrong_s2_correct']
    assert {(r['split'],r['model_key'],int(r['gt_hash_hit'])):tuple(r[k] for k in keys) for r in gt}=={(r['split'],r['model_key'],r['gt_hash_hit']):tuple(r[k] for k in keys) for r in sql_results['gt_decomposition']}

    # Reconcile to published totals without changing their denominators or outputs.
    original=list(csv.DictReader((repo/'reports/v1.10.1/quality.csv').open(encoding='utf-8-sig')))
    assert {(r['split'],r['model_key'],r['condition']):(int(r['n']),int(r['correct']),int(r['format_failures'])) for r in original if r['condition']!='S3-pure'}=={(r['split'],r['model_key'],r['condition']):(r['n'],r['correct'],r['format_failures']) for r in conditions}
    original_transitions=list(csv.DictReader((repo/'reports/v1.10.1/answer_transitions.csv').open(encoding='utf-8-sig')))
    for t in original_transitions:
        ds=[r for r in decomposition if (r['split'],r['model_key'],r['left'],r['right'])==(t['split'],t['model_key'],t['left'],t['right'])]
        assert sum(r['n'] for r in ds)==int(t['n'])
        assert sum(r['improvements'] for r in ds)==int(t['wrong_to_right'])
        assert sum(r['regressions'] for r in ds)==int(t['right_to_wrong'])

    # Deterministic post hoc case cards: bounded examples, explicitly not representative.
    categories=[('no_hash_hit_s1_wrong_s2_correct',lambda r:r['s1_wrong_s2_correct'] and not r['top3_any_gt_exact_hash_hit']),
                ('hash_hit_s1_wrong_s2_correct',lambda r:r['s1_wrong_s2_correct'] and r['top3_any_gt_exact_hash_hit']),
                ('s0_right_s1_wrong',lambda r:r['s0_right_s1_wrong']),
                ('s2_valid_choice_wrong',lambda r:r['s2_wrong'] and not r['S2_format_failure'])]
    selected=[]
    for model in MODELS:
        used=set()
        for category,predicate in categories:
            candidates=[r for r in ledger if r['split']=='frozen_test' and r['model_key']==model and r['qid'] not in used and predicate(r)]
            if not candidates:continue
            r=min(candidates,key=lambda r:hashlib.sha256(('42|'+model+'|'+category+'|'+r['qid']).encode()).hexdigest())
            used.add(r['qid']);ps=groups[r['split'],model,r['qid']];inputrow=contexts[ps['S1']['context_key']]
            selected.append({'case_id':f"{model}:{category}:{r['qid']}",'category':category,'split':r['split'],'model_key':model,'model':r['model'],
                'qid':r['qid'],'scenario':r['scenario'],'question':inputrow['question'],'choices':json.dumps(inputrow['choices'],ensure_ascii=False),
                'gold':r['gold'],'pattern':r['pattern'],'top3_any_gt_exact_hash_hit':r['top3_any_gt_exact_hash_hit'],
                'S0_raw':ps['S0']['final_output'],'S1_raw':ps['S1']['final_output'],'S2_raw':ps['S2']['final_output'],
                'visual_review_completed':False,'mechanism_adjudicated':False,
                'selection_rule':'post hoc: minimum SHA256(42|model|category|qid), one unique qid per model/category'})
    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE review_candidates(model_key TEXT,category TEXT,qid TEXT,selection_hash TEXT,PRIMARY KEY(model_key,category,qid))')
        conn.executemany('INSERT INTO review_candidates VALUES (?,?,?,?)',[(r['model_key'],category,r['qid'],hashlib.sha256(('42|'+r['model_key']+'|'+category+'|'+r['qid']).encode()).hexdigest()) for r in ledger if r['split']=='frozen_test' for category,predicate in categories if predicate(r)])
        selected_sql=[]
        for model in MODELS:
            used=[]
            for category,_ in categories:
                row=conn.execute(SQL['selected_cases'],{'model_key':model,'category':category,'excluded_qids':json.dumps(used)}).fetchone()
                if row:selected_sql.append(row);used.append(row[2])
        assert selected_sql==[(r['model_key'],r['category'],r['qid']) for r in selected]
    audit={'status':'PASS_records_only','quality_main_question_runs':17745,'paired_question_model_units':5915,
           'frozen_unique_questions':1033,'holdout_unique_questions':150,'models':5,'condition_groups':30,
           'technical_failures_in_main_quality':0,'main_quality_format_failures':sum(r['format_failures'] for r in conditions),
           'format_failures_at_token_limit':sum(r['format_failures_budget_exhausted'] for r in conditions),
           'sql_reconciled':['patterns','format_decomposition','gt_decomposition','condition_errors','record_summary','selected_cases'],
           'original_quality_and_transition_tables_reconciled':True,'selected_case_cards':len(selected),
           'visual_mechanism_reviews_completed':0,'new_inference':False,'network_access':False,
           'scientific_parameters_changed':False,'post_hoc_analysis':True,'causal_claims_supported':False,
           'quality_s3_excluded_from_this_diagnostic':62,'performance_smoke_dev_preflight_excluded':True}
    assert audit['main_quality_format_failures']==99
    return {'audit':audit,'patterns':patterns,'summary':summary,'gt_decomposition':gt,
            'format_decomposition':decomposition,'condition_errors':conditions,'scenario_contributions':scenario,
            'selected_cases':selected,'case_ledger':ledger,'sql_queries':SQL,'sql_results':sql_results}

def save(result,out):
    out.mkdir(parents=True,exist_ok=True)
    for name in ['patterns','summary','gt_decomposition','format_decomposition','condition_errors','scenario_contributions','selected_cases']:
        write_csv(out/(name+'.csv'),result[name])
    write_csv(out/'case_ledger.csv.gz',result['case_ledger'])
    for name,query in SQL.items():(out/(name+'.sql')).write_text(query+'\n')
    for name,value in [('diagnostic_results',{k:v for k,v in result.items() if k not in ['case_ledger','sql_results']}),('validation_receipt',result['audit'])]:
        (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):p.error('Use a new empty output directory')
    result=compute();save(result,args.output_dir);print(json.dumps(result['audit'],ensure_ascii=False))
