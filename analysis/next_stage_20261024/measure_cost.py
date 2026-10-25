"""Same-card, paired token-budget E3 measurements on the registered 20 qids."""
import os,sys,json,csv,time,hashlib,subprocess,threading,traceback
from pathlib import Path
import numpy as np
from supplement_core import cost_jobs,sample_energy
O=Path('/root/autodl-tmp/registered-20261024/cost');O.mkdir(exist_ok=True);R=Path('/root/autodl-tmp/EdgeCoRAG');S=Path('/root/autodl-tmp/session');C=Path('/root/autodl-tmp/corpus_v1');A=Path('/root/autodl-tmp/A_REPO/a-side/retrieval_if_v1')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
root=R/'bound-v1.10.0/integrated/frozen_test/main';original=json.loads((root/'inputs/S1.json').read_text());original.sort(key=lambda r:(hashlib.sha256(r['qid'].encode()).hexdigest(),r['qid']));queries=original[:20];qids=[r['qid'] for r in queries];assert hashlib.sha256(''.join(q+'\n' for q in sorted(qids)).encode()).hexdigest()=='13b62cd7e34ca3ed61a5d4c295ed20d87a9a2fa76880784d4817691bbe0d9778'
manifest={r['sha256']:r for r in csv.DictReader((C/'corpus_manifest.csv').open())};qsha={r['qid']:r['sha256'] for r in csv.DictReader((C/'occurrences.csv').open()) if r['role']=='query'};sel={};pool={}
sp=A/'select3/frozen_test__dim768__cosine+random.csv';pp=A/'pools/frozen_test__dim768__top10.csv'
for r in csv.DictReader(sp.open()):
 if r['strategy']=='cosine':sel.setdefault(r['qid'],[]).append(r)
for r in csv.DictReader(pp.open()):pool.setdefault(r['qid'],[]).append(r)
def ref(s):
 p=C/'images'/s[:2]/(s+'.jpg');assert sha(p)==s;z=manifest[s];return {'path':str(p),'sha256':s,'size':[int(z['w']),int(z['h'])]}
text=json.loads((S/'code/b-side/configs/shared_visual_mcq_v1.json').read_text())['text'];rows={}
for q in queries:
 selected=sorted(sel[q['qid']],key=lambda r:int(r['slot']));assert len(selected)==3 and len(pool[q['qid']])==10
 rows[q['qid']]={'qid':q['qid'],'query_image':ref(qsha[q['qid']]),'evidence':[ref(x['sha256']) for x in selected],'model_request':{'messages':[{'role':'user','content':[{'type':'image','image_index':i} for i in range(4)]+[{'type':'text','text':text.format(question=q['question'],**q['choices'])}]}]}}
(O/'inputs.json').write_text(json.dumps({'qids':qids,'rows':rows,'selection_source':str(sp),'selection_sha256':sha(sp),'pool_source':str(pp),'pool_sha256':sha(pp),'pipeline':'live FP32 query encoding, CPU V dot products, consume fixed cosine evidence; no online pool reordering','script_sha256':sha(__file__)},indent=2))
class RPC:
 def __init__(self,cmd,env,label):
  self.log=(O/(label+'.log')).open('x');self.p=subprocess.Popen(cmd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True);line=self.p.stdout.readline();self.ready=json.loads(line) if line else {'error':'worker exited before ready'}
  if not self.ready.get('ready'):raise RuntimeError(str(self.ready))
 def call(self,msg):
  self.p.stdin.write(json.dumps(msg)+'\n');self.p.stdin.flush();line=self.p.stdout.readline()
  if not line:raise RuntimeError('RPC exited')
  r=json.loads(line)
  if 'error' in r:raise RuntimeError(r['error'])
  return r
 def close(self):
  if self.p.poll() is None:
   try:self.p.stdin.write('{"close":true}\n');self.p.stdin.flush();self.p.wait(timeout=30)
   except Exception:self.p.terminate();self.p.wait(timeout=5)
  self.log.close()
def env(encoder=False):
 e=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',HF_HOME=str(R/'cache/huggingface'),HF_HUB_CACHE=str(R/'cache/huggingface/hub'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='15',MKL_NUM_THREADS='15',OPENBLAS_NUM_THREADS='15')
 if encoder:e['PYTHONPATH']=str(R/'independent-20261018-394/retriever-overlay')
 else:e.pop('PYTHONPATH',None)
 return e
class Sampler:
 def __init__(self):
  self.rows=[];self.lock=threading.Lock();self.event=threading.Event();self.f=(O/'device_samples.jsonl').open('x');self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
 def sample(self):
  p=subprocess.run(['nvidia-smi','--query-gpu=memory.used,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5);p.check_returncode();m,power=p.stdout.strip().split(',');r={'epoch':time.time(),'device_used_bytes':int(float(m)*1048576),'power_W':float(power)}
  with self.lock:self.rows.append(r);self.f.write(json.dumps(r)+'\n');self.f.flush()
  return r
 def loop(self):
  while not self.event.is_set():
   try:self.sample()
   except Exception as e:
    with self.lock:self.f.write(json.dumps({'epoch':time.time(),'error':repr(e)})+'\n');self.f.flush()
   self.event.wait(.1)
 def close(self):self.event.set();self.thread.join(timeout=6);self.f.close()
V=np.load(S/'encoded/V.npy',allow_pickle=False);assert V.shape==(4712,768) and V.dtype==np.float32
sampler=Sampler();encoder=None;gen=None;state={'models':{},'registration_commit':'f5a3f12','energy_window_note':'Synchronous boundary power samples bracket each request; energy includes boundary-sampling overhead, e2e excludes it. GPU only; sampled memory maximum.'};records=[]
try:
 encoder=RPC([str(R/'envs/gemma4/bin/python'),'-B',str(S/'autonomous/encoder_rpc.py')],env(True),'encoder')
 for model,environment in [('qwen3vl_4b','qwen3vl'),('gemma4_e2b','gemma4'),('gemma4_e4b','gemma4')]:
  status={'attempted_hot':0,'complete':False};state['models'][model]=status
  try:
   gen=RPC([str(R/'envs'/environment/'bin/python'),'-B','/root/cost_generator_rpc.py',model],env(),model);(O/(model+'_runtime.json')).write_text(json.dumps(gen.ready,indent=2))
   with (O/(model+'_requests.jsonl')).open('x') as f:
    for qid,cap,warmup in cost_jobs(qids):
     before=sampler.sample();t0=time.perf_counter();row=rows[qid];r={'model':model,'qid':qid,'cap':cap,'warmup':warmup,'generation_error':None,'start_epoch':before['epoch']}
     try:
      encoded=encoder.call({'path':row['query_image']['path']});t=time.perf_counter();scores=V@np.asarray(encoded['vector'],dtype=np.float32);assert scores.shape==(4712,) and np.isfinite(scores).all();retrieval_ms=1000*(time.perf_counter()-t)
      result=gen.call({'row':row,'cap':cap})['result'];r.update(result);r.update(encoder_ms=1000*encoded['forward_seconds'],encoder_rpc_wall_ms=1000*encoded['wall_seconds'],retrieval_ms=retrieval_ms,generation_ms=1000*result['timing']['generate_seconds'],e2e_ms=1000*(time.perf_counter()-t0))
     except Exception as e:r['generation_error']=repr(e);r['traceback']=traceback.format_exc()
     after=sampler.sample();r['end_epoch']=after['epoch']
     with sampler.lock:sampled=list(sampler.rows)
     r['energy']=sample_energy(sampled,before['epoch'],after['epoch']);r['device_peak_bytes_sampled']=max(x['device_used_bytes'] for x in sampled if before['epoch']<=x['epoch']<=after['epoch'])
     f.write(json.dumps(r)+'\n');f.flush();records.append(r)
     if not warmup:status['attempted_hot']+=1
     if r['generation_error']:raise RuntimeError(r['generation_error'])
   status['complete']=status['attempted_hot']==40
  except Exception as e:status['stop_reason']=repr(e)
  finally:
   if gen is not None:gen.close();gen=None
   (O/'status.json').write_text(json.dumps(state,indent=2));print(json.dumps({'model':model,**status}),flush=True)
except Exception as e:state['global_error']=repr(e);state['traceback']=traceback.format_exc()
finally:
 if gen is not None:gen.close()
 if encoder is not None:encoder.close()
 sampler.close();(O/'status.json').write_text(json.dumps(state,indent=2))
