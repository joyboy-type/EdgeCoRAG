"""Rebuild HQ-authorized bindings from pinned external ZIPs/packages and saved reviews.

No network, model, source edits, review judgments or budget changes. All generated
inputs/gold/media bindings/results remain external. Existing destinations refuse
reuse; keep partial output/failure receipt for diagnosis, never overwrite reviews.
"""
import argparse
import copy
import json
from pathlib import Path

from batch_inputs import read, sha, checked, load_task
from bind_batch import bind
from integrate_condition_packages import integrate, link_file
from receive_release_packages import verify_archive
from run_batch import ROOT, atomic, inspect_matrix

CONFIG=ROOT/'configs/final_binding_v1.json'
PLAN=ROOT/'configs/task_matrix_draft.json'


def configuration():
    c=read(CONFIG);plan=read(PLAN)
    if plan['binding_config_sha256']!=sha(CONFIG):raise ValueError('Final binding config changed')
    for pin in c['pins']:checked(ROOT,pin)
    if c['A_commit']!='c0e0931d8ad8d640e9c8002516fea43a70049831':raise ValueError('Different A baseline')
    ids=[t['task_id'] for t in plan['task_items']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate final task ID')
    return c,plan


def probe(source,output,condition,qid,mode='hardlink'):
    """One fixed startup question. Independent gold is copied only to scoring/."""
    b=read(source/'bundle.json');rows=read(checked(source,b['conditions'][condition]))
    selected=[r for r in rows if r['qid']==qid]
    if len(selected)!=1:raise ValueError('Probe fixed qid missing/duplicated')
    original_split=read(checked(source,b['split_manifest']))
    atomic(output/'split.json',{**original_split,'qids':[qid],'probe_parent_qids':b['qids']})
    atomic(output/'inputs'/f'{condition}.json',selected)
    answers=read(checked(source,b['answers']))
    atomic(output/'scoring/answers.json',[r for r in answers if r['qid']==qid])
    result=copy.deepcopy(b)
    result.update({'qids':[qid],'conditions':{condition:{'path':f'inputs/{condition}.json','sha256':sha(output/'inputs'/f'{condition}.json')}},
        'split_manifest':{'path':'split.json','sha256':sha(output/'split.json')},
        'answers':{'path':'scoring/answers.json','sha256':sha(output/'scoring/answers.json')},
        'scenarios':{qid:b['scenarios'][qid]},'evidence_counts':{condition:{qid:b['evidence_counts'][condition][qid]}},
        # Relative to external output/probes/<stage>, no absolute machine path.
        'image_root':'media','formal_split_approved':False})
    for ref in selected[0]['image_order']:
        original=source/'media'/ref['path']
        if original.is_file():link_file(original,output/'media'/ref['path'],mode)
    atomic(output/'bundle.json',result)


def contract(data_root,bundle_name,expected_qids,condition):
    path=data_root/bundle_name;b=read(path)
    if b['qids']!=expected_qids:raise ValueError('Unexpected fixed qids/order: '+bundle_name)
    task={'bundle':bundle_name,'bundle_sha256':sha(path),'condition':condition,'stage':'mechanism_test',
        **{k:b[k] for k in ['split','protocol_version','evidence_version']},'split_manifest_sha256':b['split_manifest']['sha256']}
    _,root,_,rows=load_task(task,data_root,decode=False)
    # Stable IDs/hash/order only, no labels or question text in selection manifest.
    return {'qids':expected_qids,'input_failures':[{'qid':r['qid'],'status':r['input_status'],'error':r['input_error']} for r in rows if r['input_status']!='ok'],
        'selection':[{'qid':r['qid'],'images':[{'image_index':x['image_index'],'evidence_id':x.get('evidence_id',x['position_key']),
                      'path':x['path'],'sha256':x['sha256']} for x in r['image_order']]} for r in rows]}


def observation_bindings(s3_root,s2_root,spec):
    """Validate saved observations against actual refs; no new visual judgment."""
    records=read(checked(ROOT,spec['review_basis']))['records'];by={}
    for record in records:
        key=(record['qid'],record['final_evidence_id'])
        if key in by:raise ValueError('Duplicate saved observation')
        by[key]=record
    def rows(root):
        return {r['qid']:r for r in [json.loads(line) for line in (root/'evidence_list.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]}
    source=rows(s3_root);gt=rows(s2_root);verified=[]
    for q in spec['S3_qids']:
        row=source[q];refs=row['evidence_order']
        if [e['evidence_id'] for e in refs]!=spec['S3_evidence_order'][q]:raise ValueError('Observation order contradicts actual source array')
        for e in refs:
            r=by.get((q,e['evidence_id']))
            if not r or r.get('semantic_verdict')!='不支持' or r.get('review_method')!='image_model_assisted':raise ValueError('Saved observation does not confirm admitted evidence')
            if r['evidence_sha256']!=e['sha256'] or r['query_sha256']!=row['question_image']['sha256'] or sorted(r['GT_sha256'])!=sorted(x['sha256'] for x in gt[q]['evidence_order']):raise ValueError('Saved observation contradicts actual candidate/query/GT hashes; exclude/report, no HQ override')
            if r.get('source_image_path')!=e['path']:raise ValueError('Saved observation image path differs')
            verified.append({'qid':q,'evidence_id':e['evidence_id'],'sha256':e['sha256']})
    return verified


def rebuild(packages,archives,data_root,mode='hardlink'):
    c,plan=configuration()
    if data_root.exists():raise ValueError('New external data-root required; preserve previous bindings/results')
    target=data_root.resolve();packages=packages.resolve();archives=archives.resolve()
    for protected in [ROOT,packages,archives]:
        if target==protected or protected in target.parents:raise ValueError('Output must be separate from code, source packages and archives')
    data_root.mkdir(parents=True)
    try:
        transports=[]
        for asset in c['release']['assets']:
            verify_archive(archives/asset['name'],asset)
            transports.append({k:asset[k] for k in ['id','name','size','sha256']})
        selections={};sources={}
        for split,spec in c['splits'].items():
            # Materialize the pinned original v2 text, not a machine-specific repo path.
            text='\n'.join(spec['qids'])+'\n'
            destination=data_root/'fixed_lists'/Path(spec['split_file']['path']).name
            destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(text.encode('utf-8'))
            if sha(destination)!=spec['split_file']['sha256']:raise ValueError('Original v2 text bytes cannot be reconstructed')
            output=data_root/'integrated'/split
            report=integrate(packages/f'{split}_s1',packages/f'{split}_s2',destination,output,
                s3_root=packages/f'{split}_s3',pins=read(checked(ROOT,spec['package_pins'])),mode=mode,
                acknowledge=True,A_commit=c['A_commit'],checklist_path=checked(ROOT,spec['review_checklist']),
                review_method=c['review_method'],review_model=c['review_model'])
            observed=observation_bindings(packages/f'{split}_s3',packages/f'{split}_s2',spec)
            if report['S3_confirmed_qids']!=spec['S3_qids']:raise ValueError('Reviewed subset changed; retain failure and report contradiction, never pad or filter to fit')
            # Explicitly retain the limited assisted-review interpretation in every bundle/score.
            for kind in ['main','s3']:
                bp=output/kind/'bundle.json'
                if bp.exists():
                    b=read(bp)
                    if kind=='s3':
                        basis=checked(ROOT,spec['review_basis']);copy_to=bp.parent/'audit/review_observations.original.json';copy_to.write_bytes(basis.read_bytes())
                        b['semantic_support_artifacts'].append({'path':'audit/review_observations.original.json','sha256':sha(copy_to)})
                    b.update({'HQ_binding_config_sha256':sha(CONFIG),'review_method':c['review_method'] if kind=='s3' else None,
                        'review_limitations':c['review_limitations'],'review_scope':'supplemental_robustness_subset' if kind=='s3' else 'original_full_split',
                        'evidence_order_policy':'actual original ID order;88 claimed-semantic-order violations/114 unresolved preserved'})
                    atomic(bp,b)
            sources[split]={'packages':report['source_packages'],'review_basis':spec['review_basis'],'verified_observation_media_bindings':observed}
            for condition in ['S0','S1','S2']:
                selections[split+'/'+condition]=contract(data_root,f'integrated/{split}/main/bundle.json',spec['qids'],condition)
            if spec['S3_qids']:
                name=f'integrated/{split}/s3/bundle.json'
                selections[split+'/S3-pure']=contract(data_root,name,spec['S3_qids'],'S3-pure')
                for r in read(data_root/f'integrated/{split}/s3/inputs/S3-pure.json'):
                    if [x['evidence_id'] for x in r['evidence']]!=spec['S3_evidence_order'][r['qid']]:raise ValueError('Original reviewed S3 evidence order changed')
        first=c['splits']['smoke_20']['qids'][0]
        for stage,condition in [('preflight_single','S0'),('preflight_multi','S1')]:
            probe(data_root/'integrated/smoke_20/main',data_root/'probes'/stage,condition,first,mode)
        atomic(data_root/'selection_manifest.json',{'version':'actual_original_ID_order_v1','sources':sources,'selections':selections,
            'ordering_claim':'Original arrays frozen.88 semantic-order violations/114 unresolved retained; no reordering.',
            'config_sha256':sha(CONFIG),'review_method':c['review_method'],'review_limitations':c['review_limitations']})
        binding={'approved':True,'scope':'full_required','protocol':plan['protocol'],'tasks':copy.deepcopy(plan['task_items'])}
        atomic(data_root/'binding.json',binding)
        bind(data_root/'binding.json',data_root,data_root/'bound_matrix.json')
        matrix=read(data_root/'bound_matrix.json')
        errors=inspect_matrix(matrix,read(ROOT/'configs/model_registry.json'))
        if errors:raise ValueError('Final matrix blocked: '+'; '.join(errors))
        if matrix['quality_question_runs']!=plan['quality_question_runs']:raise ValueError('Bound question-run count differs')
        for task in matrix['task_items']:
            b=read(data_root/task['bundle'])
            if len(b['qids'])!=task['fixed_denominator']:raise ValueError('Task denominator differs from final plan')
        all_failures={k:v['input_failures'] for k,v in selections.items() if v['input_failures']}
        receipt={'version':'final_external_binding_v1.10.0','status':'bound_with_input_failures' if all_failures else 'bound',
            'source_parent_commit':c['B_source_commit'],'code_version':read(ROOT/'package_hashes.json')['version'],'code_manifest_sha256':sha(ROOT/'package_hashes.json'),'A_commit':c['A_commit'],'config_sha256':sha(CONFIG),
            'matrix_sha256':sha(data_root/'bound_matrix.json'),'selection_manifest_sha256':sha(data_root/'selection_manifest.json'),
            'ZIP_assets':transports,'task_counts':plan['task_counts'],'input_failures':all_failures,
            'failures_remain_in_denominator':True,'review_limitations':c['review_limitations'],
            'GPU_verified':False,'runtime_results_generated':False}
        # Bind all actual JSON/CSV metadata and review files; omit media byte copies,
        # whose content hashes are already pinned in source and selection manifests.
        receipt['generated_metadata']=[{'path':p.relative_to(data_root).as_posix(),'sha256':sha(p)} for p in sorted(data_root.rglob('*'))
            if p.is_file() and 'media' not in p.relative_to(data_root).parts]
        atomic(data_root/'binding_receipt.json',receipt)
        return receipt
    except Exception as e:
        atomic(data_root/'binding.failure.json',{'status':'failed_not_ready','error':type(e).__name__+': '+str(e),'GPU_verified':False})
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inspect',action='store_true',help='Check committed pins/counts only; no acquisition or data reads')
    p.add_argument('--asset-manifest',type=Path,help='Export pinned12-asset receiver manifest only, outside code')
    p.add_argument('--packages',type=Path);p.add_argument('--archives',type=Path);p.add_argument('--data-root',type=Path)
    p.add_argument('--media-mode',choices=['hardlink','copy'],default='hardlink')
    a=p.parse_args()
    if a.asset_manifest:
        c,_=configuration();target=a.asset_manifest.resolve()
        if target.exists() or target==ROOT or ROOT in target.parents:raise ValueError('New external manifest path required')
        atomic(target,{'version':c['version'],'assets':c['release']['assets']});print(sha(target))
    elif a.inspect:
        c,plan=configuration();print(json.dumps({'version':c['version'],'tasks':plan['total_tasks'],'task_counts':plan['task_counts'],'quality_question_runs':plan['quality_question_runs'],'GPU_verified':False},indent=2))
    else:
        if not all([a.packages,a.archives,a.data_root]):p.error('--packages/--archives/--data-root are required for rebuild')
        r=rebuild(a.packages,a.archives,a.data_root,a.media_mode);print(json.dumps({'status':r['status'],'matrix_sha256':r['matrix_sha256']}))
