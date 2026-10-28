"""Model-free enforcement of the unchanged completion preregistration."""
import re,time,traceback,os

def feasibility_passed(results):
 return len(results)==3 and all(r.get('status')=='ok' and r.get('end_to_end_seconds',float('inf'))<=30 for r in results)
def summary_counts(rows,expected):
 n=len(rows);nc=sum(r['correct'] is True for r in rows);complete=n==expected
 return {'n_expected':expected,'n_rows':n,'n_correct':nc,'complete':complete,'accuracy':nc/expected if complete else None,'accuracy_observed':nc/n if n else None}
def complete_coverage(receipts,expected,key):
 return len(receipts)==len(expected) and {r[key] for r in receipts}==set(expected) and all(r.get('complete') and r['n_rows']==expected[r[key]] for r in receipts)
def run_items(items,gold,infer,state,emit):
 state.setdefault('attempted',0);state.setdefault('failed',0);state.setdefault('stopped_reason',None);rows=[]
 for it in items:
  if state['stopped_reason']:break
  deadline=os.environ.get('COMPLETION_HARD_DEADLINE_EPOCH')
  if deadline and time.time()>=float(deadline)-600:state['stopped_reason']='600_second_preservation_window';break
  raw_id=str(it['raw_id']);assert raw_id in gold
  row={'raw_id':raw_id,'qid':it['qid'],'gold':gold[raw_id],'choice':None,'correct':False,'status':'ok','started_epoch':time.time()};state['attempted']+=1
  try:
   result=infer(it);row.update(result);row['status']=result.get('status','ok');m=re.search(r'\b([ABCD])\b',result.get('response',''));row['choice']=m.group(1) if m else None;row['correct']=row['choice']==row['gold']
  except Exception as e:
   oom=type(e).__name__=='OutOfMemoryError' or 'cuda out of memory' in str(e).lower();row.update(status='OOM' if oom else 'error:'+type(e).__name__,error=str(e),traceback=traceback.format_exc(),end_to_end_seconds=getattr(e,'end_to_end_seconds',None))
  if row['status']!='ok':state['failed']+=1
  row['finished_epoch']=time.time();emit(row);rows.append(row)
  if row['status']=='OOM':state['stopped_reason']='OOM at '+it['qid']
  elif state['failed']/state['attempted']>.05:state['stopped_reason']=f"failure_rate {state['failed']}/{state['attempted']} > 0.05"
 return rows

def run_warmed_gate(items,gold,infer,emit_warm,emit_timed):
 """Fixed three warmups then the unchanged individual 30-second gate; no retries."""
 assert len(items)==3 and len({it['qid'] for it in items})==3
 warm_state={};warm=run_items(items,gold,lambda it:infer(it,600),warm_state,emit_warm)
 ready=len(warm)==3 and all(r['status']=='ok' for r in warm) and not warm_state.get('stopped_reason')
 timed_state={};results=run_items(items,gold,lambda it:infer(it,30),timed_state,emit_timed) if ready else []
 return {'passed':ready and feasibility_passed(results),'warmup_results':warm,'results':results,'warmup_state':warm_state,'timed_state':timed_state,'threshold_seconds':30,'warmup_limit_seconds':600}
