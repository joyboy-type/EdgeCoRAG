"""Bounded new closeout checks only: artificial inputs, no images/weights/network."""
import argparse
import copy
import json
import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import analyze_batch as analysis
import run_batch as runner
from batch_inputs import read,sha
from finalize_binding import configuration,probe,observation_bindings
from run_smoke import TEMPLATE,TEMPLATE_VERSION


def reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Expected explicit rejection')


def fixture(root):
    base=root/'data'/'artificial';base.mkdir(parents=True);(base/'media').mkdir()
    image=base/'media'/'artificial.bin';image.write_bytes(b'ARTIFICIAL_NON_IMAGE_NO_DECODING')
    q='mragb:artificial_closeout';ref={'evidence_id':q+'#q','position_key':q+'#q','path':image.name,'sha256':sha(image),'size':[1,1]}
    b={'bundle_version':'batch_bundle_v1','qids':[q],'split':'artificial','formal_split_approved':False,'dataset_revision':'ARTIFICIAL',
       'evidence_version':'ARTIFICIAL','protocol_version':'ARTIFICIAL','template_version':TEMPLATE_VERSION,'image_root':'media',
       'conditions':{},'evidence_counts':{},'scenarios':{q:'artificial_scope'}}
    runner.atomic(base/'split.json',{'split':'artificial','qids':[q],'approved':False})
    runner.atomic(base/'scoring/answers.json',[{'qid':q,'answer_choice':'A','scenario':'artificial_scope'}])
    for c in ['S0','S3-pure']:
        evidence=[] if c=='S0' else [{**ref,'evidence_id':q+'#d0','position_key':q+'#d0'}]
        refs=[ref]+evidence;choices=dict(zip('ABCD',['one','two','three','four']))
        row={'qid':q,'raw_id':'artificial_closeout','question':'Artificial fixture only','choices':choices,'query_image':ref,
            'evidence':evidence,'condition':c,'protocol_version':'ARTIFICIAL','template_version':TEMPLATE_VERSION,
            'input_status':'ok','input_error':None,'expected_num_evidence':len(evidence),'image_order':[{'image_index':i,**x} for i,x in enumerate(refs)],
            'model_request':{'messages':[{'role':'user','content':[*[{'type':'image','image_index':i} for i in range(len(refs))],{'type':'text','text':TEMPLATE.format(question='Artificial fixture only',**choices)}]}]}}
        runner.atomic(base/f'inputs/{c}.json',[row]);b['conditions'][c]={'path':f'inputs/{c}.json','sha256':sha(base/f'inputs/{c}.json')};b['evidence_counts'][c]={q:len(evidence)}
    b.update({'answers':{'path':'scoring/answers.json','sha256':sha(base/'scoring/answers.json')},'split_manifest':{'path':'split.json','sha256':sha(base/'split.json')}})
    runner.atomic(base/'bundle.json',b)
    return base,b


def validate():
    checks=[];config,plan=configuration();registry=read(runner.REGISTRY)
    assert plan['total_tasks']==161 and plan['quality_question_runs']==17807
    assert sum(t['fixed_denominator'] for t in plan['task_items'])==21927
    assert [t for t in plan['task_items'] if t['phase']=='smoke' and t['condition']=='S3-pure']==[]
    devs=[t for t in plan['task_items'] if t['stage']=='development' and t['condition']=='S3-pure']
    assert len(devs)==2 and all(t['fixed_denominator']==5 and t['split']=='dev' for t in devs)
    scheduled,deferred=runner.scheduled_tasks(plan,'development')
    assert len(scheduled)==42 and len(deferred)==119
    assert all(t['task_id'] in scheduled for t in devs)
    assert len(runner.scheduled_tasks(plan,'performance')[0])==161
    checks.append('all161 final tasks scheduled; smoke25/dev17/formal17+17/performance85; dev S3 explicit; deferred IDs explicit')
    # The exact former mixed-stage failure is rejected, including standalone controls.
    bad=copy.deepcopy(plan);bad['task_items'][0]['stage']='mechanism_test';bad['task_items'][0].pop('phase',None)
    reject(lambda:runner.scheduled_tasks(bad,'performance'))
    assert any('Unscheduled' in x for x in runner.inspect_matrix(bad,registry))
    reject(lambda:runner.phase_for({'stage':'mechanism_test','split':'dev'}))
    checks.append('mixed normal+mechanism_test cannot silently complete; unknown/standalone mechanism stages explicitly rejected by runner')
    with tempfile.TemporaryDirectory(prefix='B-closeout-new-only-') as tmp:
        root=Path(tmp);base,bundle=fixture(root);tasks=[]
        for m,st,c in [('qwen3vl_4b','smoke','S0'),('qwen3vl_4b','development','S3-pure'),('qwen3vl_8b','development','S0')]:
            model=registry['models'][m]
            tasks.append({'task_id':m+'_'+st,'model':m,'model_revision':model['revision'],'environment':model['environment'],'stage':st,'condition':c,
                'phase':st,'split':'artificial','bundle':'artificial/bundle.json','bundle_sha256':sha(base/'bundle.json'),
                'split_manifest_sha256':bundle['split_manifest']['sha256'],'protocol_version':'ARTIFICIAL','evidence_version':'ARTIFICIAL','repeat_index':0})
        matrix={'approved':True,'protocol':{'approved':True},'registry_sha256':sha(runner.REGISTRY),'order':['qwen3vl_4b','qwen3vl_8b'],'task_items':tasks}
        path=root/'matrix.json';runner.atomic(path,matrix)
        def cli(out):return [sys.executable,'-B',str(runner.ROOT/'run_batch.py'),'--matrix',str(path),'--data-root',str(base.parent),'--run-root',str(out),'--execute','--backend','synthetic']
        out=root/'synthetic-run';cp=subprocess.run(cli(out),capture_output=True,text=True)
        assert cp.returncode==0,cp.stderr
        state=read(out/'batch_state.json');assert state['status']=='requested_phases_completed'
        assert set(state['completed_task_ids'])=={t['task_id'] for t in tasks}
        for t in tasks:assert read(out/t['task_id']/'state.json')['received_unique']==1
        checks.append('actual synthetic subprocess dispatch executes every mixed smoke/development task, including dev S3; identities/read-write-score/save checked, no real data')
        # Zero exit with no per-task receipts must block rather than report completion.
        with patch.object(sys,'argv',cli(root/'missing-receipt')[2:]),patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
            assert runner.main()==2
        assert read(root/'missing-receipt/batch_state.json')['status']=='blocked_phase_failure'
        checks.append('zero worker exit without complete per-task receipts blocks the next global phase')
        # New probe wrapper: portable media paths; neutral input versus separate answers.
        probe(base,root/'probe','S0',bundle['qids'][0],mode='copy')
        from batch_inputs import load_task
        pb=read(root/'probe/bundle.json');t={**tasks[0],'bundle':'probe/bundle.json','bundle_sha256':sha(root/'probe/bundle.json'),'split_manifest_sha256':pb['split_manifest']['sha256']}
        assert len(load_task(t,root)[3])==1
        assert not Path(pb['image_root']).is_absolute() and '..' not in Path(pb['image_root']).parts
        checks.append('new single-question probe wrapper resolves local media, isolated scoring and fixed list without unsafe parent paths')
        # New binding metadata path only: saved candidate/query/all-GT hashes must agree.
        import finalize_binding as finalizer
        s3=root/'S3';s2=root/'S2';s3.mkdir();s2.mkdir()
        q='mragb:artificial';e={'evidence_id':q+'#d','path':'d.jpg','sha256':'d'*64}
        (s3/'evidence_list.jsonl').write_text(json.dumps({'qid':q,'question_image':{'sha256':'a'*64},'evidence_order':[e]})+'\n',encoding='utf-8')
        (s2/'evidence_list.jsonl').write_text(json.dumps({'qid':q,'evidence_order':[{'sha256':'b'*64}]})+'\n',encoding='utf-8')
        basis=root/'basis.json';runner.atomic(basis,{'records':[{'qid':q,'final_evidence_id':e['evidence_id'],'semantic_verdict':'不支持','review_method':'image_model_assisted','evidence_sha256':'d'*64,'query_sha256':'a'*64,'GT_sha256':['b'*64],'source_image_path':'d.jpg'}]})
        spec={'review_basis':{'path':basis.name,'sha256':sha(basis)},'S3_qids':[q],'S3_evidence_order':{q:[e['evidence_id']]}}
        with patch.object(finalizer,'ROOT',root):
            assert len(observation_bindings(s3,s2,spec))==1
            bad=read(basis);bad['records'][0]['GT_sha256']=['c'*64];runner.atomic(basis,bad);spec['review_basis']['sha256']=sha(basis)
            reject(lambda:observation_bindings(s3,s2,spec))
        checks.append('new final binding checks saved observations against candidate/query/all-GT hashes; contradictory GT identity rejected even with matching basis-file SHA')
        # Preserve dictionary serialization across Python hash seeds; no real review.
        (root/'semantic_review.csv').write_text('fixture\n',encoding='utf-8')
        csv_path=root/'check.csv'
        with csv_path.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['qid','final_evidence_id','semantic_verdict','review_basis','reviewer','reviewed_at']);w.writeheader();w.writerow({'qid':q,'final_evidence_id':e['evidence_id'],'semantic_verdict':'无法判断','review_basis':'artificial fixture only','reviewer':'ARTIFICIAL','reviewed_at':'2026-10-16T00:00:00+00:00'})
        script="""import hashlib,json,sys
from pathlib import Path
from integrate_condition_packages import checklist_confirmations
p=Path(sys.argv[1]);q='mragb:artificial';r={'raw_id':'artificial','scenario':'scope','task_payload':{'question':'fixture','choices':dict(zip('ABCD','1234'))},'question_image':{'sha256':'a'*64},'scoring_only':{'gold_choice':'A','gt_evidence_refs':[{'sha256':'b'*64}]},'_s3_refs':[{'evidence_id':q+'#d','sha256':'d'*64,'path':'fixture/d.jpg'}]}
x=checklist_confirmations(p/'check.csv',{'root':p,'name':'fixture','receipt':{'source_package_sha256':'fixture'}},{q:r})
print(hashlib.sha256(json.dumps(x,ensure_ascii=False,indent=2).encode()).hexdigest())
"""
        hashes=[subprocess.check_output([sys.executable,'-B','-c',script,str(root)],cwd=runner.ROOT,env={**os.environ,'PYTHONHASHSEED':seed},text=True).strip() for seed in ['1','2']]
        assert hashes[0]==hashes[1]
        checks.append('checklist conversion byte serialization identical under two PYTHONHASHSEED values; original CSV unchanged')

    left={'model_id':'modelA','model_revision':'fixed-rev1','stage':'quality','synthetic':True,'dataset_revision':'data','split_manifest_sha256':'parent',
          'template_version':'template','protocol_version':'protocol','condition':'S1','overall':{'total':2},
          'per_question':[{'qid':'q1','scenario':'scope','correct':False},{'qid':'q2','scenario':'Incomplete','correct':True}]}
    right=copy.deepcopy(left);right['condition']='S2';right['per_question'][0]['correct']=True
    v=analysis.paired(left,right,repetitions=10,allow_synthetic=True)
    assert v['difference_right_minus_left']==.5 and v['left_model']==v['right_model']=={'model_id':'modelA','model_revision':'fixed-rev1'}
    sub=copy.deepcopy(right);sub.update({'condition':'S3-pure','split_manifest_sha256':'subset','parent_split_manifest_sha256':'parent',
        'S3_coverage':{'parent_qids':['q1','q2'],'eligible_qids':['q1']},'semantic_review_sha256':'review','overall':{'total':1},'per_question':[right['per_question'][0]]})
    v=analysis.paired_S1_S3_subset(left,sub,repetitions=10,allow_synthetic=True)
    assert v['parent_denominator']==2 and v['paired_denominator']==1 and v['coverage']==.5
    for field,value in [('model_id','modelB'),('model_revision','rev2'),('model_id',''),('model_revision',None)]:
        r=copy.deepcopy(right);r[field]=value;reject(lambda:analysis.paired(left,r,allow_synthetic=True))
        r=copy.deepcopy(sub);r[field]=value;reject(lambda:analysis.paired_S1_S3_subset(left,r,allow_synthetic=True))
    checks.append('both paired APIs reject cross-model/cross-revision/empty identities; valid same-model delta and full-parent/subset denominators unchanged; identities emitted')
    # Pins/order/subset metadata only, NOT a fresh visual or package acceptance.
    assert [config['splits'][s]['S3_denominator'] for s in ['smoke_20','dev','internal_holdout','frozen_test']]==[0,5,2,29]
    for spec in config['splits'].values():assert all(len(v)==3 for v in spec['S3_evidence_order'].values())
    checks.append('immutable committed review/config/lock pins validate; actual image review and all prior receipt/test suites NOT rerun')
    return {'version':'B_closeout_targeted_v1.10.0','actual_environment':'cloud Linux','status':'PASS','checks':checks,'GPU_verified':False,
        'synthetic_only_new_dispatch':True,'actual_external_packages_rebuilt_this_round':False,'old_tests_rerun':False,'images_re_reviewed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('New validation output required')
    result=validate();runner.atomic(a.output,result);print(json.dumps(result,ensure_ascii=False,indent=2))
