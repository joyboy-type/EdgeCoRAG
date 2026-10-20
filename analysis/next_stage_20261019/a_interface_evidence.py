"""B1/B2/B3 offline archive projection; no encoding, scoring or rank computation.

Reproduce: $PY analysis/next_stage_20261019/a_interface_evidence.py
 --project <PROJECT_ROOT> --a-repo <READ_ONLY_A_WORKTREE> --out <NEW_B_OUTPUT>
All A reads are byte-only or metadata. Never imports or writes a-side modules.
"""
import argparse,csv,hashlib,json,io
from pathlib import Path

def sha_bytes(v):return hashlib.sha256(v).hexdigest()
def sha(p):return sha_bytes(Path(p).read_bytes())
def read(p):return json.loads(Path(p).read_text())
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def table(p,rows):
 with Path(p).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def newline_proof(raw,manifest):
 normalized=raw.replace(b'\r\n',b'\n');crlf=normalized.replace(b'\n',b'\r\n')
 return dict(raw_bytes=len(raw),raw_sha256=sha_bytes(raw),raw_crlf_count=raw.count(b'\r\n'),
  normalized_bytes=len(normalized),normalized_sha256=sha_bytes(normalized),
  normalized_matches_manifest=sha_bytes(normalized)==manifest['sha256'] and len(normalized)==manifest['bytes'],
  raw_matches_manifest=sha_bytes(raw)==manifest['sha256'] and len(raw)==manifest['bytes'],
  manifest_bytes=manifest['bytes'],manifest_sha256=manifest['sha256'],
  bytes_short=manifest['bytes']-len(raw),expected_CRLF_LF_delta=manifest['rows']+1,
  crlf_reconstruction_sha256=sha_bytes(crlf),crlf_reconstruction_bytes=len(crlf),
  crlf_reconstruction_matches_manifest=sha_bytes(crlf)==manifest['sha256'] and len(crlf)==manifest['bytes'],
  normalization_roundtrip=crlf.replace(b'\r\n',b'\n')==normalized)
def build(project,a_repo,out,b1_only=False):
 project,a_repo,out=Path(project) if project is not None else None,Path(a_repo),Path(out)
 if out.exists():raise ValueError('New B output required')
 out.mkdir(parents=True)
 iface=a_repo/'a-side/retrieval_if_v1';manifest=read(iface/'artifacts.json');proofs=[]
 for item in manifest['artifacts']:
  r=dict(path=item['path'],**newline_proof((iface/item['path']).read_bytes(),item));proofs.append(r)
 table(out/'B1_newline_proof.csv',proofs)
 unexpected=[r['path'] for r in proofs if not r['crlf_reconstruction_matches_manifest'] or r['bytes_short']!=r['expected_CRLF_LF_delta']]
 save(out/'B1_independent_check.json',dict(status='失败：清单口径缺陷，待 A 修复',
  artifacts=len(proofs),raw_pass=sum(r['raw_matches_manifest'] for r in proofs),
  normalized_direct_pass=sum(r['normalized_matches_manifest'] for r in proofs),
  CRLF_reconstruction_pass=sum(r['crlf_reconstruction_matches_manifest'] for r in proofs),
  unexpected_content_mismatch=unexpected,A_manifest_sha256=sha(iface/'artifacts.json'),
  method='In memory only: LF bytes restored to CRLF must match original manifest hash/size, then normalize back to exact disk LF bytes. Direct LF-normalized hash cannot equal a CRLF manifest.',
  conclusion='内容完好，仅清单行尾口径不一致，待 A 修' if not unexpected else '停止：存在无法由行尾解释的不一致',
  use_label='provisional: manifest 行尾口径待 A 修复',B1_passed=False))
 if unexpected:raise ValueError('Unexpected content mismatch; do not use files: '+str(unexpected))
 if b1_only:return dict(B1_passed=False,content_CRLF_proof_pass=sum(r['crlf_reconstruction_matches_manifest'] for r in proofs))
 if project is None:raise ValueError('B2/B3 require --project')
 import numpy as np
 base=project/'work/instance394-preflight/formal-retrieval-embeddinggemma2-backup'
 cache=base/'results/formal-retrieval-embeddinggemma2'
 partial=project/'work/next-experiment-20261019/partial-fetch-20261020/extracted'
 inputs=project/'work/instance394-preflight/formal-retrieval-embeddinggemma2-backup/controls/retrieval-formal.approved.json'
 payload=read(inputs);receipt=read(cache/'receipt.json');plan=read(partial/'plan.json');setup=read(partial/'setup.json')
 if sha(inputs)!=plan['provenance']['retrieval_controls_sha256'] or [r['id'] for r in payload['corpus']]!=plan['corpus_order']:raise ValueError('Control identity/index row order differs')
 backup=read(base/'backup-manifest.json');pins={r['path']:r for r in backup['files']}
 for p in [cache/'corpus_embeddings.npy',cache/'query_embeddings.npy',cache/'receipt.json']:
  item=pins[str(p.relative_to(base))]
  if sha(p)!=item['sha256'] or p.stat().st_size!=item['bytes']:raise ValueError('Backup identity changed: '+p.name)
 if sha(cache/'corpus_embeddings.npy')!=plan['index']['sha256']:raise ValueError('Round2 index differs')
 vectors=np.load(cache/'corpus_embeddings.npy',mmap_mode='r',allow_pickle=False)
 query=np.load(cache/'query_embeddings.npy',mmap_mode='r',allow_pickle=False)
 if vectors.shape!=(18955,768) or query.shape!=(1353,768):raise ValueError('Unexpected archived vector dimensions')
 if len(payload['corpus'])!=18955 or len(payload['queries'])!=1353:raise ValueError('Payload dimensions differ')
 def ref(p,role='other'):return dict(role=role,path=str(p.relative_to(project)),sha256=sha(p),bytes=p.stat().st_size)
 sources=[ref(p) for p in [inputs,base/'backup-manifest.json',cache/'receipt.json',partial/'plan.json',partial/'setup.json']]
 index=dict(schema='a_side_index_receipt/v1',generated_at=None,
  builder=dict(repo='joyboy-type/EdgeCoRAG',commit=None,entrypoint='a-side/scripts/independent_retrieval.py',operator=None),
  index=dict(entries=int(vectors.shape[0]),kind='flat_bruteforce',
   artifact_files=[{k:v for k,v in ref(cache/f).items() if k!='role'} for f in ['corpus_embeddings.npy','query_embeddings.npy']]),
  identity=dict(rule=None,hash_algorithm='sha256',notes='B package id/image-byte SHA map; raw-vs-q95 lineage not proven by this projection; do not assume it equals A corpus_v1'),
  dedup=dict(by_identity=None,kept_duplicates=None,notes='All18955 package ids distinct; dedup construction decision not independently recorded, not inferred from distinct ids'),
  row_order=dict(rule='insertion_order',explicit_tiebreak_key=True,notes='Archive uses payload corpus array order; round2 plan corpus_order sorted. No new ordering produced.'),
  dtype=dict(storage=str(vectors.dtype),compute=receipt['model_dtype'],tf32=None),
  normalization=dict(locus='other',applied_to='corpus_and_query',vector_norms_observed=None),
  corpus_encode=dict(images=receipt['corpus_units'],batch_size=None,device='cuda',
   seconds=receipt['corpus_embeddings_batch_encoding_seconds_including_decode'],notes='Model compute bfloat16, npy float32; batch4 indicated by pinned source, actual batch receipt absent; Normalize module/internal plus post-cast normalization must not be relabelled fp32 encoding.'),
  query_encode=dict(batch_size=1,composition='round2 live single query only; historical cache source uses chunks<=4',per_request_batching=True),
  sources=sources,counts=dict(questions=receipt['questions'],image_instances=None,unique_contents=None),
  reconciliation=dict(claimed_entries=18955,public_instances=14475,public_unique=4712,delta_vs_instances=None,delta_vs_unique=None,verdict='pending'),
  notes=['Archived-only projection; generated_at/build commit/operator not independently recorded, remain null.',
   'A14,475 instances /4,712 unique and B18,955 index entries are different accounting scopes; A a20 reconciliation output is separate.',
   'No A CSV consumed; all references to A interface remain provisional: manifest 行尾口径待 A 修复.',
   'Nulls denote missing archive evidence; a20 necessary-subset validation does not establish complete JSON-schema compliance.'])
 save(out/'B2_index_receipt.json',index)
 history_path=project/'work/next-experiment-20261019/prepared/no-self-smoke_20-ranks.jsonl'
 history={r['qid']:r['corpus_ids'] for r in map(json.loads,history_path.read_text().splitlines())}
 requests=list(map(json.loads,(partial/'results/requests.jsonl').read_text().splitlines()))
 qids=['mragb:10','mragb:1049','mragb:1051','mragb:1062','mragb:1117']
 q_index={r['qid']:i for i,r in enumerate(payload['queries'])}
 first={}
 for r in requests:
  if r['qid'] in qids and r['qid'] not in first and 'ranking' in r:first[r['qid']]=r
 rows=[];fingerprints=[]
 for q in qids:
  ids=history[q]
  if len(ids)!=10:raise ValueError('Historical candidate pool is not10')
  fingerprints.append(dict(qid=q,source='history',encoding_dtype='bfloat16',serialization='float32 little-endian contiguous row; no renormalization',
   sha256=sha_bytes(np.asarray(query[q_index[q]],dtype='<f4').tobytes()),status='archived_cache',source_sha256=sha(cache/'query_embeddings.npy')))
  for rank,candidate in enumerate(ids,1):
   rows.append(dict(qid=q,source='history',rank=rank,sha256=candidate.removeprefix('image:'),score='',
      encoding_dtype='bfloat16',status='archived_order_score_not_saved'))
  live=first.get(q)
  for rank in range(1,11):
   ranking=live['ranking'] if live else None
   rows.append(dict(qid=q,source='live',rank=rank,sha256=ranking['candidate_ids'][rank-1].removeprefix('image:') if live else '',
     score=ranking['top10_scores'][rank-1] if live else '',encoding_dtype='bfloat16',
     status='round2_archived_first_observation_non_fp32' if live else 'missing_live_pending_GPU'))
  fingerprints.append(dict(qid=q,source='live',encoding_dtype='bfloat16',serialization='float32 bytes of post-cast normalized live vector; archived fingerprint only, vector not retained',
   sha256=live['query_vector_fingerprint']['sha256'] if live else None,status='archived_bf16_not_fp32' if live else 'missing_live_pending_GPU',
   source_sha256=sha(partial/'results/requests.jsonl')))
 table(out/'B3_history_live_top10.csv',rows)
 save(out/'B3_vector_fingerprints.json',dict(rows=fingerprints,history_complete=5,live_complete=len(first),
  missing_live_qids=[q for q in qids if q not in first],history_score_available=False,
  no_reencoding=True,no_new_score_computation=True,no_rank_recomputation=True,
  history_live_same_serialization_does_not_mean_same_encoding='Both serialize float32 but model encoding bfloat16; history cache raw output vs live post-cast normalization differ'))
 params=dict(status='archive_only_not_new_fp32_run',history=dict(encoding_dtype=receipt['model_dtype'],stored_dtype=str(query.dtype),
    normalize_embeddings_API=False,Normalize_module='module2_Normalize pinned in archive; not new execution',batch_from_pinned_source=4,actual_batch_receipt=None),
  live=dict(encoding_dtype='bfloat16',batch_size=1,composition='single query',normalize_embeddings_API=False,
    post_cast_float32_normalization=True,not_fp32_protocol=True),
  packages=setup['runtime']['packages'],numpy_version_archived=None,
  source_sha256={str(p.relative_to(project)):sha(p) for p in [cache/'receipt.json',cache/'query_embeddings.npy',partial/'setup.json',partial/'code/b-side/e2e_smoke.py',partial/'code/a-side/scripts/independent_retrieval.py',history_path,partial/'results/requests.jsonl']},
  limitation='numpy absent from archived runtime receipt remains null; no version guessed from local environment')
 save(out/'B3_encoding_parameters.json',params)
 return dict(B1_passed=False,content_CRLF_proof_pass=sum(r['crlf_reconstruction_matches_manifest'] for r in proofs),index_entries=18955,history_rank_rows=50,history_scores_available=0,live_rank_rows=20,live_missing=3)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path)
 p.add_argument('--a-repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');p.add_argument('--b1-only',action='store_true');args=p.parse_args()
 if args.verify:
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   fresh=Path(d)/'derived';result=build(args.project,args.a_repo,fresh,args.b1_only)
   for f in fresh.iterdir():
    if f.read_bytes()!=(args.out/f.name).read_bytes():raise ValueError('Archive projection differs: '+f.name)
 else:result=build(args.project,args.a_repo,args.out,args.b1_only)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
