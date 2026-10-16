"""Pinned image-only model adapters. No runtime import until HFBackend is selected."""
import importlib.metadata
import time
import subprocess
import platform
from pathlib import Path
from run_candidate import build_messages

FINALIZER_VERSION='model_final_boundary_v1'


def final_text(family,decoded,special,processor=None,prefix=None):
    """Separate protocol-delimited reasoning, never search for an answer label."""
    if family=='gemma4':
        message=processor.parse_response(special,prefix=prefix)
        if not isinstance(message,dict) or message.get('role','assistant')!='assistant' or message.get('tool_calls'):
            raise ValueError('Unexpected Gemma response structure')
        content=message.get('content','')
        if not isinstance(content,str):raise ValueError('Gemma content is not a string')
        return content
    if family=='qwen35':
        stripped=decoded.lstrip()
        if stripped.startswith('<think>'):
            if stripped.count('<think>')!=1 or stripped.count('</think>')!=1:
                raise ValueError('Incomplete/ambiguous thought delimiter')
            return stripped.split('</think>',1)[1]
        if '<think>' in decoded or '</think>' in decoded:
            raise ValueError('Unexpected thought delimiter')
    return decoded


def chat_kwargs(config):
    """Transformers 5.19 processor kwargs are separate from Jinja template kwargs."""
    if config['family']=='gemma4':
        return {'enable_thinking':False,'processor_kwargs':{'images_kwargs':dict(config['image_processing'])}}
    if config['family']=='qwen35':return {'enable_thinking':False}
    return {}


class FixedBackend:
    synthetic=True
    def __init__(self,model):self.model_config=model
    def infer(self,row,root):
        messages=build_messages(row,root,lambda p:('synthetic-image',p.name))
        return {'raw_output':'A','prediction_raw':'A','final_output':'A','synthetic':True,
                'finalizer_version':FINALIZER_VERSION,'input_image_count':len(messages[0]['content'])-1,
                'input_tokens':None,'generated_tokens':None,'timing':None,'cuda_memory':None}
    def close(self):pass


class HFBackend:
    synthetic=False
    def __init__(self,model,environment,allow_download=False):
        import sys
        import torch
        import transformers
        from transformers import AutoProcessor
        if sys.version_info[:2]!=(3,12):raise RuntimeError('Pinned environments require Python 3.12')
        for name,key in [('torch','torch'),('torchvision','torchvision'),('transformers','transformers'),('Pillow','pillow')]:
            if importlib.metadata.version(name).split('+')[0]!=environment[key]:raise RuntimeError('Version mismatch: '+name)
        if not torch.cuda.is_available() or torch.cuda.device_count()!=1:raise RuntimeError('Expose one working CUDA GPU')
        if torch.version.cuda!='12.8':raise RuntimeError('Pinned cu128 runtime required')
        if model['dtype']=='bfloat16' and not torch.cuda.is_bf16_supported():raise RuntimeError('Native BF16 unsupported; no dtype fallback')
        if model['quantization']!='none' or model['thinking'] is not False:raise ValueError('Only explicit non-thinking/unquantized draft adapter is implemented')
        self.torch=torch;self.model_config=model
        torch.manual_seed(model['seed']);torch.cuda.manual_seed_all(model['seed'])
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        common={'revision':model['revision'],'trust_remote_code':False,'local_files_only':not allow_download}
        extras=dict(model['image_processing']) if model['family']!='gemma4' else {}
        started=time.perf_counter()
        self.processor=AutoProcessor.from_pretrained(model['model_id'],**common,**extras)
        cls=getattr(transformers,model['class'])
        self.model=cls.from_pretrained(model['model_id'],**common,dtype=getattr(torch,model['dtype']),
                                      attn_implementation=model['attention']).to('cuda:0').eval()
        torch.cuda.synchronize()
        self.runtime={'load_seconds':time.perf_counter()-started,'actual_dtype':str(next(self.model.parameters()).dtype),
            'cuda_runtime':torch.version.cuda,'gpu_name':torch.cuda.get_device_name(0),
            'gpu_total_bytes':torch.cuda.get_device_properties(0).total_memory,
            'processor_config':self.processor.image_processor.to_dict(),'quantization':'none',
            'chat_template_sha256':__import__('hashlib').sha256(str(self.processor.chat_template).encode()).hexdigest(),
            'python':platform.python_version(),'system':platform.platform(),
            'packages':{name:importlib.metadata.version(name) for name in ['torch','torchvision','transformers','Pillow']},
            'gpu_compute_capability':list(torch.cuda.get_device_capability(0)),
            'matmul_allow_tf32':torch.backends.cuda.matmul.allow_tf32,'cudnn_allow_tf32':torch.backends.cudnn.allow_tf32,
            'deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),'bitwise_reproducibility_claim':False}
        info=subprocess.run(['nvidia-smi','--query-gpu=uuid,name,driver_version,memory.total','--format=csv,noheader'],
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        dtype_counts={}
        for parameter in self.model.parameters():
            key=str(parameter.dtype);dtype_counts[key]=dtype_counts.get(key,0)+parameter.numel()
        self.runtime['parameter_dtype_numel']=dtype_counts
        self.runtime['nvidia_smi']={'exit_code':info.returncode,'stdout':info.stdout,'stderr':info.stderr}
        self.runtime['timing_hardware_id']=__import__('hashlib').sha256((platform.node()+'|'+info.stdout+'|'+str(torch.version.cuda)).encode()).hexdigest()
    def infer(self,row,root):
        from PIL import Image
        torch=self.torch;cfg=self.model_config
        torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats()
        started=time.perf_counter()
        def image(path):
            with Image.open(path) as im:im.load();return im.convert('RGB')
        messages=build_messages(row,root,image)
        kwargs=chat_kwargs(cfg)
        inputs=self.processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
                    return_dict=True,return_tensors='pt',**kwargs)
        # No attention-mask/token-id floating cast. Floating vision tensors alone follow model dtype.
        inputs.pop('token_type_ids',None)
        tokens=int(inputs['input_ids'].shape[-1])
        if tokens+cfg['max_new_tokens']>cfg['context_limit']:raise ValueError('Configured context limit exceeded; no truncation')
        grid=inputs['image_grid_thw'].tolist() if 'image_grid_thw' in inputs else None
        preprocess=time.perf_counter()-started
        inputs=inputs.to('cuda:0')
        for k,v in inputs.items():
            if torch.is_tensor(v) and v.is_floating_point():inputs[k]=v.to(dtype=next(self.model.parameters()).dtype)
        torch.cuda.synchronize();begin=time.perf_counter()
        with torch.inference_mode():
            output=self.model.generate(**inputs,max_new_tokens=cfg['max_new_tokens'],do_sample=False,use_cache=True)
        torch.cuda.synchronize();seconds=time.perf_counter()-begin
        tail=output[:,tokens:]
        decoded=self.processor.batch_decode(tail,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
        special=self.processor.batch_decode(tail,skip_special_tokens=False,clean_up_tokenization_spaces=False)[0]
        result={'raw_output':decoded,'prediction_raw':decoded,'raw_output_with_special_tokens':special,
                'final_output':'','finalizer_version':FINALIZER_VERSION,'final_extraction_error':None,
                'synthetic':False,'input_tokens':tokens,'generated_tokens':int(tail.shape[-1]),
                'budget_exhausted':int(tail.shape[-1])>=cfg['max_new_tokens'],
                'input_image_count':1+len(row['evidence']),'image_grid_thw':grid,
                'input_image_sizes':[r['size'] for r in [row['query_image']]+row['evidence']],
                'processed_tensor_shapes':{k:list(v.shape) for k,v in inputs.items() if hasattr(v,'shape')},
                'actual_dtype':self.runtime['actual_dtype'],'timing_hardware_id':self.runtime['timing_hardware_id'],'timing':{'preprocess_seconds':preprocess,
                'generate_seconds':seconds,'end_to_end_seconds':time.perf_counter()-started},
                'cuda_memory':{'process_allocator_peak_allocated':torch.cuda.max_memory_allocated(),
                               'process_allocator_peak_reserved':torch.cuda.max_memory_reserved(),
                               'device_total_peak_bytes':None,'device_total_peak_note':'Not sampled; allocator peak is not device-wide peak'}}
        try:result['final_output']=final_text(cfg['family'],decoded,special,self.processor,inputs['input_ids'])
        except Exception as e:result['final_extraction_error']=type(e).__name__+': '+str(e)
        result['timing']['end_to_end_seconds']=time.perf_counter()-started
        return result
    def close(self):
        import gc
        del self.model;del self.processor;gc.collect();self.torch.cuda.empty_cache()
