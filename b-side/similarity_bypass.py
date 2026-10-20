"""Export diagnostic float32 dot products from saved vectors; no models/images.

GPU-round example, AFTER authorized encoding has saved aligned vectors:
  python b-side/similarity_bypass.py --vectors "$NEW/V.npy" \
    --queries "$NEW/Q.npy" --pool "$NEW/pool.csv" --qids "$NEW/qids.txt" \
    --metadata "$NEW/encoding.json" --source live --out "$NEW/scores.csv"
Run once per history/live or batch setting into distinct new output files.

pool.csv has one row per V row, in exactly V order, with identity,sha256.
It is a full frozen candidate manifest, NOT a top10 CSV paired to a larger V.
qids.txt has one unique qid per Q row. encoding.json requires dtype (encoding
provenance, even if bf16 vectors were saved float32), tf32_enabled (bool),
batch_size (positive int), stack_versions (nonempty dict) and query_identities
(mapping each qid to its self identity). Missing self mappings fail closed.

No renormalization/casting of input arrays: V and Q must already be float32
under the claimed protocol. Scores are raw float32 dot products; this CPU NumPy
observer is not a claim to reproduce historical CUDA matmul kernels. Only the
self identity is excluded; np.lexsort((-score primary, identity tiebreak)) is
used to take top-k (default 10). The source pool is never rewritten. pool_id is the SHA256
of exact pool CSV bytes; command_sha256 binds command, code and input hashes.
CSV uses repr(float(float32_score)), an exact binary32 value represented as a
Python float with no decimal rounding or string truncation. Metadata is declared
upstream provenance, not evidence that this tool ran a GPU encoder.

CSV column semantics, in fixed order (22 columns):
- identity: exact input identity used by lexsort; production input MUST retain
  historical image_id semantics (e.g. image:*), never substitute source-byte SHA.
  Synthetic fixtures use a/b solely to expose tie ordering.
- qid: query name in Q row order; source: declared history or live.
- rank: 1..k after self removal; sha256: candidate content SHA from pool metadata,
  a separate field from identity, never used as the sorting key.
- score_fp32: repr(float(np.float32(score))), without decimal rounding/truncation.
- score_fp32_hex: float(np.float32(score)).hex(); cast to binary32 BEFORE the
  exact Python-float hex representation, not double arithmetic cast afterward.
- dtype: upstream encoder dtype declared in metadata, not NPY storage dtype.
- tf32_enabled: upstream declared Boolean, not an observation of a GPU here.
- batch_size: positive upstream encoding batch size from metadata.
- pool_id: SHA256 of the exact frozen manifest CSV bytes.
- k: requested top-k, positive integer, default 10.
- sort_key_rule: literal 'lexsort(-score, identity) ascending identity on ties'.
- self_match_removed: removed self identity, NOT Boolean; absent self is rejected.
- n_pool_scored: V rows actually dot-scored, INCLUDING the subsequently removed
  self row; differentiates e.g. 4712 and 18955.
- normalize_locus: metadata MUST be model_internal or post_cast_float32; this
  tool does not normalize or infer the upstream normalization path.
- encoder_weights_sha256: required metadata lowercase SHA256 of encoder weights.
- model_revision: required nonempty actual revision from metadata, never unknown.
- query_image_sha256: required metadata mapping qid->raw query-image SHA256;
  a single SHA string is also accepted for a single query. No image is opened.
- stack_versions: declared upstream versions plus actual exporter NumPy version.
- command_sha256: hash of command/code/input hashes and effective source/k.
- run_id: command_sha256 first 12 hex chars + '_' + UTC timestamp
  YYYYmmddTHHMMSSffffffZ; shared by all CSV rows and the JSON receipt on stdout.
Missing required provenance fails before output creation; unknown is not filled.

"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import re
import sys
import numpy as np

FIELDS=['identity','qid','source','rank','sha256','score_fp32','score_fp32_hex',
        'dtype','tf32_enabled','batch_size','pool_id','k','sort_key_rule',
        'self_match_removed','n_pool_scored','normalize_locus','encoder_weights_sha256',
        'model_revision','query_image_sha256','stack_versions','command_sha256','run_id']
SORT_KEY_RULE='lexsort(-score, identity) ascending identity on ties'



def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
    return digest.hexdigest()


def export(vectors,queries,pool,qids,metadata,source,out,command=None,k=10):
    paths=[Path(p) for p in (vectors,queries,pool,qids,metadata)]
    vectors,queries,pool,qids,metadata=paths
    out=Path(out)
    if out.exists():raise FileExistsError(out)
    if source not in ('history','live'):raise ValueError('source must be history or live')
    if type(k) is not int or k<1:raise ValueError('k must be a positive integer')
    with pool.open(newline='',encoding='utf-8-sig') as stream:
        reader=csv.DictReader(stream)
        if not {'identity','sha256'}.issubset(reader.fieldnames or []):
            raise ValueError('pool requires identity,sha256 aligned to V rows')
        candidates=list(reader)
    ids=[r['identity'] for r in candidates];shas=[r['sha256'] for r in candidates]
    if (not ids or any(not i or not i.strip() for i in ids) or len(set(ids))!=len(ids)
            or len(set(shas))!=len(shas) or any(not re.fullmatch('[0-9a-f]{64}',s or '') for s in shas)):
        raise ValueError('pool identities and sha256 must be nonempty and unique')
    names=[s.strip() for s in qids.read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.lstrip().startswith('#')]
    if not names or len(set(names))!=len(names):raise ValueError('qids must be unique and nonempty')
    meta=json.loads(metadata.read_text())
    if (meta.get('dtype') not in ('fp32','float32','bf16','bfloat16')
            or type(meta.get('tf32_enabled')) is not bool
            or type(meta.get('batch_size')) is not int or meta['batch_size']<1
            or not isinstance(meta.get('stack_versions'),dict) or not meta['stack_versions']):
        raise ValueError('Explicit dtype/TF32/batch/stack provenance required')
    selves=meta.get('query_identities')
    if not isinstance(selves,dict) or any(not isinstance(selves.get(q),str) or not selves[q].strip() for q in names):
        raise ValueError('Each qid needs an explicit self identity')
    if any(selves[q] not in ids for q in names):
        raise ValueError('Self identity must be present in this full pool')
    if meta.get('normalize_locus') not in ('model_internal','post_cast_float32'):
        raise ValueError('Explicit normalize_locus required')
    if not isinstance(meta.get('encoder_weights_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',meta['encoder_weights_sha256']):
        raise ValueError('Explicit encoder_weights_sha256 required')
    revision=meta.get('model_revision')
    if not isinstance(revision,str) or not revision.strip() or revision.strip().lower() in ('unknown','unavailable','unmeasured','null','none'):
        raise ValueError('Explicit model_revision required')
    query_hashes=meta.get('query_image_sha256')
    if isinstance(query_hashes,str) and len(names)==1:query_hashes={names[0]:query_hashes}
    if not isinstance(query_hashes,dict) or any(not isinstance(query_hashes.get(q),str) or not re.fullmatch('[0-9a-f]{64}',query_hashes[q]) for q in names):
        raise ValueError('Explicit query_image_sha256 required for every qid')
    V=np.load(vectors,mmap_mode='r',allow_pickle=False)
    Q=np.load(queries,mmap_mode='r',allow_pickle=False)
    if (V.dtype!=np.dtype('float32') or Q.dtype!=np.dtype('float32')
            or V.ndim!=2 or Q.ndim!=2 or V.shape[1]==0 or V.shape[1]!=Q.shape[1]
            or V.shape[0]!=len(ids) or Q.shape[0]!=len(names)):
        raise ValueError('float32 matrices must align exactly with pool and qids')
    if not np.isfinite(V).all() or not np.isfinite(Q).all():raise ValueError('Nonfinite vectors')
    pins=dict(zip(('V','Q','pool','qids','metadata'),map(sha256,paths)))
    binding={'command':list(command) if command is not None else [sys.executable,*sys.argv],
             'inputs':pins,'code_sha256':sha256(__file__),'source':source,'k':k}
    command_hash=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    run_id=command_hash[:12]+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    stack=dict(meta['stack_versions']);stack['similarity_bypass_numpy']=np.__version__
    stack_json=json.dumps(stack,sort_keys=True,separators=(',',':'))
    rows=[]
    for i,qid in enumerate(names):
        scores=V@Q[i]
        if scores.dtype!=np.float32 or not np.isfinite(scores).all():raise ValueError('Invalid float32 scores')
        order=np.lexsort((np.asarray(ids),-scores))
        selected=[int(j) for j in order if ids[int(j)]!=selves[qid]][:k]
        if len(selected)!=k:raise ValueError('Not enough non-self candidates for k')
        for rank,j in enumerate(selected,1):
            value=np.float32(scores[j])
            rows.append(dict(identity=ids[j],qid=qid,source=source,rank=rank,sha256=shas[j],
                score_fp32=repr(float(value)),score_fp32_hex=float(value).hex(),dtype=meta['dtype'],
                tf32_enabled=json.dumps(meta['tf32_enabled']),batch_size=meta['batch_size'],
                pool_id='sha256:'+pins['pool'],k=k,sort_key_rule=SORT_KEY_RULE,
                self_match_removed=selves[qid],n_pool_scored=V.shape[0],
                normalize_locus=meta['normalize_locus'],encoder_weights_sha256=meta['encoder_weights_sha256'],
                model_revision=revision,query_image_sha256=query_hashes[qid],
                stack_versions=stack_json,command_sha256=command_hash,run_id=run_id))
    # Verify file bindings before writing; never overwrite a historical output.
    if pins!=dict(zip(('V','Q','pool','qids','metadata'),map(sha256,paths))):
        raise ValueError('Inputs changed while exporting')
    with out.open('x',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    return {'rows':len(rows),'output_sha256':sha256(out),'command_sha256':command_hash,
            'pool_id':'sha256:'+pins['pool'],'input_sha256':pins,'run_id':run_id,
            'k':k,'n_pool_scored':V.shape[0],'fields':FIELDS}


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    for option in ('vectors','queries','pool','qids','metadata','out'):
        parser.add_argument('--'+option,type=Path,required=True)
    parser.add_argument('--source',choices=('history','live'),required=True)
    parser.add_argument('--k',type=int,default=10)
    args=parser.parse_args()
    result=export(**vars(args))
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()
