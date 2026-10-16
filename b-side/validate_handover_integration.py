"""One bounded acceptance/new-adapter check; no old suites, weights or inference packages."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from accept_handover import inspect,convert,read,write,review_splits
import handover_adapter
import run_candidate
from score_minimal import evaluate

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--handover-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--split-root',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('New output directory required')
    rows,index,report=inspect(args.handover_root)
    # The six-row interface sample is independent of the unapproved full benchmark splits.
    assert [r['raw_id'] for r in rows]==['0','1','2','3','4','24']
    assert not report['schema_errors'] and not report['baseline_blob_errors'] and not report['global_errors']
    assert all(not r['errors'] and r['prompt_slots_match'] for r in report['rows'])
    assert report['decoded_images']==62 and report['indexed_images']==62
    assert report['unique_sha256_contents']==53
    assert [x['gt_count'] for x in report['rows']]==[5,5,5,5,5,1]
    assert report['fully_constructible_S2'] and report['has_incomplete']
    args.output.mkdir(parents=True)
    bundle=convert(rows,index,report,args.output/'derived')
    assert bundle['ready_by_condition']=={'S0':6,'S1':6,'S2':6}
    source=args.handover_root.resolve()/'samples'
    newroot=args.output/'derived'; inputs=newroot/'inputs'
    loaded,manifests=handover_adapter.load_bundle(newroot/'bundle.json',inputs,source,['S0','S1','S2'])
    objects=[]
    def loader(path):
        obj=object();objects.append(obj);return obj
    messages=run_candidate.build_messages(manifests['S1'][0],source,loader)
    assert [x['image'] for x in messages[0]['content'][:-1]]==objects and len(objects)==6
    assert all(set(x)=={'type','image'} for x in messages[0]['content'][:-1])
    # Inject a missing image through the loader boundary, without changing source files.
    original_sha=handover_adapter.sha
    def missing(path):
        if path.name=='q_1.jpg':raise FileNotFoundError('Artificial missing-image injection')
        return original_sha(path)
    handover_adapter.sha=missing
    try:
        _,damaged=handover_adapter.load_bundle(newroot/'bundle.json',inputs,source,['S0'])
    finally:handover_adapter.sha=original_sha
    class NeverGenerate:
        synthetic=True
        def infer(self,*args):raise AssertionError('Must not generate when input is invalid')
    broken=next(r for r in damaged['S0'] if r['raw_id']=='1')
    failure=run_candidate.prediction_for(broken,source,NeverGenerate())
    assert failure['generation_error'] and failure['input_status']=='missing_or_invalid_image'
    assert failure['raw_id']=='1' and failure['prediction_raw']==''
    assert len(damaged['S0'])==6
    answers=read(newroot/'scoring/answers.json')
    score=evaluate(answers,[failure])
    assert score['overall']['total']==6 and score['overall']['status_counts']['missing_prediction']==5
    run=args.output/'synthetic_run'
    child=subprocess.run([sys.executable,'-B',str(ROOT/'run_candidate.py'),'--sample-root',str(source),
        '--inputs-root',str(inputs),'--bundle-manifest',str(newroot/'bundle.json'),'--answers',str(newroot/'scoring/answers.json'),
        '--output',str(run),'--backend','synthetic'],capture_output=True,text=True,encoding='utf-8')
    assert child.returncode==0,(child.stdout,child.stderr)
    summary={}; all_predictions=[]
    for c in ['S0','S1','S2']:
        result=read(run/c/'score.json');pred=[json.loads(x) for x in (run/c/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        assert result['synthetic'] and result['overall']['total']==6
        assert [r['qid'] for r in pred]==bundle['qids']
        assert all(r['qid']=='mragb:'+r['raw_id'] and r['raw_output']==r['prediction_raw'] for r in pred)
        assert result['A_baseline_commit']==bundle['baseline_commit']
        assert all(r['generation_error'] is None and r['raw_output']=='A' for r in pred)
        assert result['input_failure_count']==0
        assert 'Incomplete' in result['scenarios'] and result['scenarios']['Incomplete']['total']==1
        assert all(r['evidence_version']==bundle['evidence_version'] and r['repeat_index']==0 for r in pred)
        all_predictions.extend(pred)
        summary[c]={'fixed_denominator':6,'input_failures':0,'synthetic':True}
    assert len({r['run_batch_id'] for r in all_predictions})==1
    assert len({tuple(r['row_key']) for r in all_predictions})==18
    incomplete=next(r for r in manifests['S1'] if r['raw_id']=='24')
    assert len(incomplete['evidence'])==1 and incomplete['evidence'][0]['evidence_id'].endswith('official_retrieved0')
    assert len(next(r for r in manifests['S2'] if r['raw_id']=='24')['evidence'])==1
    unused={r['evidence_id'] for r in rows[-1]['available_evidence_untruncated']['retrieved_refs']}
    assert unused.isdisjoint({r['evidence_id'] for r in incomplete['evidence']})
    # Null media in a failed row is preserved, not silently excluded or replaced.
    import copy
    failed_rows=copy.deepcopy(rows[:1]);failed_rows[0]['question_image']=None;failed_rows[0]['status']='missing_image'
    failed_path=args.output/'null_query_fixture'
    failed_bundle=convert(failed_rows,index,report,failed_path)
    failed_input=read(failed_path/'inputs/S0.json')[0]
    null_record=run_candidate.prediction_for(failed_input,source,NeverGenerate())
    assert null_record['qid']=='mragb:0' and null_record['generation_error'] and null_record['status']=='missing_image'
    routed=handover_adapter.s3_analysis_route({'condition':'S3-pure','distractor_type':'D1','semantic_status':'undetermined'})
    assert routed['analysis_subset']=='diagnostic_only' and routed['formal_protocol_approved'] is False
    split_review=review_splits(args.split_root)
    assert split_review['unique_qids']==1353 and not split_review['duplicate_qids']
    assert split_review['approved'] is False and split_review['adopted_as_formal_question_set'] is False
    write(args.output/'derived/audit/split_review.json',split_review)
    assert 'torch' not in sys.modules and 'transformers' not in sys.modules
    evidence={'baseline_commit':bundle['baseline_commit'],'acceptance':{'schema_errors':0,'baseline_blob_errors':0,'image_reference_positions_decoded':62,'unique_sha256_contents':53},
              'ready_by_condition':bundle['ready_by_condition'],'incomplete_in_A_sample':True,'split_review':split_review,
              'new_checks':['namespaced qid+raw_id mapping','shared neutral model messages and image ordering','fixed-denominator independent condition scoring',
                            'missing-image injection retains row','new GT S2 complete','Incomplete unused candidates excluded','shared batch and composite row keys','null query retained','S3 undetermined diagnostic routing','raw_output/prediction_raw alias'],
              'summary':summary,'torch_imported':False,'transformers_imported':False,'gpu_inference_verified':False,
              'stdout':child.stdout,'stderr':child.stderr}
    write(args.output/'integration_evidence.json',evidence)
    print('PASS: fixed A baseline, Draft202012 schema, 62 image reference hashes/decodes (53 unique contents), mapping/order, new adapter and failure retention.')
    print('S0/S1/S2 ready 6/6. GT counts 5,5,5,5,5,1; Incomplete prompt evidence=1, unused candidates excluded.')
    print('Synthetic pipeline: 18 records, one shared batch, 18 distinct composite row keys. Full benchmark splits remain unapproved; no model runtime imported.')

if __name__=='__main__':main()
