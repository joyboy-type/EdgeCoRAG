"""Private official-schema projection of archived baseline predictions; never score.

Read only locally cached official metadata, contexts and immutable prediction
fields. Output contains gold/raw responses and MUST remain outside the repository.
Missing source slots are explicit rows, never reparsed or repaired.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from quality_data import MODELS,sha,read,jsonl,unique,write_json

REPO=Path(__file__).resolve().parents[2]
SPLIT_STAGE={'smoke_20':'smoke','dev':'development','internal_holdout':'quality','frozen_test':'quality'}


def project_rows(official,source,prompts):
    result=[]
    for index,metadata in enumerate(official):
        qid=metadata['qid'];item=source.get(qid);present=item is not None
        if present and (item['answer']!=metadata['answer_choice'] or item['scenario']!=metadata['scenario']):
            raise ValueError('Source/official metadata identity mismatch')
        result.append(dict(id=metadata['id'],qs_id=metadata['id'],raw_id=metadata['id'],qid=qid,
            gt_choice=metadata['answer_choice'],output=item['raw_output'] if present else '',
            prompt=prompts.get(qid,''),scenario=metadata['scenario'],official_row_index=index,
            project_split=item['split'] if present else metadata.get('project_split','unknown'),
            parse_status=item['parse_status'] if present else 'missing_prediction',
            parsed_choice=item.get('parsed_choice') if present else None,
            generation_error=item.get('generation_error') if present else None,
            source_present=present,parser_version='strict_choice_v1',parser_rerun=False,
            prompt_is_processor_rendered=False,prompt_available=qid in prompts))
    return result


def inputs(repo,metadata_dir):
    repo=Path(repo);metadata_dir=Path(metadata_dir)
    reference=read(metadata_dir/'official-full-field-projection-v3/receipt.json')
    pred_path=repo/'logs/B_predictions.jsonl.gz';context_path=repo/'logs/B_input_contexts.jsonl.gz'
    if reference['source_prediction_sha256']!=sha(pred_path):raise ValueError('Frozen prediction binding drift')
    page_rows=[]
    for pin in reference['metadata_page_receipts']:
        path=metadata_dir/'official-metadata-pages'/(str(pin['offset'])+'.json')
        if sha(path)!=pin['sha256'] or path.stat().st_size!=pin['bytes']:raise ValueError('Cached official page hash mismatch')
        page_rows+=read(path)['rows']
    page_rows.sort(key=lambda row:row['row_idx'])
    if [r['row_idx'] for r in page_rows]!=list(range(1353)):raise ValueError('Official order incomplete')
    official=[dict(qid='mragb:'+str(r['row']['id']),id=str(r['row']['id']),
                   answer_choice=r['row']['answer_choice'],scenario=r['row']['scenario']) for r in page_rows]
    if [r['qid'] for r in official]!=reference['official_dataset_order_qids']:raise ValueError('Official row order binding mismatch')
    predictions={}
    for row in jsonl(pred_path):
        if row['condition'] in ('S0','S1','S2') and row['stage']==SPLIT_STAGE[row['split']]:
            key=(row['model_key'],row['condition'],row['qid'])
            if key in predictions:raise ValueError('Duplicate source prediction')
            predictions[key]=row
    contexts=unique(jsonl(context_path),lambda row:row['context_key'])
    return official,predictions,contexts,dict(source_prediction_sha256=sha(pred_path),source_context_sha256=sha(context_path),
        official_reference_sha256=sha(metadata_dir/'official-full-field-projection-v3/receipt.json'),
        official_dataset_revision=reference['official_dataset_revision'])


def export(repo,metadata_dir,out):
    repo=Path(repo).resolve();out=Path(out).resolve()
    if out.is_relative_to(repo) or out.exists():raise ValueError('A NEW private output outside repository is required')
    official,predictions,contexts,pins=inputs(repo,metadata_dir);out.mkdir(parents=True)
    files=[];full_status=Counter()
    for model in MODELS:
        for condition in ('S0','S1','S2'):
            source={q:row for (m,c,q),row in predictions.items() if m==model and c==condition};prompts={}
            for qid,row in source.items():
                messages=contexts[row['context_key']]['input']['model_request']['messages']
                prompts[qid]='\n'.join(item['text'] for message in messages for item in message['content'] if item['type']=='text')
            rows=project_rows(official,source,prompts)
            for split in ('all',*SPLIT_STAGE):
                selected=rows if split=='all' else [row for row in rows if row['project_split']==split]
                path=out/'submission_format'/model/condition/(split+'.jsonl');path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('x') as stream:
                    for row in selected:stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                statuses=Counter(row['parse_status'] for row in selected)
                files.append(dict(file=str(path.relative_to(out)),sha256=sha(path),bytes=path.stat().st_size,
                    rows=len(selected),failure_counts={name:statuses[name] for name in ('empty_output','parse_failure','generation_error','missing_prediction')},
                    model=model,condition=condition,split=split))
                if split=='all':full_status.update(statuses)
    receipt=dict(status='official_format_export_only',**pins,files=files,full_files=15,split_files=60,
        source_slots=20295,full_export_rows=sum(r['rows'] for r in files if r['split']=='all'),
        failure_counts=dict(full_status),official_scorer_run=False,old_outputs_reparsed=False,project_scores_changed=False,
        limitations=['Private gold/raw-response projection; do not publish files','Combines original four exposure cohorts, not1353 unseen tests',
                    'Prompt is saved structured message text, not an unavailable processor-rendered string','No official leaderboard comparability or new scoring claimed'])
    write_json(out/'export_receipt.json',receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO);parser.add_argument('--metadata-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=export(args.repo,args.metadata_dir,args.out)
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
