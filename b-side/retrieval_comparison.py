"""Minimal controlled comparison before any timed run. Diagnostic only.

Part A: CPU image preprocessing cost as a function of the pinned thread count, using
the production path (`run_candidate.build_messages` + the pinned processor). Part B
(optional, needs one CUDA device): live EmbeddingGemma-2 encoding at batch=1 versus
batch=4 and the distance to the archived reference vectors.

No lease, no quality or performance claim, no writes outside --out.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TREE/'b-side'))
sys.path.insert(0, str(TREE/'a-side/scripts'))


def gpu_state():
    try:
        info = subprocess.run(['nvidia-smi', '--query-gpu=pstate,clocks.sm,clocks.max.sm,'
                               'temperature.gpu,power.draw,power.limit,utilization.gpu,memory.used',
                               '--format=csv,noheader'], capture_output=True, text=True, timeout=20)
        return dict(exit_code=info.returncode, stdout=info.stdout.strip(), stderr=info.stderr.strip())
    except Exception as error:
        return dict(exit_code=None, error=type(error).__name__, stdout='', stderr='')


def cgroup_quota():
    for path, fields in (('/sys/fs/cgroup/cpu.max', 2),):
        try:
            raw = Path(path).read_text().split()
            if len(raw) == fields and raw[0] != 'max':
                return max(1, int(raw[0])//int(raw[1])) if int(raw[1]) else None
        except (OSError, ValueError):
            pass
    try:
        quota = int(Path('/sys/fs/cgroup/cpu/cpu.cfs_quota_us').read_text())
        period = int(Path('/sys/fs/cgroup/cpu/cpu.cfs_period_us').read_text())
        return max(1, quota//period) if quota > 0 and period > 0 else None
    except (OSError, ValueError):
        return None


def build_row(plan, index):
    from evidence_selection import generation_row
    query = plan['queries'][index]
    pool = [cid for cid in plan['corpus_order'][:10]]
    return generation_row(query, plan['corpus'], pool[:3], 'cosine', 'preprocessing-sweep', 20261017)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--threads', default='1,2,4,8,16,32,64,128')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--with-gpu', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    root = args.root.resolve()
    if args.out.exists():
        raise SystemExit('Refusing to overwrite an existing receipt')
    settings = [int(value) for value in args.threads.split(',')]
    if any(not 0 < value <= 1024 for value in settings):
        raise SystemExit('Invalid thread setting')

    import torch
    from transformers import AutoProcessor
    from PIL import Image
    from run_candidate import build_messages
    from model_adapters import chat_kwargs
    from threadpoolctl import threadpool_limits, threadpool_info

    registry = json.loads((TREE/'b-side/configs/model_registry.json').read_text())
    cfg = registry['models']['gemma4_e2b']
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    processor = AutoProcessor.from_pretrained(cfg['model_id'], revision=cfg['revision'],
                                              trust_remote_code=False, local_files_only=True)
    kwargs = chat_kwargs(cfg)

    def load_image(path):
        with Image.open(path) as image:
            image.load()
            return image.convert('RGB')

    row = build_row(plan, 0)
    trials = []
    for threads in settings:
        torch.set_num_threads(threads)
        with threadpool_limits(limits=threads):
            for _ in range(2):  # warmup, not recorded
                messages = build_messages(row, root, load_image)
                processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                              return_dict=True, return_tensors='pt', **kwargs)
            times, tokens = [], None
            for _ in range(args.repeats):
                started = time.perf_counter()
                messages = build_messages(row, root, load_image)
                inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                       return_dict=True, return_tensors='pt', **kwargs)
                times.append(time.perf_counter()-started)
                tokens = int(inputs['input_ids'].shape[-1])
            pools = [pool['num_threads'] for pool in threadpool_info()]
        trials.append(dict(requested=threads, torch_intra_op=torch.get_num_threads(),
                           blas_pool_threads=pools, input_tokens=tokens,
                           images=len(messages[0]['content'])-1,
                           median_preprocess_seconds=statistics.median(times),
                           min_preprocess_seconds=min(times), max_preprocess_seconds=max(times),
                           repeats=len(times)))

    encoding = None
    if args.with_gpu:
        import numpy as np
        from sentence_transformers import SentenceTransformer
        from independent_retrieval import normalize
        from e2e_smoke import vector_distance
        spec = plan['retriever']
        encoder = SentenceTransformer(str(root/spec['cache_path']), device='cuda', local_files_only=True,
                                      trust_remote_code=False, config_kwargs={'audio_config': None},
                                      model_kwargs={'torch_dtype': torch.bfloat16})
        queries = [query for query in plan['queries'] if query['split'] == 'smoke_20'][:4]
        single, batch = {}, {}
        for query in queries:
            image = load_image(root/query['query_image']['path'])
            single[query['qid']] = normalize(encoder.encode([image], batch_size=1, normalize_embeddings=False,
                                                           convert_to_numpy=True, show_progress_bar=False), 768)[0]
            image.close()
        images = []
        for query in queries:
            images.append(load_image(root/query['query_image']['path']))
        matrix = normalize(encoder.encode(images, batch_size=4, normalize_embeddings=False,
                                          convert_to_numpy=True, show_progress_bar=False), 768)
        for image in images:
            image.close()
        for position, query in enumerate(queries):
            batch[query['qid']] = matrix[position]
        encoding = dict(queries=len(queries), batch_size_offline=4, batch_size_online=1,
                        dtype='bfloat16', revision=spec['revision'],
                        rows=[dict(qid=query['qid'],
                                   single_vs_reference=vector_distance(single[query['qid']],
                                                                       plan['reference_vectors'][query['qid']]),
                                   batch4_vs_reference=vector_distance(batch[query['qid']],
                                                                       plan['reference_vectors'][query['qid']]),
                                   single_vs_batch4=vector_distance(single[query['qid']],
                                                                    batch[query['qid']]))
                              for query in queries])

    receipt = dict(status='diagnostic_completed', plan_sha256=__import__('hashlib').sha256(
        args.plan.read_bytes()).hexdigest(), with_gpu=bool(args.with_gpu),
        cpu=dict(os_cpu_count=os.cpu_count(),
                 affinity=(len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None),
                 cgroup_quota=cgroup_quota(),
                 env={name: os.environ.get(name) for name in
                      ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')},
                 torch=dict(intra_op=torch.get_num_threads(), inter_op=torch.get_num_interop_threads(),
                            cuda=torch.version.cuda, cuda_available=torch.cuda.is_available())),
        processor=dict(model_id=cfg['model_id'], revision=cfg['revision'],
                       image_processing=dict(cfg['image_processing']),
                       config=processor.image_processor.to_dict()),
        preprocessing_trials=trials, encoding=encoding,
        gpu=gpu_state(),
        scope='diagnostic only: preprocessing cost versus thread pin, and live encoding distance; no latency claim')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(dict(status=receipt['status'],
                          best=[min(trials, key=lambda trial: trial['median_preprocess_seconds'])['requested']],
                          trials=[(trial['requested'], round(trial['median_preprocess_seconds'], 4))
                                  for trial in trials],
                          encoding=None if encoding is None else [
                              (row['qid'], round(row['single_vs_reference']['l2'], 6),
                               round(row['batch4_vs_reference']['l2'], 6),
                               round(row['single_vs_batch4']['l2'], 6))
                              for row in encoding['rows']]), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
