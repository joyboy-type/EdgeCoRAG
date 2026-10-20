"""Freeze exact recorded versions, never install/import GPU runtimes.
Reproduce with explicit --runtime-json --preflight-json --out (new directory).
The B metadata lock numpy pin is NOT an observed installed-version receipt.
"""
import argparse,json,hashlib,re
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--runtime-json',type=Path,required=True);p.add_argument('--preflight-json',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.exists():raise FileExistsError(a.out)
 runtime=json.loads(a.runtime_json.read_text())['runtime'];pre=json.loads(a.preflight_json.read_text())
 packages=dict(runtime['packages']);packages['sentence-transformers']=pre['isolated_retriever_import_check']['sentence_transformers']
 lock=REPO/'b-side/requirements-gemma4.lock.txt';numpy=next(s.split('==')[1] for s in lock.read_text().splitlines() if s.startswith('numpy=='));packages['numpy']=numpy
 driver=runtime['nvidia_smi']['stdout'].split(',')[2].strip()
 rows=['# 来自回执与registry，未重新安装验证；非新环境已验证锁。',
       '# Python=='+runtime['python']+' (round2 runtime)',
       '# CUDA-runtime=='+runtime['cuda_runtime']+' (torch build/runtime, NOT driver max CUDA)',
       '# NVIDIA-driver=='+driver+' (recorded nvidia-smi)',
       '# Driver-max-CUDA=='+pre['driver_max_CUDA']+' (capability ceiling, not runtime)',
       '# sentence-transformers from isolated-retriever import receipt; packages are not all observed in a single co-resident environment.',
       '# numpy from metadata-only B gemma lock; installed NumPy version in round2 receipt absent. Not verified by execution.']
 rows += [name+'=='+packages[name] for name in ['torch','torchvision','transformers','sentence-transformers','Pillow','numpy']]
 a.out.mkdir(parents=True);(a.out/'requirements.lock').write_text('\n'.join(rows)+'\n')
 registry_path=REPO/'b-side/configs/model_registry.json';registry=json.loads(registry_path.read_text())
 models={k:{f:v[f] for f in ['model_id','revision','weights'] if f in v} for k,v in registry['models'].items()}
 facts=dict(status='recorded_versions_only_not_reinstalled',packages=packages,python=runtime['python'],cuda_runtime=runtime['cuda_runtime'],driver=driver,
  source_sha256={'round2_setup':sha(a.runtime_json),'historical_preflight':sha(a.preflight_json),'b-side/requirements-gemma4.lock.txt':sha(lock),'b-side/configs/model_registry.json':sha(registry_path)},
  field_sources={'torch/torchvision/transformers/Pillow/Python/CUDA/driver':'round2 setup.runtime', 'sentence-transformers':'preflight.isolated_retriever_import_check','numpy':'B gemma4 metadata-only registry lock; NOT observed runtime'},
  models=models,encoder={'id':'google/embeddinggemma-2','revision':'914f7f89142e33e77833254d9c9b90c3cef7303b','weights_sha256_status':'not recorded in these selected receipts; future tool requires explicit local hash, no unknown placeholder'},
  limitations=['Not a pip-resolved complete transitive lock','NumPy installed-version evidence absent; metadata pin is not installation verification','No unified new fp32 encoder stack validated','No downloads, installs, upgrades, runtime/model imports'])
 (a.out/'environment_sources.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'packages':packages,'python':runtime['python'],'driver':driver,'cuda_runtime':runtime['cuda_runtime']},indent=2))
if __name__=='__main__':main()
