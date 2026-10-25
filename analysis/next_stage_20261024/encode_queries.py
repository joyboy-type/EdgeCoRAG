"""Query-only FP32 encoding for the registered current-pool experiment."""
import os
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME='/root/autodl-tmp/EdgeCoRAG/cache/huggingface',PYTHONDONTWRITEBYTECODE='1')
import json,csv,hashlib,time,platform
from pathlib import Path
import numpy as np
from supplement_core import check_query_ids
R=Path('/root/autodl-tmp/EdgeCoRAG');O=Path('/root/autodl-tmp/registered-20261024');O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=[]
for split in ('smoke_20','dev','frozen_test'):
 root=R/'bound-v1.10.0/integrated'/split/'main'
 for row in json.loads((root/'inputs/S0.json').read_text()):
  ref=row['query_image'];p=root/'media'/ref['path'];assert p.is_file(),p
  assert sha(p)==ref['sha256'],p
  rows.append({'qid':row['qid'],'split':split,'path':str(p),'sha256':ref['sha256']})
rows.sort(key=lambda r:r['qid']);check_query_ids([r['qid'] for r in rows],[r['qid'] for r in rows]);assert len(rows)==1203
qh=hashlib.sha256(''.join(r['qid']+'\n' for r in rows).encode()).hexdigest();assert qh=='a941678f09fad6119fbcc1557d69b9ff2a7f4042dff877f12c4494fbe5489cfc'
# Bind each query to the current corpus identity before GPU execution.
occ=list(csv.DictReader(open('/root/autodl-tmp/corpus_v1/occurrences.csv')));queries={x['qid']:x['sha256'] for x in occ if x['role']=='query'}
for r in rows:assert queries[r['qid']]==r['sha256'],r['qid']
assert sha('/root/autodl-tmp/session/encoded/V.npy')=='31a3e122be53f528d59b5ece290b0814461027d7792a0dd1ff6c2841bab827ce'
(O/'query_inputs.json').write_text(json.dumps(rows,indent=2))
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer
from threadpoolctl import threadpool_limits
torch.set_num_threads(15);torch.set_num_interop_threads(1);threadpool_limits(15);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
t=time.time();p=R/'independent-20261018-394/work/pre-experiment-20261018/retriever-cache/embeddinggemma2/914f7f89142e33e77833254d9c9b90c3cef7303b'
model=SentenceTransformer(str(p),local_files_only=True,config_kwargs={'audio_config':None},model_kwargs={'torch_dtype':torch.float32},device='cuda')
assert all(x.dtype==torch.float32 for x in model.parameters() if x.is_floating_point())
chunks=[]
for start in range(0,len(rows),16):
 images=[]
 try:
  for row in rows[start:start+16]:
   with Image.open(row['path']) as im:im.load();images.append(im.convert('RGB'))
  with torch.inference_mode():a=model.encode([{'image':im} for im in images],batch_size=16,normalize_embeddings=False,convert_to_numpy=True,show_progress_bar=False)
  assert a.dtype==np.float32 and np.isfinite(a).all();norm=np.linalg.norm(a,axis=1,keepdims=True);assert (norm>0).all();a/=norm;chunks.append(a)
 finally:
  for im in images:im.close()
 print(json.dumps({'encoded':min(start+16,len(rows)),'total':len(rows),'elapsed_s':time.time()-t}),flush=True)
a=np.concatenate(chunks);assert a.shape==(1203,768);np.save(O/'Q_1203.npy',a);(O/'Q_1203_qids.txt').write_text(''.join(r['qid']+'\n' for r in rows))
receipt={'shape':list(a.shape),'dtype':str(a.dtype),'batch_size':16,'tf32':False,'elapsed_s':time.time()-t,'qid_sha256':qh,'Q_sha256':sha(O/'Q_1203.npy'),'input_manifest_sha256':sha(O/'query_inputs.json'),'encoder_revision':p.name,'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__,'numpy':np.__version__,'python':platform.python_version(),'script_sha256':sha(__file__)}
(O/'encoding_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
