#!/usr/bin/env python3
"""Pinned Qwen3.5-9B feasibility/full execution under the existing preregistration."""
import argparse,csv,hashlib,json,os,time,traceback
from pathlib import Path
from completion_rules import run_items,summary_counts,feasibility_passed,complete_coverage
MODEL='Qwen/Qwen3.5-9B';REVISION='c202236235762e1c871ad0ccb60c8ee5ba337b9a';FIELDS=['raw_id','qid','choice','gold','correct','status']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def find_weights():
 p=Path('/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub/models--Qwen--Qwen3.5-9B');s=p/'snapshots'/REVISION;return str(s if s.exists() else p)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--mode',required=True,choices=['feasibility','full']);ap.add_argument('--media',default='/root/autodl-tmp/EdgeCoRAG/bound-v1.10.0/integrated/frozen_test/main');ap.add_argument('--weights',default='');ap.add_argument('--out',default='/root/autodl-tmp/run_20261026/9b');ap.add_argument('--fail-rate-stop',type=float,default=.05);args=ap.parse_args();assert args.fail_rate_stop==.05
 root=Path(args.media);out=Path(args.out);out.mkdir(exist_ok=True,parents=True);name='receipt_feasibility.json' if args.mode=='feasibility' else 'receipt_qwen35_9b.json';assert not (out/name).exists(),'Preserve existing result; do not rerun'
 state={};receipts=[];runtime=None;error=None;results=[];started=time.time()
 try:
  inputs={k:json.loads((root/'inputs'/(k+'.json')).read_text()) for k in ('S0','S1','S2')};gold={str(x['raw_id']):str(x['answer_choice']).strip() for x in json.loads((root/'scoring/answers.json').read_text())}
  assert all(len(v)==len({x['qid'] for x in v})==1033 for v in inputs.values());assert all({x['qid'] for x in v}=={x['qid'] for x in inputs['S0']} for v in inputs.values())
  import fla,causal_conv1d
  from completion_inference import Backend
  backend=Backend(args.weights or find_weights(),'qwen35',MODEL,REVISION);runtime=backend.runtime;runtime.update(flash_linear_attention=getattr(fla,'__version__',None),causal_conv1d=getattr(causal_conv1d,'__version__',None))
  if args.mode=='feasibility':
   with (out/'feasibility_raw.jsonl').open('x') as raw:
    def emit(r):raw.write(json.dumps(r)+'\n');raw.flush();os.fsync(raw.fileno())
    results=run_items(inputs['S0'][:3],gold,lambda it:backend.infer(it,root/'media',limit_seconds=30),state,emit)
  else:
   feasibility=json.loads((out/'receipt_feasibility.json').read_text());assert feasibility['passed'] and feasibility_passed(feasibility['results']),'Feasibility gate not passed'
   for cond,items in inputs.items():
    path=out/('s0s1s2_qwen35_9b_'+cond+'.csv')
    with path.open('x',newline='') as csvfile,(out/(cond+'_raw.jsonl')).open('x') as raw:
     writer=csv.DictWriter(csvfile,fieldnames=FIELDS);writer.writeheader()
     def emit(r):
      writer.writerow({k:r[k] for k in FIELDS});csvfile.flush();raw.write(json.dumps(r)+'\n');raw.flush();os.fsync(raw.fileno());print(json.dumps({'condition':cond,'attempted':state['attempted'],'failed':state['failed'],'qid':r['qid']}),flush=True)
     rows=run_items(items,gold,lambda it:backend.infer(it,root/'media'),state,emit)
    receipts.append({'condition':cond,**summary_counts(rows,1033),'input_sha256':sha(root/'inputs'/(cond+'.json')),'gold_sha256':sha(root/'scoring/answers.json'),'csv_sha256':sha(path),'qid_sha256':hashlib.sha256(''.join(x['qid']+'\n' for x in sorted(items,key=lambda x:x['qid'])).encode()).hexdigest(),'note':'Different family from Qwen3-VL; no pure scale claim'})
    if state.get('stopped_reason'):break
 except Exception as e:error=repr(e);state['stopped_reason']=error;state['traceback']=traceback.format_exc()
 if args.mode=='feasibility':
  passed=error is None and feasibility_passed(results);summary={'schema':'nine_b_feasibility_20261026/v2','runtime':runtime,'n':len(results),'seconds_each':[r.get('end_to_end_seconds') for r in results],'threshold_seconds':30,'passed':passed,'results':results,**state};rc=0 if passed else 5
 else:
  complete=error is None and complete_coverage(receipts,{'S0':1033,'S1':1033,'S2':1033},'condition');summary={'schema':'qwen35_9b_20261026/v2','runtime':runtime,'condition_receipts':receipts,'complete':complete,**state};rc=0 if complete else 4
 summary.update(preregistration='PREREGISTRATION_20261026_completion.md §3',started_epoch=started,finished_epoch=time.time(),error=error,return_code=rc);(out/name).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'mode':args.mode,'rc':rc,'stopped_reason':state.get('stopped_reason')}),flush=True);return rc
if __name__=='__main__':raise SystemExit(main())
