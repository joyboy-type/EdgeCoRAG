"""O2/O4/O5 supplements: explicit limits, derived cases and CPU shim validation.

Reproduce: $PY analysis/next_stage_20261019/offline_interface_supplements.py
 --work-dir <PRIVATE_WORK> --artifact-dir <QUALITY_ARTIFACTS> --verify
O2 ability replacement stays blocked; no numeric score or GPU measurement invented.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from quality_data import load,MODELS,STRATEGIES,sha,read,write_json,write_csv
from quality_stats import mechanism

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'b-side'))
import next_interface_bridge as bridge


def compute(repo,work,artifacts):
    repo=Path(repo);artifacts=Path(artifacts);data=load(repo,work);part=data['splits']['frozen_test']
    with (artifacts/'source_cluster_ci.csv').open(newline='') as stream:ci=list(csv.DictReader(stream))
    samples=[];cells=[]
    for model in MODELS:
        for strategy in STRATEGIES:
            contrast=next(row for row in ci if row['comparison']=='within_model_strategy' and row['left_model']==model
                and row['left_strategy']=='cosine' and row['right_strategy']==('random' if strategy=='random' else 'utility'))
            grouped={label:[] for label in ('retrieval_harm_proxy','not_retrieved','present_but_wrong','other')}
            for qid in part['qids']:
                pool_hit=bool(set(data['gold'][qid])&set(part['ranks'][qid]['corpus_ids']))
                label=mechanism(data['s0']['frozen_test',model,qid],part['outcomes'][model,strategy][qid],pool_hit)
                grouped[label].append(qid)
            if sum(len(ids) for ids in grouped.values())!=1033:raise ValueError('O2 partition mismatch')
            for label,ids in grouped.items():
                cells.append(dict(model=model,strategy=strategy,category=label,count=len(ids),n=1033,
                    replacement_inference='not_identified_by_current_protocol',
                    O1_left=contrast['left_strategy'],O1_right=contrast['right_strategy'],
                    O1_holm_ci_low_pp=float(contrast['holm_ci_low_pp']),O1_holm_ci_high_pp=float(contrast['holm_ci_high_pp']),
                    O1_scope='strategy contrast, not a preregistered ability-equivalence test'))
                chosen=sorted(ids,key=lambda q:hashlib.sha256(('O2-posthoc-v1:'+model+strategy+label+q).encode()).hexdigest())[:2]
                for qid in chosen:
                    samples.append(dict(model=model,strategy=strategy,qid=qid,category=label,
                        post_hoc_sample=True,selection_rule='first2 SHA256 per model/strategy/category',
                        s0_correct=data['s0']['frozen_test',model,qid],strategy_correct=part['outcomes'][model,strategy][qid],
                        O1_holm_ci_low_pp=float(contrast['holm_ci_low_pp']),O1_holm_ci_high_pp=float(contrast['holm_ci_high_pp']),
                        replacement_inference='not_supported; residual class is not proven ability replacement'))
    suite=unittest.defaultTestLoader.discover(str(repo/'tests'),pattern='test_next_interface_bridge.py')
    result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    if not result.wasSuccessful():raise ValueError('CPU bridge tests failed')
    validation=dict(status='cpu_shim_contract_passed_native_integration_pending',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        source_sha256=sha(repo/'b-side/next_interface_bridge.py'),requested_future_dtype='fp32',historical_dtype='unchanged_bf16',
        model_loaded=False,gpu_inference=False,native_A_schema_verified=False,
        blocker='a12/a15/a18 native scripts/artifacts are absent from this checkout; no A scripts modified',
        properties=['preserve A pool order','utility returns raw scores only','a12 callable owns outer boundary','utility separately timed','dimensions reported without selection','TF32 disabled and model parameter dtype checked','unavailable measurements cannot pass as0/null'])
    gaps=dict(status='declared_historic_gaps_and_new_capture_contract',source_sha256=sha(repo/'b-side/next_interface_bridge.py'),
        historical=[bridge.historical_gap(name) for name in ('rendered_prompt','device_total_peak_bytes','per_strategy_p95','system_ram_peak_bytes')],
        future_fields={'processor_rendered_prompt':'actual processor tokenize=False return; private string plus SHA256',
            'device_used_bytes_max_sampled':'whole-device sample maximum; not labelled an absolute peak',
            'device_total_peak_bytes':'only if a matching complete whole-device sampling trace supports the declared scope',
            'system_ram_peak_bytes':'separate measured system RAM trace; process RSS is not system RAM',
            'p95_seconds':'eligible measured requests only; declared minimum20 per strategy; warmups excluded'},
        gate='availability must be observed with a positive typed value; unavailable records contain no value field and fail require_observed',
        native_GPU_collection='not_executed')
    upgrade=dict(status='partially_blocked',original_proxy_partition='4 mutually exclusive categories sum1033 for each model/strategy',
        O1_strategy_pairs=15,O1_strategy_holm_intervals_cross_zero=sum(float(r['holm_ci_low_pp'])<=0<=float(r['holm_ci_high_pp']) for r in ci if r['comparison']=='within_model_strategy'),
        requested_class_D='evidence-supported ability replacement',
        blocker='Residual other cases do not establish ability substitution. All15 strategy Holm rectangles cross0; no preregistered equivalence/noninferiority or evidence intervention protocol exists.',
        result='Do not rename other as proven replacement; candidate cases and the relevant O1 intervals are supplied, not a new semantic accuracy',
        requirement_status='R21 remains partially complete; limited operational-proxy partition delivered, stronger O2 replacement claim is not completed')
    return {'mechanism_samples.csv':samples,'O2_partition_and_Holm_references.csv':cells,
        'O2_upgrade_limitations.json':upgrade,'O4_measurement_gap_contract.json':gaps,'O5_interface_validation.json':validation}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--work-dir',type=Path,required=True);parser.add_argument('--artifact-dir',type=Path,required=True)
    parser.add_argument('--verify',action='store_true');args=parser.parse_args();values=compute(args.repo,args.work_dir,args.artifact_dir)
    for name,value in values.items():
        path=args.artifact_dir/name
        if args.verify:
            if name.endswith('.json'):
                if read(path)!=value:raise ValueError('Supplement reproduction mismatch: '+name)
            else:
                stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(value[0]));writer.writeheader();writer.writerows(value)
                if path.read_bytes()!=stream.getvalue().encode():raise ValueError('Case table reproduction mismatch: '+name)
        elif name.endswith('.json'):write_json(path,value)
        else:write_csv(path,value)
    print(json.dumps(dict(status='verified' if args.verify else 'generated',samples=len(values['mechanism_samples.csv']),
        CPU_bridge_tests=values['O5_interface_validation.json']['tests'],O2_upgrade='blocked',O5_native='pending_A',GPU_executed=False),indent=2))

if __name__=='__main__':main()
