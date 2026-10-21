"""One-command Q3-Q6 reproduction and independent aggregate checks; CPU only.

Default re-derives NEW temporary aggregates from immutable source archives and
compares bytes with the saved manifest. --checks-only performs read-only
inventory/numerator/partition/interval checks for fast requirement auditing.
"""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import tempfile
from quality_data import sha,read
from quality_closure import build,REPO


def table(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def verify(repo,work,out,recompute=True):
    out=Path(out);manifest=read(out/'manifest.json')
    for name,pin in manifest['files'].items():
        path=(out/name).resolve()
        if not path.is_relative_to(out.resolve()) or sha(path)!=pin['sha256'] or path.stat().st_size!=pin['bytes']:
            raise ValueError('Derived artifact mismatch: '+name)
    rows=table(out/'fixed_rag_matrix.csv');selection={r['model']:r for r in table(out/'dev_fixed_selection.csv')}
    if len(rows)!=60:raise ValueError('Four-path matrix incomplete')
    for row in rows:
        n=int(row['n']);correct=int(row['correct'])
        if n!=dict(smoke_20=20,dev=150,frozen_test=1033)[row['split']]:raise ValueError('Fixed denominator changed')
        if abs(float(row['percent'])-100*correct/n)>1e-12:raise ValueError('Ratio denominator drift')
        if sum(int(row[k]) for k in ('ok','empty_output','parse_failure','generation_error','missing_prediction'))!=n:
            raise ValueError('Failure types do not partition denominator')
        if row['path']=='P3' and row['selected_strategy']!=selection[row['model']]['selected']:raise ValueError('P3 selection changed after dev')
    for name,expected,family in [('paired_differences.csv',30,30),('source_cluster_ci.csv',20,20)]:
        pairs=table(out/name)
        if len(pairs)!=expected:raise ValueError('Comparison family incomplete')
        for row in pairs:
            if (int(row['n']),int(row['components']),int(row['resamples']),int(row['seed']),int(row['family_size']))!=(1033,564,10000,42,family):
                raise ValueError('Bootstrap/multiplicity contract mismatch')
            if abs(float(row['delta_pp'])-100*(int(row['right_correct'])-int(row['left_correct']))/1033)>1e-10:
                raise ValueError('Paired margins do not reconcile')
            if float(row['holm_ci_low_pp'])>float(row['ci_low_pp'])+1e-10 or float(row['holm_ci_high_pp'])<float(row['ci_high_pp'])-1e-10:
                raise ValueError('Conservative family rectangle is narrower than marginal interval')
    totals=defaultdict(int)
    for row in table(out/'mechanism_breakdown.csv'):totals[row['model'],row['strategy'],row['split']]+=int(row['count'])
    if len(totals)!=45 or any(n!=dict(smoke_20=20,dev=150,frozen_test=1033)[key[2]] for key,n in totals.items()):
        raise ValueError('Mechanism categories lost questions')
    if recompute:
        with tempfile.TemporaryDirectory(prefix='edgecorag-derived-verify-') as temp:
            fresh=Path(temp)/'derived';build(repo,work,fresh)
            for name,pin in manifest['files'].items():
                if sha(fresh/name)!=pin['sha256']:raise ValueError('Reproduction differs: '+name)
            if sha(fresh/'manifest.json')!=sha(out/'manifest.json'):raise ValueError('Reproduced manifest differs')
    return dict(status='verified',manifest_sha256=sha(out/'manifest.json'),fixed_matrix_rows=60,path_pairs=30,
                source_cluster_pairs=20,mechanism_cells=180,recomputed=recompute,old_scores_reparsed=False,gpu_started=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO);parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--artifact-dir',type=Path,required=True);parser.add_argument('--checks-only',action='store_true')
    args=parser.parse_args();print(json.dumps(verify(args.repo,args.work_dir,args.artifact_dir,not args.checks_only),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
