"""Post hoc priority partition of the validated public join ledger; CPU only.
Reproduce: $PY analysis/next_stage_20261019/priority_error_partition.py --out <NEW_DIR>
Rules were documented in priority_definition_v3.md before recalculation.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
LABELS=('检索伤害','未检索到','检索到但答错','无关但未伤害','不可判定')

def boolean(value):
    if value not in ('True','False'):raise ValueError('Malformed archived boolean')
    return value=='True'

def classify(joinable,s0,s1,hit):
    if type(joinable) is not bool:raise ValueError('Boolean joinable required')
    if not joinable:return '不可判定'
    if any(type(x) is not bool for x in (s0,s1,hit)):raise ValueError('Complete boolean inputs required')
    if s0 and not s1:return '检索伤害'
    if not hit and not s1:return '未检索到'
    if hit and not s1:return '检索到但答错'
    return '无关但未伤害'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def write_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def build(out):
    from quality_data import MODELS
    from quality_stats import paired_family
    ledger=REPO/'reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz'
    group_path=REPO/'logs/results_20261020/frozen1033_image_groups_and_transitions.csv'
    rule=REPO/'reports/next_stage_20261019/error_partition_20261021/priority_definition_v3.md'
    if out.exists():raise FileExistsError('New output directory required')
    if '优先级定义为事后设定' not in rule.read_text():raise ValueError('Document rule before recalculation')
    with gzip.open(ledger,'rt') as f:source=list(csv.DictReader(f))
    with group_path.open() as f:gr=list(csv.DictReader(f))
    qids=[r['qid'] for r in gr];groups=[r['query_or_GT_image_component'] for r in gr]
    if len(set(qids))!=1033 or len(qids)!=1033 or len(set(groups))!=564:raise ValueError('Group denominator mismatch')
    by_key={(r['model'],r['qid']):r for r in source}
    if len(by_key)!=len(source) or len(source)!=5*1033:raise ValueError('Ledger duplication or missing rows')
    assignments=[];comparisons=[];counts={}
    for model in MODELS:
        vectors={label:[] for label in LABELS}
        for qid in qids:
            r=by_key[(model,qid)];known=boolean(r['joinable'])
            if known and r['missing_reason']:raise ValueError('Inconsistent joinability')
            if not known and not r['missing_reason']:raise ValueError('Missing reason required')
            label=classify(known,*(boolean(r[k]) if known else None for k in ('S0_correct','S1_correct','top3_gt_hit')))
            assignments.append({k:r[k] for k in ('model','qid','source_line_S0','source_line_S1','joinable','missing_reason','top3_gt_hit','S0_correct','S1_correct')}|{'category':label})
            for name in LABELS:vectors[name].append(label==name)
        counts[model]={label:sum(vectors[label]) for label in LABELS}
        if sum(counts[model].values())!=1033:raise ValueError('Partition denominator mismatch')
        if counts[model]['不可判定']==0 and sum(counts[model][k] for k in LABELS[:4])!=1033:raise ValueError('Four-class sum mismatch')
        for label in LABELS:comparisons.append(dict(model=model,category=label,left=[False]*1033,right=vectors[label]))
    statistics=paired_family(comparisons,groups,resamples=10000,seed=42)
    table=[]
    for r in statistics:
        table.append(dict(model=r['model'],category=r['category'],count=r['right_correct'],denominator=1033,percent=r['delta_pp'],ci_low_percent=r['ci_low_pp'],ci_high_percent=r['ci_high_pp'],family_ci_low_percent=r['holm_ci_low_pp'],family_ci_high_percent=r['holm_ci_high_pp'],components=564,resamples=10000,seed=42,interval_method=r['interval_method'],status='描述性、未预注册；优先级定义为事后设定'))
    out.mkdir(parents=True)
    buffer=io.StringIO();w=csv.DictWriter(buffer,fieldnames=list(assignments[0]),lineterminator='\n');w.writeheader();w.writerows(assignments)
    (out/'assignments_v3.csv.gz').write_bytes(gzip.compress(buffer.getvalue().encode(),mtime=0))
    write_csv(out/'partition_v3.csv',table)
    write_json(out/'summary.json',dict(counts=counts,n_per_model=1033,models=5,rows=5165,components=564,bootstrap=10000,seed=42,definition='优先级定义为事后设定',inputs={str(p.relative_to(REPO)):sha(p) for p in (ledger,group_path,rule)},implementation_sha256=sha(Path(__file__)),interval_note='Descriptive category proportions, all-False reference; full 25-cell Bonferroni rectangle, not per-comparison Holm inversion; no causal or equivalence claims'))
    write_json(out/'manifest.json',{p.name:sha(p) for p in sorted(out.iterdir())})
    print(json.dumps(counts,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    build(parser.parse_args().out)
