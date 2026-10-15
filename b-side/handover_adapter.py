"""Small loader for A-derived manifests; shared backend and strict scorer stay unchanged."""
from pathlib import Path
from run_smoke import TEMPLATE, TEMPLATE_VERSION, PROTOCOL, no_answers
from accept_handover import read, sha, resolve_image

def load_bundle(bundle_path,inputs_root,base,conditions):
    bundle_path=bundle_path.resolve();bundle=read(bundle_path)
    if bundle['baseline_commit']!='9a223095e829d4baec98c761038f84127d9f7f62':raise ValueError('Unexpected A baseline')
    if bundle['dataset_revision']!='43620fde4044bb150e158c67ad7af6b6b11e1da2':raise ValueError('Unexpected dataset revision')
    if (bundle['protocol_version'],bundle['template_version'])!=(PROTOCOL,TEMPLATE_VERSION):raise ValueError('Bundle protocol/template mismatch')
    if len(bundle['qids'])!=len(set(bundle['qids'])) or not bundle['qids']:raise ValueError('Invalid frozen qid list')
    bindings_path=bundle_path.parent/'audit/image_bindings.json'
    if sha(bindings_path)!=bundle['image_binding_sha256']:raise ValueError('Image binding manifest hash mismatch')
    bindings=read(bindings_path);manifests={}
    for condition in conditions:
        path=inputs_root/f'{condition}.json'
        if sha(path)!=bundle['input_sha256'][condition]:raise ValueError('Input manifest hash mismatch')
        rows=read(path)
        if [r['qid'] for r in rows]!=bundle['qids']:raise ValueError('Missing/duplicate/unknown manifest qid')
        for row in rows:
            no_answers(row)
            if not isinstance(row['raw_id'],str) or row['qid']!='mragb:'+row['raw_id']:raise ValueError('Namespaced id mismatch')
            if (row['condition'],row['protocol_version'],row['template_version'])!=(condition,PROTOCOL,TEMPLATE_VERSION):raise ValueError('Condition/template mismatch')
            if set(row['choices'])!=set('ABCD'):raise ValueError('Incomplete choices')
            refs=([row['query_image']] if row.get('query_image') else [])+row['evidence']
            if row['image_order']!=[{'image_index':i,**r} for i,r in enumerate(refs)]:raise ValueError('Image order mismatch')
            count=0 if condition=='S0' else (1 if bundle['scenarios'][row['qid']]=='Incomplete' else 5)
            if row['expected_num_evidence']!=count:raise ValueError('Unexpected evidence budget')
            text=TEMPLATE.format(question=row['question'],**row['choices'])
            expected={'messages':[{'role':'user','content':[*[{'type':'image','image_index':i} for i in range(len(refs))],{'type':'text','text':text}]}]}
            if row['model_request']!=expected:raise ValueError('Shared model request mismatch')
            errors=[]
            if row['input_status']=='ok' and len(row['evidence'])!=count:errors.append('Unexpected evidence count')
            # Binding and media failures are recorded on the original fixed row, never filtered.
            for ref in refs:
                binding=bindings.get(ref['position_key'])
                if not binding or binding['qid']!=row['qid'] or binding['raw_id']!=row['raw_id'] or any(binding[k]!=ref[k] for k in ['path','sha256','evidence_id','size']):
                    errors.append('Missing or mismatched image binding');continue
                try:
                    if sha(resolve_image(base,ref['path']))!=ref['sha256']:raise ValueError('Image hash mismatch')
                except Exception as e:errors.append(type(e).__name__+': '+str(e))
            if errors:
                row['input_status']='missing_or_invalid_image'
                row['input_error']='; '.join(filter(None,[row.get('input_error'),*errors]))
        manifests[condition]=rows
    return bundle,manifests

def result_metadata(row,record,model):
    """B-native result fields; not claimed to satisfy A's restrictive old result schema."""
    record.update({'raw_id':row.get('raw_id',row['qid']),'prediction_raw':record['raw_output'],
                   'prediction':record['parsed_choice'],'extraction_method':'strict_choice_v1',
                   'model_id':'synthetic/fixed_A_v1' if record['synthetic'] else model['model_id'],
                   'model_revision':None if record['synthetic'] else model['revision'],
                   'evidence_ids_order':[r.get('evidence_id',r['position_key']) for r in row['evidence']],
                   'protocol_version':row['protocol_version'],'prompt_template_version':row['template_version'],
                   'input_status':row.get('input_status','ok'),'input_error':row.get('input_error'),
                   'input_image_pixels':[r.get('size') for r in (([row['query_image']] if row.get('query_image') else [])+row['evidence'])]})
    if record['generation_error']:
        record['status']=row['input_status'] if row.get('input_status','ok')!='ok' else 'generation_failed'
    else:record['status']='ok' if record['parse_status']=='ok' else 'extraction_failed'
    return record

def s3_analysis_route(record):
    """Interface only: no distractor selection or ratio threshold is implemented."""
    if record.get('distractor_type') not in ['D1','D2']:raise ValueError('Only D1/D2 interface is in scope')
    if record.get('condition') not in ['S3-pure','S3-mixed']:raise ValueError('S3 is a category, not a concrete condition')
    semantic=record.get('semantic_status')
    if semantic not in ['confirmed_unsupportive','supports_answer','undetermined']:raise ValueError('Explicit semantic status required')
    return {**record,'analysis_subset':'diagnostic_only' if semantic=='undetermined' else ('excluded_supportive' if semantic=='supports_answer' else 'candidate_pending_protocol'),
            'formal_protocol_approved':False}
