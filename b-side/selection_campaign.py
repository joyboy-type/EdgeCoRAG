"""Proposed independent-pool selection campaign; default is offline input validation.

Real CUDA methods below are unverified. No automatic download, retry or overwrite.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import threading
import time

REPO=Path(__file__).resolve().parents[1]
CLAIMS_ROOT=REPO/'work/independent-selection-execution-claims'
sys.path.insert(0,str(REPO/'a-side/scripts'))
from evidence_selection import no_labels, pool_digest, select, generation_row, remaining_seconds
SURROGATE=('google/gemma-4-E2B-it','3e22461f65e89153144f8adb70e3b8c2cc9845a7')
STRATEGIES=('cosine','random','utility')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()


def validate_inputs(package,root):
    no_labels(package)
    if package.get('status')!='prepared_unexecuted': raise ValueError('Prepared new input package required')
    queries,corpus=package.get('queries'),package.get('corpus')
    if not isinstance(queries,list) or not queries or not isinstance(corpus,dict) or len(corpus)<10:
        raise ValueError('Queries and full indexed corpus required')
    qids=[q['qid'] for q in queries]
    if any(not isinstance(q,str) or not q for q in qids) or len(set(qids))!=len(qids):
        raise ValueError('Unique query strings required')
    if any(not isinstance(cid,str) or not cid for cid in corpus): raise ValueError('Opaque corpus strings required')
    if not isinstance(package.get('retrieval_package_sha256'),str) or len(package['retrieval_package_sha256'])!=64:
        raise ValueError('Retrieval package binding required')
    refs=[]
    for q in queries:
        if set(q)!={'qid','split','question','choices','query_image'} or q['split'] not in ('smoke_20','dev','internal_holdout','frozen_test'):
            raise ValueError('Unexpected query metadata or split')
        if not isinstance(q['question'],str) or not q['question'] or set(q['choices'])!={'A','B','C','D'} or any(not isinstance(x,str) or not x for x in q['choices'].values()):
            raise ValueError('Question and four choices required')
        refs.append(q['query_image'])
    from PIL import Image
    root=Path(root).resolve();verified={}
    for ref in refs+list(corpus.values()):
        if set(ref)!={'path','sha256','size'} or not isinstance(ref['path'],str) or not isinstance(ref['sha256'],str) or len(ref['sha256'])!=64:
            raise ValueError('Image reference shape invalid')
        if not isinstance(ref['size'],list) or len(ref['size'])!=2 or any(type(x) is not int or x<=0 for x in ref['size']):
            raise ValueError('Positive decoded dimensions required')
        p=(root/ref['path']).resolve()
        if not p.is_relative_to(root) or not p.is_file(): raise ValueError('Image missing/outside root')
        if p not in verified:
            try:
                with Image.open(p) as image:
                    image.load();size=list(image.size)
            except (OSError,ValueError) as error:
                raise ValueError('Image cannot be decoded') from error
            verified[p]=(sha(p),size)
        if verified[p]!=(ref['sha256'],ref['size']): raise ValueError('Image SHA/dimensions mismatch')
    return package


def validate_ranks(package,ranks):
    no_labels(ranks)
    if not isinstance(ranks,list) or [r['qid'] for r in ranks]!=[q['qid'] for q in package['queries']]:
        raise ValueError('Rankings must match fixed query order exactly')
    for row in ranks:
        if set(row)!={'qid','corpus_ids'} or len(row['corpus_ids'])!=10:
            raise ValueError('Exactly the bound top10 pool required')
        select(row['qid'],row['corpus_ids'],'cosine',3,20261017)
        if any(x not in package['corpus'] for x in row['corpus_ids']): raise ValueError('Unknown candidate')
    return ranks


def validate_scores(package,ranks,scores):
    no_labels(scores)
    if (scores.get('pool_sha256')!=pool_digest(ranks) or scores.get('input_package_sha256')!=pool_digest(package)
        or scores.get('score_type')!='first_step_raw_true_logit'
        or (scores.get('model_id'),scores.get('revision'))!=SURROGATE):
        raise ValueError('Score pool/input/model/protocol identity mismatch')
    table={}
    for row in scores['scores']:
        key=(row['qid'],row['candidate_id'])
        if key in table: raise ValueError('Duplicate utility score')
        score=row['raw_true_logit']
        if type(score) not in (int,float) or not math.isfinite(score): raise ValueError('Invalid utility logit')
        table[key]=score
    if set(table)!={(r['qid'],cid) for r in ranks for cid in r['corpus_ids']}:
        raise ValueError('Utility scores must cover exactly the bound pool')
    return table


def selection_rows(package,ranks,scores):
    validate_ranks(package,ranks)
    table=validate_scores(package,ranks,scores)
    rows=[]
    for q,r in zip(package['queries'],ranks):
        utility={cid:table[(q['qid'],cid)] for cid in r['corpus_ids']}
        for strategy in STRATEGIES:
            selected=select(q['qid'],r['corpus_ids'],strategy,3,20261017,utility)
            rows.append(generation_row(q,package['corpus'],selected,strategy,pool_digest(ranks),20261017))
    return rows


def write_json(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())


def require_real_scores(scores):
    if not isinstance(scores,dict) or scores.get('synthetic') is not False:
        raise ValueError('Explicit non-synthetic model scores required for real generation')


def consume_authorization(auth,root,output):
    if not isinstance(auth.get('lease_id'),str) or not auth['lease_id']:
        raise ValueError('New lease identity required')
    if not isinstance(auth.get('output_path'),str) or Path(auth['output_path']).resolve()!=Path(output).resolve():
        raise ValueError('Authorization must bind this exact new output directory')
    if not isinstance(auth.get('data_root'),str) or Path(auth['data_root']).resolve()!=Path(root).resolve():
        raise ValueError('Authorization must bind the actual data root')
    # Deliberately omit output from claim identity: changing output cannot authorize a retry.
    key=pool_digest({k:auth[k] for k in ['lease_id','mode','model_key','input_package_sha256','rankings_sha256']})
    claims=CLAIMS_ROOT
    claims.mkdir(parents=True,exist_ok=True)
    try:
        write_json(claims/(key+'.json'),{'status':'consumed_no_retry','authorization':auth,'claimed_epoch':time.time()})
    except FileExistsError as error:
        raise ValueError('Authorization already consumed; no automatic repeat') from error


def prepare_selection(package,ranks,scores,output,root):
    validate_inputs(package,root)
    rows=selection_rows(package,ranks,scores)
    out=Path(output)
    if out.exists(): raise ValueError('Output exists; no overwrite')
    out.mkdir(parents=True,exist_ok=False)
    with (out/'inputs.jsonl').open('x') as stream:
        for row in rows: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        stream.flush();os.fsync(stream.fileno())
    receipt={'status':'inputs_prepared_not_inferred','rows':len(rows),'questions':len(package['queries']),
             'input_package_sha256':pool_digest(package),'pool_sha256':pool_digest(ranks),
             'utility_scores_sha256':pool_digest(scores),'inputs_sha256':sha(out/'inputs.jsonl'),
             'model_loaded':False,'synthetic':scores.get('synthetic') is True,
             'ranked_source_provenance_independently_verified':False}
    write_json(out/'receipt.json',receipt)
    return receipt


def execute(package,root,ranks,scores,output,mode,model_key,authorization):
    # Authorization files are prepared only after human approval; no prior lease is reused.
    if package.get('execution_authorized') is not True or not authorization:
        raise ValueError('No new execution authorization; GPU remains untouched')
    auth=json.loads(Path(authorization).read_text())
    if (auth.get('input_package_sha256')!=pool_digest(package) or auth.get('mode')!=mode
        or auth.get('model_key')!=model_key or auth.get('rankings_sha256')!=pool_digest(ranks)):
        raise ValueError('Authorization does not bind this input, model, mode and rankings')
    if mode=='generate' and auth.get('utility_scores_sha256')!=pool_digest(scores):
        raise ValueError('Authorization does not bind utility scores')
    if mode=='generate':require_real_scores(scores)
    anchor=auth.get('charge_start_epoch')
    if type(anchor) not in (int,float) or not math.isfinite(anchor) or anchor>time.time():
        raise ValueError('Current billing clock anchor required')
    def budget_left():
        current=dict(auth)
        current['incurred_cny']=auth['incurred_cny']+max(0,time.time()-anchor)*auth['quoted_rate_cny_hour']/3600
        return remaining_seconds(current,time.time())-600 # preserve ten minutes for backup/shutdown
    seconds=budget_left()
    if seconds<=0: raise ValueError('Insufficient budget/deadline after backup reserve')
    validate_ranks(package,ranks)
    generated_rows=selection_rows(package,ranks,scores) if mode=='generate' else None
    registry=json.loads((REPO/'b-side/configs/model_registry.json').read_text())
    if model_key not in registry['models']: raise ValueError('Unknown pinned generator')
    cfg=registry['models'][model_key]
    if mode=='utility' and (cfg['model_id'],cfg['revision'])!=SURROGATE:
        raise ValueError('Utility surrogate must be pinned Gemma E2B')
    out=Path(output)
    if out.exists(): raise ValueError('Output exists; never overwrite or retry')
    consume_authorization(auth,root,out)
    out.mkdir(parents=True,exist_ok=False)
    receipt={'status':'started','mode':mode,'model':model_key,'model_id':cfg['model_id'],'revision':cfg['revision'],
             'input_package_sha256':pool_digest(package),'pool_sha256':pool_digest(ranks),'completed_rows':0,
             'synthetic':False,'new_method_CUDA_previously_verified':False,'started_epoch':time.time(),
             'ranked_source_provenance_independently_verified':False,
             'utility_scores_sha256':pool_digest(scores) if mode=='generate' else None,
             'lease_id':auth['lease_id']}
    def snapshot():
        temp=out/'receipt.next.json'
        with temp.open('w') as stream:
            json.dump(receipt,stream,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,out/'receipt.json')
    snapshot();backend=None;hardkill=None
    def stop(signum,frame):
        nonlocal hardkill
        hardkill=threading.Timer(5,lambda:os.kill(os.getpid(),signal.SIGKILL));hardkill.daemon=True;hardkill.start()
        raise TimeoutError('Inference deadline reached; preserve partial rows and shut down platform')
    prior=signal.signal(signal.SIGALRM,stop)
    signal.setitimer(signal.ITIMER_REAL,max(0.01,budget_left()))
    try:
        os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
        from model_adapters import HFBackend
        backend=HFBackend(cfg,registry['environments'][cfg['environment']],allow_download=False)
        receipt['runtime']=backend.runtime;snapshot()
        if mode=='utility':
            tok=backend.processor.tokenizer
            true_ids=tok.encode('True',add_special_tokens=False);false_ids=tok.encode('False',add_special_tokens=False)
            if len(true_ids)!=1 or len(false_ids)!=1 or true_ids==false_ids:
                raise ValueError('True/False must be distinct single tokens; no fallback')
            receipt.update(true_token_id=true_ids[0],false_token_id=false_ids[0]);snapshot()
        with (out/'predictions.jsonl').open('x') as stream:
            if mode=='utility':
                from PIL import Image
                import torch
                from model_adapters import chat_kwargs
                def steps():
                    for q,r in zip(package['queries'],ranks):
                        for cid in r['corpus_ids']: yield q,cid
                for q,cid in steps():
                    if budget_left()<=0: raise TimeoutError('Budget reserve reached')
                    started=time.perf_counter();images=[]
                    try:
                        for ref in [q['query_image'],package['corpus'][cid]]:
                            with Image.open(Path(root)/ref['path']) as image: images.append(image.convert('RGB'))
                        # Proposed adaptation: the query image and candidate are explicitly distinguished; no gold.
                        text=('Query: '+q['question']+'\n'+'\n'.join(f'{k}: {v}' for k,v in q['choices'].items())+
                              '\nThe first image is the query; the second is candidate evidence.\n'
                              'Is this evidence helpful for answering the query? Answer with True or False.')
                        messages=[{'role':'user','content':[{'type':'image','image':images[0]},
                                  {'type':'image','image':images[1]},{'type':'text','text':text}]}]
                        inputs=backend.processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
                            return_dict=True,return_tensors='pt',**chat_kwargs(cfg))
                        inputs.pop('token_type_ids',None)
                        if inputs['input_ids'].shape[-1]+1>cfg['context_limit']: raise ValueError('No context truncation allowed')
                        inputs=inputs.to('cuda:0')
                        for k,v in inputs.items():
                            if torch.is_tensor(v) and v.is_floating_point(): inputs[k]=v.to(dtype=next(backend.model.parameters()).dtype)
                        torch.cuda.synchronize();begin=time.perf_counter()
                        with torch.inference_mode():
                            # Direct forward yields raw logits, before generation-time processors/softmax.
                            logits=backend.model(**inputs,logits_to_keep=1).logits[0,-1,:].float()
                        torch.cuda.synchronize()
                        true=float(logits[true_ids[0]].item());false=float(logits[false_ids[0]].item())
                        if not math.isfinite(true) or not math.isfinite(false): raise ValueError('Nonfinite raw logits')
                        result={'qid':q['qid'],'candidate_id':cid,'raw_true_logit':true,'raw_false_logit':false,
                                'forward_seconds':time.perf_counter()-begin,'total_seconds':time.perf_counter()-started,
                                'input_tokens':int(inputs['input_ids'].shape[-1]),'input_image_count':2}
                    finally:
                        for image in images:image.close()
                    stream.write(json.dumps(result,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
                    receipt['completed_rows']+=1;snapshot()
            else:
                for row in generated_rows:
                    if budget_left()<=0: raise TimeoutError('Budget reserve reached')
                    result=backend.infer(row,Path(root))
                    stream.write(json.dumps({'qid':row['qid'],'split':row['split'],
                        'selection_strategy':row['selection_strategy'],'selected_ids':row['selected_ids'],**result},allow_nan=False)+'\n')
                    stream.flush();os.fsync(stream.fileno());receipt['completed_rows']+=1;snapshot()
                    if result.get('final_extraction_error'): raise ValueError('Extraction failed; retain record, no retry')
        if mode=='utility':
            results=[json.loads(x) for x in (out/'predictions.jsonl').read_text().splitlines()]
            write_json(out/'utility_scores.json',{'model_id':cfg['model_id'],'revision':cfg['revision'],
                'pool_sha256':pool_digest(ranks),'input_package_sha256':pool_digest(package),
                'score_type':'first_step_raw_true_logit','scores':results,'synthetic':False})
        receipt['status']='completed'
    except BaseException as error:
        receipt.update(status='failed_partial_no_retry',error_type=type(error).__name__,error=str(error));snapshot()
        raise
    finally:
        snapshot()
        # Keep deadline armed during model cleanup. Platform shutdown guard remains the final hard limit.
        try:
            if backend is not None:backend.close()
        except BaseException as error:
            receipt.update(status='failed_cleanup_no_retry',cleanup_error_type=type(error).__name__,cleanup_error=str(error))
            snapshot()
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior)
            if hardkill is not None:hardkill.cancel()
    return receipt


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--package',required=True,type=Path);ap.add_argument('--root',required=True,type=Path)
    ap.add_argument('--ranks',type=Path);ap.add_argument('--scores',type=Path);ap.add_argument('--output',type=Path)
    ap.add_argument('--prepare',action='store_true');ap.add_argument('--execute',action='store_true')
    ap.add_argument('--mode',choices=['utility','generate']);ap.add_argument('--model',default='gemma4_e2b')
    ap.add_argument('--authorization',type=Path)
    args=ap.parse_args()
    try:
        package=validate_inputs(json.loads(args.package.read_text()),args.root)
        if args.execute:
            # Reject unauthorized runs before trying to consume absent future ranking files.
            if not package.get('execution_authorized') or not args.authorization: raise ValueError('No new execution authorization')
        ranks=[json.loads(x) for x in args.ranks.read_text().splitlines()] if args.ranks else None
        scores=json.loads(args.scores.read_text()) if args.scores else None
        if args.execute:
            if not args.mode or not args.output or ranks is None: raise ValueError('Explicit mode/output/rankings required')
            result=execute(package,args.root,ranks,scores,args.output,args.mode,args.model,args.authorization)
        elif args.prepare:
            if args.output is None or ranks is None or scores is None: raise ValueError('Preparation needs bound rankings, scores and new output')
            result=prepare_selection(package,ranks,scores,args.output,args.root)
        else:
            result={'status':'inputs_validated_only','questions':len(package['queries']),
                    'corpus_units':len(package['corpus']),'model_loaded':False,'execution_authorized':False}
        print(json.dumps(result))
    except (ValueError,KeyError,TypeError,OSError,RuntimeError,ImportError) as e:ap.exit(2,f'ERROR: {e}\n')

if __name__=='__main__':main()
