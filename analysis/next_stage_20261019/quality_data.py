"""Read-only identity joins for archived no-self outcomes; never parses answers."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

MODELS=('qwen3vl_4b','qwen3vl_8b','gemma4_e2b','gemma4_e4b','qwen35_4b')
STRATEGIES=('cosine','random','utility')
SPLITS={'smoke_20':20,'dev':150,'frozen_test':1033}
STATUSES=('ok','empty_output','parse_failure','generation_error','missing_prediction')


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def read(path):return json.loads(Path(path).read_text())
def jsonl(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8') as stream:return [json.loads(line) for line in stream if line.strip()]

def write_json(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')

def write_csv(path,rows):
    if not rows:raise ValueError('Empty table without explicit schema')
    with Path(path).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def unique(rows,key):
    result={}
    for row in rows:
        identity=key(row)
        if identity in result:raise ValueError('Duplicate archive identity: '+str(identity))
        result[identity]=row
    return result


def load(repo,work):
    repo=Path(repo);work=Path(work);pins={}
    def pin(path,role):
        pins[role]=dict(sha256=sha(path),bytes=Path(path).stat().st_size)
    source=repo/'logs/results_20261020/no_self_scored_outcomes.jsonl.gz';pin(source,'published_no_self_outcomes')
    outcomes=unique(jsonl(source),lambda r:(r['cohort'],r['model'],r['strategy'],r['qid']))
    if len(outcomes)!=18045:raise ValueError('Fixed no-self denominator identity mismatch')
    data={};full=work/'continuous-complete-backup';manifest=read(full/'closeout-manifest.json')
    raw_pins={r['path']:r for r in manifest['files']};pin(full/'closeout-manifest.json','private_closeout_manifest')
    for split,n in SPLITS.items():
        package_path=work/'prepared'/f'selection-{split}.proposed.json';package=read(package_path)
        pin(package_path,'private_package_'+split)
        qids=[q['qid'] for q in package['queries']]
        if len(set(qids))!=n or any(q['split']!=split for q in package['queries']):raise ValueError('Fixed split differs')
        ranks_path=work/'prepared'/f'no-self-{split}-ranks.jsonl';pin(ranks_path,'private_ranks_'+split)
        ranks=unique(jsonl(ranks_path),lambda r:r['qid'])
        if set(ranks)!=set(qids):raise ValueError('Rank identity mismatch')
        part=dict(qids=qids,package=package,ranks=ranks,outcomes={},selected={},scored={},scenes={})
        for model in MODELS:
            raw_path=full/split/'results'/('generate-'+model)/'predictions.jsonl'
            if sha(raw_path)!=raw_pins[str(raw_path.relative_to(full))]['sha256']:raise ValueError('Historical source bytes changed')
            pin(raw_path,f'private_predictions_{split}_{model}')
            raw=unique(jsonl(raw_path),lambda r:(r['selection_strategy'],r['qid']))
            for strategy in STRATEGIES:
                score_path=work/'corrected-protocol-scoring'/f'{split}__{model}__{strategy}.private.json'
                score=read(score_path);pin(score_path,f'private_score_{split}_{model}_{strategy}')
                if score['source_predictions_sha256']!=sha(raw_path):raise ValueError('Archived score source binding differs')
                scored=unique(score['per_question'],lambda r:r['qid'])
                if set(scored)!=set(qids):raise ValueError('Archived score denominator mismatch')
                part['outcomes'][model,strategy]={};part['selected'][model,strategy]={};part['scored'][model,strategy]=scored
                for qid in qids:
                    public=outcomes[split,model,strategy,qid];item=scored[qid];prediction=raw[strategy,qid]
                    if item['parse_status'] not in STATUSES or type(item['correct']) is not bool:
                        raise ValueError('Archived status/outcome schema mismatch')
                    if item['parse_status']!='ok' and item['correct']:raise ValueError('A failure was excluded from correctness')
                    if (public['correct']!=item['correct'] or public['parse_status']!=item['parse_status']
                            or public['scenario']!=item['scenario'] or item['raw_output']!=prediction['final_output']):
                        raise ValueError('Published/archived outcomes diverge; do not reparse')
                    part['outcomes'][model,strategy][qid]=item['correct'];part['scenes'][qid]=item['scenario']
                    selected=prediction['selected_ids'];pool=ranks[qid]['corpus_ids']
                    if len(set(selected))!=3 or not set(selected)<=set(pool):raise ValueError('Bound selection/pool mismatch')
                    part['selected'][model,strategy][qid]=selected
                if sum(part['outcomes'][model,strategy].values())!=score['overall']['correct']:
                    raise ValueError('Archived score total mismatch')
        data[split]=part
    groups_path=repo/'logs/results_20261020/frozen1033_image_groups_and_transitions.csv';pin(groups_path,'published_component_assignments')
    with groups_path.open(encoding='utf-8-sig',newline='') as stream:groups=unique(list(csv.DictReader(stream)),lambda r:r['qid'])
    if set(groups)!=set(data['frozen_test']['qids']) or len({x['query_or_GT_image_component'] for x in groups.values()})!=564:
        raise ValueError('Existing 564-component identity mismatch')
    baseline_path=repo/'logs/B_predictions.jsonl.gz';pin(baseline_path,'historical_baseline_predictions')
    s0={};stage_map={'smoke_20':'smoke','dev':'development','frozen_test':'quality'}
    for row in jsonl(baseline_path):
        split=row['split']
        if split in SPLITS and row['condition']=='S0' and row['stage']==stage_map[split]:
            key=(split,row['model_key'],row['qid'])
            if key in s0:raise ValueError('Duplicate historical S0')
            s0[key]=bool(row['correct'])
    if len(s0)!=1203*5:raise ValueError('Historical S0 denominator mismatch')
    ret_path=work.parent/'instance394-preflight/formal-retrieval-embeddinggemma2-backup/controls/retrieval-formal.approved.json'
    # Supplied work is project/work/next-experiment..., hence retrieval backup is its sibling.
    pin(ret_path,'private_retrieval_controls')
    for split in SPLITS:
        if data[split]['package']['retrieval_package_sha256']!=sha(ret_path):raise ValueError('Retrieval control binding differs')
    retrieval=read(ret_path)
    return dict(splits=data,groups=groups,s0=s0,gold=retrieval['gold'],pins=pins)

if __name__=='__main__':argparse.ArgumentParser(description=__doc__).parse_args()
