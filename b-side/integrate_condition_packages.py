"""Read-only A S1/S2/S3 package adapter. No dataset/model/network acquisition.

Original package IDs/pools/ranks are preserved. Only generated media paths are
namespaced. Gold is checked across packages and written only by the existing
independent scoring-file writer. CSV construction labels are NOT semantic proof.
"""
import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from accept_handover import resolve_image, REV
from batch_inputs import read, sha, fingerprint
from prepare_batch_inputs import prepare, read_split
from protocol_rules import make_selection, evidence_count
from run_batch import atomic

BASE='6e02a897869cb9bb8d8337afe0e6a7d07919f339'


def full_digest(root):
    """B full-file manifest SHA, distinct from A's qid/image-only content_digest."""
    entries=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('Symlinks are not allowed inside source packages')
        if p.is_file():entries.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    return fingerprint(entries),entries


def load_package(root,condition,expected=None):
    root=root.resolve();meta=read(root/'package_meta.json')
    if meta['condition']!=condition:raise ValueError('Package condition mismatch')
    if meta.get('dataset',{}).get('revision')!=REV:raise ValueError('Package dataset revision mismatch')
    name=meta.get('name') or meta['package_version']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',name):raise ValueError('Unsafe media namespace')
    digest,files=full_digest(root)
    if expected is not None and digest!=expected:raise ValueError('Pinned full package SHA mismatch')
    rows={};index={}
    for line in (root/'evidence_list.jsonl').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():continue
        r=json.loads(line);q=r['qid']
        if q in rows or not isinstance(r['raw_id'],str) or q!='mragb:'+r['raw_id']:raise ValueError('Duplicate/malformed source qid')
        if r['provenance']['dataset_revision']!=REV:raise ValueError('Row dataset revision mismatch')
        if r['num_evidence']!=len(r['evidence_order']) or r['prompt_image_slots']!=1+len(r['evidence_order']):raise ValueError('Evidence count/slots mismatch')
        tp=r['task_payload']
        if set(tp)!=set(['question','choices']) or set(tp['choices'])!=set('ABCD') or not tp['question'] or not all(isinstance(x,str) and x.strip() for x in tp['choices'].values()):raise ValueError('Question/four-choice contract mismatch')
        if r['scoring_only']['gold_choice'] not in 'ABCD' or len(r['scoring_only']['gold_choice'])!=1:raise ValueError('Invalid independent gold')
        wanted_pool={'S1':'official_retrieved_top3','S2':'gt_evidence','S3':'pure_distractor_d1'}[condition]
        if r['pool_id']!=wanted_pool or r['is_oracle']!=(condition=='S2'):raise ValueError('Explicit source pool/oracle mismatch')
        if r['provenance'].get('condition')!=condition:raise ValueError('Row condition provenance mismatch')
        if condition=='S1' and r.get('retriever_id') is not None:raise ValueError('Published source must not masquerade as independent retrieval')
        refs=r['evidence_order'];role={'S1':'official_retrieved','S2':'gt','S3':'distractor'}[condition]
        if r.get('retrieval_ranks')!=[x.get('retrieval_rank') for x in refs] or r.get('retrieval_scores')!=[x.get('retrieval_score') for x in refs]:raise ValueError('Rank/score arrays differ from evidence')
        for k,e in enumerate(refs):
            if e['role']!=role or e['rank']!=k or e['evidence_id']!=q+'#'+role+str(k):raise ValueError('Evidence ID/role/rank order mismatch')
            if condition in ['S1','S3'] and e.get('retrieval_rank')!=k:raise ValueError('Original retrieval rank mismatch')
            if e.get('used_in_prompt') is not True:raise ValueError('Unused evidence in condition package')
        if condition=='S2' and ([e['evidence_id'] for e in refs]!=r['scoring_only']['gt_evidence_ids'] or refs!=r['scoring_only']['gt_evidence_refs']):raise ValueError('GT IDs/ref order mismatch')
        if r['status']=='ok' and len(refs)!=evidence_count('S3-pure' if condition=='S3' else condition,r['scenario']):raise ValueError('Actual evidence count mismatch; do not pad/truncate')
        if condition=='S3' and len(refs)>3:raise ValueError('S3 too many refs')
        rows[q]=r
    with (root/'evidence_index.csv').open(encoding='utf-8-sig',newline='') as f:
        for i in csv.DictReader(f):
            if i['evidence_id'] in index:raise ValueError('Duplicate index evidence ID')
            resolve_image(root,i['path']);index[i['evidence_id']]=i
    declared=set()
    for q,r in rows.items():
        query=r.get('question_image')
        if query and (query['evidence_id']!=q+'#q' or query['role']!='q' or query.get('rank') is not None):raise ValueError('Query identity mismatch')
        for e in ([query] if query else [])+r['evidence_order']:
            eid=e['evidence_id'];declared.add(eid);i=index.get(eid)
            # Missing index entries are retained as condition failures at normalization.
            if i is None:continue
            if i['qid']!=q or i['raw_id']!=r['raw_id']:raise ValueError('Index qid/raw_id mismatch')
            for key in ['path','sha256','role']:
                if i[key]!=e[key]:raise ValueError('Reference/index '+key+' mismatch')
            if i['rank']!=('' if e.get('rank') is None else str(e['rank'])) or [int(i['w']),int(i['h'])]!=[e['w'],e['h']]:raise ValueError('Index rank/size mismatch')
    if set(index)-declared:raise ValueError('Orphan indexed references')
    # Verify A's narrower digest separately; it does not cover question/options/gold/CSV.
    h=hashlib.sha256()
    for r in rows.values():
        h.update(r['qid'].encode())
        for e in ([r['question_image']] if r.get('question_image') else [])+r['evidence_order']:h.update(e['sha256'].encode())
    if meta.get('content_digest') is not None and meta['content_digest']!=h.hexdigest():raise ValueError('A declared content_digest mismatch')
    return {'root':root,'name':name,'rows':rows,'index':index,'receipt':{'condition':condition,'namespace':name,
        'package_version':meta['package_version'],'source_package_sha256':digest,'digest_algorithm':'B full-file path/bytes/SHA256 canonical manifest v1',
        'A_content_digest':meta.get('content_digest'),'externally_pinned':expected is not None,'file_count':len(files),
        'source_jsonl_sha256':sha(root/'evidence_list.jsonl'),'index_sha256':sha(root/'evidence_index.csv')}}


def same_question(a,b):
    for key in ['qid','raw_id','scenario','aspect','task_payload']:
        if a[key]!=b[key]:raise ValueError('Cross-condition '+key+' differs')
    # Compare gold independently, never place it in model_request.
    for key in ['gold_choice','answer_text']:
        if a['scoring_only'].get(key)!=b['scoring_only'].get(key):raise ValueError('Cross-condition scoring '+key+' differs')
    if {a['pool_id'],b['pool_id']}<=set(['official_retrieved_top3','gt_evidence']) and a['scoring_only'].get('gt_evidence_ids')!=b['scoring_only'].get('gt_evidence_ids'):
        raise ValueError('Cross-condition GT identity/order differs')
    qa,qb=a.get('question_image'),b.get('question_image')
    if qa and qb and any(qa[k]!=qb[k] for k in ['evidence_id','sha256','w','h']):raise ValueError('Cross-condition query identity/content differs')


def link_file(source,target,mode):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if sha(target)!=sha(source):raise ValueError('Media namespace collision')
        return
    if mode=='copy':shutil.copyfile(source,target)
    else:os.link(source,target)  # No silent copy fallback; Windows/cross-volume may use --media-mode copy.


def review_csv(package,rows,confirmations=None,confirmation_sha=None):
    """CSV -> by_qid. Derived review_id is B audit ID, not an A native field.

    Rule-only '不支持' remains candidate. Explicit unknown/support is undetermined
    for formal admission. Confirmation needs image-grounded reviewed targets and
    a local hashed basis artifact; adapter validates traceability, not human truth.
    """
    path=package['root']/'semantic_review.csv';original_sha=sha(path)
    confirmations=confirmations or {}
    if confirmations and (confirmations.get('source_review_sha256')!=original_sha or confirmations.get('source_package_sha256')!=package['receipt']['source_package_sha256']):raise ValueError('Confirmation bound to different original CSV/package')
    kept={};audit=[]
    with path.open(encoding='utf-8-sig',newline='') as f:
        for line_number,r in enumerate(csv.DictReader(f),2):
            if r['qid'] not in rows:raise ValueError('Unknown semantic-review qid')
            eid=r.get('final_evidence_id');state='candidate' if r.get('semantic_verdict')=='不支持' and r.get('fate')=='kept' else 'undetermined'
            record={**r,'source_csv_line':line_number,'admission_state':state}
            audit.append(record)
            if eid and r.get('fate')=='kept':
                key=(r['qid'],eid)
                if key in kept:raise ValueError('Duplicate kept CSV evidence identity')
                kept[key]=record
    if set(confirmations.get('by_qid',{}))-set(rows):raise ValueError('Unknown confirmation qid')
    by_qid={}
    for q,row in rows.items():
        if not row.get('_s3_refs'):continue
        confirmations_q=confirmations.get('by_qid',{}).get(q,{})
        approved={}
        for item in confirmations_q.get('evidence',[]):
            if item['evidence_id'] in approved:raise ValueError('Duplicate confirmation evidence')
            approved[item['evidence_id']]=item
        valid_ids={e['evidence_id'] for e in row['_s3_refs']}
        if set(approved)-valid_ids:raise ValueError('Unknown confirmation evidence ID')
        entries=[]
        for e in row['_s3_refs']:
            src=kept.get((q,e['evidence_id']));state=src['admission_state'] if src else 'undetermined';proof=approved.get(e['evidence_id'])
            confirmed=False
            if proof:
                if not src or state!='candidate':raise ValueError('Cannot promote rejected/unknown source evidence')
                query=row['question_image'];gts=row['scoring_only']['gt_evidence_refs']
                if proof.get('semantic_status')!='confirmed_unsupportive' or proof.get('method') not in ['human_visual','documented_semantic_review'] or not proof.get('reviewer') or not proof.get('rationale'):
                    raise ValueError('Actual per-image semantic review method/reviewer/rationale required')
                if proof.get('evidence_sha256')!=e['sha256'] or proof.get('reviewed_query_sha256')!=query['sha256'] or sorted(proof.get('reviewed_gt_sha256',[]))!=sorted(g['sha256'] for g in gts):raise ValueError('Reviewed candidate/query/all-GT identity mismatch')
                artifact=resolve_image(package['confirmation_root'],proof['basis_artifact']['path'])
                if sha(artifact)!=proof['basis_artifact']['sha256']:raise ValueError('Missing/changed actual review basis artifact')
                confirmed=True;state='confirmed'
            entries.append({'evidence_id':e['evidence_id'],'evidence_sha256':e['sha256'],
                'semantic_status':'confirmed_unsupportive' if confirmed else 'undetermined','admission_state':state,
                'source_csv_line':src.get('source_csv_line') if src else None,'source_verdict':src.get('semantic_verdict') if src else None,
                'confirmation':proof if confirmed else None})
        by_qid[q]={'review_id':'B-csv-adapter:'+fingerprint([original_sha,package['receipt']['source_package_sha256'],q,confirmation_sha]),
            'review_id_origin':'B generated audit identifier; not A native','distractor_type':'D1','evidence':entries}
    return {'version':'A_csv_review_adapter_v1','source_review_sha256':original_sha,
        'source_package_sha256':package['receipt']['source_package_sha256'],'confirmation_sha256':confirmation_sha,
        'confirmation_supplied':bool(confirmations),'semantic_claim':'Traceability validated only; rule labels are not proof of nonsupport',
        'by_qid':by_qid,'source_csv_records':audit}


def integrate(s1_root,s2_root,split_path,output,s3_root=None,confirmation_path=None,pins=None,mode='hardlink',acknowledge=False,A_commit=BASE):
    if output.exists():raise ValueError('New output directory required')
    if not re.fullmatch('[0-9a-f]{40}',A_commit):raise ValueError('Fixed full A commit required')
    if confirmation_path and not s3_root:raise ValueError('Confirmations require an S3 source package')
    pins=pins or {};packages={}
    for c,p in [('S1',s1_root),('S2',s2_root),('S3',s3_root)]:
        if p:packages[c]=load_package(p,c,pins.get(c))
    if len({p['name'] for p in packages.values()})!=len(packages):raise ValueError('Distinct per-package media namespaces required')
    destination=output.resolve();protected=[Path(__file__).resolve().parent]+[p['root'] for p in packages.values()]
    if any(destination==p or p in destination.parents for p in protected):raise ValueError('Output must be outside read-only source packages and B code')
    split=read_split(split_path,acknowledge);qids=split['qids']
    if not qids or len(set(qids))!=len(qids):raise ValueError('Invalid fixed split')
    for p in packages.values():
        if set(p['rows'])-set(qids):raise ValueError('Unknown source qid outside fixed split')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Local absolute paths never enter generated provenance; immutable original packages remain untouched.
    with tempfile.TemporaryDirectory(prefix='B-condition-normalize-',dir=output.parent) as tmp:
        temp=Path(tmp);normalized=[];all_index={};file_map={};dedup={}
        def mapped(ref,p,q,errors):
            r=copy.deepcopy(ref);eid=r['evidence_id'];i=p['index'].get(eid)
            if i is None:errors.append('Missing indexed reference '+eid)
            r['path']=p['name']+'/'+r['path'];source=resolve_image(p['root'],ref['path'])
            file_map[r['path']]=source
            if eid in all_index:
                old=all_index[eid]
                if old['sha256']!=r['sha256']:raise ValueError('Cross-package evidence ID collision')
            else:all_index[eid]={'evidence_id':eid,'raw_id':q.removeprefix('mragb:'),'qid':q,'role':r['role'],
                'rank':'' if r.get('rank') is None else r['rank'],'path':r['path'],'sha256':r['sha256'],'w':r['w'],'h':r['h']}
            return r
        for q in qids:
            present=[(c,p,p['rows'].get(q)) for c,p in packages.items() if p['rows'].get(q)]
            if not present:raise ValueError('Missing question and independent gold in all packages: '+q+'; cannot fabricate a scorable row')
            canonical=next((r for c,p,r in present if c=='S1'),present[0][2])
            for c,p,r in present:same_question(canonical,r)
            a=copy.deepcopy(canonical);a['condition_errors']={};a['status']='ok';a['pool_id']='official_retrieved_top3';a['available_evidence_untruncated']=None
            query_source=next(((p,r['question_image']) for c,p,r in present if r.get('question_image')),None)
            query_errors=[]
            a['question_image']=mapped(query_source[1],query_source[0],q,query_errors) if query_source else None
            if not query_source:query_errors.append('Missing query reference')
            a['condition_errors']['S0']=list(query_errors)
            for c in ['S1','S2','S3']:
                if c not in packages:continue
                p=packages[c];r=p['rows'].get(q);errors=list(query_errors);refs=[]
                if r is None:errors.append('Missing '+c+' source row; fixed question retained')
                else:
                    if r['status']!='ok':errors.append('A '+c+' status: '+r['status'])
                    refs=[mapped(e,p,q,errors) for e in r['evidence_order']]
                a['condition_errors'][c]=errors
                if c=='S1':a['evidence_order']=refs
                elif c=='S2':a['scoring_only']['gt_evidence_refs']=refs;a['scoring_only']['gt_evidence_ids']=[e['evidence_id'] for e in refs]
                else:a['_s3_refs']=refs
            a['num_evidence']=len(a['evidence_order']);a['retrieval_ranks']=[e.get('retrieval_rank') for e in a['evidence_order']];a['retrieval_scores']=[e.get('retrieval_score') for e in a['evidence_order']]
            normalized.append(a)
        # Repeated final bytes and near duplicates against query/all GT/each other are
        # diagnosed independently of semantic text. This is a gate, not semantic proof.
        from PIL import Image
        def dh(ref):
            with Image.open(file_map[ref['path']]) as im:
                im.load();g=im.convert('L').resize((9,8),Image.Resampling.LANCZOS);pixels=list(g.getdata())
                return sum((pixels[y*9+x]>pixels[y*9+x+1])<<(y*8+x) for y in range(8) for x in range(8))
        for a in normalized:
            q=a['qid'];refs=a.get('_s3_refs',[]);block=[]
            if not refs:continue
            guards=([a['question_image']] if a['question_image'] else [])+a['scoring_only']['gt_evidence_refs']
            hashes=[e['sha256'] for e in refs]
            if len(set(hashes))!=len(hashes):block.append('Duplicate final S3 content bytes')
            if set(hashes)&{e['sha256'] for e in guards}:block.append('S3 overlaps query/GT bytes')
            if a['condition_errors'].get('S2') or len(guards)!=1+evidence_count('S2',a['scenario']):block.append('Complete query/GT duplicate guards unavailable')
            try:
                prior=[dh(g) for g in guards]
                for e in refs:
                    value=dh(e)
                    if any((value^v).bit_count()<=6 for v in prior):block.append('S3 near duplicate of query/GT/final evidence')
                    prior.append(value)
            except Exception as exc:block.append('Duplicate check unavailable: '+type(exc).__name__)
            dedup[q]=sorted(set(block))
        for relative,p in file_map.items():
            if p.is_file():link_file(p,temp/relative,mode)
        source=temp/'evidence_list.jsonl';source.write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in normalized),encoding='utf-8')
        index=temp/'evidence_index.csv'
        with index.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['evidence_id','raw_id','qid','role','rank','path','sha256','w','h']);w.writeheader();w.writerows(all_index.values())
        metadata={'dataset_revision':REV,'A_baseline_commit':A_commit,'evidence_version':'A-multicondition@'+A_commit+'#sha256='+fingerprint({c:p['receipt'] for c,p in packages.items()})}
        selection=make_selection(normalized,metadata);selection_path=temp/'selection.json';atomic(selection_path,selection)
        main=prepare(source,index,selection_path,split_path,output/'main',acknowledge)
        review=None;s3=None
        if 'S3' in packages:
            package=packages['S3'];package['confirmation_root']=confirmation_path.parent.resolve() if confirmation_path else package['root']
            review=review_csv(package,{a['qid']:a for a in normalized},read(confirmation_path) if confirmation_path else None,sha(confirmation_path) if confirmation_path else None)
            for q,record in review['by_qid'].items():
                if dedup.get(q) or next(a for a in normalized if a['qid']==q)['condition_errors'].get('S3'):
                    record['admission_blockers']=dedup.get(q,[])+next(a for a in normalized if a['qid']==q)['condition_errors'].get('S3',[])
                    for e in record['evidence']:e['semantic_status']='undetermined';e['admission_state']='undetermined'
            review_path=temp/'semantic_review.json';atomic(review_path,review)
            from protocol_rules import verified_D1
            eligible=[a['qid'] for a in normalized if verified_D1(review['by_qid'].get(a['qid']))]
            if eligible:
                smeta={**metadata,'semantic_review_sha256':sha(review_path)}
                sselection=make_selection(normalized,smeta,review,True);sp=temp/'s3-selection.json';atomic(sp,sselection)
                s3=prepare(source,index,sp,split_path,output/'s3',acknowledge,review_path)
            atomic(output/'audit/s3_review_adapter.json',review)
            shutil.copyfile(package['root']/'semantic_review.csv',output/'audit/source_semantic_review.csv')
        for name,bundle in [('main',main),('s3',s3)]:
            if bundle is None:continue
            root=output/name
            selected={r['path'] for descriptor in bundle['conditions'].values() for row in read(root/descriptor['path']) for r in row['image_order']}
            for relative in selected:
                p=temp/relative
                if p.is_file():link_file(p,root/'media'/relative,mode)
            required=['S1','S2']+(['S3'] if name=='s3' else [])
            bundle['formal_split_approved']=bundle['formal_split_approved'] and all(packages[c]['receipt']['externally_pinned'] for c in required)
            if name=='s3':
                supporting=[]
                def support(src,relative):
                    dest=root/'audit'/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
                    supporting.append({'path':dest.relative_to(root).as_posix(),'sha256':sha(dest)})
                support(packages['S3']['root']/'semantic_review.csv','source_semantic_review.csv')
                support(confirmation_path,'confirmations.json')
                for record in review['by_qid'].values():
                    for e in record['evidence']:
                        if e.get('confirmation'):
                            basis=e['confirmation']['basis_artifact']
                            support(resolve_image(confirmation_path.parent.resolve(),basis['path']),'review_basis/'+basis['path'])
                bundle['semantic_support_artifacts']=supporting
            bundle['media_deployment']='Selected files materialized under media/<package namespace>/<original relative path>; missing files remain failed rows.'
            atomic(root/'bundle.json',bundle)
        report={'version':'condition_packages_adapter_v1.7.0','A_commit':A_commit,'fixed_qids':qids,
            'source_packages':{c:p['receipt'] for c,p in packages.items()},'S3_duplicate_diagnostics':dedup,
            'S3_confirmed_qids':s3['qids'] if s3 else [],'S3_parent_denominator':len(qids),
            'S3_coverage':len(s3['qids'])/len(qids) if s3 else 0,'S3_diagnostic_qids':[q for q in qids if not s3 or q not in s3['qids']],
            'S3_formal_admitted':s3 is not None,'actual_semantic_truth_independently_verified_by_B':False,
            'S1_S2_count_caveat':'Regular3vs5; Incomplete3vs1. Effects are not attributable solely to evidence content/quality.',
            'global_exposure_registry_complete':False,'all_prerental_complete':False}
        atomic(output/'audit/condition_integration.json',report)
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['s1','s2','split','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--s3',type=Path);p.add_argument('--confirmations',type=Path);p.add_argument('--package-pins',type=Path)
    p.add_argument('--media-mode',choices=['hardlink','copy'],default='hardlink')
    p.add_argument('--acknowledge-split-limitations',action='store_true');p.add_argument('--A-commit',default=BASE)
    a=p.parse_args()
    try:
        result=integrate(a.s1,a.s2,a.split,a.output,a.s3,a.confirmations,read(a.package_pins) if a.package_pins else None,a.media_mode,a.acknowledge_split_limitations,a.A_commit)
        print(json.dumps({'fixed_questions':len(result['fixed_qids']),'S3_coverage':result['S3_coverage'],'S3_admitted':result['S3_formal_admitted']}))
    except Exception as e:
        # Keep a failure receipt outside partial outputs; no source deletion or repair.
        atomic(a.output.with_name(a.output.name+'.failure.json'),{'status':'integration_failed','error':type(e).__name__+': '+str(e),'all_prerental_complete':False})
        raise
if __name__=='__main__':main()
