"""Statically verify pinned official scorer field contract; never executes scorer.

Reproduce: $PY analysis/next_stage_20261019/verify_official_schema.py
 --official-source <CACHED_SCORE_PY> --metadata-dir <CACHED_METADATA>
 --export-dir <PRIVATE_EXPORT>
"""
import argparse
import ast
import json
from pathlib import Path
from quality_data import sha,jsonl,read,write_json
from verify_official_export import verify,REPO

SOURCE_SHA='06cf633e01af2504e791926eb86ddf6ff10c7050279ad184ed7c9889e96eb905'
SOURCE_URL='https://raw.githubusercontent.com/mragbench/MRAG-Bench/4ae2241fdc5a9505f63dbae230e50a3097296af0/eval/score.py'


def required_fields(source):
    tree=ast.parse(source)
    return {node.slice.value for node in ast.walk(tree) if isinstance(node,ast.Subscript)
        and isinstance(node.ctx,ast.Load) and isinstance(node.value,ast.Name) and node.value.id=='item'
        and isinstance(node.slice,ast.Constant) and isinstance(node.slice.value,str)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--official-source',type=Path,required=True);parser.add_argument('--metadata-dir',type=Path,required=True)
    parser.add_argument('--export-dir',type=Path,required=True);parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if sha(args.official_source)!=SOURCE_SHA:raise ValueError('Pinned official source changed')
    fields=required_fields(args.official_source.read_text())
    if not {'gt_choice','output','prompt','scenario'}<=fields:raise ValueError('Official field contract differs')
    receipt=read(args.export_dir/'export_receipt.json')
    for item in receipt['files']:
        for row in jsonl(args.export_dir/item['file']):
            if not fields<=set(row):raise ValueError('Export lacks an official field')
    value=verify(args.repo,args.metadata_dir,args.export_dir)
    value.update(official_schema_check='pinned AST read-only field inspection',official_source_sha256=SOURCE_SHA,
                 official_source_url=SOURCE_URL,required_fields=sorted(fields),official_scorer_executed=False)
    if args.out:write_json(args.out,value)
    print(json.dumps(value,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
