"""Prepare fixed dev inputs from existing ranks only; never reads gold or scores.

The all-query order is the inference-only top10_768.jsonl, not the gold-bearing
retrieval control. No encoding, evaluation, model load, or dimension selection.
All emitted question/image references are private; publish only the manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'a-side/scripts'))
from evidence_selection import no_labels,select,generation_row,pool_digest

DIMENSIONS=(128,256,512,768)
SEED=20261017


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(out):
    out=Path(out);manifest=json.loads((out/'manifest.json').read_text())
    files=manifest['files']
    actual={str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'}
    if actual!=set(files):raise ValueError('Dimension inventory mismatch')
    for name,pin in files.items():
        p=(out/name).resolve()
        if not p.is_relative_to(out.resolve()) or p.stat().st_size!=pin['bytes'] or sha(p)!=pin['sha256']:
            raise ValueError('Dimension manifest mismatch')
    return manifest


def build(package,ranks_root,query_order,out,*,expected_queries=150,archive_manifest=None):
    import numpy as np
    no_labels(package)
    ranks_root=Path(ranks_root);query_order=Path(query_order);out=Path(out)
    if out.exists():raise ValueError('Preserve existing dimension output')
    queries=package['queries'];corpus=package['corpus'];ids=list(corpus)
    if (package.get('execution_authorized') is not False or package.get('status')!='prepared_unexecuted'
            or len(queries)!=expected_queries or not queries
            or any(q['split']!='dev' for q in queries)
            or len({q['qid'] for q in queries})!=len(queries)):
        raise ValueError('Exactly the fixed development inputs required; no holdout or authorization')
    if len(ids)<11 or len(set(ids))!=len(ids):raise ValueError('Distinct indexed corpus required')
    order_rows=[json.loads(x) for x in query_order.read_text().splitlines()]
    no_labels(order_rows)
    if any(set(row)!={'qid','corpus_ids'} for row in order_rows):raise ValueError('Inference-only query order required')
    positions={row['qid']:i for i,row in enumerate(order_rows)}
    if len(positions)!=len(order_rows) or not {q['qid'] for q in queries}<=set(positions):
        raise ValueError('Query order missing or duplicated')
    input_pins={'query_order':dict(sha256=sha(query_order),bytes=query_order.stat().st_size),
                'inference_package':dict(sha256=pool_digest(package)),
                'retrieval_package_sha256':package['retrieval_package_sha256']}
    pins=None
    if archive_manifest:
        manifest=json.loads(Path(archive_manifest).read_text())
        pins={row['path']:row for row in manifest['files']}
        input_pins['archive_manifest']=dict(sha256=sha(archive_manifest),bytes=Path(archive_manifest).stat().st_size)
    def bound(path):
        digest=sha(path)
        if pins is not None:
            name='results/'+ranks_root.name+'/'+path.name
            pin=pins.get(name,{})
            if pin.get('sha256')!=digest or pin.get('bytes')!=path.stat().st_size:
                raise ValueError('Archived inference rank/hash binding mismatch')
        return dict(sha256=digest,bytes=path.stat().st_size)
    bound(query_order)
    all_rows={}
    for dim in DIMENSIONS:
        path=ranks_root/f'rank_indices_{dim}.npy';input_pins[str(dim)]=bound(path)
        matrix=np.load(path,mmap_mode='r',allow_pickle=False)
        if matrix.shape!=(len(order_rows),len(ids)) or matrix.dtype!=np.dtype('int32'):
            raise ValueError('Full rank shape/dtype identity mismatch')
        ranks=[]
        for query in queries:
            index=positions[query['qid']];row=matrix[index]
            if not np.array_equal(np.sort(row),np.arange(len(ids))):
                raise ValueError('Each cached ranking must be a complete permutation')
            full=[ids[int(i)] for i in row]
            if dim==768 and full[:10]!=order_rows[index]['corpus_ids']:
                raise ValueError('Rank corpus/query order does not match archived top10')
            pool=[cid for cid in full if cid!='image:'+query['query_image']['sha256']][:10]
            if len(pool)!=10:raise ValueError('Ten non-self candidates required')
            ranks.append(dict(qid=query['qid'],corpus_ids=pool))
        all_rows[dim]=ranks
    out.mkdir(parents=True)
    counts={}
    for dim,ranks in all_rows.items():
        directory=out/str(dim);directory.mkdir();pool_sha=pool_digest(ranks)
        with (directory/'ranks.jsonl').open('x') as stream:
            for row in ranks:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        for strategy in ('cosine','random'):
            with (directory/(strategy+'.jsonl')).open('x') as stream:
                for query,row in zip(queries,ranks):
                    selected=select(query['qid'],row['corpus_ids'],strategy,3,SEED)
                    request=generation_row(query,corpus,selected,strategy,pool_sha,SEED)
                    stream.write(json.dumps(request,ensure_ascii=False)+'\n')
        pending=dict(status='awaiting_live_utility_scores',execution_authorized=False,
            input_package_sha256=pool_digest(package),pool_sha256=pool_sha,
            queries=len(queries),candidate_scores=len(queries)*10,score_type='first_step_raw_true_logit',
            scores=None,quality_evaluated=False)
        (directory/'utility.pending.json').write_text(json.dumps(pending,indent=2)+'\n')
        counts[str(dim)]=dict(queries=len(queries),rank_rows=len(ranks),cosine_rows=len(queries),
            random_rows=len(queries),utility_scores_pending=len(queries)*10)
    files={str(p.relative_to(out)):dict(sha256=sha(p),bytes=p.stat().st_size)
           for p in sorted(out.rglob('*')) if p.is_file()}
    manifest=dict(status='prepared_unexecuted',execution_authorized=False,dimensions=counts,
        seed=SEED,topk=10,selectk=3,no_self=True,labels_read=False,quality_evaluated=False,
        inputs=input_pins,files=files)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    verify_manifest(out)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--ranks-root',type=Path,required=True)
    parser.add_argument('--query-order',type=Path,required=True)
    parser.add_argument('--archive-manifest',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    manifest=build(json.loads(args.package.read_text()),args.ranks_root,args.query_order,args.out,
                   archive_manifest=args.archive_manifest)
    print(json.dumps(dict(dimensions=manifest['dimensions'],manifest_sha256=sha(args.out/'manifest.json')),indent=2))

if __name__=='__main__':main()
