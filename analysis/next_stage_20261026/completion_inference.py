"""Native BF16 inference, preserving preregistered images, prompt and token budget."""
import contextlib,hashlib,importlib.metadata,json,signal,subprocess,time
from pathlib import Path
import torch

class Backend:
 def __init__(self,weights,family,model_id,revision):
  from transformers import AutoProcessor,Qwen3VLForConditionalGeneration,Qwen3_5ForConditionalGeneration
  assert torch.__version__=='2.8.0+cu128' and torch.version.cuda=='12.8'
  assert torch.cuda.is_available() and torch.cuda.is_bf16_supported() and torch.cuda.get_device_properties(0).total_memory>=32*1024**3
  torch.manual_seed(42);torch.cuda.manual_seed_all(42);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
  self.family=family;self.processor=AutoProcessor.from_pretrained(weights,local_files_only=True,trust_remote_code=True,min_pixels=50176,max_pixels=262144,use_fast=False)
  if family=='qwen35' and getattr(self.processor,'chat_template',None) is None:
   ct=json.loads((Path(weights)/'tokenizer_config.json').read_text()).get('chat_template');assert ct,'Missing registered chat template';self.processor.chat_template=ct;self.processor.tokenizer.chat_template=ct
  cls=Qwen3_5ForConditionalGeneration if family=='qwen35' else Qwen3VLForConditionalGeneration;t=time.perf_counter();self.model=cls.from_pretrained(weights,local_files_only=True,trust_remote_code=True,dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda').eval();torch.cuda.synchronize()
  assert not getattr(self.model,'is_quantized',False) and next(self.model.parameters()).dtype==torch.bfloat16
  nvcc=subprocess.run(['nvcc','--version'],capture_output=True,text=True) if __import__('shutil').which('nvcc') else None
  self.runtime={'model':model_id,'revision':revision,'dtype':'bfloat16','quantization':'none','attn_implementation':'sdpa','max_new_tokens':64,'do_sample':False,'seed':42,'enable_thinking':False if family=='qwen35' else 'not_applicable','load_seconds':time.perf_counter()-t,'gpu_name':torch.cuda.get_device_name(0),'gpu_total_gib':torch.cuda.get_device_properties(0).total_memory/1024**3,'compute_capability':list(torch.cuda.get_device_capability(0)),'torch':torch.__version__,'cuda_runtime':torch.version.cuda,'matmul_allow_tf32':False,'cudnn_allow_tf32':False,'nvcc_version_raw':nvcc.stdout if nvcc else None,'chat_template_sha256':hashlib.sha256(str(self.processor.chat_template).encode()).hexdigest(),'packages':{p:importlib.metadata.version(p) for p in ('transformers','Pillow','triton')},'image_processor_config':self.processor.image_processor.to_dict(),'image_preprocessing':'unchanged protocol_main_v1.json image_processing.qwen: min_pixels=50176,max_pixels=262144,use_fast=False; no fit-to-memory changes','hardware_limitations':'new hardware/stack; no bitwise equivalence or pure scale claim'}
 def infer(self,it,media_root,limit_seconds=None):
  from PIL import Image
  started=time.perf_counter();images=[]
  def timeout(_signal,_frame):raise TimeoutError('Preregistered per-item end-to-end latency exceeded 30 seconds')
  old=signal.signal(signal.SIGALRM,timeout) if limit_seconds else None
  if limit_seconds:signal.setitimer(signal.ITIMER_REAL,limit_seconds+.01)
  try:
   for ref in it['image_order']:
    with Image.open(media_root/ref['path']) as im:im.load();images.append(im.convert('RGB'))
   text=it['model_request']['messages'][0]['content'][-1]['text'];messages=[{'role':'user','content':[{'type':'image'} for _ in images]+[{'type':'text','text':text}]}];kw={'enable_thinking':False} if self.family=='qwen35' else {}
   prompt=self.processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,**kw);inputs=self.processor(text=[prompt],images=[images],return_tensors='pt').to('cuda');torch.cuda.synchronize();begin=time.perf_counter()
   with torch.no_grad():ids=self.model.generate(**inputs,max_new_tokens=64,do_sample=False)
   torch.cuda.synchronize();generation=time.perf_counter()-begin;tail=ids[0][inputs['input_ids'].shape[1]:];response=self.processor.decode(tail,skip_special_tokens=True).strip()
   return {'response':response,'raw_output_with_special_tokens':self.processor.decode(tail,skip_special_tokens=False),'generated_tokens':len(tail),'end_to_end_seconds':time.perf_counter()-started,'generation_seconds':generation,'input_image_count':len(images),'image_identities':[r['sha256'] for r in it['image_order']],'rendered_prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'status':'ok'}
  except Exception as e:e.end_to_end_seconds=time.perf_counter()-started;raise
  finally:
   if limit_seconds:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
   for image in images:image.close()
