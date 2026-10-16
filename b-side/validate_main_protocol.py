"""Targeted v1.6 protocol/phase integration; artificial material only, no old suite rerun."""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from validate_batch_logic import fixture
from batch_inputs import read,sha,load_task
from protocol_rules import PROTOCOL,make_selection,evidence_count,published_candidates
from prepare_batch_inputs import prepare
import run_batch as runner
from model_adapters import FixedBackend
from analyze_batch import paired_S1_S3_subset,performance


def validate():
    checks=[];reg=read(runner.REGISTRY);model=reg['models']['qwen3vl_4b']
    with tempfile.TemporaryDirectory(prefix='edgecorag-main-v16-') as tmp:
        root=Path(tmp);_,_,_,source,index,split=fixture(root)
        rows=[json.loads(s) for s in source.read_text().splitlines()]
        with index.open(encoding='utf-8-sig',newline='') as f:idx=list(csv.DictReader(f))
        review={'by_qid':{}}
        def image_ref(row,role,rank):
            p=source.parent/(row['raw_id']+'_'+role+str(rank)+'.png')
            Image.new('RGB',(20+rank,16+rank),(rank*30,50,90)).save(p)
            eid=row['raw_id']+'_'+role+str(rank)
            ref={'evidence_id':eid,'path':p.name,'sha256':sha(p),'w':20+rank,'h':16+rank,
                 'retrieval_rank':rank,'retrieval_score':.5,'used_in_prompt':True}
            idx.append({'evidence_id':eid,'raw_id':row['raw_id'],'qid':row['qid'],'role':role,'rank':rank,
                        'path':p.name,'sha256':ref['sha256'],'w':ref['w'],'h':ref['h']})
            return ref
        for i,row in enumerate(rows):
            row['scenario']='Scope' if i==0 else 'Incomplete';row['pool_id']='official_retrieved_top5'
            candidates=[image_ref(row,'published',j) for j in range(5)]
            n=1 if i else 5
            for ref in candidates:ref['used_in_prompt']=ref['retrieval_rank']<n
            row['evidence_order']=candidates[:n];row['num_evidence']=n;row['retrieval_ranks']=list(range(n));row['retrieval_scores']=[.5]*n
            row['available_evidence_untruncated']={'retrieved_refs':candidates[n:]}
            gt=[image_ref(row,'actualGT',j) for j in range(1 if i else 5)]
            row['scoring_only']['gt_evidence_ids']=[r['evidence_id'] for r in gt]
            d1=[image_ref(row,'D1',j) for j in range(3)]
            review['by_qid'][row['qid']]={'review_id':'ARTIFICIAL_review_'+str(i),'distractor_type':'D1',
                'evidence':[{'evidence_id':r['evidence_id'],'semantic_status':'undetermined' if i and j==2 else 'confirmed_unsupportive'} for j,r in enumerate(d1)]}
        source.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        with index.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(idx[0]));w.writeheader();w.writerows(idx)
        review_path=root/'artificial_review.json';review_path.write_text(json.dumps(review))
        metadata={'dataset_revision':'ARTIFICIAL_ONLY','A_baseline_commit':'ARTIFICIAL_NOT_A_COMMIT',
                  'evidence_version':'ARTIFICIAL_MAIN','semantic_review_sha256':sha(review_path)}
        main=make_selection(rows,metadata);s3=make_selection(rows,metadata,review,True)
        assert [len(main['conditions']['S1']['by_qid'][r['qid']]['evidence_ids']) for r in rows]==[3,3]
        assert [len(main['conditions']['S2']['by_qid'][r['qid']]['evidence_ids']) for r in rows]==[5,1]
        assert s3['qids']==[rows[0]['qid']] and s3['S3_coverage']['diagnostic_only_qids']==[rows[1]['qid']]
        assert s3['S3_coverage']['coverage']==.5
        checks.append('main S1 is original ranked top3 for Scope/Incomplete; S2 retains actual5/1; D1 undetermined isolated')
        data=root/'external';data.mkdir()
        for name,selection in [('main',main),('s3',s3)]:
            sp=root/(name+'.selection.json');sp.write_text(json.dumps(selection));prepare(source,index,sp,split,data/name,semantic_review_path=review_path if name=='s3' else None)
            media=data/name/'media';media.mkdir()
            for p in source.parent.glob('*.png'):(media/p.name).write_bytes(p.read_bytes())
        def task(name,condition):
            b=read(data/name/'bundle.json')
            return {'task_id':name+'_'+condition.replace('-','_'),'model':'qwen3vl_4b','model_revision':model['revision'],
                'environment':model['environment'],'condition':condition,'stage':'mechanism_test','repeat_index':0,
                'split':b['split'],'bundle':name+'/bundle.json','bundle_sha256':sha(data/name/'bundle.json'),
                'split_manifest_sha256':b['split_manifest']['sha256'],'protocol_version':PROTOCOL,'evidence_version':b['evidence_version']}
        for c,counts,slots in [('S0',[0,0],[1,1]),('S1',[3,3],[4,4]),('S2',[5,1],[6,2])]:
            t=task('main',c);b,br,media,inputs=load_task(t,data,decode=True)
            assert [len(r['evidence']) for r in inputs]==counts
            assert [len(r['image_order']) for r in inputs]==slots
            for r in inputs:
                assert set(r['choices'])==set('ABCD')
                assert r['image_order'][0]['sha256']==r['query_image']['sha256']
                request=r['model_request']['messages'][0]['content']
                assert [x['image_index'] for x in request if x['type']=='image']==list(range(len(r['image_order'])))
                assert 'ARTIFICIAL_MAIN' not in request[-1]['text'] and 'confirmed_unsupportive' not in request[-1]['text']
        checks.append('query-first image objects/slots1,4,6/2; hashes/decodes/dimensions and neutral template validated')
        # Refuse a new-main S2 truncation or an S1 reordering, without touching original source.
        for c in ['S1','S2']:
            bad=copy.deepcopy(main);first=bad['conditions'][c]['by_qid'][rows[0]['qid']]
            first['evidence_ids']=list(reversed(first['evidence_ids'])) if c=='S1' else first['evidence_ids'][:3]
            sp=root/('bad'+c+'.json');sp.write_text(json.dumps(bad))
            try:prepare(source,index,sp,split,root/('bad-output-'+c))
            except ValueError:pass
            else:raise AssertionError('Invalid main selection accepted')
        checks.append('S1 rank changes and S2 forced-top3 truncation rejected')
        t=task('main','S1');run=root/'run'
        runner.run_task(t,model,data,run,lambda:FixedBackend(model))
        t3=task('s3','S3-pure')
        review_copy=data/'s3/audit/semantic_review.json';saved=review_copy.read_bytes();review_copy.unlink()
        broken=load_task(t3,data)[3]
        assert len(broken)==1 and broken[0]['input_status']=='missing_or_invalid_image'
        review_copy.write_bytes(saved)
        checks.append('actual semantic review SHA/selected IDs checked; missing review retains the fixed S3 row as failure')
        runner.run_task(t3,model,data,run,lambda:FixedBackend(model))
        left=read(run/t['task_id']/'score.json');right=read(run/t3['task_id']/'score.json')
        for score in [left,right]:score['stage']='quality';score['quality_result']=True
        result=paired_S1_S3_subset(left,right,repetitions=40,allow_synthetic=True)
        assert result['parent_denominator']==2 and result['paired_denominator']==1 and result['coverage']==.5
        assert len(left['per_question'])==2
        bad=copy.deepcopy(right);bad['S3_coverage']['eligible_qids']=['mragb:UNKNOWN']
        try:paired_S1_S3_subset(left,bad,repetitions=20,allow_synthetic=True)
        except ValueError:pass
        else:raise AssertionError('Mispaired S3 accepted')
        checks.append('S1/S3 restricted to same predeclared semantic subset; parent/subset coverage saved, full S1 unchanged')
        # New global phases are tested with synthetic subprocess stand-ins, not a GPU.
        _,_,_,inputs=load_task(t,data)
        original_task=copy.deepcopy(t)
        phase_tasks=[]
        for m in ['qwen3vl_4b','gemma4_e2b']:
            for stage,split_name in [('smoke','smoke_20'),('development','dev')]:
                d=copy.deepcopy(original_task);d.update({'task_id':m+'_'+stage,'model':m,'stage':stage,'split':split_name,
                    'model_revision':reg['models'][m]['revision'],'environment':reg['models'][m]['environment']})
                phase_tasks.append(d)
        matrix={'approved':True,'protocol':{'approved':True},'registry_sha256':sha(runner.REGISTRY),
                'order':['qwen3vl_4b','gemma4_e2b'],'task_items':phase_tasks}
        mp=root/'phases.json';mp.write_text(json.dumps(matrix));out=root/'phase-run';calls=[]
        real_subprocess=subprocess.run
        def child(cmd,*a,**kw):
            if '--worker-model' in cmd:
                phase=cmd[cmd.index('--phase')+1];key=cmd[cmd.index('--worker-model')+1];calls.append((phase,key))
                state={'tasks':[{'task_id':t['task_id'],'exit_code':0} for t in phase_tasks if t['model']==key and runner.phase_for(t)==phase]}
                runner.atomic(Path(cmd[cmd.index('--run-root')+1])/(key+'.'+phase+'.state.json'),state)
                return subprocess.CompletedProcess(cmd,0)
            return real_subprocess(cmd,*a,**kw)
        argv=['run_batch.py','--matrix',str(mp),'--data-root',str(data),'--run-root',str(out),'--execute']
        with patch.object(sys,'argv',argv),patch.object(runner.subprocess,'run',side_effect=child):assert runner.main()==0
        assert calls==[('smoke','qwen3vl_4b'),('smoke','gemma4_e2b'),('development','qwen3vl_4b'),('development','gemma4_e2b')]
        calls=[]
        def failing_child(cmd,*a,**kw):
            if '--worker-model' in cmd:
                phase=cmd[cmd.index('--phase')+1];key=cmd[cmd.index('--worker-model')+1];calls.append((phase,key))
                return subprocess.CompletedProcess(cmd,2 if key=='qwen3vl_4b' else 0)
            return real_subprocess(cmd,*a,**kw)
        argv[argv.index('--run-root')+1]=str(root/'failed-phase')
        with patch.object(sys,'argv',argv),patch.object(runner.subprocess,'run',side_effect=failing_child):assert runner.main()==2
        assert calls==[('smoke','qwen3vl_4b'),('smoke','gemma4_e2b')]
        checks.append('all-model phase order enforced; current-phase independent models continue after failure, later phases blocked')
        try:runner.phase_for({'stage':'quality','split':'frozen_test','phase':'smoke'})
        except ValueError:pass
        else:raise AssertionError('Frozen test relabeled as smoke')
        checks.append('formal split cannot bypass phase gate by relabeling')
        # Recheck durable new-main task output/resume/identity using the actual new input shape.
        before=(run/t['task_id']/'attempts.jsonl').read_bytes()
        runner.run_task(t,model,data,run,lambda:(_ for _ in ()).throw(AssertionError('Must skip completed')))
        assert (run/t['task_id']/'attempts.jsonl').read_bytes()==before
        for record in [json.loads(x) for x in before.decode().splitlines()]:
            assert record['raw_output']==record['prediction_raw'] and record['parser_version']=='strict_choice_v1'
        checks.append('new-main shape resumes without generation; raw aliases/parser version unchanged')
    assert all(m['dtype']=='bfloat16' and m['max_new_tokens']==64 and not m['thinking'] for m in reg['models'].values())
    assert not any(n in sys.modules for n in ['torch','transformers'])
    return {'version':'integrated_prerental_v1.6.0','actual_environment':'cloud Linux Python3.12; existing isolated Pillow audit env',
            'synthetic':True,'old_tests_rerun':False,'GPU_verified':False,'real_model_or_processor_loaded':False,
            'checks':checks,'passed_groups':len(checks)}


def validate_new_boundaries():
    from verify_external_package import verify
    from prepare_batch_inputs import read_split
    checks=[];reg=read(runner.REGISTRY)
    with tempfile.TemporaryDirectory(prefix='edgecorag-new-boundaries-') as tmp:
        root=Path(tmp);data,bundle,*_=fixture(root)
        tasks=[]
        for key in ['qwen3vl_4b','gemma4_e2b']:
            tasks.append({'task_id':key+'_control','model':key,'model_revision':reg['models'][key]['revision'],
                'environment':reg['models'][key]['environment'],'condition':'S1','stage':'development',
                'repeat_index':0,'split':bundle['split'],'bundle':'fixture/bundle.json','bundle_sha256':sha(data/'bundle.json'),
                'split_manifest_sha256':bundle['split_manifest']['sha256'],'protocol_version':bundle['protocol_version'],
                'evidence_version':bundle['evidence_version']})
        matrix={'approved':True,'protocol':{'approved':True},'registry_sha256':sha(runner.REGISTRY),
            'order':['qwen3vl_4b','gemma4_e2b'],'task_items':tasks}
        mp=root/'control.json';mp.write_text(json.dumps(matrix));out=root/'processes'
        cmd=[sys.executable,'-B',str(runner.ROOT/'run_batch.py'),'--matrix',str(mp),'--data-root',str(data.parent),
            '--run-root',str(out),'--backend','synthetic','--execute']
        result=subprocess.run(cmd,capture_output=True,text=True);assert result.returncode==0,result.stderr
        for key in matrix['order']:
            state=read(out/(key+'.development.state.json'));assert state['tasks'][0]['exit_code']==0
        before=(out/'qwen3vl_4b_control/attempts.jsonl').read_bytes()
        result=subprocess.run(cmd,capture_output=True,text=True);assert result.returncode==0,result.stderr
        assert (out/'qwen3vl_4b_control/attempts.jsonl').read_bytes()==before
        checks.append('new worker phase/fingerprint path exercised by two actual synthetic subprocesses; resume produces no duplicate attempt')
        media=data/'media';p=next(media.glob('*.png'));table=root/'hashes.csv'
        with table.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['rel_path','bytes','sha256']);w.writeheader();w.writerow({'rel_path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
        assert verify(media,table,True)['passed']
        raw=p.read_bytes();p.write_bytes(b'corrupt');assert not verify(media,table,True)['passed'];p.write_bytes(raw)
        checks.append('external hash-index verifier decodes artificial media and fails on corruption; never repairs/downloads')
        # Text split wrapper is checked against supplied pinned v2 metadata, without reading real questions.
        real_refs=read(runner.ROOT/'configs/a_delivery_refs.json')
        root_refs=copy.deepcopy(real_refs)
        split=root/'smoke_20.v2.txt';split.write_text('mragb:synthetic_only\n')
        root_refs['splits']['smoke_20']={'path':'a-side/splits/smoke_20.v2.txt','count':1,'sha256':sha(split)}
        import prepare_batch_inputs as prep
        real_read=prep.read
        def refs(path):
            if path.name=='a_delivery_refs.json':return root_refs
            return real_read(path)
        with patch.object(prep,'read',side_effect=refs):
            d=read_split(split);assert not d['approved'] and not d['source_group_isolation']
            d=read_split(split,True);assert d['approved'] and d['exposure_uncertainty_acknowledged'] and not d['exposure_registry_complete']
        checks.append('v2 text-list import verifies pinned hash/count and distinguishes explicit limitation acknowledgment from exhaustive exposure/source isolation')
    # Artificial timing numbers exist only in this unit check, never as experiment evidence.
    fake=[{'stage':'performance','synthetic':False,'model_id':'ARTIFICIAL_'+str(i//100),'model_revision':'ARTIFICIAL',
        'condition':'S1','protocol_version':PROTOCOL,'evidence_version':'ARTIFICIAL','run_batch_id':'ARTIFICIAL',
        'timing_hardware_id':'ARTIFICIAL_HOST_'+str(i//100),'actual_dtype':'ARTIFICIAL',
        'row_key':['ARTIFICIAL',i],'timing':{'generate_seconds':1,'end_to_end_seconds':2}} for i in range(200)]
    value=performance(fake,100);assert len(value['groups'])==2 and 'metrics' not in value
    try:performance(fake+[fake[0]],100)
    except ValueError:pass
    else:raise AssertionError('Duplicate performance observation accepted')
    assert performance(fake[:3],100)['metrics']['generate_seconds']['p95'] is None
    checks.append('performance groups isolate models/hosts; duplicate observations refused; n3 has no main-protocol P95')
    return {'synthetic':True,'GPU_verified':False,'old_tests_rerun':False,'checks':checks,'passed_groups':len(checks)}

if __name__=='__main__':
    a=validate();b=validate_new_boundaries();a['checks']+=b['checks'];a['passed_groups']+=b['passed_groups'];print(json.dumps(a,indent=2))
