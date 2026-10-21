"""Compare archived failure denominators; never parse or rescore model output.
Reproduce: $PY analysis/next_stage_20261019/reconcile_export_failures.py --verify
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from quality_data import jsonl,sha
from export_official import SPLIT_STAGE
REPO=Path(__file__).resolve().parents[2]
OUT=Path('reports/next_stage_20261019/b_iface_fix_20261021/failure_denominators.json')

def build(repo):
    a=repo/'logs/B_predictions.jsonl.gz'
    b=repo/'logs/results_20261020/no_self_scored_outcomes.jsonl.gz'
    raw=jsonl(a);selected=[r for r in raw if r['condition'] in ('S0','S1','S2') and r['stage']==SPLIT_STAGE[r['split']]]
    no_self=jsonl(b)
    result=[]
    for path,rows,split_key in ((a,selected,'split'),(b,no_self,'cohort')):
        statuses=Counter(r['parse_status'] for r in rows)
        result.append(dict(file=str(path.relative_to(repo)),sha256=sha(path),denominator=len(rows),
            parser='strict_choice_v1 archived status copied; parser NOT rerun',
            split_counts=dict(sorted(Counter(r[split_key] for r in rows).items())),
            failure_counts=dict(sorted(statuses.items())),parse_failure=statuses['parse_failure']))
    if (len(raw),len(selected),len(no_self),result[0]['parse_failure'],result[1]['parse_failure'])!=(21927,20295,18045,117,79):
        raise ValueError('Published denominator/failure count differs; do not silently repair')
    return dict(status='reconciled_different_scopes',sources=result,
        conclusion='117: B_predictions strict_choice_v1，S0/S1/S2主stage、含internal_holdout的四split，20295槽位；79: no_self_scored_outcomes 同解析器、三策略三split无holdout，18045行。文件/条件/split/分母不同，不能直接比较。',
        model_loaded=False,outputs_reparsed=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args()
    result=build(REPO);data=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.verify:
        if (REPO/OUT).read_text()!=data:raise ValueError('Reconciliation output differs')
    else:(REPO/OUT).write_text(data)
    print(data,end='')
if __name__=='__main__':main()
