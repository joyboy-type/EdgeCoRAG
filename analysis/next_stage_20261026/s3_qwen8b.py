#!/usr/bin/env python3
"""Pinned native-processor S3 execution, with immediate registered stop rules."""
import argparse,csv,hashlib,json,os,time,traceback
from pathlib import Path
from completion_rules import run_items,summary_counts,complete_coverage
MODEL='Qwen/Qwen3-VL-8B-Instruct';REVISION='0c351dd01ed87e9c1b53cbc748cba10e6187ff3b';SPLITS={'dev':5,'internal_holdout':2,'frozen_test':29};NAMES={'dev':'dev','internal_holdout':'holdout','frozen_test':'frozen'};FIELDS=['raw_id','qid','choice','gold','correct','status']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--media',default='/root/autodl-tmp/EdgeCoRAG/bound-v1.10.0/integrated');ap.add_argument('--out',default='/root/autodl-tmp/run_20261026/s3');ap.add_argument('--weights',default='');ap.add_argument('--fail-rate-stop',type=float,default=.05);args=ap.parse_args();assert args.fail_rate_stop==.05
 root=Path(args.media);out=Path(args.out);out.mkdir(exist_ok=True,parents=True);assert not (out/'receipt_s3_qwen3vl_8b.json').exists(),'Preserve existing result; do not rerun'
 state={};receipts=[];runtime=None;error=None;started=time.time()
 try:
  prepared={}
  for split,n in SPLITS.items():
   p=root/split/'s3';items=json.loads((p/'inputs/S3-pure.json').read_text());assert len(items)==len({r['qid'] for r in items})==n;gold={str(r['raw_id']):str(r['answer_choice']).strip() for r in json.loads((p/'scoring/answers.json').read_text())};assert all(str(r['raw_id']) in gold and len(r['image_order'])==4 for r in items);prepared[split]=(p,items,gold)
  from completion_inference import Backend
  weights=args.weights or '/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/'+REVISION;backend=Backend(weights,'qwen3vl',MODEL,REVISION);runtime=backend.runtime
  for split,(p,items,gold) in prepared.items():
   csvpath=out/('s3_qwen3vl_8b_'+NAMES[split]+'.csv')
   with csvpath.open('x',newline='') as csvfile,(out/(split+'_raw.jsonl')).open('x') as raw:
    writer=csv.DictWriter(csvfile,fieldnames=FIELDS);writer.writeheader()
    def emit(r):
     writer.writerow({k:r[k] for k in FIELDS});csvfile.flush();raw.write(json.dumps(r)+'\n');raw.flush();os.fsync(raw.fileno());print(json.dumps({'split':split,'qid':r['qid'],'attempted':state['attempted'],'failed':state['failed']}),flush=True)
    rows=run_items(items,gold,lambda it:backend.infer(it,p/'media'),state,emit)
   receipts.append({'split':split,'split_out':NAMES[split],**summary_counts(rows,SPLITS[split]),'input_sha256':sha(p/'inputs/S3-pure.json'),'gold_sha256':sha(p/'scoring/answers.json'),'qid_sha256':hashlib.sha256(''.join(q+'\n' for q in sorted(r['qid'] for r in items)).encode()).hexdigest(),'csv_sha256':sha(csvpath),'disclosure':'AI图像辅助、label-aware、非人工盲审；仅子集描述'})
   if state.get('stopped_reason'):break
 except Exception as e:error=repr(e);state['stopped_reason']=error;state['traceback']=traceback.format_exc()
 complete=error is None and complete_coverage(receipts,SPLITS,'split');rc=0 if complete else 4;summary={'schema':'s3_qwen3vl_8b_20261026/v2','runtime':runtime,'split_receipts':receipts,'complete':complete,**state,'error':error,'return_code':rc,'preregistration':'PREREGISTRATION_20261026_completion.md §2','started_epoch':started,'finished_epoch':time.time()};(out/'receipt_s3_qwen3vl_8b.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'complete':complete,'rc':rc,'stopped_reason':state.get('stopped_reason')}),flush=True);return rc
if __name__=='__main__':raise SystemExit(main())
