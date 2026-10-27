#!/usr/bin/env python3
"""Detached single-instance completion and preservation/shutdown controller."""
import argparse,fcntl,hashlib,json,os,signal,socket,subprocess,tarfile,time,traceback
from pathlib import Path
EXPECTED_HOST='autodl-container-3n631bugr0-a3d5fb59'
BASE=Path('/root/autodl-tmp/completion-run-20261028')
MIG=Path('/root/autodl-tmp/edgecorag-migrate-20261028')
PYTHON='/root/autodl-tmp/envs/completion/bin/python'

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n');tmp.replace(p);os.sync()
def migration_valid(receipt,manifest,sha):
 return receipt.get('complete') is True and receipt.get('bad')==[] and receipt.get('manifest_sha256')==sha and receipt.get('checked')==receipt.get('expected')==manifest.get('file_count') and receipt.get('total_bytes')==manifest.get('total_bytes')
def kill_group(pgid):
 try:os.killpg(pgid,signal.SIGTERM)
 except ProcessLookupError:return
 time.sleep(1)
 try:os.killpg(pgid,signal.SIGKILL)
 except (ProcessLookupError,PermissionError):pass

def run_command(cmd,log,timeout,state):
 with Path(log).open('ab') as output:
  proc=subprocess.Popen(cmd,stdout=output,stderr=subprocess.STDOUT,start_new_session=True);state['active_pgid']=proc.pid
  if state.get('state_path'):write(state['state_path'],state)
  try:return proc.wait(timeout=max(.01,timeout))
  except subprocess.TimeoutExpired:kill_group(proc.pid);proc.wait();return 124
  finally:state['active_pgid']=None

def archive_results(root,target):
 root=Path(root);target=Path(target);files={str(p.relative_to(root)):digest(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith('.lock')};target.parent.mkdir(exist_ok=True,parents=True)
 with tarfile.open(target,'w:gz') as tf:
  for relative in sorted(files):tf.add(root/relative,arcname=root.name+'/'+relative,recursive=False)
 with tarfile.open(target,'r:gz') as tf:
  for relative,sha in files.items():
   stream=tf.extractfile(root.name+'/'+relative);assert stream and hashlib.sha256(stream.read()).hexdigest()==sha
 return {'path':str(target),'sha256':digest(target),'bytes':target.stat().st_size,'files':len(files),'verified':True,'members':files}

def stop_instance(evidence):
 assert socket.gethostname()==EXPECTED_HOST,'Refuse shutdown on another host'
 receipt={'host':socket.gethostname(),'epoch':time.time(),'status':'issuing_shutdown_after_preservation',**evidence};p=BASE/'shutdown_receipt.json';write(p,receipt)
 try:
  result=subprocess.run(['shutdown','-h','now'],capture_output=True,text=True,timeout=15);receipt.update(shutdown_rc=result.returncode,shutdown_stdout=result.stdout,shutdown_stderr=result.stderr)
 except Exception as e:receipt['shutdown_error']=repr(e)
 write(p,receipt);time.sleep(8);found=[]
 for candidate in Path('/proc').glob('[0-9]*'):
  try:
   if (candidate/'comm').read_text().strip()=='supervisord' and b'/init/supervisor/supervisor.ini' in (candidate/'cmdline').read_bytes():found.append(int(candidate.name))
  except OSError:pass
 if len(found)!=1:raise RuntimeError('Cannot identify unique AutoDL supervisor: '+str(found))
 receipt.update(status='stopping_current_platform_supervisor',supervisor_pid=found[0]);write(p,receipt);os.kill(found[0],signal.SIGTERM)

def preserve_and_stop(state):
 if state.get('active_pgid'):kill_group(state['active_pgid'])
 state.update(finished_epoch=time.time(),active_pgid=None)
 write(BASE/'final_receipt_20261028.json',state)
 evidence={'final_receipt_sha256':digest(BASE/'final_receipt_20261028.json')}
 try:
  evidence['archive']=archive_results(BASE,BASE.parent/'completion-results-20261028.tar.gz');write(BASE/'archive_verification.json',evidence['archive'])
 except Exception as e:evidence['archive_error']=repr(e);write(BASE/'archive_error.json',{'error':repr(e),'raw_results_remain_on_persistent_disk':True})
 os.sync();stop_instance(evidence)

def watchdog():
 assert socket.gethostname()==EXPECTED_HOST
 while not (BASE/'controller_armed.json').exists():time.sleep(2)
 armed=json.loads((BASE/'controller_armed.json').read_text());deadline=armed['hard_deadline_epoch'];pid=armed['pid']
 while True:
  time.sleep(10)
  try:os.kill(pid,0);alive=True
  except ProcessLookupError:alive=False
  if not alive or time.time()>deadline-300:
   state=json.loads((BASE/'controller_state.json').read_text()) if (BASE/'controller_state.json').exists() else {}
   state['watchdog_reason']='controller_disappeared' if not alive else 'hard_deadline_preservation'
   if alive:
    try:os.kill(pid,signal.SIGKILL)
    except ProcessLookupError:pass
   preserve_and_stop(state);return

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--watchdog',action='store_true');ap.add_argument('--hours',type=float,default=4);args=ap.parse_args()
 assert socket.gethostname()==EXPECTED_HOST
 BASE.mkdir(exist_ok=True,parents=True)
 if args.watchdog:return watchdog()
 lock=(BASE/'controller.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 state={'schema':'completion_controller_20261028/v1','pid':os.getpid(),'host':socket.gethostname(),'started_epoch':time.time(),'active_pgid':None,'steps':[],'state_path':str(BASE/'controller_state.json'),'source_commit':(BASE/'source_commit.txt').read_text().strip()};deadline=time.time()+args.hours*3600;state['hard_deadline_epoch']=deadline
 write(BASE/'controller_armed.json',state);os.environ.update(COMPLETION_HARD_DEADLINE_EPOCH=str(deadline),CUDA_HOME='/root/autodl-tmp/cuda128',TORCH_CUDA_ARCH_LIST='8.9',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONUNBUFFERED='1')
 os.environ['PATH']='/root/autodl-tmp/cuda128/bin:/root/autodl-tmp/envs/completion/bin:/root/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
 code=Path(__file__).parent
 def phase(name,cmd,seconds):
  state['phase']=name;write(BASE/'controller_state.json',state);t=time.time();rc=run_command(cmd,BASE/(name+'.log'),min(seconds,deadline-600-time.time()),state);state['steps'].append({'step':name,'rc':rc,'started_epoch':t,'finished_epoch':time.time()});write(BASE/'controller_state.json',state);return rc
 try:
  manifest=json.loads((MIG/'manifest.json').read_text());receipt=json.loads((MIG/'verification.json').read_text());assert migration_valid(receipt,manifest,digest(MIG/'manifest.json')),'Migration verification mismatch'
  state['migration_verification']=receipt;state['phase']='waiting_environment';write(BASE/'controller_state.json',state);env_deadline=time.time()+1800
  while not (BASE/'environment_exit_code.txt').exists():
   if time.time()>env_deadline:raise RuntimeError('environment_setup_wait_exceeded_30_minutes')
   time.sleep(10)
  state['environment_install_rc']=int((BASE/'environment_exit_code.txt').read_text())
  rc=phase('environment_check',[PYTHON,str(code/'env_check.py'),'--json',str(BASE/'env_check.json')],120)
  if not (BASE/'env_check.json').exists():raise RuntimeError('Environment checker could not import dependencies; see environment_check.log')
  env=json.loads((BASE/'env_check.json').read_text());v=env['verdict'];feas=None
  if v['nine_b_ready']:feas=phase('nine_b_feasibility',[PYTHON,str(code/'nine_b.py'),'--mode','feasibility','--out',str(BASE/'9b')],900)
  else:state['nine_b_blocker']='Environment gate NO; see env_check.json'
  if v['s3_8b_ready']:phase('s3_full',[PYTHON,str(code/'s3_qwen8b.py'),'--out',str(BASE/'s3')],1800)
  else:state['s3_blocker']='Environment gate NO; see env_check.json'
  if feas==0:phase('nine_b_full',[PYTHON,str(code/'nine_b.py'),'--mode','full','--out',str(BASE/'9b')],deadline-600-time.time())
  elif feas is not None:state['nine_b_blocker']='Feasibility not passed; no full run'
  state['phase']='finished_or_registered_stop'
 except Exception as e:state.update(phase='blocked',error=repr(e),traceback=traceback.format_exc())
 finally:preserve_and_stop(state)
if __name__=='__main__':main()
