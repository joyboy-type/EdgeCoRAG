"""Single-GPU, model-by-model runner with append-only attempts; default is inspection."""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
from batch_inputs import read,sha,fingerprint,load_task,checked
from model_adapters import HFBackend,FixedBackend
from run_candidate import is_oom_error
from score_minimal import evaluate,parse_choice,PARSER_VERSION

ROOT=Path(__file__).resolve().parent
REGISTRY=ROOT/'configs/model_registry.json'
STAGES=['preflight_single','preflight_multi','smoke','development','quality','performance']
PHASES=['smoke','development','internal_holdout','frozen_test','performance']

def phase_for(task):
    if task['stage'] not in STAGES:raise ValueError('Unscheduled task stage: '+str(task['stage'])+'; use development for dev S3, not mechanism_test')
    if task['stage'] in ['preflight_single','preflight_multi','smoke']:expected='smoke'
    elif task['stage']=='quality':expected=task['split']
    else:expected=task['stage']
    if task.get('phase') and task['phase']!=expected:raise ValueError('Task phase conflicts with stage/split')
    return expected


def scheduled_tasks(matrix,through_phase):
    """Every item maps to a known phase; deferred work is explicit, never dropped."""
    limit=PHASES.index(through_phase);scheduled=[];deferred=[]
    for task in matrix['task_items']:
        phase=phase_for(task)
        if phase not in PHASES:raise ValueError('Unscheduled phase: '+phase)
        (scheduled if PHASES.index(phase)<=limit else deferred).append(task['task_id'])
    return scheduled,deferred


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def atomic_jsonl(path,rows):
    path=Path(path);temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def append(path,value):
    with Path(path).open('a',encoding='utf-8') as f:
        f.write(json.dumps(value,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())

@contextlib.contextmanager
def lock(path):
    """OS releases lock on process death; lock file is not an in-progress flag."""
    with Path(path).open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def history(path,expected_fingerprint,allowed_qids):
    """Recover only a torn trailing write; malformed complete lines are hard errors."""
    if not path.exists():return [],{}
    raw=path.read_bytes();lines=raw.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b'\n'):
        try:json.loads(lines[-1].decode('utf-8'))
        except (ValueError,UnicodeDecodeError):
            backup=path.with_name(path.name+'.torn-'+str(time.time_ns()))
            backup.write_bytes(lines[-1]);raw=b''.join(lines[:-1])
            with path.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        else:
            # Complete JSON survived, only the newline was interrupted.
            with path.open('ab') as f:f.write(b'\n');f.flush();os.fsync(f.fileno())
    records=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s]
    latest={};seen=set()
    for r in records:
        if r['config_fingerprint']!=expected_fingerprint:raise ValueError('Attempt fingerprint mismatch')
        q=r['qid'];key=(tuple(r['row_key']),r['attempt'])
        if q not in allowed_qids:raise ValueError('Unknown qid in attempt history')
        if key in seen:raise ValueError('Duplicate composite attempt key')
        if r['attempt']!=(latest[q]['attempt']+1 if q in latest else 1):raise ValueError('Nonsequential attempt history')
        if q in latest and r['row_key']!=latest[q]['row_key']:raise ValueError('Composite key changed within task')
        seen.add(key);latest[q]=r
    return records,latest


def failed(record):
    """Technical failure only; strict format noncompliance remains a scored wrong answer."""
    return (bool(record.get('generation_error') or record.get('final_extraction_error') or record.get('oom'))
            or record.get('input_status','ok')!='ok'
            or record.get('parse_status') not in ('ok','parse_failure','empty_output'))

def code_versions():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*'))
            if p.is_file() and p.suffix in ['.py','.json','.txt','.sh'] and '__pycache__' not in p.parts}


def task_identity(task,model,rows,backend):
    return {'task':task,'model':model,'qids':[r['qid'] for r in rows],'backend':backend,
            'code':code_versions(),'code_version':read(ROOT/'package_hashes.json')['version'],
            'package_manifest_sha256':sha(ROOT/'package_hashes.json'),'parser':PARSER_VERSION,'warmup_runs':3}


def snapshot(task_dir,task,model,bundle,bundle_root,rows,latest,synthetic,status):
    # The scorer alone reads the independent answer file. The adapter never receives it.
    answer_path=checked(bundle_root,bundle['answers'])
    answers=read(answer_path)
    if [a['qid'] for a in answers]!=bundle['qids']:raise ValueError('Scoring fixed qids differ from input list')
    selected=[latest[r['qid']] for r in rows if r['qid'] in latest]
    format_failures=[r['qid'] for r in selected if not failed(r) and r.get('parse_status') in ('parse_failure','empty_output')]
    projection=[{'qid':r['qid'],'raw_output':r['final_output'],'generation_error':r['generation_error']} for r in selected]
    score=evaluate(answers,projection)
    score.update({'synthetic':synthetic,'task_id':task['task_id'],'stage':task['stage'],
        'execution_failure_policy':'technical_only_format_wrong_v1',
        'format_failure_count':len(format_failures),'technical_failure_count':sum(failed(r) for r in selected),
        'condition':task['condition'],'model_id':model['model_id'],'model_revision':model['revision'],
        'scoring_boundary':'final_output projection; complete raw output retained in predictions/attempts',
        'input_failure_count':sum(r['input_status']!='ok' for r in rows),
        'quality_result':task['stage']=='quality','not_an_independent_test':task['stage']!='quality',
        'performance_repeats_excluded_from_accuracy':task['stage']=='performance',
        'evidence_version':bundle['evidence_version'],'protocol_version':bundle['protocol_version'],
        'dataset_revision':bundle['dataset_revision'],'split_manifest_sha256':bundle['split_manifest']['sha256'],
        'template_version':bundle['template_version'],'A_baseline_commit':bundle.get('A_baseline_commit'),
        'subset_parent_qids':bundle.get('subset_parent_qids'),'S3_coverage':bundle.get('S3_coverage'),
        'semantic_review_sha256':bundle.get('semantic_review_sha256'),
        'parent_split_manifest_sha256':read(checked(bundle_root,bundle['split_manifest'])).get('parent_split_manifest_sha256'),
        'selection_timing':bundle.get('selection_timing'),'retrieval_timing':bundle.get('retrieval_timing'),
        'cross_hardware_timing_added':False,'review_method':bundle.get('review_method'),
        'review_scope':bundle.get('review_scope'),'review_limitations':bundle.get('review_limitations'),
        'HQ_binding_config_sha256':bundle.get('HQ_binding_config_sha256'),'evidence_order_policy':bundle.get('evidence_order_policy')})
    atomic_jsonl(task_dir/'predictions.jsonl',selected)
    atomic_jsonl(task_dir/'scorer_projection.jsonl',projection)
    # Performance gets no aggregate accuracy: its repeats cannot become quality rows.
    if task['stage']!='performance':atomic(task_dir/'score.json',score)
    pending=[r['qid'] for r in rows if r['qid'] not in latest]
    retry=[r['qid'] for r in selected if failed(r)]
    atomic(task_dir/'retry_queue.json',{'missing_qids':pending,'failed_qids':retry,'explicit_retry_required':True,
        'format_failure_qids_not_retried':format_failures})
    atomic(task_dir/'state.json',{'status':status,'fixed_total':len(rows),'received_unique':len(latest),
        'missing_qids':pending,'failed_qids':retry,'exit_code':2 if pending or retry else 0,
        'format_failure_qids':format_failures,'format_failures_count_as_incorrect':True,
        'execution_failure_policy':'technical_only_format_wrong_v1',
        'stage':task['stage'],'synthetic':synthetic})
    return not pending and not retry


def run_task(task,model,data_root,run_root,backend_factory,backend=None,backend_kind='synthetic',retry=False,inject_stop=None):
    bundle,bundle_root,media,rows=load_task(task,data_root,decode=backend_kind=='hf')
    task_dir=run_root/task['task_id'];task_dir.mkdir(parents=True,exist_ok=True)
    identity=task_identity(task,model,rows,backend_kind);fp=fingerprint(identity)
    metadata=task_dir/'identity.json'
    with lock(task_dir/'writer.lock'):
        if metadata.exists():
            if read(metadata)['config_fingerprint']!=fp:raise ValueError('Configuration fingerprint changed; use a new run root')
        else:atomic(metadata,{'config_fingerprint':fp,'identity':identity,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        _,latest=history(task_dir/'attempts.jsonl',fp,set(bundle['qids']))
        for q,r in latest.items():
            expected=[run_root.name,task['task_id'],q,model['model_id'],model['revision'],task['condition'],task['protocol_version'],task['repeat_index'],task['evidence_version']]
            if r['row_key']!=expected:raise ValueError('History composite key does not match task')
        state_path=task_dir/'state.json'
        prior_oom=(state_path.exists() and read(state_path).get('status')=='oom_stopped') or any(r.get('oom') for r in latest.values())
        if prior_oom and not retry:
            snapshot(task_dir,task,model,bundle,bundle_root,rows,latest,backend_kind=='synthetic','oom_stopped')
            return backend,True,False
        todo=[r for r in rows if r['qid'] not in latest or (retry and failed(latest[r['qid']]))]
        if not todo:
            okay=snapshot(task_dir,task,model,bundle,bundle_root,rows,latest,backend_kind=='synthetic','completed')
            return backend,False,okay
        snapshot(task_dir,task,model,bundle,bundle_root,rows,latest,backend_kind=='synthetic','running')
        oom=False;startup_error=None
        try:
            new_backend=backend is None
            if new_backend:backend=backend_factory()
            if backend_kind=='hf' and (new_backend or not (task_dir/'warmup.json').exists()):
                probes=[r for r in rows if r['input_status']=='ok']
                if not probes:raise ValueError('No ready warmup inputs')
                warmups=[]
                for _ in range(3):
                    try:
                        warmups.append({'output':backend.infer(probes[0],media),'generation_error':None,'not_scored':True})
                    except Exception as e:
                        warmups.append({'generation_error':type(e).__name__+': '+str(e),'traceback':traceback.format_exc(),'not_scored':True})
                        atomic(task_dir/('warmup-'+str(time.time_ns())+'.json'),{'records':warmups,'attempt_failed':True})
                        raise
                append(task_dir/'warmup_history.jsonl',{'records':warmups,'not_scored':True,'runtime':backend.runtime})
                atomic(task_dir/'warmup.json',{'records':warmups,'not_scored':True,'runtime':backend.runtime})
        except Exception as e:
            startup_error=type(e).__name__+': '+str(e);oom=is_oom_error(e)
            append(task_dir/'errors.jsonl',{'phase':'startup_or_warmup','error':startup_error,'oom':oom,'traceback':traceback.format_exc()})
        for row in todo:
            if oom:break
            q=row['qid'];attempt=latest[q]['attempt']+1 if q in latest else 1
            record={'qid':q,'raw_id':row['raw_id'],'raw_output':'','prediction_raw':'','final_output':'',
                    'generation_error':None,'parser_version':PARSER_VERSION,'parse_status':'generation_error','parsed_choice':None,
                    'synthetic':backend_kind=='synthetic','attempt':attempt,'config_fingerprint':fp,
                    'model_id':model['model_id'],'model_revision':model['revision'],'condition':task['condition'],
                    'protocol_version':task['protocol_version'],'evidence_version':task['evidence_version'],
                    'template_version':row['template_version'],'run_batch_id':run_root.name,'repeat_index':task['repeat_index'],
                    'stage':task['stage'],'evidence_ids_order':[r.get('evidence_id',r['position_key']) for r in row['evidence']],
                    'input_status':row['input_status'],'input_error':row.get('input_error'),
                    'review_method':bundle.get('review_method'),'review_scope':bundle.get('review_scope'),
                    'review_limitations':bundle.get('review_limitations'),'HQ_binding_config_sha256':bundle.get('HQ_binding_config_sha256')}
            record['row_key']=[run_root.name,task['task_id'],q,model['model_id'],model['revision'],task['condition'],task['protocol_version'],task['repeat_index'],task['evidence_version']]
            try:
                if startup_error:raise RuntimeError(startup_error)
                if row['input_status']!='ok':raise ValueError('InputUnavailable: '+str(row.get('input_error')))
                record.update(backend.infer(row,media))
                if record['raw_output']!=record['prediction_raw']:raise ValueError('Raw aliases differ')
                record['parsed_choice'],record['parse_status']=parse_choice(record['final_output'])
                if record.get('final_extraction_error'):
                    record['parsed_choice']=None;record['parse_status']='final_extraction_failure'
            except Exception as e:
                oom=is_oom_error(e);record['oom']=oom
                record['generation_error']=type(e).__name__+': '+str(e);record['traceback']=traceback.format_exc()
                if backend_kind=='hf' and backend is not None:
                    try:record['cuda_memory']={'process_allocator_peak_allocated':backend.torch.cuda.max_memory_allocated(),'process_allocator_peak_reserved':backend.torch.cuda.max_memory_reserved()}
                    except Exception:pass
            record['prediction_raw']=record['raw_output']
            append(task_dir/'attempts.jsonl',record);latest[q]=record
            # Test-only hook is injected in process; no production CLI switch.
            if inject_stop:inject_stop(record)
        okay=snapshot(task_dir,task,model,bundle,bundle_root,rows,latest,backend_kind=='synthetic','oom_stopped' if oom else 'completed_with_failures' if startup_error else 'completed')
        if startup_error or oom:okay=False
        return backend,oom,okay


def inspect_matrix(matrix,registry):
    errors=[];ids=set()
    if not matrix.get('approved') or not matrix.get('protocol',{}).get('approved'):errors.append('Matrix/protocol not approved')
    if matrix['registry_sha256']!=sha(REGISTRY):errors.append('Registry SHA differs')
    for t in matrix['task_items']:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',t['task_id']):errors.append('Unsafe task_id')
        if t['task_id'] in ids:errors.append('Duplicate task_id: '+t['task_id'])
        ids.add(t['task_id'])
        if t['stage'] not in STAGES:errors.append('Unknown task stage')
        if not isinstance(t.get('repeat_index'),int) or t.get('repeat_index',-1)<0:errors.append('Invalid repeat index')
        if t['stage']=='quality' and t.get('repeat_index')!=0:errors.append('Quality repeat must be zero')
        try:phase_for(t)
        except ValueError as e:errors.append(str(e))
        if t['model'] not in registry['models']:errors.append('Unknown model: '+t['model']);continue
        m=registry['models'][t['model']]
        if t['model_revision']!=m['revision'] or t['environment']!=m['environment']:errors.append('Task model pin mismatch')
        for k in ['split','bundle','bundle_sha256','split_manifest_sha256','evidence_version','protocol_version']:
            if not t.get(k):errors.append(t['task_id']+': missing '+k)
        if t['stage']=='quality' and t.get('protocol_version')=='official_loader_smoke_v1':errors.append('Smoke protocol cannot become formal by relabeling the split')
        if t['stage']=='quality':
            stages={x['stage'] for x in matrix['task_items'] if x['model']==t['model']}
            for s in ['preflight_single','preflight_multi','smoke','development']:
                if s not in stages:errors.append(t['model']+': missing prerequisite '+s)
    active={t['model'] for t in matrix['task_items']}
    if len(set(matrix['order']))!=len(matrix['order']) or set(matrix['order'])!=active:errors.append('Model order must list every active model exactly once')
    quality=[(t['model'],t['condition']) for t in matrix['task_items'] if t['stage']=='quality']
    expected={(m,c) for m in registry['models'] for c in ['S0','S1','S2']+(['S3-pure'] if m.startswith('gemma4') else [])}
    quality_splits={t['split'] for t in matrix['task_items'] if t['stage']=='quality'}
    for split in quality_splits:
        pairs=[(t['model'],t['condition']) for t in matrix['task_items'] if t['stage']=='quality' and t['split']==split]
        if len(pairs)!=17 or set(pairs)!=expected:errors.append('Exactly 17 mandatory quality combinations required per split: '+str(split))
        if split not in ['internal_holdout','frozen_test']:errors.append('Quality stage must name internal_holdout or frozen_test')
    if matrix.get('scope')=='full_required' and quality_splits!={'internal_holdout','frozen_test'}:errors.append('Full scope requires holdout and frozen-test phases')
    try:scheduled_tasks(matrix,'performance')
    except ValueError as e:errors.append(str(e))
    return sorted(set(errors))


def worker(args,matrix,registry):
    model=registry['models'][args.worker_model]
    factory=(lambda:FixedBackend(model)) if args.backend=='synthetic' else (lambda:HFBackend(model,registry['environments'][model['environment']],args.allow_download))
    all_tasks=[t for t in matrix['task_items'] if t['model']==args.worker_model]
    phase=getattr(args,'phase',None)
    tasks=[t for t in all_tasks if not phase or phase_for(t)==phase]
    if not tasks:raise ValueError('Worker has no tasks for requested phase/model')
    tasks.sort(key=lambda t:(STAGES.index(t['stage']),t['task_id']))
    backend=None;passed=set();states=[]
    for previous in all_tasks:
        state=args.run_root/previous['task_id']/'state.json'
        if previous not in tasks and state.exists() and read(state).get('exit_code')==0:passed.add(previous['stage'])
    try:
        for t in tasks:
            required={'preflight_multi':{'preflight_single'},'smoke':{'preflight_single','preflight_multi'},'development':{'preflight_single','preflight_multi','smoke'},
                      'quality':{'preflight_single','preflight_multi','development'},
                      'performance':{'preflight_single','preflight_multi','development'}}.get(t['stage'],set())
            if args.backend=='hf' and not required<=passed:
                states.append({'task_id':t['task_id'],'status':'blocked_prerequisite','exit_code':2});continue
            backend,oom,okay=run_task(t,model,args.data_root,args.run_root,factory,backend,args.backend,args.retry_failures)
            states.append({'task_id':t['task_id'],'status':'oom_stopped' if oom else 'completed' if okay else 'completed_with_failures','exit_code':0 if okay else 2})
            if okay:passed.add(t['stage'])
            if oom:
                for remaining in tasks[len(states):]:states.append({'task_id':remaining['task_id'],'status':'blocked_after_model_oom','exit_code':2})
                break
    except Exception as e:
        states.append({'status':'worker_error','error':type(e).__name__+': '+str(e),'traceback':traceback.format_exc(),'exit_code':2})
    finally:
        if backend is not None:
            try:backend.close()
            except Exception:pass
        atomic(args.run_root/(args.worker_model+('.'+phase if phase else '')+'.state.json'),{'model':args.worker_model,'synthetic':args.backend=='synthetic','tasks':states})
    return 2 if any(s['exit_code'] for s in states) else 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix',type=Path,default=ROOT/'configs/task_matrix_draft.json')
    p.add_argument('--data-root',type=Path)
    p.add_argument('--run-root',type=Path)
    p.add_argument('--backend',choices=['synthetic','hf'],default='synthetic')
    p.add_argument('--env-map',type=Path,help='External JSON mapping environment names to explicit Python executables')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--allow-download',action='store_true')
    p.add_argument('--retry-failures',action='store_true')
    p.add_argument('--worker-model',help=argparse.SUPPRESS)
    p.add_argument('--phase',help=argparse.SUPPRESS)
    p.add_argument('--through-phase',choices=PHASES,default='performance')
    args=p.parse_args();matrix=read(args.matrix);registry=read(REGISTRY)
    errors=inspect_matrix(matrix,registry)
    if not args.execute:
        print(json.dumps({'quality_combinations':len({(t['model'],t['condition']) for t in matrix['task_items'] if t['stage']=='quality'}),
            'quality_task_count_across_splits':sum(t['stage']=='quality' for t in matrix['task_items']),
            'formula':matrix.get('quality_formula'),'ready':not errors,'blocker_count':len(errors),'blockers':errors[:20],
            'blockers_truncated':len(errors)>20},indent=2));return
    if errors:raise ValueError('Matrix blocked: '+'; '.join(errors))
    if not args.data_root or not args.run_root:raise ValueError('Explicit data/run roots required')
    args.data_root=args.data_root.resolve();args.run_root=args.run_root.resolve()
    if args.run_root==ROOT or ROOT in args.run_root.parents:raise ValueError('Keep results outside code')
    if args.run_root==args.data_root or args.data_root in args.run_root.parents:raise ValueError('Keep results outside read-only external data')
    args.run_root.mkdir(parents=True,exist_ok=True)
    if args.worker_model:
        expected={'matrix_sha256':sha(args.matrix),'registry_sha256':sha(REGISTRY),'code':code_versions(),'backend':args.backend}
        if not (args.run_root/'batch_identity.json').exists() or read(args.run_root/'batch_identity.json')!=expected:
            raise ValueError('Worker requires matching parent batch identity')
        return worker(args,matrix,registry)
    with lock(args.run_root/'batch.writer.lock'):
        identity={'matrix_sha256':sha(args.matrix),'registry_sha256':sha(REGISTRY),'code':code_versions(),'backend':args.backend}
        path=args.run_root/'batch_identity.json'
        if path.exists() and read(path)!=identity:raise ValueError('Batch fingerprint changed; refuse mixed configuration')
        if not path.exists():atomic(path,identity)
        envs=read(args.env_map) if args.env_map else {}
        if args.backend=='hf' and not args.env_map:raise ValueError('Separate model environments must be explicit')
        results=[]
        expected_tasks,deferred_tasks=scheduled_tasks(matrix,args.through_phase)
        active_phases=[p for p in PHASES if any(phase_for(t)==p for t in matrix['task_items'])]
        for phase in active_phases:
            if phase in PHASES and PHASES.index(phase)>PHASES.index(args.through_phase):break
            phase_results=[]
            for key in matrix['order']:
                if not any(t['model']==key and phase_for(t)==phase for t in matrix['task_items']):continue
                env=registry['models'][key]['environment'];python=envs.get(env,sys.executable)
                if args.backend=='hf' and env not in envs:raise ValueError('Missing model environment: '+env)
                cmd=[python,'-u','-B',str(ROOT/'run_batch.py'),'--matrix',str(args.matrix.resolve()),'--data-root',str(args.data_root),
                     '--run-root',str(args.run_root),'--backend',args.backend,'--execute','--worker-model',key,'--phase',phase]
                if args.allow_download:cmd.append('--allow-download')
                if args.retry_failures:cmd.append('--retry-failures')
                with (args.run_root/(key+'.'+phase+'.log')).open('a',encoding='utf-8') as log:
                    try:result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'CUDA_VISIBLE_DEVICES':'0','PYTHONUTF8':'1'})
                    except KeyboardInterrupt:
                        atomic(args.run_root/'batch_state.json',{'status':'interrupted','phase':phase,'model_results':results});raise
                # A zero worker exit is insufficient without every requested task receipt.
                state_path=args.run_root/(key+'.'+phase+'.state.json')
                expected_ids={t['task_id'] for t in matrix['task_items'] if t['model']==key and phase_for(t)==phase}
                receipt=read(state_path) if state_path.exists() else {}
                actual=receipt.get('tasks',[])
                ids=[t.get('task_id') for t in actual]
                complete=(len(ids)==len(set(ids)) and set(ids)==expected_ids and all(t.get('exit_code')==0 for t in actual))
                code=result.returncode or (0 if complete else 2)
                row={'model':key,'phase':phase,'exit_code':code,'task_receipts_complete':complete,'policy':'continue_other_models_in_current_phase; block_next_phase_on_failure'}
                results.append(row);phase_results.append(row)
                atomic(args.run_root/'batch_state.json',{'status':'running','phase':phase,'model_results':results})
            if any(r['exit_code'] for r in phase_results):
                atomic(args.run_root/'batch_state.json',{'status':'blocked_phase_failure','phase':phase,'model_results':results})
                return 2
        atomic(args.run_root/'batch_state.json',{'status':'requested_phases_completed','through_phase':args.through_phase,'completed_task_ids':expected_tasks,'deferred_task_ids':deferred_tasks,'model_results':results})
        return 0

if __name__=='__main__':sys.exit(main())
