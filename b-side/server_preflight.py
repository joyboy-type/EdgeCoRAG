"""Read-only server preflight; no weights/config downloads and no model allocation."""
import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def collect(workdir, check_runtime=False):
    cfg = json.loads((ROOT/'configs/qwen3_vl_4b_smoke.json').read_text(encoding='utf-8'))
    report = {'python':platform.python_version(), 'system':platform.system(), 'machine':platform.machine(),
              'python_target':cfg['python_minor'], 'disk_free_bytes':shutil.disk_usage(workdir).free,
              'tmux_available':bool(shutil.which('tmux')), 'packages':{}, 'runtime_imported':check_runtime,
              'model_loaded':False, 'weights_downloaded':False, 'needs_gpu_verification':True}
    for name in ['torch','torchvision','transformers','Pillow']:
        try: report['packages'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: report['packages'][name] = None
    expected={'torch':cfg['torch_version'],'torchvision':cfg['torchvision_version'],
              'transformers':cfg['transformers_version'],'Pillow':cfg['pillow_version']}
    report['version_match']={k: bool(report['packages'][k]) and report['packages'][k].split('+')[0]==v for k,v in expected.items()}
    report['python_minor_matches']=sys.version_info[:2]==(3,12)
    try:
        import os
        report['host_physical_memory_bytes']=os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
    except (ValueError, OSError, AttributeError): report['host_physical_memory_bytes']=None
    if shutil.which('nvidia-smi'):
        cmd = ['nvidia-smi','--query-gpu=index,name,driver_version,memory.total,memory.used,utilization.gpu','--format=csv,noheader']
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
        report['nvidia_smi'] = {'returncode':p.returncode,'gpus':p.stdout.strip(),'error':p.stderr.strip()}
    else: report['nvidia_smi'] = None
    if check_runtime:
        try:
            import torch
            from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
            report['runtime'] = {'torch_version':torch.__version__, 'built_cuda':torch.version.cuda,
                                 'cuda_available':torch.cuda.is_available(), 'device_count':torch.cuda.device_count(),
                                 'class_imports':True}
            if torch.cuda.is_available():
                report['runtime']['devices'] = [{'name':torch.cuda.get_device_name(i), 'compute_capability':list(torch.cuda.get_device_capability(i)),
                                                  'total_memory_bytes':torch.cuda.get_device_properties(i).total_memory} for i in range(torch.cuda.device_count())]
                report['runtime']['small_cuda_kernel_result']=float((torch.ones(1,device='cuda')*2).item())
        except Exception as e: report['runtime_error'] = type(e).__name__+': '+str(e)
    return report

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workdir', type=Path, default=Path.cwd())
    p.add_argument('--check-runtime', action='store_true', help='Import installed runtime classes; never call from_pretrained')
    args = p.parse_args()
    result = collect(args.workdir, args.check_runtime)
    print(json.dumps(result,ensure_ascii=True,indent=2))
    if args.check_runtime and ('runtime_error' in result or not result.get('runtime',{}).get('cuda_available') or not all(result['version_match'].values()) or not result['python_minor_matches']):
        sys.exit(2)
