"""Explicit development/evaluation stages; no model download or automatic stage promotion."""
import argparse,json,time
from pathlib import Path
import mmdocrag_generate as base
from mmdocrag_generate import sha,read_json,no_duplicates

def validate_package(package, root, split):
    package, root = Path(package), Path(root).resolve()
    manifest = read_json(package / 'manifest.json')
    rows = [json.loads(s, object_pairs_hook=no_duplicates)
            for s in (package / 'generation_inputs.jsonl').read_text().split('\n') if s.strip()]
    qids = manifest.get('qids')
    if (manifest.get('split') != split or split not in {'dev', 'evaluation'} or manifest.get('setting') != '15'
            or manifest.get('qid_type') != 'int' or not isinstance(qids, list) or not qids
            or any(type(q) is not int for q in qids) or len(set(qids)) != len(qids)):
        raise ValueError('Nonempty split-scoped 15-setting integer manifest required')
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


def validate_predecessor_manifest(package, packaged, count):
    package = Path(package)
    manifest = read_json(package/'manifest.json')
    if (sha(package/'manifest.json') != packaged['manifest_sha256']
            or sha(package/'generation_inputs.jsonl') != packaged['files_sha256']['generation_inputs']
            or len(manifest['qids']) != count or manifest['split'] != 'dev' or manifest['setting'] != '15'):
        raise ValueError('Wrong predecessor package identity or count')
    return manifest


def completed_stage(path, models, qids, expected, revisions=None):
    if (not isinstance(qids, list) or not qids
            or any(type(q) is not int for q in qids) or len(set(qids)) != len(qids)):
        raise ValueError('Predecessor requires unique integer question IDs')
    pins = {}
    for model in models:
        directory = Path(path) / model
        receipt = read_json(directory / 'receipt.json')
        identity = receipt.get('identity', {})
        if (receipt.get('status') != 'completed'
                or type(receipt.get('expected_questions')) is not int
                or type(receipt.get('completed_questions')) is not int
                or not isinstance(identity.get('qids'), list)
                or any(type(q) is not int for q in identity['qids'])
                or receipt.get('expected_questions') != len(qids)
                or receipt.get('completed_questions') != len(qids)
                or identity.get('model') != model or identity.get('qids') != qids
                or (revisions is not None and identity.get('model_revision') != revisions[model])
                or any(identity.get(k) != v for k, v in expected.items())):
            raise ValueError('Predecessor identity/completion mismatch: ' + model)
        predictions = directory / 'predictions.jsonl'
        if sha(predictions) != receipt.get('predictions_sha256'):
            raise ValueError('Predecessor predictions changed: ' + model)
        rows = [json.loads(s, object_pairs_hook=no_duplicates) for s in predictions.read_text().splitlines() if s.strip()]
        if ([r.get('q_id') for r in rows] != qids or any(
                type(r.get('q_id')) is not int or r.get('generation_status') != 'completed'
                or not isinstance(r.get('response'), str)
                or (r.get('generation_error') is not None and r['generation_error'] != '') for r in rows)):
            raise ValueError('Incomplete predecessor outputs: ' + model)
        pins[model] = {'receipt_sha256': sha(directory / 'receipt.json'), 'predictions_sha256': sha(predictions)}
    return pins


def validate_freeze(freeze, pins):
    if (freeze.get('reviewed') is not True or freeze.get('accept_partial_truncation') is not True
            or freeze.get('pins') != pins):
        raise ValueError('Stage review/freeze does not bind exact inputs, code and predecessors')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['root','registry','cpu-receipt','packaging-receipt','prompt','plan']:
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--cohort',choices=['development','evaluation_pilot'],required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--output',type=Path)
    p.add_argument('--generate',action='store_true')
    a = p.parse_args()
    plan = read_json(a.plan)
    cohort = a.cohort
    package = a.root/'work/mmdocrag-images/inputs'/cohort
    split,n = ('dev',32) if cohort == 'development' else ('evaluation',200)
    manifest,rows,identity = validate_package(package,a.root,split)
    cpu = read_json(a.cpu_receipt)
    checked = next(c for c in cpu['native_checks'] if c['model'] == a.model)
    packaged = next(c for c in read_json(a.packaging_receipt)['cohorts'] if c['cohort'] == cohort)
    registry = base.validate_approved_registry(a.registry,cpu['model_registry_sha256'])
    config = registry['models'][a.model]
    if (len(rows) != n or checked['status'] != 'cpu_native_preprocessing_passed'
            or manifest['qids'] != [r['q_id'] for r in checked['questions']]
            or manifest['dataset_revision'] != plan['dataset_revision']
            or identity['manifest_sha256'] != packaged['manifest_sha256']
            or identity['generation_inputs_sha256'] != packaged['files_sha256']['generation_inputs']
            or sha(a.prompt) != checked['system_prompt_sha256']
            or config['revision'] != checked['revision']
            or sha(Path(base.__file__).with_name('model_adapters.py')) != cpu['model_adapters_sha256']):
        raise ValueError('Stage/package/native/model identity mismatch')
    if (plan['cohort'] != cohort or plan['campaign_sha256'] != sha(__file__)
            or plan['base_sha256'] != sha(base.__file__)
            or plan['cpu_sha256'] != sha(a.cpu_receipt)
            or plan['packaging_sha256'] != sha(a.packaging_receipt)
            or plan['models'] != list(registry['models'])):
        raise ValueError('Plan/code/native receipt identity drift')
    identity.update(model=a.model,model_revision=config['revision'],registry_sha256=sha(a.registry),
            prompt_sha256=sha(a.prompt),max_new_tokens=512,model_adapters_sha256=cpu['model_adapters_sha256'],
            campaign_plan_sha256=sha(a.plan),cohort=cohort)
    if not a.generate:
        print(json.dumps({'status':'validated_only_no_model_loaded','questions':n,'identity':identity}))
        return
    if a.output is None or a.output.exists():
        raise ValueError('Fresh output directory required')
    predecessor = 'technical_dev_attempt2' if cohort == 'development' else 'development'
    if plan['prior_stage'] != predecessor:
        raise ValueError('Incorrect predecessor stage')
    prior_cohort = 'technical_dev' if cohort == 'development' else 'development'
    prior_packaged = next(c for c in read_json(a.packaging_receipt)['cohorts'] if c['cohort'] == prior_cohort)
    prior_manifest = validate_predecessor_manifest(a.root/'work/mmdocrag-images/inputs'/prior_cohort,
            prior_packaged,8 if cohort == 'development' else 32)
    prior = completed_stage(a.root/'results'/predecessor,plan['models'],prior_manifest['qids'],{
        **{k:identity[k] for k in ['registry_sha256','prompt_sha256','dataset_revision','max_new_tokens','model_adapters_sha256']},
        'manifest_sha256':prior_packaged['manifest_sha256'],
        'generation_inputs_sha256':prior_packaged['files_sha256']['generation_inputs'],
        'split':'dev','setting':'15',
        'runner_sha256':sha(base.__file__) if cohort == 'development' else sha(__file__)},
        revisions={key:registry['models'][key]['revision'] for key in plan['models']})
    pins = {'predecessors':prior,'campaign_sha256':sha(__file__),'base_sha256':sha(base.__file__),
            'cpu_sha256':sha(a.cpu_receipt),'packaging_sha256':sha(a.packaging_receipt),
            'manifest_sha256':identity['manifest_sha256'],'generation_inputs_sha256':identity['generation_inputs_sha256'],
            'registry_sha256':identity['registry_sha256'],'prompt_sha256':identity['prompt_sha256']}
    validate_freeze(plan['freeze'],pins)
    if time.time() >= plan['deadline_unix'] - 600:
        raise ValueError('Insufficient remaining time before billing deadline')
    receipt = base.run_stage(rows,None,a.output,identity,warmups=0,backend_factory=lambda:base.NativeBackend(
            config,registry['environments'][config['environment']],a.root,a.prompt.read_text(),checked))
    print(json.dumps({'status':receipt['status'],'completed_questions':receipt['completed_questions']}))
    if receipt['status'] != 'completed':
        raise SystemExit(2)

if __name__ == '__main__':
    main()
