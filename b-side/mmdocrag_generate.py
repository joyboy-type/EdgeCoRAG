"""Technical-dev-only MMDocRAG entry. Default validates; GPU generation needs opt-in.

No evaluator, judge, automatic download, provider billing control, or resume.
The caller must arrange the separately authorized GPU lease deadline/budget.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=no_duplicates)


def validate_package(package, root):
    package, root = Path(package), Path(root).resolve()
    manifest = read_json(package / 'manifest.json')
    rows = [json.loads(s, object_pairs_hook=no_duplicates)
            for s in (package / 'generation_inputs.jsonl').read_text().split('\n') if s.strip()]
    qids = manifest.get('qids')
    if (manifest.get('split') != 'dev' or manifest.get('setting') != '15'
            or manifest.get('qid_type') != 'int' or not isinstance(qids, list) or not qids
            or any(type(q) is not int for q in qids) or len(set(qids)) != len(qids)):
        raise ValueError('Only a nonempty split-scoped dev/15 integer manifest is accepted')
    if [r.get('q_id') for r in rows] != qids:
        raise ValueError('Input qids must match complete frozen order')
    for row in rows:
        if set(row) != {'q_id', 'question', 'text_quotes', 'img_quotes'}:
            raise ValueError('Generation fields must exclude labels and unknown fields')
        if type(row['q_id']) is not int or not isinstance(row['question'], str):
            raise ValueError('Question/qid type invalid')
        if not isinstance(row['text_quotes'], list) or not isinstance(row['img_quotes'], list):
            raise ValueError('Quote lists required')
        for n, q in enumerate(row['text_quotes'], 1):
            if set(q) != {'quote_id', 'text'} or q['quote_id'] != f'text{n}' or not isinstance(q['text'], str):
                raise ValueError('Text IDs/fields must match original numbered order')
        for n, q in enumerate(row['img_quotes'], 1):
            if set(q) != {'quote_id', 'local_content_path', 'sha256', 'width', 'height'} or q['quote_id'] != f'image{n}':
                raise ValueError('Image IDs/fields must match original numbered order')
            path = (root / q['local_content_path']).resolve()
            if not path.is_relative_to(root) or not path.is_file() or sha(path) != q['sha256']:
                raise ValueError('Image path outside root, missing, or changed')
    identity = {'manifest_sha256': sha(package / 'manifest.json'),
                'generation_inputs_sha256': sha(package / 'generation_inputs.jsonl'),
                'split': manifest['split'], 'setting': manifest['setting'],
                'dataset_revision': manifest['dataset_revision'], 'qids': qids,
                'runner_sha256': sha(__file__)}
    return manifest, rows, identity


def build_messages(row, root, image_loader, prompt):
    content = [{'type': 'text', 'text': 'Text Quotes are:\n' + '\n'.join(
        '[' + q['quote_id'].removeprefix('text') + '] ' + q['text'] for q in row['text_quotes'])
        + '\nImage Quotes are:\n'}]
    for q in row['img_quotes']:
        content.extend([{'type': 'text', 'text': q['quote_id'] + ' is '},
                        {'type': 'image', 'image': image_loader(Path(root) / q['local_content_path'])}])
    content.append({'type': 'text', 'text': 'The user question is: ' + row['question']})
    return [{'role': 'system', 'content': [{'type': 'text', 'text': prompt}]},
            {'role': 'user', 'content': content}]


def validate_approved_registry(path, expected_sha256):
    if sha(path) != expected_sha256:
        raise ValueError('Complete model/environment registry changed after CPU preflight')
    return read_json(path)


def validate_native_identity(expected, rendered_sha256, input_ids_sha256, tensor_shapes):
    if (expected['rendered_sha256'] != rendered_sha256
            or expected['input_ids_sha256'] != input_ids_sha256
            or expected['tensor_shapes'] != tensor_shapes):
        raise ValueError('Native preprocessing differs from approved CPU input identity')


def run_stage(rows, infer, output, identity, warmups=3, backend_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'running', 'identity': identity, 'expected_questions': len(rows),
               'completed_questions': 0, 'warmup_count': 0, 'judge': 'not_evaluated',
               'provider_billing_controlled_by_runner': False}
    backend = None
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    try:
        with (output / 'warmups.jsonl').open('x') as wf, (output / 'predictions.jsonl').open('x') as pf:
            if backend_factory is not None:
                receipt['phase'] = 'model_loading'
                backend = backend_factory()
                infer = backend.infer
                identity['runtime'] = backend.runtime
            receipt['phase'] = 'warmup'
            for i in range(warmups):
                value = infer(rows[0])
                wf.write(json.dumps({'warmup': i, 'scored': False, 'result': value}, ensure_ascii=False) + '\n')
                wf.flush()
                receipt['warmup_count'] += 1
            receipt['phase'] = 'generation'
            for row in rows:
                receipt['failed_q_id'] = row['q_id']
                value = infer(row)
                if (not isinstance(value.get('response'), str)
                        or any(type(value.get(k)) is not int or value[k] < 0 for k in ['in_tok', 'out_tok'])
                        or type(value.get('truncated')) is not bool):
                    raise ValueError('Backend response/token/termination contract invalid')
                pred = {**value, 'q_id': row['q_id'], 'generation_status': 'completed'}
                pf.write(json.dumps(pred, ensure_ascii=False, allow_nan=False) + '\n')
                pf.flush()
                receipt['completed_questions'] += 1
            receipt.pop('failed_q_id', None)
            receipt['status'] = 'completed'
    except Exception as exc:
        receipt['status'] = 'technical_failure'
        receipt['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception as exc:
                receipt['status'] = 'technical_failure'
                receipt['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
        receipt['predictions_sha256'] = sha(output / 'predictions.jsonl') if (output / 'predictions.jsonl').exists() else None
        (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


class NativeBackend:
    def __init__(self, model, environment, root, prompt, checked):
        from model_adapters import HFBackend
        self.root, self.prompt = Path(root), prompt
        self.config = {**model, 'max_new_tokens': 512}
        self.base = HFBackend(self.config, environment, allow_download=False)
        self.runtime = self.base.runtime
        self.expected = {r['q_id']: r for r in checked['questions']}
        if hashlib.sha256(str(self.base.processor.chat_template).encode()).hexdigest() != checked['chat_template_sha256']:
            self.base.close()
            raise ValueError('Native chat template changed after CPU preflight')

    def infer(self, row):
        from PIL import Image
        from model_adapters import chat_kwargs
        torch, processor = self.base.torch, self.base.processor
        images = []
        def load(path):
            with Image.open(path) as im:
                im.load()
                image = im.convert('RGB')
            images.append(image)
            return image
        try:
            begin = time.perf_counter()
            messages = build_messages(row, self.root, load, self.prompt)
            kwargs = chat_kwargs(self.config)
            rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **kwargs)
            inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                        return_dict=True, return_tensors='pt', **kwargs)
            tokens = int(inputs['input_ids'].shape[-1])
            if tokens + 512 > self.config['context_limit']:
                raise ValueError('Context limit exceeded; no truncation or replacement')
            shapes = {k: list(v.shape) for k, v in inputs.items() if hasattr(v, 'shape')}
            validate_native_identity(self.expected[row['q_id']], hashlib.sha256(rendered.encode()).hexdigest(),
                    hashlib.sha256(json.dumps(inputs['input_ids'].tolist(), separators=(',', ':')).encode()).hexdigest(), shapes)
            inputs.pop('token_type_ids', None)
            inputs = inputs.to('cuda:0')
            for k, v in inputs.items():
                if torch.is_tensor(v) and v.is_floating_point():
                    inputs[k] = v.to(dtype=next(self.base.model.parameters()).dtype)
            torch.cuda.synchronize()
            preprocessed = time.perf_counter()
            with torch.inference_mode():
                result = self.base.model.generate(**inputs, max_new_tokens=512, do_sample=False, use_cache=True)
            torch.cuda.synchronize()
            tail = result[:, tokens:]
            text = processor.batch_decode(tail, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
            special = processor.batch_decode(tail, skip_special_tokens=False, clean_up_tokenization_spaces=False)[0]
            return {'response': text, 'raw_output_with_special_tokens': special,
                    'rendered_prompt': rendered, 'rendered_prompt_sha256': hashlib.sha256(rendered.encode()).hexdigest(),
                    'in_tok': tokens, 'out_tok': int(tail.shape[-1]), 'truncated': int(tail.shape[-1]) >= 512,
                    'image_count': len(images), 'tensor_shapes': shapes,
                    'preprocess_seconds_cpu_and_transfer': preprocessed - begin,
                    'generate_seconds': time.perf_counter() - preprocessed}
        finally:
            for image in images:
                image.close()

    def close(self):
        self.base.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--prompt', type=Path, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--cpu-receipt', type=Path, required=True)
    parser.add_argument('--packaging-receipt', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    manifest, rows, identity = validate_package(args.package, args.root)
    cpu = read_json(args.cpu_receipt)
    checked = next(r for r in cpu['native_checks'] if r['model'] == args.model)
    if (checked['status'] != 'cpu_native_preprocessing_passed' or len(rows) != 8
            or manifest['qids'] != [r['q_id'] for r in checked['questions']]):
        raise ValueError('Only the CPU-checked eight technical-dev qids are accepted')
    package = read_json(args.packaging_receipt)['cohorts']
    expected = next(c for c in package if c['cohort'] == 'technical_dev')
    if (identity['manifest_sha256'] != expected['manifest_sha256']
            or identity['generation_inputs_sha256'] != expected['files_sha256']['generation_inputs']
            or sha(args.prompt) != checked['system_prompt_sha256']):
        raise ValueError('Input package/prompt changed after preflight')
    registry = validate_approved_registry(args.registry, cpu['model_registry_sha256'])
    config = registry['models'][args.model]
    if (config['revision'] != checked['revision'] or config['dtype'] != 'bfloat16'
            or config['thinking'] is not False or config['quantization'] != 'none'
            or config['seed'] != 42):
        raise ValueError('Model revision changed after CPU preflight')
    if sha(Path(__file__).with_name('model_adapters.py')) != cpu['model_adapters_sha256']:
        raise ValueError('Frozen CUDA adapter changed after CPU preflight')
    identity.update(model=args.model, model_revision=config['revision'], registry_sha256=sha(args.registry),
                    prompt_sha256=sha(args.prompt), max_new_tokens=512,
                    model_adapters_sha256=sha(Path(__file__).with_name('model_adapters.py')))
    if not args.generate:
        print(json.dumps({'status': 'validated_only_no_model_loaded', 'questions': len(rows), 'identity': identity}))
        return
    if args.output is None or args.output.exists():
        raise ValueError('Fresh --output directory required before loading any weights')
    receipt = run_stage(rows, None, args.output, identity, backend_factory=lambda: NativeBackend(
            config, registry['environments'][config['environment']], args.root, args.prompt.read_text(), checked))
    print(json.dumps({'status': receipt['status'], 'completed_questions': receipt['completed_questions']}))
    if receipt['status'] != 'completed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
