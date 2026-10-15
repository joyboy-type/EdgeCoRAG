"""Bind A's explicit selection manifest to neutral inputs; never choose a formal protocol."""
import argparse
import csv
import json
from pathlib import Path
import hashlib
import platform
import time
from protocol_rules import PROTOCOL as MAIN_PROTOCOL,published_candidates,evidence_count,make_selection,verified_D1
from accept_handover import reference,resolve_image
from batch_inputs import read,sha
from run_smoke import TEMPLATE,TEMPLATE_VERSION,no_answers
from run_batch import atomic


def read_split(path,acknowledge=False):
    if path.suffix.lower()!='.txt':return read(path)
    refs=read(Path(__file__).parent/'configs/a_delivery_refs.json')
    match=[(name,d) for name,d in refs['splits'].items() if Path(d['path']).name==path.name]
    if len(match)!=1 or sha(path)!=match[0][1]['sha256']:raise ValueError('A split filename/hash differs from pinned v2')
    name,d=match[0];qids=[s.strip() for s in path.read_text(encoding='utf-8').splitlines() if s.strip() and not s.lstrip().startswith('#')]
    if len(qids)!=d['count'] or len(set(qids))!=len(qids):raise ValueError('A split count/unique qids mismatch')
    return {'split':name,'qids':qids,'approved':acknowledge,'kind':'internal_benchmark_holdout' if name in ['internal_holdout','frozen_test'] else name,
        'A_commit':refs['commit'],'A_split_sha256':d['sha256'],'A_split_manifest_sha256':refs['split_manifest']['sha256'],
        'all_touched_qids':read(Path(__file__).parent/'configs/debug_question_ids.json')['qids'],
        'exposure_registry_complete':False,'exposure_uncertainty_acknowledged':acknowledge,
        'source_group_isolation':False,'limitation':'Known minimum exposure registry; v2 per-question fallback, cross-split image dependence remains.'}


def prepare(source_jsonl,index_csv,selection_path,split_path,output,acknowledge_split=False,semantic_review_path=None):
    if output.exists():raise ValueError('New output directory required')
    code=Path(__file__).resolve().parent;target=output.resolve();source_root=source_jsonl.parent.resolve()
    if target==code or code in target.parents or target==source_root or source_root in target.parents:
        raise ValueError('Keep generated data outside code and read-only A sources')
    selection=read(selection_path);split=read_split(split_path,acknowledge_split);semantic_review=None
    if selection['protocol_version']==MAIN_PROTOCOL and 'S3-pure' in selection['conditions']:
        if semantic_review_path is None or sha(semantic_review_path)!=selection.get('semantic_review_sha256'):
            raise ValueError('Actual semantic review artifact matching SHA-256 is required for main D1')
        semantic_review=read(semantic_review_path)
    parent_qids=list(split['qids'])
    if selection.get('S3_coverage'):
        coverage=selection['S3_coverage']
        if coverage['parent_qids']!=parent_qids or not set(selection['qids'])<=set(parent_qids):raise ValueError('S3 parent split mismatch')
        parent_hash=hashlib.sha256(json.dumps(split,ensure_ascii=False,indent=2).encode()).hexdigest()
        split={**split,'qids':selection['qids'],'parent_qids':parent_qids,'parent_split_manifest_sha256':parent_hash,'source_split_sha256':sha(split_path)}
    if selection['qids']!=split['qids']:raise ValueError('Selection/split fixed list differs')
    if not selection['qids'] or len(set(selection['qids']))!=len(selection['qids']):raise ValueError('Invalid selection qids')
    originals=[json.loads(s) for s in source_jsonl.read_text(encoding='utf-8').splitlines() if s.strip()]
    source={}
    for r in originals:
        if r['qid'] in source:raise ValueError('Duplicate source qid')
        if not isinstance(r['raw_id'],str) or r['qid']!='mragb:'+r['raw_id']:raise ValueError('Source ID mismatch')
        if r['num_evidence']!=len(r['evidence_order']):raise ValueError('A num_evidence/list mismatch')
        for field,key in [('retrieval_ranks','retrieval_rank'),('retrieval_scores','retrieval_score')]:
            if r.get(field) is not None and r[field]!=[x.get(key) for x in r['evidence_order']]:raise ValueError('A rank/score alignment mismatch')
        source[r['qid']]=r
    if set(selection['qids'])-set(source):raise ValueError('Missing fixed source rows; A must supply failure rows rather than omit qids')
    with index_csv.open(encoding='utf-8-sig',newline='') as f:index_rows=list(csv.DictReader(f))
    index={}
    for r in index_rows:
        if r['evidence_id'] in index:raise ValueError('Duplicate evidence ID')
        index[r['evidence_id']]=r
    counts={};conditions={};provenance=[]
    output.mkdir(parents=True)
    answers=[{'qid':q,'raw_id':source[q]['raw_id'],'answer_choice':source[q]['scoring_only']['gold_choice'],
              'scenario':source[q]['scenario']} for q in selection['qids']]
    atomic(output/'scoring/answers.json',answers)
    atomic(output/'split.json',split)
    for c,descriptor in selection['conditions'].items():
        if c not in ['S0','S1','S2','S3-pure']:raise ValueError('Unsupported concrete condition')
        rows=[];counts[c]={}
        for q in selection['qids']:
            a=source[q];pick=descriptor['by_qid'][q];selected=pick['evidence_ids'];errors=[]
            if len(set(selected))!=len(selected):raise ValueError('Duplicated evidence IDs; no padding allowed')
            if c=='S0' and selected:raise ValueError('S0 must be query only')
            if c=='S1':
                if descriptor['source'] not in ['official_clip_candidates','A_independent_reretrieval']:raise ValueError('Explicit S1 source required')
                eligible=([r['evidence_id'] for r in published_candidates(a)] if selection['protocol_version']==MAIN_PROTOCOL else
                          [r['evidence_id'] for r in a['evidence_order'] if r.get('used_in_prompt',True) is True])
                if selection['protocol_version']==MAIN_PROTOCOL and selected!=eligible[:3]:raise ValueError('Main S1 must use exact published top3, including Incomplete')
                if any(e not in eligible for e in selected):errors.append('S1 selection includes unused/unavailable source ref')
                if [eligible.index(e) for e in selected if e in eligible]!=sorted(eligible.index(e) for e in selected if e in eligible):raise ValueError('S1 original evidence order changed')
            if c=='S2':
                actual=a['scoring_only'].get('gt_evidence_ids',[])
                if selection['protocol_version']==MAIN_PROTOCOL and (selected!=actual or len(actual)!=evidence_count('S2',a['scenario'])):
                    raise ValueError('Main S2 must retain all actual GT in order,5/1; no top3 truncation')
                if any(e not in actual for e in selected):raise ValueError('S2 substitution outside GT refs')
                if [actual.index(e) for e in selected]!=sorted(actual.index(e) for e in selected):raise ValueError('GT order changed')
            if selection['protocol_version']==MAIN_PROTOCOL and pick['expected_num_evidence']!=evidence_count(c,a['scenario']):raise ValueError('Main protocol evidence count mismatch')
            if c=='S3-pure':
                if semantic_review is not None:
                    declared=semantic_review.get('by_qid',{}).get(q)
                    if not declared or verified_D1(declared)!=selected or pick.get('review_id')!=declared.get('review_id'):
                        raise ValueError('Selected D1 refs/review ID do not match actual semantic review artifact')
                if selection['protocol_version']==MAIN_PROTOCOL and (pick.get('distractor_type')!='D1' or not pick.get('review_id') or not selection.get('semantic_review_sha256')):
                    raise ValueError('Main S3 needs D1 review ID and semantic review artifact hash')
                if pick.get('distractor_type') not in ['D1','D2']:raise ValueError('Explicit D1/D2 required')
                if pick.get('semantic_status')!='confirmed_unsupportive':errors.append('S3 undetermined/supportive: diagnostic only; not formal-ready')
            evidence=[]
            for eid in selected:
                if eid not in index:errors.append('Unindexed evidence '+eid);continue
                i=index[eid]
                if i['qid']!=q or i['raw_id']!=a['raw_id']:raise ValueError('Index evidence/question ID mismatch')
                evidence.append(reference({**i,'w':int(i['w']),'h':int(i['h'])}))
            query=reference(a['question_image']) if a.get('question_image') else None
            if query is None:errors.append('missing query image')
            payload=a['task_payload']
            if set(payload['choices'])!=set('ABCD'):raise ValueError('Four complete options required')
            refs=([query] if query else [])+evidence
            for r in refs:
                try:
                    path=resolve_image(source_jsonl.parent.resolve(),r['path'])
                    if sha(path)!=r['sha256']:raise ValueError('Image hash mismatch')
                    from PIL import Image
                    with Image.open(path) as im:
                        im.load()
                        if list(im.size)!=r['size']:raise ValueError('Image dimensions mismatch')
                except Exception as e:errors.append(type(e).__name__+': '+str(e))
            text=TEMPLATE.format(question=payload['question'],**payload['choices'])
            row={'qid':q,'raw_id':a['raw_id'],'question':payload['question'],'choices':payload['choices'],
                'query_image':query,'evidence':evidence,'condition':c,'protocol_version':selection['protocol_version'],
                'template_version':TEMPLATE_VERSION,'input_status':'ok' if not errors and a['status']=='ok' else 'input_unavailable',
                'input_error':'; '.join(errors+([] if a['status']=='ok' else ['A status: '+a['status']])) or None,
                'expected_num_evidence':pick['expected_num_evidence'],'image_order':[{'image_index':i,**r} for i,r in enumerate(refs)],
                'model_request':{'messages':[{'role':'user','content':[*[{'type':'image','image_index':i} for i in range(len(refs))],{'type':'text','text':text}]}]}}
            no_answers(row);rows.append(row);counts[c][q]=pick['expected_num_evidence']
            provenance.append({'qid':q,'condition':c,'source':descriptor['source'],'selected_ids':selected,
                'selection_sha256':sha(selection_path),'A_source_sha256':sha(source_jsonl),'input_status':row['input_status'],
                'diagnostic_only':c=='S3-pure' and pick.get('semantic_status')!='confirmed_unsupportive',
                'semantic_status':pick.get('semantic_status'),'distractor_type':pick.get('distractor_type'),
                'review_id':pick.get('review_id'),'original_prompt_flags_overridden_by_main_top3':c=='S1' and selection['protocol_version']==MAIN_PROTOCOL})
        p=output/'inputs'/(c+'.json');atomic(p,rows);conditions[c]={'path':p.relative_to(output).as_posix(),'sha256':sha(p)}
    # Media are not copied. External deployment must provide the selected source media
    # under media/ preserving paths. A may hardlink locally; no images enter code Git.
    bundle={'bundle_version':'batch_bundle_v1','qids':selection['qids'],'split':split['split'],
        'formal_split_approved':split.get('approved',False),'dataset_revision':selection['dataset_revision'],
        'A_baseline_commit':selection.get('A_baseline_commit'),
        'evidence_version':selection['evidence_version'],'protocol_version':selection['protocol_version'],
        'template_version':TEMPLATE_VERSION,'conditions':conditions,'evidence_counts':counts,
        'image_root':'media','answers':{'path':'scoring/answers.json','sha256':sha(output/'scoring/answers.json')},
        'split_manifest':{'path':'split.json','sha256':sha(output/'split.json')},'selection_sha256':sha(selection_path),
        'scenarios':{q:source[q]['scenario'] for q in selection['qids']},
        'subset_parent_qids':selection.get('S3_coverage',{}).get('parent_qids') if selection.get('S3_coverage') else None,
        'S3_coverage':selection.get('S3_coverage'),'semantic_review_sha256':selection.get('semantic_review_sha256'),
        'selection_timing':selection.get('selection_timing'),'retrieval_timing':None,
        'retrieval_timing_note':'Published candidates; no retrieval executed, null is not measured zero.',
        'condition_sources':{c:d['source'] for c,d in selection['conditions'].items()},
        'diagnostic_only_qids':{c:[r['qid'] for r in provenance if r['condition']==c and r['diagnostic_only']] for c in conditions},
        'media_deployment':'Provide original selected files under media/ with unchanged relative paths; no media copied by this script.'}
    atomic(output/'audit/selection_provenance.json',provenance)
    if semantic_review is not None:(output/'audit/semantic_review.json').write_bytes(semantic_review_path.read_bytes())
    atomic(output/'bundle.json',bundle)
    return bundle

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['source-jsonl','index-csv','split','output']:p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--selection',type=Path)
    p.add_argument('--derive-main-selection',action='store_true')
    p.add_argument('--d1-review',type=Path)
    p.add_argument('--s3-only',action='store_true')
    p.add_argument('--acknowledge-split-limitations',action='store_true',help='Explicit approval of v2 exposure/dependence limitations; never claims source isolation')
    p.add_argument('--A-commit',default=read(Path(__file__).parent/'configs/a_delivery_refs.json')['commit'])
    a=p.parse_args()
    if bool(a.selection)==bool(a.derive_main_selection):raise ValueError('Select explicit manifest OR main-rule derivation')
    if a.derive_main_selection:
        started=time.perf_counter()
        rows=[json.loads(s) for s in a.source_jsonl.read_text(encoding='utf-8').splitlines() if s.strip()]
        metadata={'dataset_revision':'43620fde4044bb150e158c67ad7af6b6b11e1da2','A_baseline_commit':a.A_commit,
            'evidence_version':'A@'+a.A_commit+'#sha256='+hashlib.sha256(a.source_jsonl.read_bytes()+b'\0'+a.index_csv.read_bytes()).hexdigest(),
            'semantic_review_sha256':sha(a.d1_review) if a.d1_review else None}
        selection=make_selection(rows,metadata,read(a.d1_review) if a.d1_review else None,a.s3_only)
        selection['selection_timing']={'seconds':time.perf_counter()-started,'host':platform.platform(),
            'scope':'CPU source read and deterministic evidence selection only; not model or retrieval time'}
        a.selection=a.output.with_name(a.output.name+'.selection.json')
        if a.selection.exists():raise ValueError('Selection output already exists')
        atomic(a.selection,selection)
    b=prepare(a.source_jsonl,a.index_csv,a.selection,a.split,a.output,a.acknowledge_split_limitations,a.d1_review)
    print(json.dumps({'qids':len(b['qids']),'conditions':list(b['conditions']),'media_not_copied':True}))
