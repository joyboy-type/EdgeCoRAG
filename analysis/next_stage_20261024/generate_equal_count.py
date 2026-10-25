"""One model, immutable S2 inputs truncated to three; durable per-request output."""
import os,sys,json,time,hashlib,traceback
from pathlib import Path
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME='/root/autodl-tmp/EdgeCoRAG/cache/huggingface',PYTHONDONTWRITEBYTECODE='1')
sys.path.insert(0,'/root/autodl-tmp/session/code/b-side')
from supplement_core import equal_count
from model_adapters import HFBackend
from score_minimal import parse_choice
import torch
torch.set_num_threads(15);torch.set_num_interop_threads(1)
O=Path('/root/autodl-tmp/registered-20261024');key=sys.argv[1];out=O/key;out.mkdir(exist_ok=True)
root=Path('/root/autodl-tmp/EdgeCoRAG/bound-v1.10.0/integrated/frozen_test/main')
rows=json.loads((root/'inputs/S2.json').read_text());rows.sort(key=lambda r:r['qid']);assert len(rows)==1033
assert hashlib.sha256(''.join(r['qid']+'\n' for r in rows).encode()).hexdigest()=='2a102ea80297f371dbe793125ac98c084880168929cf8a0781aac315c485d9bc'
answers={x['qid']:x for x in json.loads((root/'scoring/answers.json').read_text())}
registry=json.loads(Path('/root/autodl-tmp/session/code/b-side/configs/model_registry.json').read_text());cfg=registry['models'][key];assert cfg['max_new_tokens']==64
# Validate bytes before model load; retain the original bound image references.
for r in rows:
 for im in [r['query_image']]+r['evidence']:
  p=root/'media'/im['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==im['sha256']
status={'model_key':key,'attempted':0,'failures':0,'complete':False,'started_epoch':time.time(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
def save(): (out/'status.json').write_text(json.dumps(status,indent=2))
save()
try:
 backend=HFBackend(cfg,registry['environments'][cfg['environment']],allow_download=False)
 (out/'runtime.json').write_text(json.dumps(backend.runtime,indent=2))
 with (out/'predictions.jsonl').open('x') as f:
  for original in rows:
   row=equal_count(original);rec={'qid':row['qid'],'model_key':key,'condition':'S2@3','primary956':len(original['evidence'])==5,'evidence_ids_order':[x['evidence_id'] for x in row['evidence']],'generation_error':None,'scenario':answers[row['qid']]['scenario']}
   try:
    rec.update(backend.infer(row,root/'media'));rec['parsed_choice'],rec['parse_status']=parse_choice(rec['final_output'])
    failure=bool(rec.get('final_extraction_error')) or not rec.get('raw_output','').strip()
    if failure:rec['generation_error']=rec.get('final_extraction_error') or 'EmptyOutput'
   except Exception as e:rec['generation_error']=repr(e);rec['traceback']=traceback.format_exc();rec['oom']='out of memory' in str(e).lower();failure=True
   rec['correct']=rec.get('parsed_choice')==answers[row['qid']]['answer_choice'];rec['finished_epoch']=time.time()
   f.write(json.dumps(rec)+'\n');f.flush();status['attempted']+=1;status['failures']+=int(failure);save()
   if status['attempted']%25==0:print(json.dumps(status),flush=True)
   if rec.get('oom') or status['failures']/status['attempted']>.05:
    status['stop_reason']='oom' if rec.get('oom') else 'generation_failures_gt_5_percent';break
 status['complete']=status['attempted']==1033;backend.close()
except Exception as e:status['stop_reason']=repr(e);status['traceback']=traceback.format_exc();print(traceback.format_exc(),flush=True)
finally:status['finished_epoch']=time.time();save();print(json.dumps(status),flush=True)
