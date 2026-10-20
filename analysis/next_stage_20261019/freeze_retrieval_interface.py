"""Freeze the declared retrieval interface from local pinned files; no model load.

Hash actual cached model bytes, processor configs, production sources and template.
The frozen device contract remains pending live GPU verification. No gold/labels,
cache paths, source-plan contents, credentials, or authorization enter the output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'a-side/scripts'))
from evidence_selection import no_labels


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def bytes_sha(data):return hashlib.sha256(data).hexdigest()
def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def reject_paths(value):
    if isinstance(value,dict):
        for key,child in value.items():reject_paths(key);reject_paths(child)
    elif isinstance(value,list):
        for child in value:reject_paths(child)
    elif isinstance(value,str) and (value.startswith(('/', '~','file:')) or ':\\' in value):
        raise ValueError('Absolute paths forbidden in interface freeze')


def freeze(spec,model_dir,repo=REPO):
    repo=Path(repo).resolve();model_dir=Path(model_dir).resolve()
    no_labels(spec)
    if (not isinstance(spec.get('revision'),str) or len(spec['revision'])!=40
            or spec.get('dimension')!=768 or not spec.get('required_files')):
        raise ValueError('Pinned 768-dimension retrieval model required')
    model_files={}
    for row in spec['required_files']:
        name=row['path'];path=(model_dir/name).resolve()
        if not path.is_relative_to(model_dir) or path.stat().st_size!=row['bytes']:
            raise ValueError('Pinned model file identity mismatch')
        digest=file_sha(path)
        if row['algorithm']=='sha256':observed=digest
        elif row['algorithm']=='git_blob_sha1':
            observed=hashlib.sha1(b'blob '+str(path.stat().st_size).encode()+b'\0'+path.read_bytes()).hexdigest()
        else:raise ValueError('Unsupported model file digest algorithm')
        if observed!=row['digest']:raise ValueError('Pinned model file hash mismatch')
        if name in model_files:raise ValueError('Duplicate model file')
        model_files[name]=dict(sha256=digest,bytes=path.stat().st_size,
                              declared_algorithm=row['algorithm'],declared_digest=row['digest'])
    parameters={}
    for name in ('preprocessor_config.json','processor_config.json','sentence_bert_config.json','config_sentence_transformers.json'):
        path=model_dir/name
        if path.exists():parameters[name]=dict(value=json.loads(path.read_text()),sha256=file_sha(path))
    template_path=repo/'b-side/configs/shared_visual_mcq_v1.json'
    template=json.loads(template_path.read_text())
    registry=json.loads((repo/'b-side/configs/model_registry.json').read_text())
    generation=registry['models']['gemma4_e2b']
    interface=dict(
        model=dict(model_id=spec['model_id'],revision=spec['revision'],dimension=768,
                   model_files=model_files),
        preprocessing=dict(decode='PIL.Image.open',color='convert(RGB)',resize='pinned processor defaults',
            processor_parameters=parameters,trust_remote_code=False,local_files_only=True,
            config_kwargs=dict(audio_config=None)),
        device='cuda',model_dtype='bfloat16',ranking_dtype='float32',
        encode_kwargs=dict(normalize_embeddings=False,convert_to_numpy=True,show_progress_bar=False),
        batch_size=dict(online=1,offline=4),
        normalization=dict(dtype='float32',operation='truncate first dimension components then L2 per row',
                           finite_nonzero_required=True),
        ranking=dict(metric='cosine dot product after normalization',stable_sort='numpy.lexsort((ids, -similarity))',
                     tie_break='corpus id ascending',no_self='remove image:query_image.sha256 before truncation; replenish to ten',topk=10),
        selection=dict(k=3,seed=20261017,cosine='first three',
            random='SHA256 of JSON [seed,qid,candidate_id]; take three smallest digest; restore pool order',
            utility='descending raw first-step True logit; pool index breaks ties; restore pool order',
            utility_model_id=generation['model_id'],utility_revision=generation['revision']),
        generation_template=dict(version=template['version'],sha256=file_sha(template_path)),
        verification_status='declared_local_interface; real-device thread values and vector distances await approved S0')
    names=['b-side/e2e_smoke.py','b-side/e2e_cost.py','b-side/e2e_lease.py','b-side/boot_watchdog.py',
        'b-side/session_runner.py','b-side/model_adapters.py','a-side/scripts/independent_retrieval.py',
        'a-side/scripts/evidence_selection.py','analysis/next_stage_20261019/build_dimension_inputs.py',
        'analysis/next_stage_20261019/freeze_retrieval_interface.py',
        'analysis/next_stage_20261019/analysis_paths.py',
        'analysis/next_stage_20261019/prepare_cost_experiment.py',
        'analysis/next_stage_20261019/build_run_bundle.py',
        'analysis/next_stage_20261019/materialize_lease.py',
        'analysis/next_stage_20261019/verify_local_preparation.py',
        'analysis/next_stage_20261019/audit_requirement_evidence.py',
        'analysis/next_stage_20261019/report_completion_counts.py','b-side/configs/model_registry.json',
        'b-side/configs/shared_visual_mcq_v1.json']
    sources={name:dict(sha256=file_sha(repo/name),bytes=(repo/name).stat().st_size) for name in names}
    # Top-level aliases make the key contract easy to inspect; interface binds all fields.
    result=dict(schema='retrieval_interface_freeze_v1',interface=interface,
        interface_sha256=bytes_sha(canonical(interface)),source_files=sources,
        source_files_sha256=bytes_sha(canonical(sources)),
        batch_size=interface['batch_size'],ranking=interface['ranking'],selection=interface['selection'])
    no_labels(result);reject_paths(result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True,help='private inference-only plan carrying retriever pins')
    parser.add_argument('--model-dir',type=Path,required=True)
    parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise ValueError('Preserve existing interface freeze')
    plan=json.loads(args.plan.read_text());no_labels(plan)
    result=freeze(plan['retriever'],args.model_dir,args.repo)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(interface_sha256=result['interface_sha256'],artifact_sha256=file_sha(args.out),
                         model_files=len(result['interface']['model']['model_files'])),indent=2))

if __name__=='__main__':main()
