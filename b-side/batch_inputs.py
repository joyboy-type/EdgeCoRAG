"""Explicit external batch bundle reader; no scoring answers are read here."""
import hashlib
import json
from pathlib import Path
from accept_handover import resolve_image
from run_smoke import TEMPLATE,TEMPLATE_VERSION,no_answers
from protocol_rules import PROTOCOL as MAIN_PROTOCOL,evidence_count,verified_D1


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def external(root,name):return resolve_image(Path(root).resolve(),name)
def checked(root,descriptor):
    path=external(root,descriptor['path'])
    if sha(path)!=descriptor['sha256']:raise ValueError('External file hash mismatch: '+descriptor['path'])
    return path

def load_task(task,data_root,decode=False):
    bundle_path=external(data_root,task['bundle'])
    if sha(bundle_path)!=task['bundle_sha256']:raise ValueError('Task bundle hash mismatch')
    bundle=read(bundle_path);root=bundle_path.parent
    if bundle['bundle_version']!='batch_bundle_v1':raise ValueError('Explicit batch bundle required; legacy A6 is smoke-only')
    for key in ['evidence_version','protocol_version','split']:
        if task[key]!=bundle[key]:raise ValueError('Task/bundle '+key+' mismatch')
    qids=bundle['qids']
    if not qids or len(set(qids))!=len(qids):raise ValueError('Empty/duplicate fixed qids')
    if not all(isinstance(q,str) and q.startswith('mragb:') and len(q)>6 for q in qids):raise ValueError('Invalid project qids')
    split_path=checked(root,bundle['split_manifest'])
    if sha(split_path)!=task['split_manifest_sha256']:raise ValueError('Task split hash mismatch')
    split=read(split_path)
    if split['qids']!=qids or split['split']!=bundle['split']:raise ValueError('Fixed-list split mismatch')
    if task['stage']=='quality':
        if bundle['protocol_version']!=MAIN_PROTOCOL:raise ValueError('Formal quality requires frozen main protocol')
        if bundle['dataset_revision']!='43620fde4044bb150e158c67ad7af6b6b11e1da2':raise ValueError('Unexpected formal MRAG data revision')
        if len(bundle.get('A_baseline_commit') or '')!=40:raise ValueError('Formal A source commit required')
        if not split.get('approved') or not bundle.get('formal_split_approved'):raise ValueError('Unapproved formal split')
        if split.get('kind')!='internal_benchmark_holdout':raise ValueError('Quality holdout kind must be explicit')
        touched=set(read(Path(__file__).parent/'configs/debug_question_ids.json')['qids'])|set(split.get('all_touched_qids',[]))
        if touched.intersection(qids):raise ValueError('Exposed questions in independent holdout')
        if not split.get('exposure_registry_complete') and not split.get('exposure_uncertainty_acknowledged'):raise ValueError('Explicit exposure-reconciliation approval or uncertainty acknowledgment required')
    elif task['stage'] not in ['preflight_single','preflight_multi','smoke','development','performance','mechanism_test']:
        raise ValueError('Unknown task stage')
    if bundle['template_version']!=TEMPLATE_VERSION:raise ValueError('Unchanged shared template required')
    path=checked(root,bundle['conditions'][task['condition']]);rows=read(path)
    if [r['qid'] for r in rows]!=qids:raise ValueError('Missing/duplicate/unknown input qid or wrong order')
    media=external(root,bundle['image_root']);out=[];semantic_review=None;semantic_error=None
    if task['condition']=='S3-pure' and bundle['protocol_version']==MAIN_PROTOCOL:
        try:
            review_path=external(root,'audit/semantic_review.json')
            if sha(review_path)!=bundle['semantic_review_sha256']:raise ValueError('Semantic artifact SHA differs')
            semantic_review=read(review_path)
            if semantic_review.get('version')=='A_csv_review_adapter_v1':
                supports=bundle.get('semantic_support_artifacts',[])
                if not supports:raise ValueError('CSV-adapted review support artifacts missing')
                for descriptor in supports:checked(root,descriptor)
        except Exception as e:semantic_error=type(e).__name__+': '+str(e)
    for source in rows:
        # Whitelist neutral input fields. No GT/retrieval correctness/provenance enters backend messages.
        allowed={'qid','raw_id','question','choices','query_image','evidence','condition','protocol_version','template_version',
                 'input_status','input_error','expected_num_evidence','image_order','model_request'}
        if set(source)-allowed:raise ValueError('Unexpected generation fields: '+str(set(source)-allowed))
        row=dict(source);no_answers(row)
        if row['qid']!='mragb:'+row['raw_id'] or not isinstance(row['raw_id'],str):raise ValueError('raw_id mapping mismatch')
        if row['condition']!=task['condition'] or row['protocol_version']!=task['protocol_version']:raise ValueError('Condition/protocol mismatch')
        if row['template_version']!=TEMPLATE_VERSION:raise ValueError('Template mismatch')
        if set(row['choices'])!=set('ABCD') or not all(isinstance(v,str) and v.strip() for v in row['choices'].values()):raise ValueError('Four complete choices required')
        if not isinstance(row['question'],str) or not row['question'].strip():raise ValueError('Empty question')
        refs=([row['query_image']] if row['query_image'] else [])+row['evidence']
        if row['image_order']!=[{'image_index':i,**r} for i,r in enumerate(refs)]:raise ValueError('Image order mismatch')
        expected={'messages':[{'role':'user','content':[*[{'type':'image','image_index':i} for i in range(len(refs))],
                  {'type':'text','text':TEMPLATE.format(question=row['question'],**row['choices'])}]}]}
        if row['model_request']!=expected:raise ValueError('Neutral shared request mismatch')
        errors=[]
        if task['condition']=='S3-pure' and row['protocol_version']==MAIN_PROTOCOL:
            if semantic_error:errors.append('SemanticReviewUnavailable: '+semantic_error)
            elif verified_D1(semantic_review.get('by_qid',{}).get(row['qid']))!=[r['evidence_id'] for r in row['evidence']]:
                errors.append('Selected D1 images differ from reviewed evidence IDs')
        if not row['query_image']:errors.append('missing query image')
        if len(row['evidence'])!=row['expected_num_evidence']:errors.append('evidence count differs from explicit selection')
        if task['condition']=='S0' and (row['expected_num_evidence']!=0 or row['evidence']):raise ValueError('S0 must have no evidence')
        if row['expected_num_evidence']!=bundle['evidence_counts'][task['condition']][row['qid']]:raise ValueError('Frozen count mismatch')
        if row['protocol_version']==MAIN_PROTOCOL:
            if row['expected_num_evidence']!=evidence_count(task['condition'],bundle['scenarios'][row['qid']]):raise ValueError('Main protocol count mismatch')
            if task['condition']=='S1' and bundle['condition_sources']['S1']!='official_clip_candidates':raise ValueError('Main S1 source mismatch')
            if task['condition']=='S3-pure' and (not bundle.get('semantic_review_sha256') or not bundle.get('S3_coverage')):raise ValueError('Reviewed D1 subset contract missing')
        for ref in refs:
            try:
                p=external(media,ref['path'])
                if sha(p)!=ref['sha256']:raise ValueError('image SHA mismatch')
                if decode:
                    from PIL import Image
                    with Image.open(p) as im:
                        im.load()
                        if list(im.size)!=ref['size']:raise ValueError('Decoded dimensions differ')
            except Exception as e:errors.append(type(e).__name__+': '+str(e))
        if errors:
            row['input_status']='missing_or_invalid_image';row['input_error']='; '.join(filter(None,[row.get('input_error'),*errors]))
        out.append(row)
    if task['stage']=='preflight_single' and not any(r['input_status']=='ok' and not r['evidence'] for r in out):raise ValueError('Single-image probe missing')
    if task['stage']=='preflight_multi' and not any(r['input_status']=='ok' and r['evidence'] for r in out):raise ValueError('Multi-image probe missing')
    return bundle,root,media,out
