"""Rearrange existing joined S0/S1 outcomes; no experiments or log edits.
Reproduce: $PY analysis/next_stage_20261019/error_crosstab.py --out <NEW_DIR>
Four cells partition S1 correctness x top3 GT hit. Harm is an overlapping
subset of wrong answers, not a fifth cell and not a causal estimate.
"""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
MODELS=('qwen3vl_4b','qwen3vl_8b','gemma4_e2b','gemma4_e4b','qwen35_4b')
CELLS=('未命中但答对','未命中且答错','命中但答错','命中且答对')

def boolean(value):
    if value not in ('True','False'):raise ValueError('Malformed boolean')
    return value=='True'

def summarize(rows,*,models=MODELS,denominator=1033):
    by_model={model:{} for model in models}
    for r in rows:
        if r['model'] not in by_model:raise ValueError('Unexpected model')
        model=by_model[r['model']]
        if r['qid'] in model:raise ValueError('Duplicate model/qid')
        if not boolean(r['joinable']) or r['missing_reason']:raise ValueError('Missing joined inputs')
        model[r['qid']]=tuple(boolean(r[k]) for k in ('top3_gt_hit','S0_correct','S1_correct'))
    reference=None;result=[]
    for name,model in by_model.items():
        if len(model)!=denominator:raise ValueError('Fixed denominator mismatch')
        hits={qid:values[0] for qid,values in model.items()}
        if reference is None:reference=hits
        if hits!=reference:raise ValueError('Shared retrieval hit mismatch across models')
        counts=dict.fromkeys(CELLS,0);harm=0
        for hit,s0,s1 in model.values():
            cell=('命中且答对' if s1 else '命中但答错') if hit else ('未命中但答对' if s1 else '未命中且答错')
            counts[cell]+=1;harm+=s0 and not s1
        n_hit=sum(hits.values());n_miss=denominator-n_hit
        if sum(counts.values())!=denominator or harm>counts['未命中且答错']+counts['命中但答错']:raise ValueError('Invalid partition or overlay')
        result.append(dict(model=name,**counts,命中数=n_hit,未命中数=n_miss,分母=denominator,检索伤害=harm,检索伤害占比=100*harm/denominator))
    return result

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def build(out):
    if out.exists():raise FileExistsError('New output directory required')
    ledger=REPO/'reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz'
    with gzip.open(ledger,'rt') as f:table=summarize(list(csv.DictReader(f)))
    out.mkdir(parents=True)
    with (out/'main_table.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]),lineterminator='\n');writer.writeheader();writer.writerows(table)
    receipt=dict(source=str(ledger.relative_to(REPO)),source_sha256=sha(ledger),implementation_sha256=sha(Path(__file__)),shared_hit_qids_identical=True,hit=table[0]['命中数'],miss=table[0]['未命中数'],denominator=1033,table=table,harm_note='S0对且S1错；答错题的子集，与2×2重叠，不得相加；不作因果解释',failures='沿用原日志正确标记，解析/生成失败计错并保留分母，无重解析',selection='无策略选择；仅重排既有frozen结果')
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);build(p.parse_args().out)
