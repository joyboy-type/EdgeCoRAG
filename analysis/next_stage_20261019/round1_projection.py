"""Measure immutable round-1 bytes/vectors and project B3 without scoring.
Reproduce: $PY analysis/next_stage_20261019/round1_projection.py --project <PROJECT_ROOT> --out <NEW_OUT>
--verify compares a temporary byte-identical reconstruction with --out.
Five-query sha256 columns preserve archived candidate image:* suffixes, NOT
source JPEG byte SHA256; historical/live encoding is bfloat16, not fp32.
"""
import argparse,copy,hashlib,json,re,tempfile
from pathlib import Path
from a_interface_evidence import sha,sha_bytes,save,table,read
REPO=Path(__file__).resolve().parents[2]

def measure_identity(rows,project):
    ids=[];digests=[];total=0
    for row in rows:
        path=(project/row['path']).resolve()
        if not path.is_relative_to(project.resolve()):raise ValueError('Corpus path outside explicit project')
        data=path.read_bytes();digest=sha_bytes(data)
        if digest!=row['sha256']:raise ValueError('Original image byte mismatch; stop')
        if not re.fullmatch('image:[0-9a-f]{64}',row['id']):raise ValueError('Unexpected identity syntax')
        ids.append(row['id']);digests.append(digest);total+=len(data)
    return dict(rows=len(rows),unique_ids=len(set(ids)),unique_raw_byte_sha256=len(set(digests)),
        duplicate_content_rows=len(rows)-len(set(digests)),id_suffix_not_raw_byte_sha256=sum(i!='image:'+s for i,s in zip(ids,digests)),
        verified_source_bytes=total,all_source_bytes_match_declared_sha256=True,
        row_order_id_digest=sha_bytes(('\n'.join(ids)+'\n').encode()))

def build(project,out):
    import numpy as np
    project,out=Path(project).resolve(),Path(out).resolve()
    if not project.is_dir() or out.exists():raise ValueError('Existing explicit project and new output required')
    base=project/'work/instance394-preflight/formal-retrieval-embeddinggemma2-backup'
    cache=base/'results/formal-retrieval-embeddinggemma2';partial=project/'work/next-experiment-20261019/partial-fetch-20261020/extracted'
    inputs=base/'controls/retrieval-formal.approved.json';payload=read(inputs);receipt=read(cache/'receipt.json')
    manifest=read(base/'backup-manifest.json');pins={r['path']:r for r in manifest['files']}
    for name in ('corpus_embeddings.npy','query_embeddings.npy','receipt.json'):
        path=cache/name;pin=pins[str(path.relative_to(base))]
        if sha(path)!=pin['sha256'] or path.stat().st_size!=pin['bytes']:raise ValueError('Frozen index/receipt binding changed')
    query=np.load(cache/'query_embeddings.npy',mmap_mode='r',allow_pickle=False)
    vectors=np.load(cache/'corpus_embeddings.npy',mmap_mode='r',allow_pickle=False)
    measured=measure_identity(payload['corpus'],project)
    if measured['rows']!=vectors.shape[0] or vectors.shape!=(18955,768):raise ValueError('Corpus/vector dimensions differ')
    if measured['unique_ids']!=18955 or measured['unique_raw_byte_sha256']!=18955:raise ValueError('Unexpected original corpus identity count')
    plan=read(partial/'plan.json')
    if sha(inputs)!=plan['provenance']['retrieval_controls_sha256'] or [r['id'] for r in payload['corpus']]!=plan['corpus_order']:raise ValueError('Index order provenance differs')
    code=project/'work/instance394-preflight/formal-frozen-test-backup/outputs/EdgeCoRAG-delivery-20261017/a-side/scripts/independent_retrieval.py'
    code_pin=read(REPO/'provenance/results_20261020/e2e_smoke_public_receipt.json')['source_pins']['a-side/scripts/independent_retrieval.py']
    if sha(code)!=code_pin:raise ValueError('Archived source does not match historical pin')
    norms=np.linalg.norm(vectors,axis=1)
    measured.update(storage_dtype=str(vectors.dtype),encoding_dtype=receipt['model_dtype'],
        stored_norm_min=float(norms.min()),stored_norm_max=float(norms.max()),runtime_receipt_sha256=sha(cache/'receipt.json'),
        pinned_archive_source_sha256=sha(code),receipt_fields_absent=[k for k in ('batch_size','normalization','tf32') if k not in receipt],
        source_code_only={'batch_size':4,'tf32':False,'ranking_normalization':'post_cast_float32; saved cache precedes this step'},
        limitation='Code values are not runtime observations. Cache is bf16 encoder output serialized float32, not an fp32 encoding.')
    out.mkdir(parents=True)
    index=copy.deepcopy(read(REPO/'reports/next_stage_20261019/a_interface_review_20261021/B2_index_receipt.json'))
    index['identity'].update(rule='sha256_raw_bytes',notes='18955 source byte SHA256 verified; image:* IDs are distinct opaque aliases, ALL suffixes differ from source byte SHA256; preserve original bijection, no relabelling as q95.')
    index['dedup'].update(by_identity=True,kept_duplicates=measured['duplicate_content_rows'],notes='Snapshot has18955 unique IDs and18955 unique verified raw-byte SHA256, no retained duplicate content. This describes snapshot uniqueness, not an observed builder dedup decision.')
    index['dtype']['tf32']=None
    index['normalization'].update(locus='other',vector_norms_observed=f"{norms.min():.9f}..{norms.max():.9f}")
    index['corpus_encode'].update(batch_size=None,notes='Runtime receipt does not record batch. SHA-pinned archived source specifies4; not a fresh runtime observation.')
    index['normalization']['applied_to']='corpus_and_query'
    index['counts']['unique_contents']=measured['unique_raw_byte_sha256']
    index['row_order']['notes']='Original payload corpus order equals round2 index corpus_order exactly; no index/rank rebuilt.'
    index['notes'] += ['Measured current source byte hashes match18955 archived source digests; image:* suffix is NOT the raw byte SHA.',
        'reconciliation remains pending; deltas4480/14243 are arithmetic only, adjudication left to A.',
        'Runtime batch_size/tf32/normalization fields absent. SHA-pinned code specifies batch4/TF32false and float32 renormalization during ranking AFTER cache save; missing runtime evidence remains blocked.']
    save(out/'G2_index_receipt.json',index);save(out/'G2_measured_evidence.json',measured)
    history_path=project/'work/next-experiment-20261019/prepared/no-self-smoke_20-ranks.jsonl'
    history={r['qid']:r['corpus_ids'] for r in map(json.loads,history_path.read_text().splitlines())}
    requests=list(map(json.loads,(partial/'results/requests.jsonl').read_text().splitlines()))
    qids=['mragb:10','mragb:1049','mragb:1051','mragb:1062','mragb:1117'];q_index={r['qid']:i for i,r in enumerate(payload['queries'])};first={}
    for r in requests:
        if r['qid'] in qids and r['qid'] not in first and 'ranking' in r:first[r['qid']]=r
    rows=[];availability=[];fingerprints=[]
    for q in qids:
        if len(history[q])!=10:raise ValueError('Historical pool size differs')
        for rank,candidate in enumerate(history[q],1):rows.append(dict(qid=q,source='history',rank=rank,sha256=candidate.removeprefix('image:'),score=''))
        live=first.get(q)
        for rank in range(1,11):
            rows.append(dict(qid=q,source='live',rank=rank,sha256=live['ranking']['candidate_ids'][rank-1].removeprefix('image:') if live else '',score=live['ranking']['top10_scores'][rank-1] if live else ''))
        availability.append(dict(qid=q,history_rows=10,history_score_rows=0,live_rows=10 if live else 0,live_missing_slots=0 if live else 10,
            status='archived_bf16_batch1' if live else 'missing_live_pending_GPU',encoding_dtype='bfloat16'))
        fingerprints.append(dict(qid=q,history=sha_bytes(np.asarray(query[q_index[q]],dtype='<f4').tobytes()),
            live=live['query_vector_fingerprint']['sha256'] if live else 'missing_live_pending_GPU',
            serialized_dtype='float32',encoder_dtype='bfloat16',live_batch=1,live_vector_bytes_available=False))
    table(out/'five_query_top10.csv',rows);table(out/'five_query_availability.csv',availability)
    save(out/'five_query_fingerprints.json',dict(rows=fingerprints,history=5,live=2,missing_live=3,no_reencoding=True,no_new_dot_products=True))
    save(out/'projection_sources.json',{str(p.relative_to(project)):sha(p) for p in [inputs,cache/'receipt.json',cache/'corpus_embeddings.npy',cache/'query_embeddings.npy',partial/'plan.json',partial/'results/requests.jsonl',history_path,code]})
    return dict(entries=18955,unique_contents=18955,duplicates=0,alias_suffix_mismatches=measured['id_suffix_not_raw_byte_sha256'],history_rows=50,live_rows=20,missing_live_slots=30,missing_runtime_fields=measured['receipt_fields_absent'])
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:
        with tempfile.TemporaryDirectory() as d:
            fresh=Path(d)/'new';result=build(a.project,fresh)
            for f in fresh.iterdir():
                if f.read_bytes()!=(a.out/f.name).read_bytes():raise ValueError('Projection drift: '+f.name)
    else:result=build(a.project,a.out)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
