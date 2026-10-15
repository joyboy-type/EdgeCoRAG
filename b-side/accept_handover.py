"""Read-only A handover audit and minimal B input conversion. No dataset/model downloads."""
import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath

from run_smoke import TEMPLATE, TEMPLATE_VERSION, PROTOCOL, no_answers

ROOT=Path(__file__).resolve().parent
BASELINE=json.loads((ROOT/'configs/a_handover_baseline.json').read_text(encoding='utf-8'))
REV='43620fde4044bb150e158c67ad7af6b6b11e1da2'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def resolve_image(root,name):
    p=PurePosixPath(name)
    if '\\' in name or p.is_absolute() or '..' in p.parts or ':' in name:
        raise ValueError('Unsafe image path: '+name)
    resolved=(root/Path(*p.parts)).resolve()
    if root not in resolved.parents: raise ValueError('Image escapes samples root')
    return resolved

def image_refs(row):
    """Audit/binding enumeration only; never use the untruncated pool to build S1."""
    available=row.get('available_evidence_untruncated') or {}
    return ([row['question_image']] if row.get('question_image') else [])+row['evidence_order']+available.get('retrieved_refs',[])+(row['scoring_only'].get('gt_evidence_refs') or [])+available.get('gt_refs',[])

def review_splits(split_root):
    """Report only. None of these lists is used as the inference/scoring question set."""
    manifest=read(split_root/'split_manifest.json');known=read(ROOT/'configs/debug_question_ids.json')
    assignments={};counts={};hashes={};duplicates=[]
    for name in ['smoke_20','dev','internal_holdout','frozen_test']:
        path=split_root/(name+'.txt');qids=[x.strip() for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
        counts[name]=len(qids);hashes[name]=sha(path)
        if hashes[name]!=manifest['splits'][name]['sha256']:raise ValueError('Split hash mismatch: '+name)
        for qid in qids:
            if qid in assignments:duplicates.append(qid)
            assignments[qid]=name
    return {'approved':False,'adopted_as_formal_question_set':False,'baseline_commit':BASELINE['commit'],
            'counts':counts,'unique_qids':len(assignments),'duplicate_qids':duplicates,'file_sha256':hashes,
            'known_exposed_assignments':{qid:assignments.get(qid) for qid in known['qids']},
            'reviewed_ids_forced_to_dev':manifest.get('reviewed_ids_forced_to_dev'),
            'group_by':manifest.get('group_by'),'rationale':manifest.get('rationale'),
            'group_isolation_verified':False,
            'blockers':['Known exposed questions remain in internal_holdout/frozen_test; reviewed_ids_forced_to_dev is empty.',
                        'group_by and rationale disagree; grouped source isolation is not established.',
                        'A and B must reconcile all touched IDs, revise split generation and update hashes. Known registry is a minimum, not exhaustive.'],
            'holdout_kind':'internal benchmark holdout, not external validation'}

def inspect(handover):
    from PIL import Image
    from jsonschema import Draft202012Validator
    root=handover.resolve(); samples=root/'samples'
    source=(samples/'evidence_sample.jsonl')
    rows=[json.loads(x) for x in source.read_text(encoding='utf-8').splitlines() if x.strip()]
    with (samples/'evidence_index.csv').open(encoding='utf-8-sig',newline='') as f: index=list(csv.DictReader(f))
    schema=read(root/'contracts/evidence_list.schema.json');Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema)
    index_by_id={}; faults=[];schema_errors=[];blob_errors=[];image_audit=[]
    # Baseline attestation is separate from row validation. Missing assets remain row failures.
    for name,expected in BASELINE['blob_sha1'].items():
        if not name.startswith('handover/'): continue
        p=root/name.removeprefix('handover/')
        if not p.is_file(): blob_errors.append({'path':name,'error':'missing_baseline_file'});continue
        b=p.read_bytes();actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if actual!=expected:blob_errors.append({'path':name,'error':'git_blob_mismatch'})
    for entry in index:
        eid=entry['evidence_id']
        if eid in index_by_id: faults.append('duplicate index evidence_id: '+eid)
        index_by_id[eid]=entry
    qids=set();raw_ids=set();details=[]
    for row in rows:
        errors=[];raw=row.get('raw_id');qid=row.get('qid')
        if not isinstance(raw,str) or qid!='mragb:'+raw: errors.append('raw_id/qid mapping mismatch')
        if qid in qids or raw in raw_ids:errors.append('duplicate qid/raw_id')
        qids.add(qid);raw_ids.add(raw)
        for error in validator.iter_errors(row):
            schema_errors.append({'qid':qid,'path':'/'.join(map(str,error.path)),'message':error.message})
            errors.append('schema: '+error.message)
        if row['provenance']['dataset_repo']!='uclanlp/MRAG-Bench' or row['provenance']['dataset_revision']!=REV:
            errors.append('dataset provenance mismatch')
        choices=row.get('task_payload',{}).get('choices')
        if not isinstance(choices,dict) or set(choices)!=set('ABCD') or not all(isinstance(v,str) and v.strip() for v in choices.values()):
            errors.append('four complete nonempty choices required')
        if not row.get('task_payload',{}).get('question'):errors.append('question missing')
        refs=row['evidence_order']
        if row['num_evidence']!=len(refs):errors.append('num_evidence/list mismatch')
        if row.get('retrieval_ranks') is not None and row['retrieval_ranks']!=[x.get('retrieval_rank') for x in refs]:errors.append('retrieval_ranks mismatch')
        if row.get('retrieval_scores') is not None and row['retrieval_scores']!=[x.get('retrieval_score') for x in refs]:errors.append('retrieval_scores mismatch')
        if [x.get('retrieval_rank') for x in refs]!=list(range(len(refs))):errors.append('official rank order is not ascending')
        unused=(row.get('available_evidence_untruncated') or {}).get('retrieved_refs',[])
        if any(r.get('used_in_prompt') is not False for r in unused):errors.append('Untruncated references must be marked used_in_prompt=false')
        if row['status']=='ok' and any(r.get('used_in_prompt',True) is not True for r in refs):errors.append('evidence_order contains an unused reference')
        expected_count=1 if row['scenario']=='Incomplete' else 5
        if row['status']=='ok' and len(refs)!=expected_count:errors.append('Official scenario evidence count mismatch')
        if row['scenario']=='Incomplete' and [r.get('retrieval_rank') for r in unused]!=[1,2,3,4]:errors.append('Incomplete unused candidate ranks mismatch')
        gt_refs=row['scoring_only'].get('gt_evidence_refs') or []
        if [r['evidence_id'] for r in gt_refs]!=(row['scoring_only'].get('gt_evidence_ids') or []):errors.append('GT ids/ref order mismatch')
        if row['status']=='ok' and len(gt_refs)!=expected_count:errors.append('Official GT count mismatch; never pad')
        for ref in image_refs(row):
            eid=ref['evidence_id'];idx=index_by_id.get(eid)
            expected_id=qid+'#'+ref['role']+('' if ref.get('rank') is None else str(ref['rank']))
            if eid!=expected_id:errors.append('evidence_id mapping mismatch: '+eid)
            if not idx:errors.append('missing indexed evidence: '+eid);continue
            for k in ['path','sha256','role']:
                if idx[k]!=ref[k]:errors.append('index mismatch '+k+': '+eid)
            if idx['qid']!=qid or idx['raw_id']!=raw:errors.append('index question mapping mismatch: '+eid)
            if idx['rank']!=('' if ref.get('rank') is None else str(ref['rank'])):errors.append('index rank mismatch: '+eid)
            item={'qid':qid,'evidence_id':eid,'path':ref['path'],'sha256':ref['sha256'],'declared_size':[ref['w'],ref['h']]}
            try:
                image=resolve_image(samples,ref['path'])
                if sha(image)!=ref['sha256']:raise ValueError('sha256 mismatch')
                with Image.open(image) as im:
                    im.load();size=list(im.size);im.convert('RGB').load()
                    if size!=[ref['w'],ref['h']] or size!=[int(idx['w']),int(idx['h'])]:raise ValueError('dimension mismatch')
                    item.update({'decoded':True,'size':size,'format':im.format})
            except Exception as e:
                item.update({'decoded':False,'error':type(e).__name__+': '+str(e)});errors.append(eid+': '+item['error'])
            image_audit.append(item)
        gt_ids=row['scoring_only'].get('gt_evidence_ids') or []
        missing_gt=[eid for eid in gt_ids if eid not in index_by_id]
        if not gt_ids:missing_gt=['GT list not supplied']
        details.append({'qid':qid,'raw_id':raw,'scenario':row['scenario'],'source_status':row['status'],
                        'errors':errors,'gt_ids':gt_ids,'unresolved_gt_ids':missing_gt,'gt_count':len(gt_refs),'unused_candidate_count':len(unused),
                        'prompt_slots_match':row.get('prompt_image_slots')==len(refs)+1})
    declared_ids={r['evidence_id'] for row in rows for r in image_refs(row)}
    if declared_ids!=set(index_by_id):faults.append('Orphan or unindexed image reference positions')
    package_content_hash=hashlib.sha256(source.read_bytes()+b'\0'+(samples/'evidence_index.csv').read_bytes()).hexdigest()
    report={'baseline_commit':BASELINE['commit'],'schema_validation':'Draft202012Validator',
            'source_path_root':'handover/samples (actual JSONL and CSV paths), not handover root as one schema description says',
            'questions':len(rows),'indexed_images':len(index),'decoded_images':sum(x['decoded'] for x in image_audit),
            'schema_errors':schema_errors,'baseline_blob_errors':blob_errors,'global_errors':faults,
            'rows':details,'image_audit':image_audit,'has_incomplete':any(x['scenario']=='Incomplete' for x in rows),
            'fully_constructible_S2':all(not d['unresolved_gt_ids'] for d in details),
            'image_reference_positions':len(image_audit),'unique_sha256_contents':len({r['sha256'] for r in image_audit}),
            'source_package_content_sha256':package_content_hash,
            'encoding':read(samples/'sample_meta.json').get('encoding'),
            'A_validator_review':'Read only: validate_handover_package checks serialization and assumes a local project_config path; validate_schema also imports local config and can return success when targets are absent. Neither was executed. No TLS bypass/environment commands executed.',
            'protocol_differences':['Exact GT-byte overlap is a retrieval hit, not automatically answer leakage; never used to filter S1.',
              'Incomplete remains in overall fixed denominator and is reported separately when present.',
              'Nonoverlapping hashes do not establish S3 semantic irrelevance.',
              'Benchmark holdout is internal, not external validation.',
              'A result extraction_method enum still lacks strict_choice_v1; parser_version accepts it. B-native records remain an explicit extension.',
              'A proto_official_v1 is retained as source metadata; B startup inputs use official_loader_smoke_v1, not an agreed formal protocol.']}
    return rows,index_by_id,report

def reference(ref):
    return {'position_key':ref['evidence_id'],'path':ref['path'],'sha256':ref['sha256'],'evidence_id':ref['evidence_id'],'size':[ref['w'],ref['h']]}

def convert(rows,index,report,output):
    issues={d['qid']:d for d in report['rows']};all_inputs={c:[] for c in ['S0','S1','S2']};answers=[];provenance=[]
    for row in rows:
        qid=row['qid'];query=reference(row['question_image']) if row.get('question_image') else None;detail=issues[qid]
        answers.append({'qid':qid,'raw_id':row['raw_id'],'answer_choice':row['scoring_only']['gold_choice'],'scenario':row['scenario']})
        for condition in all_inputs:
            status='ok';reasons=[];selected=[]
            if row['status']!='ok':status=row['status'];reasons.append('A source status: '+row['status'])
            if detail['errors']:status='handover_invalid';reasons+=detail['errors']
            count=0 if condition=='S0' else (1 if row['scenario']=='Incomplete' else 5)
            if condition=='S1':
                if row['pool_id']!='official_retrieved_top5':status='unsupported_pool';reasons.append('A reindexed/formal protocols not adopted')
                selected=[reference(r) for r in row['evidence_order'] if r.get('used_in_prompt',True) is True][:count]
            elif condition=='S2':
                gtids=row['scoring_only'].get('gt_evidence_ids') or []
                for eid in gtids[:count]:
                    if eid in index:
                        e=index[eid];selected.append(reference({**e,'w':int(e['w']),'h':int(e['h'])}))
                if detail['unresolved_gt_ids'] or len(selected)!=count:
                    status='missing_gt';reasons.append('GT image IDs have no complete explicit indexed files; no substitution/padding')
            if len(selected)!=count:
                if status=='ok':status='missing_evidence'
                reasons.append(f'Expected {count} evidence files, resolved {len(selected)}')
            if query is None:
                status='missing_image';reasons.append('Query reference is null; row retained')
            refs=([query] if query else [])+selected
            text=TEMPLATE.format(question=row['task_payload']['question'],**row['task_payload']['choices'])
            record={'qid':qid,'raw_id':row['raw_id'],'question':row['task_payload']['question'],'choices':row['task_payload']['choices'],
                    'query_image':query,'evidence':selected,'condition':condition,'protocol_version':PROTOCOL,'template_version':TEMPLATE_VERSION,
                    'input_status':status,'input_error':'; '.join(reasons) or None,'expected_num_evidence':count,
                    'image_order':[{'image_index':i,**ref} for i,ref in enumerate(refs)],
                    'model_request':{'messages':[{'role':'user','content':[*[{'type':'image','image_index':i} for i in range(len(refs))],{'type':'text','text':text}]}]}}
            no_answers(record);all_inputs[condition].append(record)
            provenance.append({'qid':qid,'raw_id':row['raw_id'],'condition':condition,'input_status':status,
                  'source_protocol':row['protocol_version'],'protocol_version':PROTOCOL,'baseline_commit':BASELINE['commit'],
                  'dataset':row['provenance'],'source':{'S0':'none','S1':'official_clip_candidates','S2':'A_declared_GT_unavailable' if status!='ok' else 'A_gt_images'}[condition],
                  'evidence_ids_order':[r['evidence_id'] for r in selected],
                  'retrieval_ranks':row.get('retrieval_ranks') if condition=='S1' else None,
                  'retrieval_scores':row.get('retrieval_scores') if condition=='S1' else None})
    for c,data in all_inputs.items():write(output/'inputs'/f'{c}.json',data)
    write(output/'scoring/answers.json',answers)
    write(output/'audit/handover_acceptance.json',report)
    write(output/'audit/selection_provenance.json',provenance)
    write(output/'audit/id_mapping.json',[{'raw_id':r['raw_id'],'qid':r['qid']} for r in rows])
    fixed={'bundle_version':'a_handover_b_adapter_v2','baseline_commit':BASELINE['commit'],'dataset_revision':REV,
           'evidence_version':'A-interface-sample-v2@'+BASELINE['commit']+'#sha256='+report['source_package_content_sha256'],
           'split_status':'REJECTED_PENDING_REVIEW; six-row interface fixture only, not a formal split',
           'protocol_version':PROTOCOL,'template_version':TEMPLATE_VERSION,'qids':[r['qid'] for r in rows],
           'input_sha256':{c:sha(output/'inputs'/f'{c}.json') for c in all_inputs},'answers_sha256':sha(output/'scoring/answers.json'),
           'scenarios':{r['qid']:r['scenario'] for r in rows},
           'image_binding_sha256':sha(output/'audit/image_bindings.json') if (output/'audit/image_bindings.json').exists() else None,
           'ready_by_condition':{c:sum(r['input_status']=='ok' for r in data) for c,data in all_inputs.items()},
           'formal_protocol_frozen':False}
    bindings={}
    for row in rows:
        for r in image_refs(row):
            bindings[r['evidence_id']]={'qid':row['qid'],'raw_id':row['raw_id'],**reference(r)}
    write(output/'audit/image_bindings.json',bindings)
    fixed['image_binding_sha256']=sha(output/'audit/image_bindings.json')
    write(output/'bundle.json',fixed)
    return fixed

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--handover-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('New output directory required')
    rows,index,report=inspect(args.handover_root)
    args.output.mkdir(parents=True)
    bundle=convert(rows,index,report,args.output)
    print(json.dumps({'questions':report['questions'],'decoded_images':report['decoded_images'],'schema_errors':len(report['schema_errors']),
                      'baseline_blob_errors':len(report['baseline_blob_errors']),'ready_by_condition':bundle['ready_by_condition'],
                      'S2_complete':report['fully_constructible_S2']},indent=2))
