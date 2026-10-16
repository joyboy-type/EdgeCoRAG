"""One bounded mechanism suite: artificial images/questions only, no inference runtime."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import sys
from unittest.mock import patch
from PIL import Image
import batch_inputs as inputs
import run_batch as runner
from prepare_batch_inputs import prepare
from model_adapters import FixedBackend,final_text
from run_smoke import TEMPLATE_VERSION,no_answers
from analyze_batch import paired,performance


def fixture(root):
    src=root/'source';src.mkdir();index=[];originals=[];qids=['mragb:artificial_x','mragb:artificial_y']
    selection={'qids':qids,'dataset_revision':'ARTIFICIAL_ONLY','evidence_version':'ARTIFICIAL_ONLY',
               'protocol_version':'mechanism_only_v1','conditions':{c:{'source':{'S0':'none','S1':'official_clip_candidates','S2':'GT_images','S3-pure':'A_distractors'}[c],'by_qid':{}} for c in ['S0','S1','S2','S3-pure']}}
    for n,q in enumerate(qids):
        raw=q.split(':',1)[1];refs={}
        for pos,role in enumerate(['query','retrieved','gt','distractor']):
            p=src/(raw+'_'+role+'.png');Image.new('RGB',(16+pos,12+pos),(50*n,30*pos,128)).save(p)
            ref={'evidence_id':raw+'_'+role,'path':p.name,'sha256':inputs.sha(p),'w':16+pos,'h':12+pos,'used_in_prompt':True,'retrieval_rank':0,'retrieval_score':.5}
            refs[role]=ref
            index.append({'evidence_id':ref['evidence_id'],'raw_id':raw,'qid':q,'role':role,'rank':0,'path':p.name,'sha256':ref['sha256'],'w':ref['w'],'h':ref['h']})
        originals.append({'qid':q,'raw_id':raw,'question_image':refs['query'],'evidence_order':[refs['retrieved']],
            'num_evidence':1,'retrieval_ranks':[0],'retrieval_scores':[.5],'scenario':'artificial_scope' if n==0 else 'Incomplete',
            'task_payload':{'question':'Artificial fixture: choose the indicated option.','choices':dict(zip('ABCD',['one','two','three','four']))},
            'scoring_only':{'gold_choice':'B','gt_evidence_ids':[refs['gt']['evidence_id']]},'status':'ok'})
        for c,key in [('S0',None),('S1','retrieved'),('S2','gt'),('S3-pure','distractor')]:
            selection['conditions'][c]['by_qid'][q]={'evidence_ids':[] if key is None else [refs[key]['evidence_id']],
                'expected_num_evidence':0 if c=='S0' else 1,'distractor_type':'D1','semantic_status':'confirmed_unsupportive'}
    jp=src/'source.jsonl';jp.write_text(''.join(json.dumps(r)+'\n' for r in originals),encoding='utf-8')
    cp=src/'index.csv'
    with cp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
    sp=root/'selection.json';sp.write_text(json.dumps(selection),encoding='utf-8')
    split=root/'split.json';split.write_text(json.dumps({'qids':qids,'split':'artificial_mechanism','approved':False,'kind':'artificial'}),encoding='utf-8')
    out=root/'data'/'fixture';bundle=prepare(jp,cp,sp,split,out)
    (out/'media').mkdir()
    for p in src.glob('*.png'):(out/'media'/p.name).write_bytes(p.read_bytes())
    return out,bundle,sp,jp,cp,split


def validate():
    checks=[];registry=inputs.read(runner.REGISTRY);model=registry['models']['qwen3vl_4b']
    with tempfile.TemporaryDirectory(prefix='edgecorag-batch-mechanism-') as td:
        root=Path(td);data,bundle,selection,source,index,split=fixture(root)
        def task(condition='S1',name='test'):
            return {'task_id':name,'model':'qwen3vl_4b','model_revision':model['revision'],'environment':model['environment'],
                'condition':condition,'stage':'mechanism_test','repeat_index':0,'split':bundle['split'],
                'bundle':'fixture/bundle.json','bundle_sha256':inputs.sha(data/'bundle.json'),
                'split_manifest_sha256':bundle['split_manifest']['sha256'],'protocol_version':bundle['protocol_version'],
                'evidence_version':bundle['evidence_version']}
        # Explicit conversion/media decoding/order and leakage boundary for every condition.
        for c in ['S0','S1','S2','S3-pure']:
            b,_,_,rows=inputs.load_task(task(c),data.parent,decode=True)
            assert len(rows)==2
            assert [len(r['evidence']) for r in rows]==([0,0] if c=='S0' else [1,1])
            for row in rows:no_answers(row)
            sent=[]
            from run_candidate import build_messages
            messages=build_messages(rows[0],data/'media',lambda p:sent.append(object()) or sent[-1])
            assert [r['image'] for r in messages[0]['content'][:-1]]==sent
        checks.append('explicit A selection converts S0/S1/S2/S3; neutral fields, hashes, decode and ordered image objects')
        calls=[]
        class Count(FixedBackend):
            def infer(self,row,base):calls.append(row['qid']);return super().infer(row,base)
        t=task();out=root/'resume'
        def interrupt(r):raise KeyboardInterrupt('injected after fsync')
        try:runner.run_task(t,model,data.parent,out,lambda:Count(model),inject_stop=interrupt)
        except KeyboardInterrupt:pass
        else:raise AssertionError('Expected interrupt')
        assert len(calls)==1
        runner.run_task(t,model,data.parent,out,lambda:Count(model))
        assert len(calls)==2 and len(set(calls))==2
        runner.run_task(t,model,data.parent,out,lambda:Count(model))
        assert len(calls)==2
        assert inputs.read(out/'test/state.json')['received_unique']==2
        checks.append('interrupt after durable write -> resume skips complete record; repeated resume performs no generation')
        changed=copy.deepcopy(model);changed['max_new_tokens']+=1
        try:runner.run_task(t,changed,data.parent,out,lambda:Count(changed))
        except ValueError as e:assert 'fingerprint' in str(e)
        else:raise AssertionError('Changed configuration accepted')
        checks.append('changed configuration fingerprint rejected')
        journal=out/'test/attempts.jsonl';saved=journal.read_bytes()
        journal.write_bytes(saved+b'{"qid":')
        runner.run_task(t,model,data.parent,out,lambda:Count(model))
        assert journal.read_bytes()==saved and list(journal.parent.glob('*.torn-*'))
        for mutation in ['duplicate','unknown']:
            rows=[json.loads(s) for s in saved.decode().splitlines()]
            bad=copy.deepcopy(rows[0])
            if mutation=='unknown':bad['qid']='mragb:NOT_IN_FIXTURE'
            journal.write_bytes(saved+(json.dumps(bad)+'\n').encode())
            try:runner.run_task(t,model,data.parent,out,lambda:Count(model))
            except ValueError:pass
            else:raise AssertionError(mutation+' accepted')
        journal.write_bytes(saved)
        checks.append('torn tail preserved/recovered; duplicate attempt and unknown qid rejected')
        # OOM affects only this task/model; unattempted rows retain the fixed denominator.
        oomcalls=[]
        class OOM(FixedBackend):
            def infer(self,row,base):oomcalls.append(row['qid']);raise RuntimeError('CUDA out of memory: injected')
        out2=root/'oom';backend,stopped,okay=runner.run_task(t,model,data.parent,out2,lambda:OOM(model))
        assert stopped and not okay and len(oomcalls)==1
        score=inputs.read(out2/'test/score.json')
        assert score['overall']['total']==2 and score['overall']['status_counts']['missing_prediction']==1
        runner.run_task(t,model,data.parent,out2,lambda:Count(model),retry=True)
        history=[json.loads(s) for s in (out2/'test/attempts.jsonl').read_text().splitlines()]
        assert len(history)==3 and history[0]['oom'] and history[1]['attempt']==2
        checks.append('OOM stops before next generation; full denominator/missing queue; explicit retry retains first failure and attempt history')
        # Warmup >=3, fake HF backend only; no runtime imported.
        warmcalls=[]
        class Warm(FixedBackend):
            runtime={'test':'injected fake HF facade; not a GPU run'}
            def infer(self,row,base):warmcalls.append(row['qid']);return super().infer(row,base)
        runner.run_task(t,model,data.parent,root/'warm',lambda:Warm(model),backend_kind='hf')
        assert len(warmcalls)==5
        assert len(inputs.read(root/'warm/test/warmup.json')['records'])==3
        class WarmOOM(Warm):
            def infer(self,row,base):raise RuntimeError('CUDA out of memory: warmup injected')
        _,stopped,okay=runner.run_task(t,model,data.parent,root/'warmoom',lambda:WarmOOM(model),backend_kind='hf')
        assert stopped and not okay and not (root/'warmoom/test/attempts.jsonl').exists()
        checks.append('three unscored warmups; warmup OOM stops all scored generation')
        # Missing files become failures, not dropped rows.
        victim=data/'media/artificial_x_retrieved.png';vbytes=victim.read_bytes();victim.unlink()
        out3=root/'missing';before=len(calls)
        runner.run_task(t,model,data.parent,out3,lambda:Count(model))
        assert len(calls)==before+1
        score=inputs.read(out3/'test/score.json');assert score['overall']['total']==2
        assert json.loads((out3/'test/predictions.jsonl').read_text().splitlines()[0])['input_status']=='missing_or_invalid_image'
        victim.write_bytes(vbytes)
        checks.append('missing image retained as fixed-list failure; only ready row generated')
        # Missing input qid is an input contract error, not a silently smaller test.
        original=(data/'inputs/S1.json').read_bytes();r=json.loads(original);r.pop()
        (data/'inputs/S1.json').write_text(json.dumps(r));b=copy.deepcopy(bundle)
        b['conditions']['S1']['sha256']=inputs.sha(data/'inputs/S1.json');(data/'bundle.json').write_text(json.dumps(b))
        try:inputs.load_task(task(),data.parent)
        except ValueError as e:assert 'qid' in str(e)
        else:raise AssertionError('Missing input qid accepted')
        (data/'inputs/S1.json').write_bytes(original);(data/'bundle.json').write_text(json.dumps(bundle,indent=2))
        checks.append('missing fixed input qid rejected')
        class GemmaProcessor:
            def parse_response(self,text,prefix):return {'role':'assistant','content':'B','thinking':'A'}
        assert final_text('gemma4','A B','<thought>A</thought>B',GemmaProcessor(),'prefix')=='B'
        assert final_text('qwen35','<think>A</think>\nB','')=='\nB'
        try:final_text('qwen35','<think>unfinished A','')
        except ValueError:pass
        else:raise AssertionError('Unclosed thought accepted')
        for key,m in registry['models'].items():
            assert len(m['revision'])==40 and m['class'] in ['Qwen3VLForConditionalGeneration','Gemma4ForConditionalGeneration','Qwen3_5ForConditionalGeneration']
        checks.append('family-specific final boundary only; no answer-letter scan; five model pins/classes registered (not imported)')
        # Scenario-stratified pairing and source grouping use artificial scores only.
        s=inputs.read(out/'test/score.json');s['stage']='quality';s['quality_result']=True
        result=paired(s,s,repetitions=50,allow_synthetic=True)
        assert result['difference_right_minus_left']==0 and 'Incomplete' in result['scenarios']
        try:paired(s,s,groups={'source_ids':{}},allow_synthetic=True)
        except ValueError:pass
        else:raise AssertionError('Unfounded groups accepted')
        assert performance([{'stage':'performance','synthetic':False,'timing':{'generate_seconds':1,'end_to_end_seconds':2}}]*3)['metrics']['generate_seconds']['p95'] is None
        checks.append('paired/scenario analysis; unsupported grouping refused; 3 timing samples do not produce P95; no accuracy repeat rows')
    assert not any(name in sys.modules for name in ['torch','transformers'])
    return {'version':'batch_prepare_v1.5.0','synthetic_mechanism_only':True,'GPU_verified':False,
        'old_tests_rerun':False,'checks':checks,'passed':len(checks)}


def validate_controls():
    """Additional new batch-control boundaries; does not rerun validate()."""
    import argparse
    import subprocess
    from types import SimpleNamespace
    checks=[];registry=inputs.read(runner.REGISTRY)
    with tempfile.TemporaryDirectory(prefix='edgecorag-controls-') as td:
        root=Path(td);data,bundle,*_=fixture(root)
        def task(model,name,stage='development'):
            m=registry['models'][model]
            return {'task_id':name,'model':model,'model_revision':m['revision'],'environment':m['environment'],
                'condition':'S1','stage':stage,'repeat_index':0,'split':bundle['split'],
                'bundle':'fixture/bundle.json','bundle_sha256':inputs.sha(data/'bundle.json'),
                'split_manifest_sha256':bundle['split_manifest']['sha256'],'protocol_version':bundle['protocol_version'],
                'evidence_version':bundle['evidence_version']}
        tasks=[task('qwen3vl_4b','qwen_mechanism'),task('gemma4_e2b','gemma_mechanism')]
        matrix={'approved':True,'protocol':{'approved':True},'registry_sha256':inputs.sha(runner.REGISTRY),
            'order':['qwen3vl_4b','gemma4_e2b'],'task_items':tasks,'quality_formula':'ARTIFICIAL_ONLY'}
        mp=root/'matrix.json';mp.write_text(json.dumps(matrix))
        cmd=[sys.executable,'-B',str(runner.ROOT/'run_batch.py'),'--matrix',str(mp),'--data-root',str(data.parent),
            '--run-root',str(root/'process-run'),'--backend','synthetic','--execute']
        r=subprocess.run(cmd,capture_output=True,text=True);assert r.returncode==0,r.stderr
        for model,task_id in [('qwen3vl_4b','qwen_mechanism'),('gemma4_e2b','gemma_mechanism')]:
            assert inputs.read(root/'process-run'/(model+'.development.state.json'))['tasks'][0]['exit_code']==0
            assert inputs.read(root/'process-run'/task_id/'score.json')['synthetic'] is True
        r=subprocess.run(cmd,capture_output=True,text=True);assert r.returncode==0,r.stderr
        assert len((root/'process-run/qwen_mechanism/attempts.jsonl').read_text().splitlines())==2
        checks.append('two sequential model subprocesses; separate conditions/scores; same-configuration batch resume creates no duplicate attempts')
        altered=copy.deepcopy(matrix);altered['protocol']['new_setting']='changed';mp.write_text(json.dumps(altered))
        r=subprocess.run(cmd,capture_output=True,text=True);assert r.returncode!=0 and 'fingerprint' in r.stderr
        checks.append('parent batch fingerprint rejects changed protocol before model subprocesses')
        # Worker OOM policy is tested at the process/task boundary using a stub.
        states=[]
        fake=SimpleNamespace(close=lambda:states.append('closed'))
        def stop(*args,**kwargs):states.append(args[0]['task_id']);return fake,True,False
        matrix['task_items']=[task('qwen3vl_4b','first'),task('qwen3vl_4b','second')]
        args=argparse.Namespace(worker_model='qwen3vl_4b',backend='synthetic',data_root=data.parent,
            run_root=root/'worker-oom',retry_failures=False,allow_download=False)
        args.run_root.mkdir()
        with patch.object(runner,'run_task',side_effect=stop):assert runner.worker(args,matrix,registry)==2
        result=inputs.read(args.run_root/'qwen3vl_4b.state.json')
        assert states==['first','closed'] and result['tasks'][1]['status']=='blocked_after_model_oom'
        checks.append('worker OOM stops remaining same-model tasks and closes backend')
        broken=copy.deepcopy(matrix);broken['task_items']=[task('qwen3vl_4b','quality','quality')]
        assert any('prerequisite' in e for e in runner.inspect_matrix(broken,registry))
        broken['task_items'][0]['task_id']='../escape'
        assert 'Unsafe task_id' in runner.inspect_matrix(broken,registry)
        checks.append('quality prerequisites and unsafe task paths rejected')
    return {'synthetic_mechanism_only':True,'GPU_verified':False,'checks':checks,'passed':len(checks)}

if __name__=='__main__':
    a=validate();b=validate_controls();a['checks']+=b['checks'];a['passed']+=b['passed'];print(json.dumps(a,indent=2))
