"""Read-only source-to-export verification; never reparses or scores responses."""
import argparse
from collections import Counter
from pathlib import Path
import json
from export_official import inputs,project_rows,REPO,SPLIT_STAGE
from quality_data import sha,jsonl,read


def check_rows(rows,official,source,prompts):
    expected=project_rows(official,source,prompts)
    if rows!=expected:raise ValueError('Export does not exactly project immutable source fields/order')
    if len({row['qid'] for row in rows})!=len(rows):raise ValueError('Duplicate exported question')
    return True


def verify(repo,metadata_dir,out):
    out=Path(out);receipt=read(out/'export_receipt.json')
    official,predictions,contexts,pins=inputs(repo,metadata_dir)
    for key,value in pins.items():
        if receipt[key]!=value:raise ValueError('Export source identity mismatch')
    all_rows=0
    for item in receipt['files']:
        path=out/item['file']
        if not path.resolve().is_relative_to(out.resolve()) or sha(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:
            raise ValueError('Export member identity mismatch')
        rows=jsonl(path)
        if len(rows)!=item['rows']:raise ValueError('Export denominator changed')
        model,condition=item['model'],item['condition']
        source={q:row for (m,c,q),row in predictions.items() if m==model and c==condition};prompts={}
        for qid,row in source.items():
            messages=contexts[row['context_key']]['input']['model_request']['messages']
            prompts[qid]='\n'.join(part['text'] for message in messages for part in message['content'] if part['type']=='text')
        projected=project_rows(official,source,prompts)
        expected=projected if item['split']=='all' else [row for row in projected if row['project_split']==item['split']]
        if rows!=expected:raise ValueError('Source row/status/output/order mismatch')
        if item['split']=='all':all_rows+=len(rows)
    if all_rows!=receipt['full_export_rows'] or all_rows!=20295:raise ValueError('Fixed official slots mismatch')
    return dict(status='verified_official_projection_only',files=len(receipt['files']),full_export_rows=all_rows,
                source_prediction_sha256=pins['source_prediction_sha256'],export_receipt_sha256=sha(out/'export_receipt.json'),
                failure_counts=receipt['failure_counts'],old_outputs_reparsed=False,official_scorer_run=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO);parser.add_argument('--metadata-dir',type=Path,required=True)
    parser.add_argument('--export-dir',type=Path,required=True);parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=verify(args.repo,args.metadata_dir,args.export_dir)
    if args.out:
        with args.out.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
