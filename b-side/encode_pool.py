"""Prepare aligned EG2 vectors for a future explicitly authorized GPU round.

Protocol matches pinned A a18: google/embeddinggemma-2 revision
914f7f89142e33e77833254d9c9b90c3cef7303b, fp32, TF32=False, batch16,
PIL RGB input, normalize_embeddings=False followed by float32 L2 renormalization.
No inference on import or --dry-run. No automatic model/data downloads.

Future GPU example (NOT executed by the offline reproduction guide):
 python b-side/encode_pool.py --corpus-manifest "$CORPUS_CSV" \
   --queries-manifest "$QUERIES_CSV" --encoder-dir "$LOCAL_SNAPSHOT" \
   --weights-file "$LOCAL_SNAPSHOT/model.safetensors" \
   --weights-sha256 "$WEIGHTS_SHA256" \
   --revision 914f7f89142e33e77833254d9c9b90c3cef7303b --out "$NEW/encoded"
Append --dry-run to validate manifests, weights binding and protocol only.
Corpus CSV: identity,sha256,path, one row per V row; query CSV adds qid, one
row per Q row. Paths are relative to each manifest. Identity must retain the
historical image_id convention; never substitute byte SHA for an image:* alias.
Dry-run checks schema/count shapes without opening images or importing models.
Encoding time formula: (N_V+N_Q)*e; two 4712-image passes => 2*4712*e.
This is arithmetic, not measured runtime; excludes loading, IO overhead and
query batch1 sensitivity. This tool produces batch16 Q only, NOT an a18 receipt.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import numpy as np

MODEL_ID='google/embeddinggemma-2'
REVISION='914f7f89142e33e77833254d9c9b90c3cef7303b'
BATCH_SIZE=16
DIM=768


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()


def validate_inputs(corpus,queries,revision,weights_sha256):
 if revision!=REVISION or not isinstance(weights_sha256,str) or not re.fullmatch('[0-9a-f]{64}',weights_sha256):
  raise ValueError('Fixed revision and explicit weights SHA256 required')
 if not corpus or not queries:raise ValueError('Nonempty manifests required')
 for rows,query in [(corpus,False),(queries,True)]:
  for r in rows:
   if any(not isinstance(r.get(k),str) or not r[k].strip() for k in ('identity','path','sha256')) or not re.fullmatch('[0-9a-f]{64}',r['sha256']):
    raise ValueError('Manifest identity,path,sha256 required')
   if query and (not isinstance(r.get('qid'),str) or not r['qid'].strip()):raise ValueError('Query qid required')
 if len({r['identity'] for r in corpus})!=len(corpus) or len({r['sha256'] for r in corpus})!=len(corpus):raise ValueError('Corpus identities/content must be unique')
 if len({r['qid'] for r in queries})!=len(queries):raise ValueError('Duplicate qid')
 identities={r['identity']:r['sha256'] for r in corpus}
 if any(identities.get(r['identity'])!=r['sha256'] for r in queries):raise ValueError('Query self identity/content must align with corpus')
 return dict(V_shape=[len(corpus),DIM],Q_shape=[len(queries),DIM],dtype='float32',
             tf32_enabled=False,batch_size=BATCH_SIZE,model_id=MODEL_ID,
             model_revision=revision,encoder_weights_sha256=weights_sha256,
             normalize_locus='post_cast_float32',model_loaded=False)


def set_protocol(torch_module):
 torch_module.backends.cuda.matmul.allow_tf32=False
 torch_module.backends.cudnn.allow_tf32=False
 if (type(torch_module.backends.cuda.matmul.allow_tf32) is not bool or torch_module.backends.cuda.matmul.allow_tf32
     or type(torch_module.backends.cudnn.allow_tf32) is not bool or torch_module.backends.cudnn.allow_tf32):
  raise ValueError('TF32 must explicitly be False')


def encode_bundle(corpus,queries,encode,torch_module,out,revision,weights_sha256,versions):
 out=Path(out)
 if out.exists():raise FileExistsError(out)
 receipt=validate_inputs(corpus,queries,revision,weights_sha256)
 set_protocol(torch_module)
 arrays=[]
 for rows in (corpus,queries):
  values=np.asarray(encode(rows,BATCH_SIZE))
  if values.dtype!=np.float32 or values.shape!=(len(rows),DIM) or not np.isfinite(values).all():
   raise ValueError('Encoder must return finite float32 (rows,768), no silent casts')
  norms=np.linalg.norm(values,axis=1,keepdims=True)
  if np.any(norms<=0):raise ValueError('Zero vector cannot be normalized')
  normalized=values/np.maximum(norms,np.float32(1e-12))
  if normalized.dtype!=np.float32:raise ValueError('Normalization must stay float32')
  arrays.append(normalized)
 out.mkdir(parents=True)
 np.save(out/'V.npy',arrays[0],allow_pickle=False);np.save(out/'Q.npy',arrays[1],allow_pickle=False)
 with (out/'pool.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['identity','sha256'],lineterminator='\n');w.writeheader()
  w.writerows({k:r[k] for k in w.fieldnames} for r in corpus)
 (out/'qids.txt').write_text(''.join(r['qid']+'\n' for r in queries))
 metadata={**receipt,'model_loaded':True,'stack_versions':versions,
           'query_identities':{r['qid']:r['identity'] for r in queries},
           'query_image_sha256':{r['qid']:r['sha256'] for r in queries}}
 (out/'encoding.json').write_text(json.dumps(metadata,sort_keys=True,indent=2)+'\n')
 receipt.update(model_loaded=True,artifact_sha256={p.name:sha(p) for p in sorted(out.iterdir())})
 (out/'encode_receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
 return receipt


def read_manifest(path):
 with path.open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
 for row in rows:
  row['path']=str((path.parent/row['path']).resolve())
 return rows


def main():
 p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
 for name in ('corpus-manifest','queries-manifest','encoder-dir','weights-file','out'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--revision',required=True);p.add_argument('--weights-sha256',required=True)
 p.add_argument('--dry-run',action='store_true');args=p.parse_args()
 corpus=read_manifest(args.corpus_manifest);queries=read_manifest(args.queries_manifest)
 receipt=validate_inputs(corpus,queries,args.revision,args.weights_sha256)
 if not args.encoder_dir.is_dir() or not args.weights_file.resolve().is_relative_to(args.encoder_dir.resolve()):raise ValueError('Explicit local snapshot/weights required')
 if sha(args.weights_file)!=args.weights_sha256:raise ValueError('Local weights hash differs')
 if args.out.exists():raise FileExistsError(args.out)
 if args.dry_run:
  print(json.dumps(dict(receipt,dry_run=True,weights_binding_verified=True),indent=2));return
 # Only the explicitly invoked GPU path can reach runtime/image imports.
 os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
 import torch
 from PIL import Image
 from sentence_transformers import SentenceTransformer
 if not torch.cuda.is_available():raise ValueError('GPU path requires explicitly provisioned CUDA')
 set_protocol(torch)
 model=SentenceTransformer(str(args.encoder_dir),revision=REVISION,local_files_only=True,
   config_kwargs={'audio_config':None},model_kwargs={'torch_dtype':torch.float32},device='cuda')
 if any(p.dtype!=torch.float32 for p in model.parameters()):raise ValueError('Encoder parameters must be fp32')
 def encode(rows,batch):
  images=[]
  for row in rows:
   if sha(row['path'])!=row['sha256']:raise ValueError('Image bytes differ from declared SHA')
   with Image.open(row['path']) as image:images.append({'image':image.convert('RGB')})
  try:return model.encode(images,batch_size=batch,normalize_embeddings=False,show_progress_bar=False,convert_to_numpy=True)
  finally:
   for image in images:image['image'].close()
 versions={n:importlib.metadata.version(n) for n in ('torch','torchvision','transformers','sentence-transformers','Pillow','numpy')}
 versions['python']=sys.version.split()[0];versions['cuda_runtime']=torch.version.cuda
 result=encode_bundle(corpus,queries,encode,torch,args.out,args.revision,args.weights_sha256,versions)
 print(json.dumps(result,indent=2))


if __name__=='__main__':main()
