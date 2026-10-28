#!/usr/bin/env python3
"""Prospectively registered fixed warmup and independent 9B gate, with no shutdown."""
import argparse,csv,hashlib,importlib.metadata,json,os,socket,time,traceback
from pathlib import Path
from completion_rules import run_items,run_warmed_gate,summary_counts,complete_coverage
from nine_b import MODEL,REVISION,FIELDS,find_weights,sha
QIDS=['mragb:6','mragb:11','mragb:12']
def save(path,value):
 p=Path(path);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.sync()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--hours',type=float,default=4);args=ap.parse_args();out=Path(args.out);out.mkdir(exist_ok=True,parents=True);assert not (out/'final_receipt_warmed.json').exists(),'Do not overwrite a prior run'
 assert Path('/root/autodl-tmp/KEEP_INSTANCE_RUNNING').exists(),'User requires this instance to remain on'
 root=Path('/root/autodl-tmp/EdgeCoRAG/bound-v1.10.0/integrated/frozen_test/main');started=time.time();deadline=started+args.hours*3600;os.environ['COMPLETION_HARD_DEADLINE_EPOCH']=str(deadline)
 state={'schema':'nine_b_fixed_warmup_20261028/v1','host':socket.gethostname(),'pid':os.getpid(),'started_epoch':started,'hard_deadline_epoch':deadline,'shutdown_policy':'KEEP_RUNNING: no shutdown on any outcome','phase':'initializing','full_state':{},'condition_receipts':[],'complete':False,'return_code':4,'preregistration':'PREREGISTRATION_20261026_completion.md §9','preregistration_sha256':sha(out/'PREREGISTRATION_20261026_completion.md')}
 def phase(name):state['phase']=name;save(out/'state.json',state)
 try:
  inputs={k:json.loads((root/'inputs'/(k+'.json')).read_text()) for k in ['S0','S1','S2']};gold_rows=json.loads((root/'scoring/answers.json').read_text());gold={str(r['raw_id']):r['answer_choice'].strip() for r in gold_rows}
  for k,items in inputs.items():
   assert len(items)==len({r['qid'] for r in items})==1033
   assert hashlib.sha256(''.join(q+'\n' for q in sorted(r['qid'] for r in items)).encode()).hexdigest()=='2a102ea80297f371dbe793125ac98c084880168929cf8a0781aac315c485d9bc'
   assert all(str(r['raw_id']) in gold and gold[str(r['raw_id'])] in 'ABCD' for r in items)
  assert [r['qid'] for r in inputs['S0'][:3]]==QIDS
  cold=Path('/root/autodl-tmp/completion-9b-20261028b/9b/receipt_feasibility.json');state['cold_result']={'path':str(cold),'sha256':sha(cold),'passed':json.loads(cold.read_text())['passed']};assert not state['cold_result']['passed']
  import fla,causal_conv1d
  from completion_inference import Backend
  versions={p:importlib.metadata.version(p) for p in ['flash-linear-attention','fla-core','causal-conv1d']};assert versions=={'flash-linear-attention':'0.4.2','fla-core':'0.4.2','causal-conv1d':'1.7.0'},versions
  backend=Backend(find_weights(),'qwen35',MODEL,REVISION);state['runtime']={**backend.runtime,'packages_extra':versions};phase('fixed_warmup_then_timed_gate')
  with (out/'warmup_raw.jsonl').open('x') as warmfile,(out/'timed_gate_raw.jsonl').open('x') as timedfile:
   def emit_to(file,label,row):
    file.write(json.dumps(row,ensure_ascii=False)+'\n');file.flush();os.fsync(file.fileno());print(json.dumps({'phase':label,'qid':row['qid'],'status':row['status'],'seconds':row.get('end_to_end_seconds')}),flush=True)
   gate=run_warmed_gate(inputs['S0'][:3],gold,lambda item,limit:backend.infer(item,root/'media',limit_seconds=limit),lambda r:emit_to(warmfile,'warmup',r),lambda r:emit_to(timedfile,'timed_gate',r))
  state['warmed_gate']=gate;save(out/'receipt_warmed_feasibility.json',{'runtime':state['runtime'],'cold_result':state['cold_result'],'preregistration':state['preregistration'],'preregistration_sha256':state['preregistration_sha256'],**gate})
  if not gate['passed']:state.update(stopped_reason='Independent warmed feasibility gate not passed',return_code=5);return 5
  phase('full')
  for condition,items in inputs.items():
   csvpath=out/('s0s1s2_qwen35_9b_'+condition+'.csv')
   with csvpath.open('x',newline='') as csvfile,(out/(condition+'_raw.jsonl')).open('x') as raw:
    writer=csv.DictWriter(csvfile,fieldnames=FIELDS);writer.writeheader()
    def emit(row):
     writer.writerow({k:row[k] for k in FIELDS});csvfile.flush();os.fsync(csvfile.fileno());raw.write(json.dumps(row,ensure_ascii=False)+'\n');raw.flush();os.fsync(raw.fileno());print(json.dumps({'condition':condition,'attempted':state['full_state']['attempted'],'failed':state['full_state']['failed'],'qid':row['qid'],'seconds':row.get('end_to_end_seconds')}),flush=True)
    rows=run_items(items,gold,lambda item:backend.infer(item,root/'media'),state['full_state'],emit)
   state['condition_receipts'].append({'condition':condition,**summary_counts(rows,1033),'input_path':str(root/'inputs'/(condition+'.json')),'input_sha256':sha(root/'inputs'/(condition+'.json')),'gold_path':str(root/'scoring/answers.json'),'gold_sha256':sha(root/'scoring/answers.json'),'csv_sha256':sha(csvpath),'qid_sha256':'2a102ea80297f371dbe793125ac98c084880168929cf8a0781aac315c485d9bc','query_plus_evidence_images':{'S0':'1+0','S1':'1+3','S2':'1+5 (956); 1+1 (77)'}[condition]});save(out/'state.json',state)
   if state['full_state'].get('stopped_reason'):break
  state['complete']=complete_coverage(state['condition_receipts'],{'S0':1033,'S1':1033,'S2':1033},'condition');state['return_code']=0 if state['complete'] else 4;return state['return_code']
 except Exception as e:state.update(error=repr(e),traceback=traceback.format_exc(),return_code=4);return 4
 finally:
  state.update(phase='finished',finished_epoch=time.time());save(out/'final_receipt_warmed.json',state)
  try:
   from completion_controller import archive_results
   receipt=archive_results(out,out.parent/(out.name+'-results.tar.gz'));save(out/'archive_verification.json',receipt)
  except Exception as e:save(out/'archive_error.json',{'error':repr(e),'raw_results_preserved':True})
  print(json.dumps({'complete':state['complete'],'rc':state['return_code'],'shutdown':'disabled; instance remains on'}),flush=True)
if __name__=='__main__':raise SystemExit(main())
