"""Per-environment read-only preflight; optional tiny CUDA kernel, never a model load/download."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from batch_inputs import read,sha

ROOT=Path(__file__).resolve().parent

def inspect(model_key,workdir,runtime=False):
    registry=read(ROOT/'configs/model_registry.json');m=registry['models'][model_key];env=registry['environments'][m['environment']]
    value={'model':m,'environment':env,'registry_sha256':sha(ROOT/'configs/model_registry.json'),
        'python':platform.python_version(),'platform':platform.platform(),'disk_free_bytes':shutil.disk_usage(workdir).free,
        'tmux_available':bool(shutil.which('tmux')),'model_loaded':False,'weights_downloaded':False,'runtime_requested':runtime,'packages':{},'errors':[]}
    if sys.version_info[:2]!=(3,12):value['errors'].append('Python 3.12 required')
    for name,key in [('torch','torch'),('torchvision','torchvision'),('transformers','transformers'),('Pillow','pillow')]:
        try:version=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:version=None
        value['packages'][name]=version
        if not version or version.split('+')[0]!=env[key]:value['errors'].append(name+' version mismatch/missing')
    if runtime:
        try:
            import torch
            import transformers
            value['model_class_present']=hasattr(transformers,m['class'])
            if not value['model_class_present']:value['errors'].append('Model class missing')
            if not torch.cuda.is_available() or torch.cuda.device_count()!=1:raise RuntimeError('Exactly one visible CUDA GPU required')
            value.update({'cuda_runtime':torch.version.cuda,'gpu_name':torch.cuda.get_device_name(0),
                'gpu_total_bytes':torch.cuda.get_device_properties(0).total_memory,'bf16_supported':torch.cuda.is_bf16_supported(),
                'small_cuda_result':float((torch.ones(1,device='cuda')*2).item())})
            torch.cuda.synchronize()
            if torch.version.cuda!='12.8':value['errors'].append('Expected cu128 build')
            if m['dtype']=='bfloat16' and not value['bf16_supported']:value['errors'].append('BF16 unsupported; no fallback')
            info=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],capture_output=True,text=True,encoding='utf-8',timeout=20)
            value['nvidia_smi']={'exit_code':info.returncode,'stdout':info.stdout,'stderr':info.stderr}
        except Exception as e:value['errors'].append(type(e).__name__+': '+str(e))
    value['status']='blocked' if value['errors'] else 'runtime_preflight_passed_model_still_untested' if runtime else 'metadata_only'
    return value

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',required=True);p.add_argument('--workdir',type=Path,default=Path.cwd());p.add_argument('--runtime',action='store_true')
    a=p.parse_args();v=inspect(a.model,a.workdir,a.runtime);print(json.dumps(v,indent=2));sys.exit(2 if a.runtime and v['errors'] else 0)
