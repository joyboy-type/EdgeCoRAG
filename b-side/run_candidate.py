"""Candidate smoke adapter: validate, synthetic, or explicitly selected CUDA inference."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

from score_minimal import parse_choice, PARSER_VERSION
from run_smoke import no_answers, TEMPLATE, TEMPLATE_VERSION, PROTOCOL
from handover_adapter import load_bundle, result_metadata

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT/'configs/qwen3_vl_4b_smoke.json').read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def save(path, value):
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2)
        f.flush(); os.fsync(f.fileno())

def validate_inputs(path, sample_root, condition):
    rows = read(path)
    if not isinstance(rows,list) or [r['qid'] for r in rows] != ['0','43']:
        raise ValueError('Exactly qids 0 and 43 in order are required for this smoke.')
    assets = read(sample_root/'audit/assets.json')
    mapping = {a['position_key']:a for a in assets}
    for row in rows:
        no_answers(row)
        if (row['condition'],row['protocol_version'],row['template_version']) != (condition,PROTOCOL,TEMPLATE_VERSION):
            raise ValueError('Condition/protocol/template mismatch')
        count = 0 if condition == 'S0' else (1 if row['qid']=='43' else 5)
        refs = [row['query_image']]+row['evidence']
        if len(row['evidence']) != count or len(row['image_order']) != len(refs):
            raise ValueError('Incorrect evidence/image count')
        text = TEMPLATE.format(question=row['question'], **row['choices'])
        expected = {'messages':[{'role':'user','content':[*[{'type':'image','image_index':i} for i in range(len(refs))],{'type':'text','text':text}]}]}
        if row['model_request'] != expected:
            raise ValueError('Model request differs from fixed shared template/order')
        for i,ref in enumerate(refs):
            a = mapping[ref['position_key']]
            field = 'image' if i==0 else ('retrieved_images' if condition=='S1' else 'gt_images')
            if a['qid']!=row['qid'] or a['field']!=field or a['index']!=max(0,i-1):
                raise ValueError('Incorrect query/evidence order')
            if ref['sha256']!=a['sha256'] or ref['path']!=a['file'] or row['image_order'][i]!={'image_index':i,**ref}:
                raise ValueError('Image manifest binding differs')
            p=(sample_root/ref['path']).resolve()
            if sample_root not in p.parents or digest(p)!=ref['sha256']:
                raise ValueError('Image outside sample root or hash mismatch')
    return rows

def build_messages(row, sample_root, loader):
    """Only image objects and neutral text are sent to the official processor."""
    refs = [row['query_image']]+row['evidence']
    images = [loader((sample_root/ref['path']).resolve()) for ref in refs]
    content = []
    for item in row['model_request']['messages'][0]['content']:
        if item['type']=='image': content.append({'type':'image','image':images[item['image_index']]})
        elif item['type']=='text': content.append({'type':'text','text':item['text']})
        else: raise ValueError('Unsupported content')
    return [{'role':'user','content':content}]

class SyntheticBackend:
    synthetic=True
    def infer(self,row,root):
        # Opaque stand-ins verify ordered image binding; no tokenization or GPU claims.
        messages=build_messages(row,root,lambda p:('synthetic-image',p.name))
        return {'raw_output':'A','final_output':'A','synthetic':True,'input_image_count':len(messages[0]['content'])-1,
                'input_tokens':None,'generated_tokens':None,'timing':None,'cuda_memory':None}

class QwenBackend:
    synthetic=False
    def __init__(self,allow_download=False):
        import torch
        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
        if sys.version_info[:2]!=(3,12): raise RuntimeError('Use the pinned Python 3.12 environment')
        for name,expected in [('torch',CFG['torch_version']),('torchvision',CFG['torchvision_version']),('transformers',CFG['transformers_version']),('Pillow',CFG['pillow_version'])]:
            if importlib.metadata.version(name).split('+')[0]!=expected: raise RuntimeError(f'{name} version differs from candidate configuration')
        if not torch.cuda.is_available() or torch.cuda.device_count()!=1: raise RuntimeError('Expose exactly one working NVIDIA GPU with CUDA_VISIBLE_DEVICES')
        if torch.version.cuda!='12.8': raise RuntimeError('This startup configuration requires the pinned cu128 runtime')
        self.torch=torch
        torch.manual_seed(CFG['seed'])
        start=time.perf_counter()
        self.processor=AutoProcessor.from_pretrained(CFG['model_id'],revision=CFG['revision'],trust_remote_code=False,
                           local_files_only=not allow_download,use_fast=False,
                           min_pixels=CFG['image_processing']['min_pixels'],max_pixels=CFG['image_processing']['max_pixels'])
        self.model=Qwen3VLForConditionalGeneration.from_pretrained(CFG['model_id'],revision=CFG['revision'],trust_remote_code=False,
                           local_files_only=not allow_download,dtype=torch.float16,attn_implementation='sdpa').to('cuda:0').eval()
        torch.cuda.synchronize()
        self.load_seconds=time.perf_counter()-start
        self.actual_dtype=str(next(self.model.parameters()).dtype)
        self.processor_config=self.processor.image_processor.to_dict()
    def infer(self,row,root):
        from PIL import Image
        torch=self.torch
        torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
        started=time.perf_counter()
        def load(p):
            with Image.open(p) as im:
                im.load(); return im.convert('RGB')
        messages=build_messages(row,root,load)
        inputs=self.processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt')
        inputs.pop('token_type_ids',None)
        preprocessing=time.perf_counter()-started
        tokens=int(inputs['input_ids'].shape[-1])
        grid=inputs['image_grid_thw'].tolist() if 'image_grid_thw' in inputs else None
        inputs=inputs.to('cuda:0')
        torch.cuda.synchronize(); begin=time.perf_counter()
        with torch.inference_mode():
            ids=self.model.generate(**inputs,max_new_tokens=CFG['max_new_tokens'],do_sample=False,use_cache=True)
        torch.cuda.synchronize(); generation=time.perf_counter()-begin
        tail=ids[:,tokens:]
        decoded=self.processor.batch_decode(tail,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
        special=self.processor.batch_decode(tail,skip_special_tokens=False,clean_up_tokenization_spaces=False)[0]
        return {'raw_output':decoded,'final_output':decoded,'raw_output_with_special_tokens':special,'synthetic':False,
                'input_image_count':len(messages[0]['content'])-1,'input_tokens':tokens,'generated_tokens':int(tail.shape[-1]),
                'image_grid_thw':grid,'actual_dtype':self.actual_dtype,
                'timing':{'preprocess_seconds':preprocessing,'generate_seconds':generation,'total_seconds':time.perf_counter()-started},
                'cuda_memory':{'max_allocated_bytes':torch.cuda.max_memory_allocated(),'max_reserved_bytes':torch.cuda.max_memory_reserved()}}

def is_oom_error(error):
    """Recognize allocator OOM without importing the inference runtime."""
    return (any(t.__name__ == 'OutOfMemoryError' for t in type(error).__mro__)
            or 'cuda out of memory' in str(error).lower()
            or 'cuda error: out of memory' in str(error).lower())

def prediction_for(row,base,backend):
    record={'qid':row['qid'],'condition':row['condition'],'raw_output':'','final_output':'','generation_error':None,
            'parsed_choice':None,'parse_status':'generation_error','parser_version':PARSER_VERSION,'synthetic':backend.synthetic,
            'input_tokens':None,'generated_tokens':None,'timing':None,'cuda_memory':None}
    try:
        if row.get('input_status','ok')!='ok':
            raise ValueError('InputUnavailable: '+str(row.get('input_error') or row['input_status']))
        record.update(backend.infer(row,base))
        record['parsed_choice'],record['parse_status']=parse_choice(record['final_output'])
    except Exception as e:
        record['generation_error']=type(e).__name__+': '+str(e)
        record['error_traceback']=traceback.format_exc()
        record['oom']=is_oom_error(e)
        if not backend.synthetic:
            try:
                record['cuda_memory']={'max_allocated_bytes':backend.torch.cuda.max_memory_allocated(),'max_reserved_bytes':backend.torch.cuda.max_memory_reserved()}
                backend.torch.cuda.empty_cache()
            except Exception: pass
    return result_metadata(row,record,CFG)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs-root',type=Path,required=True)
    p.add_argument('--sample-root',type=Path,required=True)
    p.add_argument('--answers',type=Path,help='Given only to independent scorer; never read by adapter')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--backend',choices=['validate','synthetic','qwen'],default='validate')
    p.add_argument('--allow-download',action='store_true',help='Explicitly permit pinned weights/processor download on future server')
    p.add_argument('--bundle-manifest',type=Path,help='Explicit A-derived bundle, separate from legacy two-question fixtures')
    p.add_argument('--conditions',nargs='+',choices=['S0','S1','S2'],default=['S0','S1','S2'])
    args=p.parse_args()
    base=args.sample_root.resolve(); output=args.output.resolve()
    if output.exists(): raise ValueError('Output exists; select a new run directory')
    if ROOT==output or ROOT in output.parents: raise ValueError('Keep run outputs outside the repository code directory')
    if len(args.conditions)!=len(set(args.conditions)):raise ValueError('Duplicate condition names')
    bundle=None
    if args.bundle_manifest:
        bundle,manifests=load_bundle(args.bundle_manifest,args.inputs_root,base,args.conditions)
        expected_answers=bundle['answers_sha256']
    else:
        integrity=read(ROOT/'configs/sources_and_integrity.json')['external_sample_material']['integrity_sha256']
        for name,expected in integrity.items():
            if name!='scoring/answers.json' and digest(base/name)!=expected:
                raise ValueError('External source integrity mismatch: '+name)
        server_integrity=read(ROOT/'configs/server_materials.json')
        for condition in args.conditions:
            if digest(args.inputs_root/f'{condition}.json')!=server_integrity['input_sha256'][condition]:
                raise ValueError('Prepared input manifest hash differs: '+condition)
        manifests={c:validate_inputs(args.inputs_root/f'{c}.json',base,c) for c in args.conditions}
        expected_answers=integrity['scoring/answers.json']
    if args.backend!='validate' and not args.answers: raise ValueError('--answers required for independent condition scoring')
    output.mkdir(parents=True)
    code_hashes={n:digest(ROOT/n) for n in ['run_candidate.py','handover_adapter.py','accept_handover.py','score_minimal.py','run_smoke.py','configs/shared_visual_mcq_v1.json','configs/qwen3_vl_4b_smoke.json']}
    metadata={'backend':args.backend,'synthetic':args.backend=='synthetic','model':CFG,'code_sha256':code_hashes,
              'python':platform.python_version(),'system':platform.platform(),'protocol':PROTOCOL,'template':TEMPLATE_VERSION,
              'input_sha256':{c:digest(args.inputs_root/f'{c}.json') for c in manifests},'status':'validated_inputs',
              'weights_loaded':False,'packages':{}}
    metadata['package_manifest_sha256']=digest(ROOT/'package_hashes.json')
    metadata['A_baseline_commit']=bundle['baseline_commit'] if bundle else None
    metadata['evidence_version']=bundle.get('evidence_version') if bundle else None
    metadata['dataset_revision']=bundle['dataset_revision'] if bundle else '43620fde4044bb150e158c67ad7af6b6b11e1da2'
    metadata['bundle_sha256']=digest(args.bundle_manifest) if bundle else None
    metadata['fixed_qids']=[r['qid'] for r in next(iter(manifests.values()))]
    metadata['run_batch_id']=output.name
    git=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True,encoding='utf-8') if __import__('shutil').which('git') else None
    metadata['git_commit']=git.stdout.strip() if git and git.returncode==0 else None
    metadata['code_version_note']='Per-file and package hashes identify the actual files, including uncommitted edits; git_commit alone does not.'
    for name in ['torch','torchvision','transformers','Pillow']:
        try:metadata['packages'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: metadata['packages'][name]=None
    if args.backend=='validate':
        save(output/'run.json',metadata); print('PASS: adapter input validation only; no inference runtime imported.'); return
    save(output/'run.started.json',metadata)
    backend=None; load_error=None; stop_error=None
    try:
        ready_rows=[r for rows in manifests.values() for r in rows if r.get('input_status','ok')=='ok']
        if not ready_rows:
            backend=type('UnavailableBackend',(),{'synthetic':args.backend=='synthetic'})()
        else:backend=SyntheticBackend() if args.backend=='synthetic' else QwenBackend(args.allow_download)
        if not backend.synthetic and ready_rows:
            metadata.update({'weights_loaded':True,'model_load_seconds':backend.load_seconds,'actual_dtype':backend.actual_dtype,
                             'quantization':'none','processor_config':backend.processor_config,
                             'cuda_runtime':backend.torch.version.cuda,'gpu_name':backend.torch.cuda.get_device_name(0),
                             'gpu_total_bytes':backend.torch.cuda.get_device_properties(0).total_memory,
                             'gpu_compute_capability':list(backend.torch.cuda.get_device_capability(0))})
            info=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],
                                capture_output=True,text=True,encoding='utf-8',errors='replace')
            metadata['nvidia_smi']=info.stdout.strip()
            warmups=[]
            for _ in range(CFG['warmup_runs']):
                record=prediction_for(ready_rows[0],base,backend)
                warmups.append(record)
                if record.get('oom'):
                    stop_error=record['generation_error']
                    metadata['oom_origin']={'phase':'warmup','qid':record['qid'],'condition':record['condition']}
                    break
            save(output/'warmup.json',{'not_scored':True,'records':warmups})
            metadata['warmup_success']=all(x['generation_error'] is None for x in warmups)
    except Exception as e:
        load_error=type(e).__name__+': '+str(e)
        metadata['startup_error']=load_error
        if is_oom_error(e):
            stop_error=load_error
            metadata['oom_origin']={'phase':'startup'}
        save(output/'startup_error.json',{'error':load_error,'traceback':traceback.format_exc()})
    summary={}; generation_failures=0
    for c,rows in manifests.items():
        d=output/c;d.mkdir(); pred=d/'predictions.jsonl'
        with pred.open('x',encoding='utf-8') as f:
            for row in rows:
                if load_error or stop_error:
                    record={'qid':row['qid'],'raw_output':'','final_output':'','generation_error':('NotRunAfterOOM: '+stop_error) if stop_error else load_error,'parsed_choice':None,
                            'parse_status':'generation_error','parser_version':PARSER_VERSION,'synthetic':args.backend=='synthetic','condition':c}
                    record['execution_status']='not_run_after_oom' if stop_error else 'startup_failed'
                    record=result_metadata(row,record,CFG)
                else:
                    record=prediction_for(row,base,backend)
                    if record.get('oom'):
                        stop_error=record['generation_error']
                        metadata['oom_origin']={'phase':'inference','qid':row['qid'],'condition':c}
                        record['execution_status']='oom'
                # OOM is fail-stop across all remaining questions/conditions. Only
                # failure records and independent scoring continue; no model retry.

                record['evidence_version']=bundle.get('evidence_version') if bundle else None
                record['run_batch_id']=metadata['run_batch_id']
                record['repeat_index']=0
                record['row_key']=[record['run_batch_id'],record['qid'],record['model_id'],record['model_revision'],c,
                                   row['protocol_version'],record['repeat_index'],record['evidence_version']]
                generation_failures+=int(record['generation_error'] is not None)
                f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
        score=d/'score.json'
        if digest(args.answers)!=expected_answers:
            raise ValueError('Scoring answer file differs from verified external fixture; predictions remain saved')
        child=subprocess.run([sys.executable,'-B',str(ROOT/'score_minimal.py'),'--answers',str(args.answers),'--predictions',str(pred),'--output',str(score)],capture_output=True,text=True,encoding='utf-8')
        save(d/'scorer_execution.json',{'returncode':child.returncode,'stdout':child.stdout,'stderr':child.stderr})
        if child.returncode: raise RuntimeError('Independent scorer failed; inspect scorer_execution.json')
        value=read(score)
        value.update({'synthetic':args.backend=='synthetic','condition':c,'protocol_version':PROTOCOL,'smoke_only':True})
        value['input_failure_count']=sum(r.get('input_status','ok')!='ok' for r in rows)
        value['valid_model_condition']=args.backend=='qwen' and not load_error and value['input_failure_count']==0 and value['overall']['status_counts']['generation_error']==0
        value['A_baseline_commit']=bundle['baseline_commit'] if bundle else None
        value['evidence_version']=bundle.get('evidence_version') if bundle else None
        value['run_batch_id']=metadata['run_batch_id']
        value['qid_raw_id_mapping']=[{'qid':r['qid'],'raw_id':r.get('raw_id',r['qid'])} for r in rows]
        # Add aliases only after independent scoring; prediction-carried correctness is never trusted.
        predictions=[json.loads(x) for x in pred.read_text(encoding='utf-8').splitlines()]
        correct_by_id={r['qid']:r['correct'] for r in value['per_question']}
        save(d/'results.b_native.json',{'condition':c,'synthetic':args.backend=='synthetic',
             'schema_note':'B-native extension, not A result schema compliant until strict_choice_v1 is accepted',
             'rows':[{**r,'correct':correct_by_id[r['qid']]} for r in predictions]})
        # Existing scorer remains unchanged. Annotate only this newly created run result.
        score.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        summary[c]=value['overall'];print(c,'synthetic='+str(value['synthetic']),value['overall'],flush=True)
    if stop_error:
        metadata['oom_error']=stop_error
        metadata['oom_policy']='stop generation; preserve fixed-list failures; no retry or budget adjustment'
    metadata.update({'status':'oom_stopped' if stop_error else 'startup_failed' if load_error else ('completed_with_generation_failures' if generation_failures else 'completed'),
                     'generation_failure_count':generation_failures,'summary':summary})
    save(output/'run.json',metadata)
    if load_error or stop_error or generation_failures: sys.exit(2)
    print('COMPLETE: smoke only; inspect errors and parse status before treating this as successful model execution.')

if __name__=='__main__':
    main()
