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
used to take top10. The source pool is never rewritten. pool_id is the SHA256
of exact pool CSV bytes; command_sha256 binds command, code and input hashes.
CSV uses repr(float(float32_score)), an exact binary32 value represented as a
Python float with no decimal rounding or string truncation. Metadata is declared
upstream provenance, not evidence that this tool ran a GPU encoder.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np

FIELDS=['qid','source','rank','sha256','score_fp32','dtype','tf32_enabled',
        'batch_size','pool_id','stack_versions','command_sha256']


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
    return digest.hexdigest()


def export(vectors,queries,pool,qids,metadata,source,out,command=None):
    paths=[Path(p) for p in (vectors,queries,pool,qids,metadata)]
    vectors,queries,pool,qids,metadata=paths
    out=Path(out)
    if out.exists():raise FileExistsError(out)
    if source not in ('history','live'):raise ValueError('source must be history or live')
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
    V=np.load(vectors,mmap_mode='r',allow_pickle=False)
    Q=np.load(queries,mmap_mode='r',allow_pickle=False)
    if (V.dtype!=np.dtype('float32') or Q.dtype!=np.dtype('float32')
            or V.ndim!=2 or Q.ndim!=2 or V.shape[1]==0 or V.shape[1]!=Q.shape[1]
            or V.shape[0]!=len(ids) or Q.shape[0]!=len(names)):
        raise ValueError('float32 matrices must align exactly with pool and qids')
    if not np.isfinite(V).all() or not np.isfinite(Q).all():raise ValueError('Nonfinite vectors')
    pins=dict(zip(('V','Q','pool','qids','metadata'),map(sha256,paths)))
    binding={'command':list(command) if command is not None else [sys.executable,*sys.argv],
             'inputs':pins,'code_sha256':sha256(__file__)}
    command_hash=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    stack=dict(meta['stack_versions']);stack['similarity_bypass_numpy']=np.__version__
    stack_json=json.dumps(stack,sort_keys=True,separators=(',',':'))
    rows=[]
    for i,qid in enumerate(names):
        scores=V@Q[i]
        if scores.dtype!=np.float32 or not np.isfinite(scores).all():raise ValueError('Invalid float32 scores')
        order=np.lexsort((np.asarray(ids),-scores))
        selected=[int(j) for j in order if ids[int(j)]!=selves[qid]][:10]
        if len(selected)!=10:raise ValueError('Need ten non-self candidates')
        for rank,j in enumerate(selected,1):
            rows.append(dict(qid=qid,source=source,rank=rank,sha256=shas[j],
                score_fp32=repr(float(scores[j])),dtype=meta['dtype'],
                tf32_enabled=json.dumps(meta['tf32_enabled']),batch_size=meta['batch_size'],
                pool_id='sha256:'+pins['pool'],stack_versions=stack_json,command_sha256=command_hash))
    # Verify file bindings before writing; never overwrite a historical output.
    if pins!=dict(zip(('V','Q','pool','qids','metadata'),map(sha256,paths))):
        raise ValueError('Inputs changed while exporting')
    with out.open('x',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    return {'rows':len(rows),'output_sha256':sha256(out),'command_sha256':command_hash,
            'pool_id':'sha256:'+pins['pool'],'input_sha256':pins}


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    for option in ('vectors','queries','pool','qids','metadata','out'):
        parser.add_argument('--'+option,type=Path,required=True)
    parser.add_argument('--source',choices=('history','live'),required=True)
    args=parser.parse_args()
    result=export(**vars(args))
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()
