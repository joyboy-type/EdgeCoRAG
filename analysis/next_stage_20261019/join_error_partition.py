"""Offline exact slot->content->dataset-gold join; no images or answer parsing.
Reproduce with --gold-controls <archived retrieval-formal.approved.json> --out
<NEW_OUTPUT> --private-probe <NEW_JSON_OUTSIDE_REPO>. Optional --print-probe
prints requested20 gold/evidence ID lists; never publish that private probe.
Original requested rules are emitted as overlapping flags, never silently changed
into a partition. Missing-input unknown is separate from uncovered correct rows.
"""
import argparse,csv,gzip,hashlib,io,json,re
from pathlib import Path
from collections import Counter
from quality_stats import paired_family
from quality_data import MODELS
REPO=Path(__file__).resolve().parents[2]
LABELS=['未检索到','检索到但答错','检索伤害','无关但未伤害']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rows(p):
 with gzip.open(p,'rt') as f:return [json.loads(s) for s in f]
def success(r):return bool(r['correct'] and r['parse_status']=='ok' and not r.get('generation_error') and not r.get('input_error'))
def resolve(row,contexts):
 ctx=contexts.get(row['context_key'])
 if ctx is None:return None,'missing_context'
 data=ctx['input']
 if ctx['condition']!=row['condition'] or data['qid']!=row['qid']:raise ValueError('Context identity mismatch')
 refs=data.get('evidence')
 if refs is None:return None,'missing_evidence_refs'
 if [r['evidence_id'] for r in refs]!=row['evidence_ids_order']:raise ValueError('Stored evidence order differs from prediction')
 if any(not re.fullmatch('[0-9a-f]{64}',r.get('sha256','')) for r in refs):return None,'missing_content_sha256'
 return [r['sha256'] for r in refs],''
def gold_hit(content_shas,gold_ids):
 if not gold_ids or any(not re.fullmatch('image:[0-9a-f]{64}',x) for x in gold_ids):raise ValueError('Dataset gold must be explicit image:* IDs')
 return bool(set('image:'+x for x in content_shas)&set(gold_ids))
def flags(s0,s1,hit):
 return {'未检索到':not hit,'检索到但答错':hit and not s1,
         '检索伤害':s0 and not s1,'无关但未伤害':not s1 and not hit and not(s0 and not s1)}
def table(p,data):
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)
def build(repo,gold_controls,out,probe):
 repo=Path(repo).resolve();out=Path(out);probe=Path(probe).resolve()
 if out.exists() or probe.exists():raise FileExistsError('New output/probe required')
 if probe.is_relative_to(repo):raise ValueError('Raw gold probe must stay private outside repository')
 ppath=repo/'logs/B_predictions.jsonl.gz';cpath=repo/'logs/B_input_contexts.jsonl.gz'
 predictions=rows(ppath);context_rows=rows(cpath);contexts={r['context_key']:r for r in context_rows}
 if len(contexts)!=len(context_rows):raise ValueError('Duplicate context_key')
 assert len(predictions)==21927
 gold=json.loads(Path(gold_controls).read_text())['gold']
 source={}
 for line,r in enumerate(predictions,1):
  if r['split']=='frozen_test' and r['stage']=='quality' and r['condition'] in ('S0','S1','S2'):
   key=(r['model_key'],r['condition'],r['qid'])
   if key in source:raise ValueError('Duplicate primary row')
   source[key]=(line,r)
 with (repo/'logs/results_20261020/frozen1033_image_groups_and_transitions.csv').open() as f:group_rows=list(csv.DictReader(f))
 qids=[r['qid'] for r in group_rows];groups=[r['query_or_GT_image_component'] for r in group_rows]
 assert len(qids)==len(set(qids))==1033 and len(set(groups))==564
 joined=[];probes=[];comparisons=[];diagnostics=[]
 for model in MODELS:
  vectors={label:[] for label in LABELS};known=[];overlap=[];uncovered=[];gold_agree=0
  for qid in qids:
   s0=source.get((model,'S0',qid));s1=source.get((model,'S1',qid));s2=source.get((model,'S2',qid))
   reason='';hit=None
   if not s0 or not s1 or not s2:reason='missing_primary_condition'
   elif qid not in gold:reason='missing_qid_to_gold'
   else:
    evidence,reason=resolve(s1[1],contexts);gt,reason_gt=resolve(s2[1],contexts)
    reason=reason or reason_gt
    if not reason:
     if set('image:'+x for x in gt)!=set(gold[qid]):raise ValueError('S2 content SHA vs dataset-gold mismatch')
     gold_agree+=1;hit=gold_hit(evidence,gold[qid])
   valid=not reason;known.append(valid)
   values=flags(success(s0[1]),success(s1[1]),hit) if valid else {label:False for label in LABELS}
   membership=sum(values.values());overlap.append(valid and membership>1);uncovered.append(valid and membership==0)
   for label in LABELS:vectors[label].append(values[label])
   joined.append(dict(model=model,qid=qid,source_line_S0=s0[0] if s0 else '',source_line_S1=s1[0] if s1 else '',source_line_S2=s2[0] if s2 else '',
       joinable=valid,missing_reason=reason,top3_gt_hit=hit if valid else '',S0_correct=success(s0[1]) if s0 else '',S1_correct=success(s1[1]) if s1 else '',
       membership_count=membership if valid else '',**values))
   if model==MODELS[0] and len(probes)<20 and valid:
    probes.append(dict(qid=qid,gold_ids=gold[qid],evidence_ids_order=s1[1]['evidence_ids_order'],mapped_evidence_ids=['image:'+x for x in evidence],direct_same_namespace=all(x.startswith('image:') for x in s1[1]['evidence_ids_order']),top3_gt_hit=hit))
  diagnostics.append(dict(model=model,queries=1033,joinable=sum(known),unknown_missing_input=1033-sum(known),unknown_fraction=(1033-sum(known))/1033,
    gold_S2_content_match=gold_agree,multiple_membership=sum(overlap),no_class_but_inputs_complete=sum(uncovered),sum_of_four_counts=sum(sum(v) for v in vectors.values()),
    partition_valid=sum(overlap)==0 and sum(uncovered)==0))
  for label in LABELS:comparisons.append(dict(model=model,category=label,definition_status='original_requested_overlapping_flag_NOT_partition',left=[False]*1033,right=vectors[label]))
 intervals=paired_family(comparisons,groups)
 for r in intervals:
  diag=next(d for d in diagnostics if d['model']==r['model']);r['count']=r['right_correct'];r['percent']=100*r['count']/1033;r['joinable']=diag['joinable'];r['unknown_missing_input']=diag['unknown_missing_input']
 out.mkdir(parents=True);probe.parent.mkdir(parents=True,exist_ok=True)
 save(probe,probes);table(out/'partition_v2.csv',intervals)
 text=io.StringIO();w=csv.DictWriter(text,fieldnames=list(joined[0]),lineterminator='\n');w.writeheader();w.writerows(joined)
 (out/'join_v2.csv.gz').write_bytes(gzip.compress(text.getvalue().encode(),mtime=0))
 summary=dict(source_rows=21927,models=5,queries_per_model=1033,direct_comparison_same_namespace=False,
   linkage='prediction.context_key -> B_input_contexts.input.evidence[evidence_id].sha256 -> image:<sha256> -> dataset gold; S2 content sets independently checked against archived gold',
   joined_model_query_pairs=sum(d['joinable'] for d in diagnostics),total_model_query_pairs=5165,join_fraction=sum(d['joinable'] for d in diagnostics)/5165,
   diagnostics=diagnostics,definition_conflict=['无关但未伤害 is subset of 未检索到','检索伤害 overlaps both retrieval/error groups','S1 correct with GT hit is uncovered; cannot call missing-input unknown'],
   result_status='identity_join_complete; original four-rule partition impossible, pending explicit definition clarification',
   source_sha256={'logs/B_predictions.jsonl.gz':sha(ppath),'logs/B_input_contexts.jsonl.gz':sha(cpath),'private_archived_gold_controls':sha(gold_controls)},
   private_probe={'questions':len(probes),'sha256':sha(probe),'raw_ids_published':False},
   statistics='qid paired S0/S1;564 image components;10000 resamples seed42;20 flag family; descriptive basic CIs and Holm-compatible conservative rectangle=Bonferroni, not inference',
   previous_limitation_correction='20d1505 checked role slot strings but omitted available B_input_contexts slot-to-SHA table. Real join available; previous unknowns reflected incomplete inspection, not missing historical data.')
 save(out/'namespace_v2.json',summary)
 return summary,probes

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=REPO);p.add_argument('--gold-controls',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--private-probe',type=Path,required=True);p.add_argument('--print-probe',action='store_true');a=p.parse_args()
 summary,probes=build(a.repo,a.gold_controls,a.out,a.private_probe)
 if a.print_probe:
  for row in probes:print(json.dumps(row,ensure_ascii=False))
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
