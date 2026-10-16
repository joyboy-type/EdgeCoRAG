"""One targeted round for new condition-package interfaces; no model/downloads."""
import argparse
import copy
import csv
import json
from pathlib import Path
import random
import shutil
import tempfile

from PIL import Image
from accept_handover import REV
from batch_inputs import read,sha,load_task
from integrate_condition_packages import integrate,full_digest,BASE
from model_adapters import FixedBackend
import run_batch


def write_package(root,condition,originals,source_root=None):
    root.mkdir();index=[];rows=[]
    for n,original in enumerate(originals):
        r=copy.deepcopy(original);q=r['qid'];rid=r['raw_id']
        if source_root:
            if condition=='S1':refs=(r['evidence_order']+(r.get('available_evidence_untruncated') or {}).get('retrieved_refs',[]))[:3]
            else:refs=r['scoring_only']['gt_evidence_refs']
            refs=copy.deepcopy(refs);query=copy.deepcopy(r['question_image'])
            for e in refs:e['used_in_prompt']=True
            for e in [query]+refs:
                old=source_root/e['path'];dest=root/e['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old,dest)
        else:
            role={'S1':'official_retrieved','S2':'gt','S3':'distractor'}[condition]
            count=3 if condition in ['S1','S3'] else (1 if r['scenario']=='Incomplete' else 5)
            refs=[]
            for k in range(-1,count):
                # Same relative paths across S1/S2/S3 deliberately hold different evidence bytes.
                path=f'images/{rid}/'+('query.png' if k==-1 else f'e{k}.png')
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
                rng=random.Random(1000+n*100+(k+1)*10+(0 if k==-1 else {'S1':1,'S2':2,'S3':3}[condition]))
                im=Image.new('RGB',(24,24));im.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(576)]);im.save(p)
                role_k='q' if k==-1 else role;rank=None if k==-1 else k
                e={'evidence_id':q+'#'+role_k+('' if rank is None else str(rank)),
                    'role':role_k,'rank':rank,'path':path,'sha256':sha(p),'w':24,'h':24}
                if k==-1:query=e
                else:e.update({'retrieval_rank':k if condition!='S2' else None,'retrieval_score':None,'used_in_prompt':True});refs.append(e)
        for e in [query]+refs:
            index.append({'evidence_id':e['evidence_id'],'raw_id':rid,'qid':q,'role':e['role'],'rank':'' if e['rank'] is None else e['rank'],
                'path':e['path'],'sha256':e['sha256'],'w':e['w'],'h':e['h']})
        r.update({'question_image':query,'evidence_order':refs,'num_evidence':len(refs),'prompt_image_slots':1+len(refs),
            'pool_id':{'S1':'official_retrieved_top3','S2':'gt_evidence','S3':'pure_distractor_d1'}[condition],
            'is_oracle':condition=='S2','retriever_id':None,'retrieval_ranks':[e.get('retrieval_rank') for e in refs],
            'retrieval_scores':[e.get('retrieval_score') for e in refs],'available_evidence_untruncated':None,'status':'ok',
            'provenance':{'dataset_revision':REV,'condition':condition}})
        r['scoring_only']['gt_evidence_refs']=refs if condition=='S2' else None
        r['scoring_only']['gt_evidence_ids']=([e['evidence_id'] for e in refs] if condition=='S2' else
            [q+'#gt'+str(k) for k in range(1 if r['scenario']=='Incomplete' else 5)] if condition=='S1' else [])
        rows.append(r)
    (root/'evidence_list.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    with (root/'evidence_index.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
    (root/'package_meta.json').write_text(json.dumps({'name':root.name,'package_version':root.name,'condition':condition,'dataset':{'revision':REV}}))
    if condition=='S3':
        with (root/'semantic_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['qid','final_evidence_id','semantic_verdict','fate','justification']);w.writeheader()
            for r in rows:
                for e in r['evidence_order']:w.writerow({'qid':r['qid'],'final_evidence_id':e['evidence_id'],'semantic_verdict':'不支持','fate':'kept','justification':'ARTIFICIAL rule-only label'})
    return rows


def task(output,condition,name='main'):
    b=read(output/name/'bundle.json');m=read(run_batch.REGISTRY)['models']['qwen3vl_4b']
    return {'task_id':'ARTIFICIAL_'+name+'_'+condition,'model':'qwen3vl_4b','model_revision':m['revision'],
        'environment':m['environment'],'condition':condition,'stage':'mechanism_test','repeat_index':0,
        'split':b['split'],'bundle':name+'/bundle.json','bundle_sha256':sha(output/name/'bundle.json'),
        'split_manifest_sha256':b['split_manifest']['sha256'],'protocol_version':b['protocol_version'],'evidence_version':b['evidence_version']}


def rejected(call):
    try:call()
    except ValueError:return
    raise AssertionError('Invalid cross-condition source was accepted')


def validate(legacy_six_root=None):
    checks=[]
    with tempfile.TemporaryDirectory(prefix='B-package-v17-') as td:
        root=Path(td)
        originals=[{'raw_id':str(i),'qid':'mragb:fixture_'+str(i),'scenario':'Scope' if i==0 else 'Incomplete','aspect':'ARTIFICIAL',
            'task_payload':{'question':'ARTIFICIAL interface question','choices':dict(zip('ABCD',['one','two','three','four']))},
            'scoring_only':{'gold_choice':'B','answer_text':'two'}} for i in range(2)]
        for r in originals:r['raw_id']=r['qid'].split(':',1)[1]
        s1,s2,s3=[root/x for x in ['art_s1','art_s2','art_s3']]
        p1=write_package(s1,'S1',originals);p2=write_package(s2,'S2',originals);p3=write_package(s3,'S3',originals)
        split=root/'split.json';split.write_text(json.dumps({'qids':[r['qid'] for r in originals],'split':'artificial_mechanism','approved':False,'kind':'artificial'}))
        out=root/'converted';receipt=integrate(s1,s2,split,out,s3)
        assert receipt['S3_coverage']==0 and not (out/'s3').exists()
        review=read(out/'audit/s3_review_adapter.json')
        assert all(e['admission_state']=='candidate' and e['semantic_status']=='undetermined' for r in review['by_qid'].values() for e in r['evidence'])
        assert review['source_review_sha256']==sha(s3/'semantic_review.csv')
        assert review['source_package_sha256']==full_digest(s3)[0]
        checks.append('CSV rule-only labels remain candidate; actual CSV/full-package hashes/evidence IDs and derived audit review IDs preserved; no formal S3')
        for c,counts,slots in [('S0',[0,0],[1,1]),('S1',[3,3],[4,4]),('S2',[5,1],[6,2])]:
            b,_,_,rows=load_task(task(out,c),out,True)
            assert [len(r['evidence']) for r in rows]==counts and [len(r['image_order']) for r in rows]==slots
            assert all(r['input_status']=='ok' for r in rows)
            for r in rows:
                assert r['image_order'][0]['sha256']==r['query_image']['sha256']
                assert 'gold_choice' not in json.dumps(r) and 'semantic_verdict' not in json.dumps(r)
            run_batch.run_task(task(out,c),read(run_batch.REGISTRY)['models']['qwen3vl_4b'],out,root/'synthetic_runs',lambda:FixedBackend({}))
        a=read(out/'main/inputs/S1.json')[0]['evidence'][0];b=read(out/'main/inputs/S2.json')[0]['evidence'][0]
        assert a['path']!=b['path'] and a['sha256']!=b['sha256']
        checks.append('Split condition pools retained; query-first neutral inputs; 0/3/5-or1 evidence and1/4/6-or2 slots; colliding relative paths isolated; synthetic output scored per condition')
        # Reject metadata/gold/query/rank/ID drift before runnable output.
        jp=s2/'evidence_list.jsonl';saved=jp.read_bytes()
        for key in ['question','choices','gold','query','rank','GT_ids','unknown','duplicate']:
            rr=copy.deepcopy(p2)
            if key=='question':rr[0]['task_payload']['question']='changed'
            elif key=='choices':rr[0]['task_payload']['choices']['A']='changed'
            elif key=='gold':rr[0]['scoring_only']['gold_choice']='D'
            elif key=='query':rr[0]['question_image']['sha256']='0'*64
            elif key=='rank':rr[0]['evidence_order'][0]['rank']=4
            elif key=='GT_ids':rr[0]['scoring_only']['gt_evidence_ids']=list(reversed(rr[0]['scoring_only']['gt_evidence_ids']))
            elif key=='unknown':rr[0]['qid']='mragb:unknown'
            else:rr.append(copy.deepcopy(rr[0]))
            jp.write_text(''.join(json.dumps(r)+'\n' for r in rr));rejected(lambda:integrate(s1,s2,split,root/('bad_'+key)))
        jp.write_bytes(saved)
        checks.append('Question/choices/independent gold/query/ID/rank drift and duplicate/unknown source qids rejected')
        # Missing one condition row is not silently excluded; canonical independent gold comes from another package.
        jp.write_text(json.dumps(p2[0])+'\n');ip=s2/'evidence_index.csv';saved_idx=ip.read_bytes()
        with ip.open(encoding='utf-8-sig',newline='') as f:ii=list(csv.DictReader(f))
        with ip.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(ii[0]));w.writeheader();w.writerows([r for r in ii if r['qid']==p2[0]['qid']])
        missing=root/'missing_row';integrate(s1,s2,split,missing)
        rows=read(missing/'main/inputs/S2.json');assert len(rows)==2 and rows[1]['input_status']=='input_unavailable'
        assert len(read(missing/'main/scoring/answers.json'))==2
        jp.write_bytes(saved);ip.write_bytes(saved_idx)
        image=s2/p2[1]['evidence_order'][0]['path'];image_saved=image.read_bytes();image.unlink()
        missing=root/'missing_image';integrate(s1,s2,split,missing)
        assert read(missing/'main/inputs/S2.json')[1]['input_status']=='input_unavailable'
        image.write_bytes(image_saved)
        checks.append('Missing condition row or media remains a failed fixed-denominator question; no GT padding/substitution')
        # Actual confirmation-shaped ARTIFICIAL artifacts test mechanics, not semantic efficacy.
        proof_file=root/'basis.txt';proof_file.write_text('ARTIFICIAL semantic review fixture, not real visual evidence')
        cf={'source_review_sha256':sha(s3/'semantic_review.csv'),'source_package_sha256':full_digest(s3)[0],'by_qid':{}}
        q=p3[0]['qid'];cf['by_qid'][q]={'evidence':[]}
        for e in p3[0]['evidence_order']:
            cf['by_qid'][q]['evidence'].append({'evidence_id':e['evidence_id'],'semantic_status':'confirmed_unsupportive',
                'method':'human_visual','reviewer':'ARTIFICIAL reviewer','rationale':'ARTIFICIAL test only','evidence_sha256':e['sha256'],
                'reviewed_query_sha256':p1[0]['question_image']['sha256'],'reviewed_gt_sha256':[g['sha256'] for g in p2[0]['evidence_order']],
                'basis_artifact':{'path':'basis.txt','sha256':sha(proof_file)}})
        cp=root/'confirmations.json';cp.write_text(json.dumps(cf));confirmed=root/'confirmed'
        result=integrate(s1,s2,split,confirmed,s3,cp)
        assert result['S3_confirmed_qids']==[q] and result['S3_coverage']==.5
        assert len(load_task(task(confirmed,'S3-pure','s3'),confirmed,True)[3])==1
        # Deleting a support artifact fails the same fixed row, not a reduced denominator.
        support=confirmed/'s3/audit/review_basis/basis.txt';support.unlink()
        rr=load_task(task(confirmed,'S3-pure','s3'),confirmed)[3]
        assert len(rr)==1 and rr[0]['input_status']=='missing_or_invalid_image'
        checks.append('Hashed independent per-evidence confirmation/basis/query/all-GT identities gate S3; declared same-question subset and coverage; runtime retains failure if review basis disappears')
        bad=copy.deepcopy(cf);bad['source_review_sha256']='0'*64;cp.write_text(json.dumps(bad))
        rejected(lambda:integrate(s1,s2,split,root/'bad_review',s3,cp));cp.write_text(json.dumps(cf))
        bad=copy.deepcopy(cf);bad['by_qid'][q]['evidence'][0]['reviewed_gt_sha256']=[];cp.write_text(json.dumps(bad))
        rejected(lambda:integrate(s1,s2,split,root/'bad_gt_review',s3,cp));cp.write_text(json.dumps(cf))
        rejected(lambda:integrate(s1,s2,split,root/'bad_pin',pins={'S1':'0'*64}))
        checks.append('Changed CSV/package pin and incomplete reviewed-GT identity rejected; formal split not approved by unpinned packages')
        # Duplicated bytes with distinct IDs are not three pure distractors.
        old=copy.deepcopy(p3);e0,e1=p3[0]['evidence_order'][:2]
        shutil.copyfile(s3/e0['path'],s3/e1['path']);p3[0]['evidence_order'][1]['sha256']=e0['sha256']
        (s3/'evidence_list.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in p3))
        with (s3/'evidence_index.csv').open(encoding='utf-8-sig',newline='') as f:ii=list(csv.DictReader(f))
        for row in ii:
            if row['evidence_id']==e1['evidence_id']:row['sha256']=e0['sha256']
        with (s3/'evidence_index.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(ii[0]));w.writeheader();w.writerows(ii)
        duplicate=root/'duplicate_bytes';receipt=integrate(s1,s2,split,duplicate,s3)
        assert 'Duplicate final S3 content bytes' in receipt['S3_duplicate_diagnostics'][q]
        assert 'S3 near duplicate of query/GT/final evidence' in receipt['S3_duplicate_diagnostics'][q]
        checks.append('Final-three mutual byte/near-duplicate and query/all-GT near-duplicate gate executed independently of mechanical semantic labels')
        if legacy_six_root:
            rows=[json.loads(line) for line in (legacy_six_root/'evidence_sample.jsonl').read_text().splitlines() if line.strip()]
            assert [r['raw_id'] for r in rows]==['0','1','2','3','4','24']
            legacy1=root/'known6_s1';legacy2=root/'known6_s2';write_package(legacy1,'S1',rows,legacy_six_root);write_package(legacy2,'S2',rows,legacy_six_root)
            legacy_split=root/'known6.json';legacy_split.write_text(json.dumps({'qids':[r['qid'] for r in rows],'split':'known_six_adapter_only','approved':False,'kind':'known_debug_fixture'}))
            converted=root/'known6';integrate(legacy1,legacy2,legacy_split,converted)
            for c in ['S0','S1','S2']:
                rr=load_task(task(converted,c),converted,True)[3];assert len(rr)==6 and all(r['input_status']=='ok' for r in rr)
                assert [len(r['evidence']) for r in rr]==([0]*6 if c=='S0' else [3]*6 if c=='S1' else [5]*5+[1])
            checks.append('Existing six IDs0,1,2,3,4,24 only: newly split-package adapter decode/hash/order and exactS0/S1/S2counts pass; not acceptance of A new formal packages')
    return {'version':'condition_adapter_v1.7.0','execution_environment':'cloud Linux; existing isolated Pillow audit env',
        'checks':checks,'passed_groups':len(checks),'synthetic_mechanism_checks':True,'old_test_suites_rerun':False,
        'actual_A_formal_packages_received':False,'real_model_loaded':False,'GPU_verified':False,'new_test_question_contents_opened':False}

def validate_checklist_delta():
    """v1.7.1 delta ONLY: synthetic A-finalized fields/checklist conversion."""
    import hashlib
    from integrate_condition_packages import load_package,full_digest
    checks=[]
    with tempfile.TemporaryDirectory(prefix='B-checklist-delta-') as td:
        root=Path(td)
        originals=[{'raw_id':'checklist_fixture','qid':'mragb:checklist_fixture','scenario':'Incomplete','aspect':'ARTIFICIAL',
            'task_payload':{'question':'ARTIFICIAL only','choices':dict(zip('ABCD',['one','two','three','four']))},
            'scoring_only':{'gold_choice':'B','answer_text':'two'}}]
        s1,s2,s3=[root/x for x in ['fixture_s1','fixture_s2','fixture_s3']]
        write_package(s1,'S1',originals);write_package(s2,'S2',originals);rows=write_package(s3,'S3',originals)
        for r in rows:
            r['retrieval_ranks']=[None]*len(r['evidence_order'])
            for e in r['evidence_order']:e['retrieval_rank']=None
        (s3/'evidence_list.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        with (s3/'evidence_index.csv').open(encoding='utf-8-sig',newline='') as f:index=list(csv.DictReader(f))
        h=hashlib.sha256()
        for i in sorted(index,key=lambda x:x['path']):h.update(i['path'].encode()+b'\0'+i['sha256'].encode()+b'\n')
        meta=read(s3/'package_meta.json');meta.update({'content_digest':h.hexdigest(),'content_digest_algorithm':'sha256','file_hashes_csv':'file_hashes.csv','content_digest_scope':'sorted path\\x00sha256\\n images only'})
        (s3/'package_meta.json').write_text(json.dumps(meta))
        with (s3/'file_hashes.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['rel_path','bytes','sha256']);w.writeheader()
            for i in index:w.writerow({'rel_path':i['path'],'bytes':(s3/i['path']).stat().st_size,'sha256':i['sha256']})
        fields=['qid','final_evidence_id','semantic_verdict','review_basis','reviewer','reviewed_at']
        pending=[{'qid':r['qid'],'final_evidence_id':e['evidence_id'],'semantic_verdict':'','review_basis':'','reviewer':'','reviewed_at':''} for r in rows for e in r['evidence_order']]
        checklist=s3/'review_checklist.csv'
        def save(records):
            with checklist.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
        save(pending);pinned=full_digest(s3)[0];media_digest=meta['content_digest']
        package=load_package(s3,'S3');assert package['receipt']['A_content_digest']==media_digest
        assert package['receipt']['A_digest_scheme']=='A_finalized_S3_sorted_path_NUL_sha256_LF'
        original=(s3/'evidence_list.jsonl').read_bytes()
        rows[0]['retrieval_ranks']=[0,None,None];rows[0]['evidence_order'][0]['retrieval_rank']=0
        (s3/'evidence_list.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        rejected(lambda:load_package(s3,'S3'))
        (s3/'evidence_list.jsonl').write_bytes(original)
        checks.append('New finalized S3 null retrieval ranks and sorted image-index digest accepted; nonnull/mixed finalized ranks rejected; positional ranks preserved')
        split=root/'split.json';split.write_text(json.dumps({'qids':['mragb:checklist_fixture'],'split':'artificial_delta','approved':False,'kind':'artificial'}))
        blank=root/'blank';result=integrate(s1,s2,split,blank,s3,checklist_path=checklist,review_method='human_visual')
        assert not result['S3_formal_admitted']
        trace=read(blank/'audit/s3_review_adapter.json');assert trace['source_checklist_sha256']==sha(checklist)
        assert len(trace['checklist_records'])==3
        checks.append('Blank checklist plus automatic source initial labels never admits S3; original checklist SHA and six fields retained')
        filled=[{**r,'semantic_verdict':'不支持','review_basis':'ARTIFICIAL visual-basis fixture only','reviewer':'ARTIFICIAL reviewer','reviewed_at':'2026-10-16T12:00:00+08:00'} for r in pending]
        save(filled)
        assert full_digest(s3)[0]!=pinned and load_package(s3,'S3')['receipt']['A_content_digest']==media_digest
        rejected(lambda:load_package(s3,'S3',pinned))
        unm=root/'method_missing';assert not integrate(s1,s2,split,unm,s3,checklist_path=checklist)['S3_formal_admitted']
        assisted_missing=root/'assisted_model_missing';assert not integrate(s1,s2,split,assisted_missing,s3,checklist_path=checklist,review_method='image_model_assisted')['S3_formal_admitted']
        checks.append('Filled CSV changes full metadata/review package hash while media digest stays unchanged; stale full pin rejected; no implicit human method or anonymous model assistance')
        before=checklist.read_bytes();confirmed=root/'confirmed';result=integrate(s1,s2,split,confirmed,s3,checklist_path=checklist,review_method='image_model_assisted',review_model='ARTIFICIAL_MODEL@fixture_revision')
        assert result['S3_formal_admitted'] and checklist.read_bytes()==before
        rr=read(confirmed/'s3/audit/semantic_review.json')
        proof=next(iter(rr['by_qid'].values()))['evidence'][0]['confirmation']
        assert proof['method']=='image_model_assisted' and proof['review_model']=='ARTIFICIAL_MODEL@fixture_revision'
        assert proof['checklist_record']['reviewed_at']=='2026-10-16T12:00:00+08:00'
        assert sha(confirmed/'s3/audit/review_basis/review_checklist.source.csv')==sha(checklist)
        assert load_task(task(confirmed,'S3-pure','s3'),confirmed,True)[3][0]['input_status']=='ok'
        assert 'review_basis' not in json.dumps(read(confirmed/'s3/inputs/S3-pure.json'))
        checks.append('Explicit artificial assisted review converts traceably with reviewer/model/time/basis and source bytes immutable; hashes checked at runtime; review/gold absent from generation inputs')
        unknown=copy.deepcopy(filled);unknown[0]['semantic_verdict']='无法判断';save(unknown)
        assert not integrate(s1,s2,split,root/'unknown',s3,checklist_path=checklist,review_method='human_visual')['S3_formal_admitted']
        save(filled+[filled[0]]);rejected(lambda:integrate(s1,s2,split,root/'duplicate_review',s3,checklist_path=checklist,review_method='human_visual'))
        bad=copy.deepcopy(filled);bad[0]['final_evidence_id']='unknown';save(bad);rejected(lambda:integrate(s1,s2,split,root/'unknown_id',s3,checklist_path=checklist,review_method='human_visual'))
        checks.append('Unknown semantic verdict excludes whole fixed3 subset; duplicate or unknown checklist evidence identities fail closed')
    return {'version':'checklist_delta_v1.7.1','checks':checks,'passed_groups':len(checks),'synthetic_only':True,
        'old_suites_rerun':False,'actual_formal_packages_received':False,'new_real_debug_ids_inspected':False,
        'real_semantic_review_performed':False,'GPU_verified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--legacy-six-root',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--checklist-delta-only',action='store_true');a=p.parse_args()
    result=validate_checklist_delta() if a.checklist_delta_only else validate(a.legacy_six_root);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'passed_groups':result['passed_groups'],'GPU_verified':False}))
