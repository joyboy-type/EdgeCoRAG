"""Same-machine technical smoke; native CUDA integration remains unverified.

Hot requests use a resident corpus index and live query encoding. Cold setup is
recorded separately. This module never starts a cloud instance or downloads.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import struct
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'a-side/scripts'))
from evidence_selection import no_labels, pool_digest, select, generation_row
from independent_retrieval import file_sha, normalize, validate_weights

# Thread variables an OpenMP/BLAS runtime may read before any Python import.
# The historical smoke inherited an unparsable OMP_NUM_THREADS, so libgomp warned
# twice and kept an undocumented thread count; these helpers record what the
# process actually inherited, replace it with a pinned value before BLAS loads,
# and observe the effective counts afterwards.
THREAD_ENV_VARS = ('OMP_NUM_THREADS', 'OMP_THREAD_LIMIT', 'MKL_NUM_THREADS',
                   'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')
MANAGED_THREAD_VARS = tuple(name for name in THREAD_ENV_VARS if name != 'OMP_THREAD_LIMIT')
MAX_CPU_THREADS = 1024
MAX_LEASE_SECONDS = 7200  # consolidated single-rental sessions exceed the old 45-minute cap


def _legal_thread_value(raw):
    if not isinstance(raw, str) or not raw.isdigit():
        return False
    return 0 < int(raw)


def default_affinity():
    if hasattr(os, 'sched_getaffinity'):
        return len(os.sched_getaffinity(0))
    return os.cpu_count()


def cpu_quota_threads(read=None):
    """CPU count allowed by the cgroup quota, or None when unlimited/unreadable.

    A container can expose far more CPUs than its quota allows; pinning OpenMP to the
    visible count then oversubscribes and dominates CPU preprocessing.
    """
    read = (lambda p: Path(p).read_text().strip()) if read is None else read
    try:
        raw = read('/sys/fs/cgroup/cpu.max')
        fields = raw.split()
        if len(fields) == 2 and fields[0] != 'max':
            quota, period = int(fields[0]), int(fields[1])
            if quota > 0 and period > 0:
                return max(1, quota // period)
    except (OSError, ValueError):
        pass
    try:
        quota = int(read('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'))
        period = int(read('/sys/fs/cgroup/cpu/cpu.cfs_period_us'))
        if quota > 0 and period > 0:
            return max(1, quota // period)
    except (OSError, ValueError):
        pass
    return None


def inherited_thread_environment(environ=None):
    environ = os.environ if environ is None else environ
    return {name: environ.get(name) for name in THREAD_ENV_VARS}


def invalid_thread_values(environ=None):
    environ = os.environ if environ is None else environ
    return {name: environ[name] for name in THREAD_ENV_VARS
            if environ.get(name) is not None and not _legal_thread_value(environ[name])}


def resolve_cpu_threads(setting, cpu_count=None, affinity=None, quota=None):
    """Plan pins a positive integer, or 'affinity' = min(visible CPUs, cgroup quota)."""
    cpu_count = os.cpu_count if cpu_count is None else cpu_count
    affinity = default_affinity if affinity is None else affinity
    quota = cpu_quota_threads if quota is None else quota
    if setting == 'affinity':
        visible = affinity() or cpu_count()
        allowed = quota()
        available = min(visible, allowed) if allowed else visible
    elif type(setting) is int and 0 < setting <= MAX_CPU_THREADS:
        available = setting
    else:
        raise ValueError('Plan must pin a positive CPU thread integer or affinity')
    if type(available) is not int or not 0 < available <= MAX_CPU_THREADS:
        raise ValueError('Resolved CPU thread count out of range')
    return available


def configure_cpu_threads(threads, environ=None):
    """Record inherited thread settings, then pin the managed variables."""
    environ = os.environ if environ is None else environ
    if type(threads) is not int or not 0 < threads <= MAX_CPU_THREADS:
        raise ValueError('CPU thread count must be a positive integer')
    inherited = inherited_thread_environment(environ)
    invalid = invalid_thread_values(environ)
    removed = {}
    limit = environ.get('OMP_THREAD_LIMIT')
    if limit is not None:
        if not _legal_thread_value(limit):
            removed['OMP_THREAD_LIMIT'] = environ.pop('OMP_THREAD_LIMIT')
        elif int(limit) < threads:
            raise ValueError('OMP_THREAD_LIMIT would silently cap the pinned thread count')
    applied = {}
    for name in MANAGED_THREAD_VARS:
        environ[name] = str(threads)
        applied[name] = str(threads)
    return dict(requested=threads, inherited=inherited, invalid_inherited=invalid,
                removed_invalid=removed, applied=applied,
                note=('inherited values are recorded verbatim and then overridden before any '
                      'NumPy/BLAS/PyTorch import; they are not retro-documented as measured'))


def apply_cpu_threads(threads, torch_module=None, threadpool_limits=None):
    """Enforce the pinned thread count before any parallel work starts.

    Environment variables alone are not enforcement: a BLAS build may cap or ignore
    them (the round-2 run asked for 128 and observed 64). The applied values are read
    back afterwards and a mismatch aborts the run instead of measuring an unknown
    configuration.
    """
    if type(threads) is not int or not 0 < threads <= MAX_CPU_THREADS:
        raise ValueError('CPU thread count must be a positive integer')
    if torch_module is None:
        import torch as torch_module
    if threadpool_limits is None:
        try:
            from threadpoolctl import threadpool_limits as threadpool_limits
        except Exception:
            threadpool_limits = None
    applied = dict(requested=threads, torch_intra_op=None, torch_inter_op=None,
                   threadpoolctl_applied=False, errors=[])
    handle = None
    torch_module.set_num_threads(threads)
    applied['torch_intra_op'] = torch_module.get_num_threads()
    try:
        torch_module.set_num_interop_threads(1)
        applied['torch_inter_op'] = torch_module.get_num_interop_threads()
    except Exception as error:
        applied['errors'].append('inter_op:' + type(error).__name__)
        applied['torch_inter_op'] = torch_module.get_num_interop_threads()
    if threadpool_limits is None:
        applied['errors'].append('threadpoolctl unavailable')
    else:
        handle = threadpool_limits(limits=threads)
        applied['threadpoolctl_applied'] = True
    if applied['torch_intra_op'] != threads:
        raise ValueError('PyTorch intra-op threads do not match the pinned count')
    return applied, handle


def release_thread_limits(handle):
    if handle is not None:
        handle.unregister()


def blas_evidence():
    try:
        from threadpoolctl import threadpool_info
    except Exception:
        return {'available': False,
                'reason': 'threadpoolctl unavailable; BLAS thread count left unverified'}
    try:
        pools = threadpool_info()
    except Exception as error:
        return {'available': False, 'reason': type(error).__name__}
    return {'available': True,
            'pools': [{k: pool.get(k) for k in ('internal_api', 'num_threads', 'prefix')}
                      for pool in pools]}


def observed_parallel_evidence(requested, cpu_count=None, affinity=None, quota=None,
                               torch_threads=None, torch_interop=None, blas=None):
    """Measured values only; nothing is filled in when a probe is unavailable."""
    cpu_count = os.cpu_count if cpu_count is None else cpu_count
    affinity = default_affinity if affinity is None else affinity
    quota = cpu_quota_threads if quota is None else quota
    blas = blas_evidence if blas is None else blas
    threads = None if torch_threads is None else torch_threads()
    evidence = blas()
    pools = evidence.get('pools') or []
    observed_pools = [pool.get('num_threads') for pool in pools]
    return dict(requested=requested, cpu_count=cpu_count(), affinity_count=affinity(),
                cpu_quota=quota(), torch_intra_op_threads=threads,
                torch_inter_op_threads=None if torch_interop is None else torch_interop(),
                torch_matches_requested=threads == requested,
                blas_pool_threads=observed_pools,
                blas_matches_requested=(None if not observed_pools
                                        else all(value == requested for value in observed_pools)),
                blas_threadpool=evidence)


def verify_thread_configuration(observed):
    """A pinned configuration that did not take effect must abort before measuring."""
    if not observed.get('torch_matches_requested'):
        raise ValueError('PyTorch intra-op threads do not match the pinned CPU thread count')
    if observed.get('torch_inter_op_threads') not in (None, 1):
        raise ValueError('PyTorch inter-op threads were not pinned to one')
    if observed.get('blas_matches_requested') is False:
        raise ValueError('BLAS thread pools do not match the pinned CPU thread count')
    return True


def no_self_pool(ids, query_sha):
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate ranking identities')
    pool = [cid for cid in ids if cid != 'image:'+query_sha][:10]
    if len(pool) != 10:
        raise ValueError('Ten distinct non-self candidates required')
    return pool


def ranking_evidence(order, scores, query_sha, pool=None):
    """Score-level record of one live ranking, so boundary stability is measured.

    The scan stops after the eleventh non-self candidate, so recording stays off the
    measured critical path. Pass the pool that `no_self_pool` already validated to
    skip a second full uniqueness scan; omitting it re-validates the whole order.
    """
    order = list(order)
    if len(order) != len(scores):
        raise ValueError('Ranking and similarity sequences are misaligned')
    if len(order) < 11:
        raise ValueError('Full ranking with at least eleven candidates required')
    self_id = 'image:'+query_sha
    picked, self_rank = [], None
    for index, cid in enumerate(order):
        if not isinstance(cid, str) or not cid:
            raise ValueError('Ranking identities must be unique nonempty strings')
        if cid == self_id:
            self_rank = index if self_rank is None else self_rank
            continue
        picked.append((index, cid))
        if len(picked) == 11:
            break
    if len(picked) < 11:
        raise ValueError('Ranking must contain eleven candidates beyond the query image')
    head = [float(scores[index]) for index, _ in picked]
    if any(not math.isfinite(value) for value in head):
        raise ValueError('Nonfinite similarity in reference ranking')
    if any(head[i] < head[i+1] for i in range(10)):
        raise ValueError('Similarity must be non-increasing along the ranking')
    candidates = [cid for _, cid in picked]
    if pool is None:
        if len(set(order)) != len(order):
            raise ValueError('Ranking identities must be unique nonempty strings')
        pool = candidates[:10]
    if len(pool) != 10 or len(set(pool)) != 10 or list(pool) != candidates[:10]:
        raise ValueError('Ten distinct non-self candidates required in ranking order')
    top = head[:10]
    return dict(candidate_ids=list(pool), top10_scores=top,
                top10_adjacent_gaps=[top[i]-top[i+1] for i in range(9)],
                boundary_gap=top[-1]-head[10], boundary_candidate=candidates[10],
                self_rank=self_rank,
                self_rank_scope='scanned through the eleventh non-self candidate',
                units='cosine similarity of normalized float32 index vectors on CPU')


def vector_distance(live, reference):
    """Distance from a live query vector to its archived reference vector."""
    live = [float(value) for value in live]
    reference = [float(value) for value in reference]
    if len(live) != len(reference) or not live:
        raise ValueError('Vector shape mismatch')
    if any(not math.isfinite(value) for value in live + reference):
        raise ValueError('Nonfinite vector')
    norm_live = math.sqrt(sum(value * value for value in live))
    norm_reference = math.sqrt(sum(value * value for value in reference))
    difference = [a - b for a, b in zip(live, reference)]
    return dict(dimension=len(live), l2=math.sqrt(sum(value * value for value in difference)),
                linf=max(abs(value) for value in difference),
                cosine=(sum(a * b for a, b in zip(live, reference)) / (norm_live * norm_reference))
                       if norm_live and norm_reference else None,
                bitwise_equal=live == reference,
                scope='live query vector vs archived reference vector, both float32-normalized')


def reference_vectors(plan):
    """Validate archived reference vectors; returns {} when the plan carries none."""
    references = plan.get('reference_vectors')
    if references is None:
        return {}
    if not isinstance(references, dict) or set(references) != {q['qid'] for q in plan['queries']}:
        raise ValueError('Reference vectors must cover exactly the plan queries')
    for qid, values in references.items():
        if (not isinstance(values, list) or len(values) != RETRIEVER_SPEC['dimension']
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
            raise ValueError('Malformed reference vector: ' + qid)
    return references


def attach_reference_vectors(plan):
    """Validate and attach archived reference vectors so live encoding is measurable."""
    references = reference_vectors(plan)
    for query in plan['queries']:
        if query['qid'] in references:
            query['reference_vector'] = references[query['qid']]
    return references


def vector_fingerprint(vector):
    if hasattr(vector, 'tobytes') and hasattr(vector, 'dtype'):
        data, dtype, dimension = vector.tobytes(), str(vector.dtype), int(getattr(vector, 'size', 0))
    else:
        values = [float(value) for value in vector]
        data, dtype, dimension = struct.pack('<%df' % len(values), *values), 'float32', len(values)
    if not data or dimension <= 0:
        raise ValueError('Empty query vector')
    return dict(dtype=dtype, dimension=dimension, sha256=hashlib.sha256(data).hexdigest())


def schedule(queries):
    no_labels(queries)
    if (len(queries) != 5 or len({q['qid'] for q in queries}) != 5
            or any(q['split'] != 'smoke_20' for q in queries)):
        raise ValueError('Exactly five unique observed smoke queries required')
    rows = [dict(qid=queries[0]['qid'],strategy=s,repeat=-1,warmup=True)
            for s in ('cosine','utility')]
    for repeat in range(3):
        for i,q in enumerate(queries):
            strategies = ('cosine','utility') if (repeat+i)%2 == 0 else ('utility','cosine')
            rows.extend(dict(qid=q['qid'],strategy=s,repeat=repeat,warmup=False) for s in strategies)
    return rows


def _request(q, corpus, strategy, runtime, clock=time.perf_counter,
            splits=('smoke_20',), strategies=('cosine','utility')):
    no_labels(q)
    if q['split'] not in splits or strategy not in strategies:
        raise ValueError('Request outside the declared observed scope')
    runtime.sync(); runtime.reset_peak(); started=clock(); parts={}
    def timed(name, action):
        begin=clock(); value=action(); runtime.sync(); elapsed=clock()-begin
        if not math.isfinite(elapsed) or elapsed < 0: raise ValueError('Invalid component clock')
        parts[name]=elapsed
        return value
    vector=timed('query_decode_encode_seconds',lambda:runtime.encode(q))
    def retrieve():
        order,scores=runtime.rank(vector)
        pool=no_self_pool(order,q['query_image']['sha256'])
        return pool,ranking_evidence(order,scores,q['query_image']['sha256'],pool)
    pool,evidence=timed('ranking_no_self_seconds',retrieve)
    reference=q.get('reference_vector')
    comparison=None if reference is None else vector_distance(vector,reference)
    def selection():
        scores=runtime.utility(q,pool) if strategy=='utility' else None
        ids=select(q['qid'],pool,strategy,3,20261017,scores)
        return generation_row(q,corpus,ids,strategy,pool_digest(pool),20261017)
    row=timed('selection_request_build_seconds',selection)
    # HFBackend.infer resets allocator peaks; preserve the pre-generation segment.
    before=runtime.peak()
    result=timed('generation_decode_seconds',lambda:runtime.infer(row))
    after=runtime.peak(); runtime.sync(); elapsed=clock()-started
    if not math.isfinite(elapsed) or elapsed < sum(parts.values()):
        raise ValueError('Invalid outer request clock')
    memory={k:max(before[k],after[k]) for k in ('allocated_bytes','reserved_bytes')}
    reported=result.get('cuda_memory') or {}
    for k,field in [('allocated_bytes','process_allocator_peak_allocated'),
                    ('reserved_bytes','process_allocator_peak_reserved')]:
        if reported.get(field) is not None: memory[k]=max(memory[k],reported[field])
    return dict(qid=q['qid'],strategy=strategy,candidate_ids=pool,
                ranking=evidence,query_vector_fingerprint=vector_fingerprint(vector),
                query_vector_vs_reference=comparison,
                selected_ids=row['selected_ids'],generation=result,
                final_output=result.get('final_output'),synthetic=runtime.synthetic,
                end_to_end_seconds=elapsed,components=parts,memory=memory,
                memory_scope='process CUDA allocator; maximum across both reset segments; not device total')


def request(q, corpus, strategy, runtime, clock=time.perf_counter,
            splits=('smoke_20',), strategies=('cosine','utility')):
    """Future runs only: device-wide sampled resources; never allocator relabeling."""
    from recording_policy import ResourceSampler
    synthetic=runtime.synthetic
    unreadable=lambda name: (_ for _ in ()).throw(OSError('synthetic runtime'))
    sampler=ResourceSampler(None if synthetic else getattr(runtime,'device_memory',None),
                            meminfo=unreadable if synthetic else None).start()
    record=None
    try:
        record=_request(q,corpus,strategy,runtime,clock,splits,strategies)
    finally:
        sampler.sample()
        resources=sampler.finish()
        generation=record['generation'] if record is not None else {}
        resources['rendered_prompt']=generation.get('rendered_prompt',
            dict(status='not_recorded',reason='backend did not return actual processor-rendered string'))
        resources['timing_scope']='sampler setup/teardown excluded from existing end_to_end_seconds; in-request instrumentation overhead included'
        runtime.last_recording=resources
    record['recording']=resources
    return record


def save(path, value):
    tmp=path.with_suffix('.next.json')
    with tmp.open('w') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def run(queries,corpus,output,runtime):
    jobs=schedule(queries); lookup={q['qid']:q for q in queries}
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    receipt=dict(status='running',synthetic=runtime.synthetic,completed_requests=0,
                 measured_requests=0,p95_seconds=None,
                 scope='technical smoke on observed queries; no accuracy or deployment claim')
    save(out/'receipt.json',receipt); measured=[]
    try:
        with (out/'requests.jsonl').open('x') as f:
            for job in jobs:
                try: record=dict(job,**{k:v for k,v in request(lookup[job['qid']],corpus,job['strategy'],runtime).items() if k not in job})
                except BaseException as error:
                    f.write(json.dumps(dict(job,error_type=type(error).__name__,error=str(error),recording=getattr(runtime,'last_recording',{})))+'\n')
                    f.flush();os.fsync(f.fileno());raise
                f.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
                receipt['completed_requests']+=1
                if not job['warmup']:
                    measured.append(record);receipt['measured_requests']+=1
                save(out/'receipt.json',receipt)
        receipt['median_seconds_by_strategy']={s:statistics.median(r['end_to_end_seconds'] for r in measured if r['strategy']==s) for s in ('cosine','utility')}
        receipt['status']='completed'
    except BaseException as error:
        receipt.update(status='failed_partial_no_retry',error_type=type(error).__name__,error=str(error));raise
    finally: save(out/'receipt.json',receipt)
    return receipt


def check_lease(auth, now, estimate):
    if any(auth.get(k) is not True for k in ('execution_authorized','protocol_approved','shutdown_verified')):
        raise ValueError('New explicit approval and verified platform timer required')
    keys=('charge_start_epoch','deadline_epoch','quoted_rate_cny_hour','max_rate_cny_hour',
          'max_incremental_cny','incurred_cny','storage_reserve_cny')
    if any(type(auth.get(k)) not in (float,int) or not math.isfinite(auth[k]) for k in keys):
        raise ValueError('Finite lease values required')
    anchor=auth['charge_start_epoch']; deadline=auth['deadline_epoch'];rate=auth['quoted_rate_cny_hour']
    if (not anchor <= now < deadline <= anchor+MAX_LEASE_SECONDS or
            not 0 < rate <= auth['max_rate_cny_hour'] <= 2.18 or
            not 0 < auth['max_incremental_cny'] <= 3 or auth['incurred_cny'] < 0 or
            auth['storage_reserve_cny'] < .5 or type(estimate) not in (float,int) or
            not math.isfinite(estimate) or estimate <= 0):
        raise ValueError('Smoke lease exceeds scope, time or budget bounds')
    projected=(deadline-anchor)*rate/3600+auth['incurred_cny']+auth['storage_reserve_cny']
    available=deadline-now-600
    if projected > auth['max_incremental_cny'] or available <= estimate*1.25:
        raise ValueError('Insufficient whole-lease budget including 25% margin and 600-second preservation')
    return available


def process_rss_bytes(path='/proc/self/status', read=None):
    """Measured process memory from /proc; returns None where the file is absent."""
    read = (lambda p: Path(p).read_text()) if read is None else read
    try:
        text = read(path)
    except OSError:
        return None
    values = {}
    for line in text.splitlines():
        if line.startswith(('VmHWM:', 'VmRSS:')):
            name, _, rest = line.partition(':')
            parts = rest.split()
            if len(parts) == 2 and parts[1] == 'kB':
                values[name.lower()] = int(parts[0]) * 1024
    return dict(current_bytes=values.get('vmrss'), peak_bytes=values.get('vmhwm'))


class NativeRuntime:
    synthetic=False
    def __init__(self,plan,root):
        import importlib.metadata
        if importlib.metadata.version('sentence-transformers')!='6.1.0':
            raise RuntimeError('Pinned sentence-transformers 6.1.0 required')
        import numpy as np
        import torch
        from sentence_transformers import SentenceTransformer
        from model_adapters import HFBackend
        self.root=Path(root);self.torch=torch;self.np=np
        self.corpus=plan['corpus'];self.ids=np.asarray(plan['corpus_order'])
        begin=time.perf_counter()
        self.rss_before_index=process_rss_bytes()
        self.vectors=normalize(np.load(self.root/plan['index']['path'],allow_pickle=False),768)
        self.rss_after_index=process_rss_bytes()
        if self.vectors.shape != (len(self.ids),768): raise ValueError('Index shape mismatch')
        spec=plan['retriever'];weights=self.root/spec['cache_path'];validate_weights(weights,spec)
        self.encoder=SentenceTransformer(str(weights),device='cuda',local_files_only=True,
            trust_remote_code=False,config_kwargs={'audio_config':None},model_kwargs={'torch_dtype':torch.bfloat16})
        registry=json.loads((REPO/'b-side/configs/model_registry.json').read_text())
        self.cfg=registry['models']['gemma4_e2b']
        self.backend=HFBackend(self.cfg,registry['environments'][self.cfg['environment']],allow_download=False)
        tokenizer=self.backend.processor.tokenizer
        self.true_ids=tokenizer.encode('True',add_special_tokens=False)
        false_ids=tokenizer.encode('False',add_special_tokens=False)
        if len(self.true_ids)!=1 or len(false_ids)!=1 or self.true_ids==false_ids:raise ValueError('Single distinct True/False tokens required')
        self.sync();self.cold_setup_seconds=time.perf_counter()-begin
    def sync(self): self.torch.cuda.synchronize()
    def reset_peak(self): self.torch.cuda.reset_peak_memory_stats()
    def peak(self): return dict(allocated_bytes=self.torch.cuda.max_memory_allocated(),reserved_bytes=self.torch.cuda.max_memory_reserved())
    def device_memory(self):
        free,total=self.torch.cuda.mem_get_info()
        return dict(free_bytes=int(free),total_bytes=int(total),used_bytes=int(total-free),
                    scope=('CUDA device-wide via cudaMemGetInfo at a request boundary; '
                           'sampled, not a peak, and not system RAM'))
    def encode(self,q):
        from PIL import Image
        with Image.open(self.root/q['query_image']['path']) as im:
            image=im.convert('RGB')
            try:
                values=self.encoder.encode([image],batch_size=1,normalize_embeddings=False,
                    convert_to_numpy=True,show_progress_bar=False)
            finally:image.close()
        return normalize(values,768)[0]
    def rank(self,vector):
        similarity=self.vectors@vector
        order=self.np.lexsort((self.ids,-similarity))
        return self.ids[order].tolist(),similarity[order]
    def search(self,vector): return self.rank(vector)[0]
    def utility(self,q,pool):
        from PIL import Image
        from model_adapters import chat_kwargs
        torch=self.torch;backend=self.backend;scores={}
        for cid in pool:
            images=[]
            try:
                for ref in (q['query_image'],self.corpus[cid]):
                    with Image.open(self.root/ref['path']) as im: images.append(im.convert('RGB'))
                text=('Query: '+q['question']+'\n'+'\n'.join(f'{k}: {v}' for k,v in q['choices'].items())+
                      '\nThe first image is the query; the second is candidate evidence.\n'
                      'Is this evidence helpful for answering the query? Answer with True or False.')
                messages=[{'role':'user','content':[{'type':'image','image':im} for im in images]+[{'type':'text','text':text}]}]
                inputs=backend.processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
                    return_dict=True,return_tensors='pt',**chat_kwargs(self.cfg))
                inputs.pop('token_type_ids',None)
                if inputs['input_ids'].shape[-1]+1>self.cfg['context_limit']:raise ValueError('No context truncation')
                inputs=inputs.to('cuda:0')
                for k,v in inputs.items():
                    if torch.is_tensor(v) and v.is_floating_point():inputs[k]=v.to(dtype=next(backend.model.parameters()).dtype)
                with torch.inference_mode():
                    logits=backend.model(**inputs,logits_to_keep=1).logits[0,-1,:].float()
                scores[cid]=float(logits[self.true_ids[0]].item())
            finally:
                for image in images:image.close()
        return scores
    def infer(self,row): return self.backend.infer(row,self.root)


ENTRY = 'b-side/e2e_smoke.py'
REQUIRED_SOURCES = ('b-side/recording_policy.py',
    'b-side/e2e_smoke.py','b-side/e2e_lease.py','b-side/model_adapters.py',
    'b-side/run_candidate.py','b-side/run_smoke.py','b-side/handover_adapter.py',
    'b-side/accept_handover.py','b-side/score_minimal.py',
    'b-side/configs/model_registry.json','b-side/configs/shared_visual_mcq_v1.json',
    'b-side/configs/qwen3_vl_4b_smoke.json',
    'b-side/configs/a_handover_baseline.json',
    'a-side/scripts/evidence_selection.py','a-side/scripts/independent_retrieval.py')
RETRIEVER_SPEC = dict(model_id='google/embeddinggemma-2',
                      revision='914f7f89142e33e77833254d9c9b90c3cef7303b',dimension=768)


def validate_plan(plan,root,repo=REPO):
    no_labels(plan);schedule(plan['queries']);root=Path(root).resolve();repo=Path(repo).resolve()
    if plan.get('status')!='prepared_unexecuted' or plan.get('execution_authorized') is not False:
        raise ValueError('Prepared, unexecuted plan required; authorization is a separate new lease')
    if plan.get('entry')!=ENTRY:raise ValueError('Smoke plan must name its own execution entry')
    resolve_cpu_threads(plan.get('cpu_threads'))
    reference_vectors(plan)
    if (set(plan['source_pins'])!=set(REQUIRED_SOURCES) or
            any(file_sha(repo/name)!=digest for name,digest in plan['source_pins'].items())):
        raise ValueError('Source pin mismatch')
    if any(plan['retriever'].get(k)!=v for k,v in RETRIEVER_SPEC.items()):raise ValueError('Pinned EG768 required')
    ids=plan['corpus_order'];corpus=plan['corpus']
    if len(ids)<11 or len(ids)!=len(set(ids)) or set(ids)!=set(corpus):raise ValueError('Corpus/index order mismatch')
    if type(plan.get('estimate_seconds')) not in (int,float) or not 0<plan['estimate_seconds']<=1600:
        raise ValueError('Bounded smoke estimate required')
    checked={}
    def verify(ref):
        p=(root/ref['path']).resolve()
        if not p.is_relative_to(root) or not p.is_file():raise ValueError('Input missing/outside root')
        if p not in checked:checked[p]=file_sha(p)
        if checked[p]!=ref['sha256']:raise ValueError('Input hash mismatch')
    verify(plan['index'])
    for q in plan['queries']:
        if set(q)!={'qid','split','question','choices','query_image'} or set(q['choices'])!=set('ABCD'):
            raise ValueError('Unexpected query metadata')
        verify(q['query_image'])
    for ref in corpus.values():verify(ref)
    return dict(status='validated_no_model_loaded',questions=5,corpus_units=len(ids),
                requests=32,measured_requests=30,synthetic=False,gpu_execution_performed=False)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--worker',action='store_true');ap.add_argument('--output',type=Path)
    a=ap.parse_args();plan=json.loads(a.plan.read_text());root=a.root.resolve()
    if not a.worker:
        print(json.dumps(validate_plan(plan,root),indent=2));return
    if a.output is None:raise ValueError('New output required')
    lease_path=a.output.parent/'lease.json';lease=json.loads(lease_path.read_text())
    if lease.get('plan_sha256')!=file_sha(a.plan) or Path(lease['output_path']).resolve()!=a.output.parent.resolve():
        raise ValueError('Worker lease binding mismatch')
    check_lease(lease,time.time(),plan['estimate_seconds'])
    claim=root/'e2e-claims'/(pool_digest({'lease_id':lease['lease_id']})+'.json')
    if json.loads(claim.read_text())!=lease:raise ValueError('Parent claim required')
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    # Must precede every NumPy/PyTorch import so the pinned value wins over the
    # inherited environment; the inherited raw values are preserved in the receipt.
    threads=resolve_cpu_threads(plan['cpu_threads'])
    configuration=configure_cpu_threads(threads)
    applied,thread_handle=apply_cpu_threads(threads)
    configuration['applied_threads']=applied
    save(a.output.parent/'thread-configuration.json',configuration)
    started=time.perf_counter();validation=validate_plan(plan,root)
    save(a.output.parent/'validation.json',validation)
    runtime=NativeRuntime(plan,root)
    configuration['observed']=observed_parallel_evidence(
        threads,torch_threads=runtime.torch.get_num_threads,
        torch_interop=runtime.torch.get_num_interop_threads)
    verify_thread_configuration(configuration['observed'])
    save(a.output.parent/'thread-configuration.json',configuration)
    save(a.output.parent/'setup.json',dict(cold_setup_seconds=runtime.cold_setup_seconds,
        validation_and_setup_seconds=time.perf_counter()-started,runtime=runtime.backend.runtime,
        cpu_threads=configuration,
        index_memory=dict(resident_vector_bytes=runtime.vectors.nbytes,
                          rss_before_index=runtime.rss_before_index,
                          rss_after_index=runtime.rss_after_index,
                          scope='resident float32 index array plus measured /proc process counters; not device memory'),
        topology='EG768 plus Gemma E2B co-resident on one CUDA GPU; same E2B reused for utility/generation',
        online_corpus_encoding=False,live_query_encoding=True,device_total_peak_bytes=None))
    attach_reference_vectors(plan)
    run(plan['queries'],plan['corpus'],a.output,runtime)


if __name__=='__main__':main()
