"""Bind external approved A materials to the frozen main protocol; no source data copied."""
import argparse
import json
from pathlib import Path
from batch_inputs import read,sha,external,load_task
from run_batch import ROOT,REGISTRY,atomic,inspect_matrix,phase_for
from protocol_rules import PROTOCOL,evidence_count


def bind(binding_path,data_root,output):
    if output.exists():raise ValueError('New matrix output path required')
    if output.resolve()==ROOT or ROOT in output.resolve().parents:raise ValueError('Bound real-data matrices remain external')
    binding=read(binding_path);registry=read(REGISTRY);protocol=read(ROOT/'configs/protocol_main_v1.json')
    if binding.get('protocol',protocol)!=protocol:raise ValueError('Binding differs from frozen protocol; requires an explicit new code/config version')
    tasks=[];bundles={};question_content={};condition_hashes={};fixed_lists={}
    for source in binding['tasks']:
        t=dict(source);m=registry['models'][t['model']]
        bpath=external(data_root,t['bundle']);bundle=read(bpath)
        t.update({'model_revision':m['revision'],'environment':m['environment'],'bundle_sha256':sha(bpath),
            'split_manifest_sha256':bundle['split_manifest']['sha256'],'split':bundle['split'],
            'protocol_version':bundle['protocol_version'],'evidence_version':bundle['evidence_version']})
        t['phase']=phase_for(t)
        t['status']='bound_offline_GPU_unverified'
        if t['stage']=='quality' and t.get('repeat_index')!=0:raise ValueError('Quality has exactly one repeat0 per split/model/condition')
        if t['protocol_version']!=PROTOCOL:raise ValueError('Main protocol required; old official_loader_smoke_v1 is legacy only')
        bundle,root,media,rows=load_task(t,data_root,decode=True);bundles[t['task_id']]=bundle
        if t['condition']=='S1' and bundle['condition_sources']['S1']!='official_clip_candidates':raise ValueError('Main S1 uses published candidates only')
        for row in rows:
            if row['expected_num_evidence']!=evidence_count(t['condition'],bundle['scenarios'][row['qid']]):raise ValueError('S1/S3=3 including Incomplete; S2 actual5/1; S0=0')
            neutral=(row['question'],row['choices'],row['query_image'])
            key=(bundle['split'],row['qid'])
            if key in question_content and question_content[key]!=neutral:raise ValueError('Different question/options/query between conditions/models')
            question_content[key]=neutral
        if t['condition']=='S3-pure':
            if bundle.get('diagnostic_only_qids',{}).get('S3-pure'):raise ValueError('Undetermined is diagnostic only, not a pure-distractor quality task')
            if not bundle.get('semantic_review_sha256') or not bundle.get('S3_coverage'):raise ValueError('S3 needs semantic review hash and explicit eligible/parent coverage')
        # Identical content per condition/split across models. Performance repeat tasks reuse it.
        key=(bundle['split'],t['condition'],t['stage'])
        sig=bundle['conditions'][t['condition']]['sha256']
        if key in condition_hashes and condition_hashes[key]!=sig:raise ValueError('Condition input content differs between models/repeats')
        condition_hashes[key]=sig
        if t['stage']=='quality':
            list_key=(bundle['split'],'S3' if t['condition']=='S3-pure' else 'main')
            if list_key in fixed_lists and fixed_lists[list_key]!=bundle['qids']:raise ValueError('Paired quality lists differ')
            fixed_lists[list_key]=bundle['qids']
        tasks.append(t)
    for (split,kind),qids in fixed_lists.items():
        if kind=='S3':
            parent=fixed_lists[(split,'main')]
            if not set(qids)<=set(parent):raise ValueError('S3 must use a fixed subset of the same split')
            for t in tasks:
                if t['stage']=='quality' and t['split']==split and t['condition']=='S3-pure':
                    if bundles[t['task_id']]['S3_coverage']['parent_qids']!=parent:raise ValueError('S3 parent denominator mismatch')
    scope=binding.get('scope','full_required')
    if scope not in ['full_required','smoke_only']:raise ValueError('Explicit supported binding scope required')
    quality_splits={t['split'] for t in tasks if t['stage']=='quality'}
    if scope=='full_required' and quality_splits!={'internal_holdout','frozen_test'}:raise ValueError('Full required matrix needs both holdout and frozen-test phases')
    if scope=='smoke_only' and any(t['phase']!='smoke' for t in tasks):raise ValueError('Smoke-only cannot be labeled full preparation')
    matrix={'version':'bound_batch_v1.10','approved':binding.get('approved',False),'scope':scope,'protocol':protocol,
        'registry_sha256':sha(REGISTRY),'binding_sha256':sha(binding_path),'order':[m for m in registry['models'] if any(t['model']==m for t in tasks)],
        'quality_formula':'For each formal split:15*N+2*N_S3; S1/S3 subset comparison does not add quality generations',
        'quality_question_runs':sum(len(bundles[t['task_id']]['qids']) for t in tasks if t['stage']=='quality'),
        'task_items':tasks,'optional_excluded':protocol['optional_not_blocking'],'all_formal_materials_integrated':scope=='full_required'}
    errors=inspect_matrix(matrix,registry);atomic(output,matrix)
    print(json.dumps({'sha256':sha(output),'ready':not errors,'blockers':errors,'scope':scope,'quality_question_runs':matrix['quality_question_runs']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['binding','data-root','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();bind(a.binding,a.data_root.resolve(),a.output)
