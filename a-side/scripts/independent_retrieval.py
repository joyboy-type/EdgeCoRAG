"""Independent image retrieval. Default validates files only; never downloads models.

Execution requires an explicitly authorized package, CUDA BF16, pinned local
weights and a new output directory. This entry does not implement utility
selection, answer generation, a deployable router, or end-to-end measurement.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time



RETRIEVERS = {
    'embeddinggemma2': ('google/embeddinggemma-2', '914f7f89142e33e77833254d9c9b90c3cef7303b', 768,
                       {'1_Pooling/config.json', '2_Normalize/config.json', 'chat_template.jinja',
                        'config.json', 'config_sentence_transformers.json', 'model.safetensors',
                        'modules.json', 'preprocessor_config.json', 'processor_config.json',
                        'sentence_bert_config.json', 'tokenizer.json', 'tokenizer.model', 'tokenizer_config.json'}),
    'clip': ('openai/clip-vit-base-patch32', '3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268', 512,
             {'config.json', 'merges.txt', 'preprocessor_config.json', 'pytorch_model.bin',
              'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json'}),
}


def required_cache_files(spec):
    for model_id, revision, dimension, files in RETRIEVERS.values():
        if spec.get('model_id') == model_id and spec.get('revision') == revision and spec.get('dimension') == dimension:
            declared = [row.get('path') for row in spec.get('required_files', [])]
            if len(set(declared)) != len(declared) or set(declared) != files:
                raise ValueError('Incomplete or unexpected model cache file manifest')
            return files
    raise ValueError('Unknown or unpinned retriever model identity')


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def normalize(vectors, dim):
    import numpy as np
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2 or not isinstance(dim, int) or not 0 < dim <= array.shape[1]:
        raise ValueError('Invalid embedding shape or dimension')
    array = array[:, :dim]
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if not np.isfinite(array).all() or not np.isfinite(norms).all() or (norms <= 0).any():
        raise ValueError('Nonfinite or zero embedding')
    return array / norms


def evaluate_rankings(query_ids, ranked_ids, gold, k_values):
    n = len(query_ids)
    if not n or len(set(query_ids)) != n or set(query_ids) != set(gold) or len(ranked_ids) != n:
        raise ValueError('Duplicate, missing or unknown query identities')
    if not k_values or any(not isinstance(k, int) or k <= 0 for k in k_values):
        raise ValueError('Invalid k')
    pool = set(ranked_ids[0])
    if not pool:
        raise ValueError('Empty corpus')
    result = {'questions': n, 'mrr': 0., 'questions_without_indexed_gt': 0}
    for k in k_values:
        result[f'hit_at_{k}'] = result[f'recall_at_{k}'] = 0.
    for qid, ranking in zip(query_ids, ranked_ids):
        if len(ranking) != len(set(ranking)) or set(ranking) != pool:
            raise ValueError('Duplicate candidate or inconsistent full ranking pool')
        if not isinstance(gold[qid], list) or any(not isinstance(v, str) or not v for v in gold[qid]):
            raise ValueError('Gold identities must be a list of nonempty strings')
        targets = set(gold[qid])
        if not targets or len(targets) != len(gold[qid]):
            raise ValueError('Gold must be a nonempty unique identity set')
        ranks = [i + 1 for i, candidate in enumerate(ranking) if candidate in targets]
        result['questions_without_indexed_gt'] += not bool(targets & pool)
        result['mrr'] += (1 / min(ranks) if ranks else 0) / n
        for k in k_values:
            hits = len(set(ranking[:k]) & targets)
            result[f'hit_at_{k}'] += bool(hits) / n
            result[f'recall_at_{k}'] += hits / len(targets) / n
    return result



def evaluate_cohorts(queries, rankings, gold, k_values):
    if len(queries) != len(rankings) or len({q['qid'] for q in queries}) != len(queries):
        raise ValueError('Combined query identity alignment failed')
    result = {}
    for split in sorted({q['split'] for q in queries}):
        positions = [i for i, q in enumerate(queries) if q['split'] == split]
        qids = [queries[i]['qid'] for i in positions]
        result[split] = evaluate_rankings(qids, [rankings[i] for i in positions],
                                         {q: gold[q] for q in qids}, k_values)
    return result


def validate_package(package, root):
    root = Path(root).resolve()
    payload = json.loads(Path(package).read_text())
    if payload.get('status') != 'prepared_unexecuted':
        raise ValueError('Expected prepared_unexecuted package')
    queries, corpus = payload.get('queries'), payload.get('corpus')
    if not isinstance(queries, list) or not queries:
        raise ValueError('Query inputs missing')
    query_fields = {'qid', 'split', 'path', 'sha256'}
    if any(set(row) != query_fields for row in queries):
        raise ValueError('Query input may contain only qid, split, image path and SHA; no gold/text metadata')
    if not isinstance(corpus, list) or not corpus or any(set(row) != {'id', 'path', 'sha256'} for row in corpus):
        raise ValueError('Opaque corpus identity inputs required')
    qids = [row['qid'] for row in queries]
    ids = [row['id'] for row in corpus]
    if any(not isinstance(v, str) or not v for v in qids + ids):
        raise ValueError('Query and corpus identities must be nonempty strings')
    if len(set(qids)) != len(qids) or len(set(ids)) != len(ids):
        raise ValueError('Duplicate query or corpus identities')
    if set(payload.get('gold', {})) != set(qids):
        raise ValueError('Scoring-only gold qids do not match query qids')
    if any(not isinstance(v, list) or not v or any(not isinstance(i, str) or not i for i in v) or len(set(v)) != len(v) for v in payload['gold'].values()):
        raise ValueError('Gold identity sets must be nonempty and unique')
    for row in queries + corpus:
        path = (root / row['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_sha(path) != row['sha256']:
            raise ValueError('Input path missing, outside root, or SHA mismatch: ' + row['path'])
    if not payload.get('models') or payload.get('query_modality') != 'image_only':
        raise ValueError('Pinned retrievers and proposed matched image_only modality required')
    for key, model in payload['models'].items():
        if key not in RETRIEVERS or model.get('model_id') != RETRIEVERS[key][0]:
            raise ValueError('Unknown retriever key or identity')
        required_cache_files(model)
    return payload


def validate_weights(directory, spec):
    root = Path(directory).resolve()
    expected = required_cache_files(spec)
    consumed_extensions = {'.json', '.safetensors', '.bin', '.model', '.txt', '.jinja', '.py'}
    present = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.suffix in consumed_extensions and not any(part.startswith('.') for part in p.relative_to(root).parts)}
    if present != expected:
        raise ValueError('Local cache has undeclared or missing loader input files')
    for row in spec['required_files']:
        path = (root / row['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Required local cache file missing: ' + row['path'])
        if row['algorithm'] == 'sha256':
            actual = file_sha(path)
        elif row['algorithm'] == 'git_blob_sha1':
            data = path.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        else:
            raise ValueError('Unknown cache hash algorithm')
        if actual != row['digest']:
            raise ValueError('Cache file identity drift: ' + row['path'])


def execute(payload, root, model_key, weights, output, split):
    if payload.get('execution_authorized') is not True:
        raise ValueError('Execution is not authorized in this preparation package')
    if model_key not in payload['models'] or not weights or not output:
        raise ValueError('Explicit model, weights and new output required')
    selected = [q for q in payload['queries'] if split == 'all' or q['split'] == split]
    if not selected:
        raise ValueError('Selected fixed split is empty')
    out = Path(output)
    if out.exists():
        raise ValueError('Output exists; preserve it and choose a new approved run')
    spec = payload['models'][model_key]
    validate_weights(weights, spec)
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    import numpy as np
    import torch
    from PIL import Image
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise ValueError('This proposed runtime requires CUDA BF16; no implicit CPU/offload fallback')
    torch.manual_seed(42)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    out.mkdir(parents=True, exist_ok=False)
    result = {'status': 'started', 'model': model_key, 'revision': spec['revision'],
              'split': split, 'query_modality': 'image_only', 'model_dtype': 'bfloat16',
              'offline_local_cache_only': True, 'GPU_interface_previously_verified': False}
    def write_receipt():
        (out / 'receipt.json').write_text(json.dumps(result, indent=2))
    write_receipt()
    try:
        start = time.perf_counter()
        if model_key == 'embeddinggemma2':
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(str(weights), device='cuda', local_files_only=True,
                                        trust_remote_code=False, config_kwargs={'audio_config': None},
                                        model_kwargs={'torch_dtype': torch.bfloat16})
            def encode(images):
                return model.encode(images, batch_size=4, normalize_embeddings=False,
                                    convert_to_numpy=True, show_progress_bar=False)
        else:
            from transformers import CLIPModel, CLIPProcessor
            model = CLIPModel.from_pretrained(str(weights), local_files_only=True,
                                             torch_dtype=torch.bfloat16, weights_only=True).to('cuda').eval()
            processor = CLIPProcessor.from_pretrained(str(weights), local_files_only=True)
            def encode(images):
                tensor = processor(images=images, return_tensors='pt')['pixel_values'].to('cuda', dtype=torch.bfloat16)
                with torch.inference_mode():
                    pooled = model.vision_model(pixel_values=tensor).pooler_output
                    return model.visual_projection(pooled).float().cpu().numpy()
        torch.cuda.synchronize()
        result['load_seconds'] = time.perf_counter() - start
        def encode_entries(entries, name):
            batches = []
            started = time.perf_counter()
            for offset in range(0, len(entries), 4):
                images = []
                for row in entries[offset:offset + 4]:
                    with Image.open(root / row['path']) as im:
                        images.append(im.convert('RGB'))
                try:
                    with torch.inference_mode():
                        batches.append(np.asarray(encode(images), dtype=np.float32))
                finally:
                    for image in images:
                        image.close()
            torch.cuda.synchronize()
            result[name + '_batch_encoding_seconds_including_decode'] = time.perf_counter() - started
            array = np.concatenate(batches, axis=0)
            if array.shape != (len(entries), spec['dimension']) or not np.isfinite(array).all():
                raise ValueError('Unexpected encoded dimension or nonfinite embeddings')
            np.save(out / (name + '.npy'), array)
            return array
        corpus_vec = encode_entries(payload['corpus'], 'corpus_embeddings')
        query_vec = encode_entries(selected, 'query_embeddings')
        ids = np.array([r['id'] for r in payload['corpus']])
        qids = [r['qid'] for r in selected]
        dimensions = [128, 256, 512, 768] if model_key == 'embeddinggemma2' else [512]
        scores = {}
        for dim in dimensions:
            cv, qv = normalize(corpus_vec, dim), normalize(query_vec, dim)
            ranks = np.lib.format.open_memmap(out / f'rank_indices_{dim}.npy', mode='w+', dtype=np.int32,
                                             shape=(len(selected), len(ids)))
            started = time.perf_counter()
            for i, vector in enumerate(qv):
                similarity = cv @ vector
                ranks[i] = np.lexsort((ids, -similarity))
            ranks.flush()
            result[f'ranking_cpu_seconds_dim{dim}'] = time.perf_counter() - started
            # Gold is used only after encoding and complete ranking have finished.
            metrics = evaluate_cohorts(selected, [ids[row].tolist() for row in ranks],
                                       {q: payload['gold'][q] for q in qids}, [1, 5])
            for cohort in metrics.values():
                cohort['denominator'] = 'all questions in this fixed split; unmatched exact GT contributes zero'
            scores[str(dim)] = metrics
            with (out / f'top10_{dim}.jsonl').open('x') as stream:
                for qid, row in zip(qids, ranks):
                    stream.write(json.dumps({'qid': qid, 'corpus_ids': ids[row[:10]].tolist()}) + '\n')
        (out / 'retrieval_metrics.json').write_text(json.dumps(scores, indent=2))
        result.update(status='completed', questions=len(selected), corpus_units=len(ids), dimensions=dimensions,
                      model_generation_answers=0, timing_scope='batch image encoding and CPU exact cosine ranking only; not end-to-end')
    except Exception as error:
        result.update(status='failed_no_automatic_retry', error_type=type(error).__name__, error=str(error))
        write_receipt()
        raise
    write_receipt()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--model', choices=['embeddinggemma2', 'clip'])
    parser.add_argument('--weights', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--split', choices=['all', 'smoke_20', 'dev', 'internal_holdout', 'frozen_test'])
    args = parser.parse_args()
    try:
        payload = validate_package(args.package, args.root)
        if not args.execute:
            print(json.dumps({'status': 'inputs_validated_only', 'questions': len(payload['queries']),
                              'corpus_units': len(payload['corpus']), 'model_loaded': False,
                              'execution_authorized': payload.get('execution_authorized') is True}))
        else:
            print(json.dumps(execute(payload, args.root.resolve(), args.model, args.weights, args.output, args.split)))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, ImportError) as error:
        parser.exit(2, f'ERROR: {error}\n')

if __name__ == '__main__':
    main()
