"""Pinned generation adapter with an explicit request token cap."""
import os,sys,json,contextlib
from pathlib import Path
os.environ.update(HF_HOME='/root/autodl-tmp/EdgeCoRAG/cache/huggingface',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
sys.path.insert(0,'/root/autodl-tmp/session/code/b-side')
from model_adapters import HFBackend
import torch
torch.set_num_threads(15);torch.set_num_interop_threads(1)
key=sys.argv[1];reg=json.loads(Path('/root/autodl-tmp/session/code/b-side/configs/model_registry.json').read_text());cfg=reg['models'][key]
try:
 with contextlib.redirect_stdout(sys.stderr):backend=HFBackend(cfg,reg['environments'][cfg['environment']],allow_download=False)
 print(json.dumps({'ready':True,'runtime':backend.runtime}),flush=True)
 for line in sys.stdin:
  msg=json.loads(line)
  if msg.get('close'):break
  cap=msg['cap'];assert cap in (2,256);backend.model_config['max_new_tokens']=cap
  try:
   with contextlib.redirect_stdout(sys.stderr):r=backend.infer(msg['row'],Path('/'))
   print(json.dumps({'result':r}),flush=True)
  except Exception as e:print(json.dumps({'error':repr(e)}),flush=True);break
 backend.close()
except Exception as e:print(json.dumps({'error':repr(e)}),flush=True);raise
