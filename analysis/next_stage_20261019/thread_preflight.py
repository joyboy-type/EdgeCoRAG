"""B4 CPU-only hostile-environment preflight. No model or CUDA calls.

Reproduce (also Linux target command, only when its session is approved):
$PY analysis/next_stage_20261019/thread_preflight.py --out <NEW_JSON>
All7 environments run; unavailable torch/threadpoolctl are explicit, not skipped.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'b-side'))
import e2e_smoke as smoke
BAD=['abc','','0','-1','4.0',' 4']
def invalid(v):return not isinstance(v,str) or not v.isdigit() or int(v)<=0
def bounded(requested,cpu,affinity,quota):
 values=[requested,cpu,affinity]
 if quota is not None:values.append(quota)
 if any(type(v) is not int or v<=0 for v in values):raise ValueError('Invalid CPU allowance')
 return min(values)
def enforce(applied,observed,intra,inter,pools):
 if applied!=observed:raise ValueError('applied != observed')
 if intra!='unavailable' and intra!=applied:raise ValueError('torch intra mismatch')
 if inter!='unavailable' and inter!=1:raise ValueError('torch interop must be1')
 if pools!='unavailable' and any(v!=applied for v in pools):raise ValueError('BLAS mismatch')
def worker(requested):
 cpu=os.cpu_count();affinity=smoke.default_affinity();quota=smoke.cpu_quota_threads()
 actual=bounded(requested,cpu,affinity,quota)
 inherited=smoke.inherited_thread_environment()
 configuration=smoke.configure_cpu_threads(actual)
 observed=int(os.environ['OMP_NUM_THREADS'])
 intra=inter=pools=blas='unavailable';unavailable={}
 try:import torch
 except ImportError:unavailable['torch']='unavailable'
 else:
  torch.set_num_threads(actual);torch.set_num_interop_threads(1)
  intra,inter=torch.get_num_threads(),torch.get_num_interop_threads()
 try:from threadpoolctl import threadpool_limits,threadpool_info
 except ImportError:unavailable['threadpoolctl']='unavailable'
 else:
  import numpy as np
  np.ones((2,2))@np.ones((2,2))
  limits=threadpool_limits(limits=actual)
  blas=[{k:p.get(k) for k in ['internal_api','num_threads','prefix']} for p in threadpool_info()]
  pools=[p['num_threads'] for p in blas]
 enforce(actual,observed,intra,inter,pools)
 return dict(env_inherited=inherited,invalid_detected=invalid(inherited.get('OMP_NUM_THREADS')),
  applied=actual,observed=observed,cpu_count=cpu,affinity=affinity,cgroup_quota=quota,
  torch_intra=intra,torch_inter=inter,blas_pools=blas,
  blas_matches_requested='unavailable' if pools=='unavailable' or not pools else all(v==actual for v in pools),
  configured=configuration,unavailable=unavailable,
  scope='CPU only; macOS cannot reproduce target libgomp warning; no target GPU-machine claim')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true')
 p.add_argument('--requested',type=int,default=8);p.add_argument('--out',type=Path);args=p.parse_args()
 if args.worker:
  print(json.dumps(worker(args.requested),ensure_ascii=False));return
 rows=[]
 for v in [*BAD,'8']:
  env={k:val for k,val in os.environ.items() if k not in smoke.THREAD_ENV_VARS}
  env['OMP_NUM_THREADS']=v;env['PYTHONDONTWRITEBYTECODE']='1'
  result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker','--requested',str(args.requested)],
    env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError('Thread apply aborted: '+result.stderr)
  r=json.loads(result.stdout);r['hostile_value']=v
  if r['invalid_detected']!=(v in BAD):raise ValueError('Illegal value was not detected')
  rows.append(r)
 value=dict(status='CPU_environment_verified_backend_availability_explicit',cases=len(rows),rows=rows,
  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  formal_backend_ready=all(r['torch_intra']!='unavailable' and r['blas_matches_requested'] is True for r in rows),
  target_linux_validation='待 GPU 会话；本机不可复现 libgomp')
 if args.out:
  with args.out.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps(value,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
