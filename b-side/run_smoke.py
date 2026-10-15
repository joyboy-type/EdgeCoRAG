"""Two-fixture offline input construction and synthetic scoring; no model loading."""
import argparse
import hashlib
import json
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROTOCOL = 'official_loader_smoke_v1'
TEMPLATE_VERSION = 'shared_visual_mcq_v1'
REVISION = '43620fde4044bb150e158c67ad7af6b6b11e1da2'
SCORER_SHA = '93c6164b4d164eb3bdc52227003067c546656f9a7aef2e608b22a60dbe030159'
TEMPLATE = json.loads((ROOT/'configs/shared_visual_mcq_v1.json').read_text(encoding='utf-8'))['text']

def require(condition, message):
    if not condition:
        raise ValueError(message)

def load(p):
    return json.loads(p.read_text(encoding='utf-8'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def no_answers(value):
    if isinstance(value, dict):
        require(not set(value).intersection({'answer','answer_choice','gt_choice','correct','relevance','is_relevant'}), 'Answer/relevance key in generation input')
        for x in value.values(): no_answers(x)
    elif isinstance(value, list):
        for x in value: no_answers(x)

def decode(p, expected):
    try:
        from PIL import Image
    except ImportError:
        require(sys.platform == 'darwin' and shutil.which('sips'),
                'Image decoding needs Pillow or macOS sips. No packages were installed. Stop and report this error.')
        with tempfile.TemporaryDirectory(prefix='edgecorag_decode_') as temp:
            converted = Path(temp) / 'decoded.png'
            result = subprocess.run(['sips','-s','format','png',str(p),'--out',str(converted)], capture_output=True, text=True, encoding='utf-8')
            require(result.returncode == 0 and converted.is_file(), f'sips decode failed: {p}')
            info = subprocess.run(['sips','-g','pixelWidth','-g','pixelHeight',str(converted)], capture_output=True, text=True, encoding='utf-8', check=True).stdout
            width = re.search(r'pixelWidth:\s*(\d+)',info)
            height = re.search(r'pixelHeight:\s*(\d+)',info)
            require(width and height and [int(width[1]),int(height[1])] == expected, f'sips dimension mismatch: {p}')
        return 'macOS_sips_png_decode'
    with Image.open(p) as im:
        im.load()
        require(list(im.size) == expected, f'Dimension mismatch: {p}')
        im.convert('RGB').load()
    return 'Pillow_decode_RGB'

def index_by_qid(rows):
    require(isinstance(rows,list) and [r['qid'] for r in rows] == ['0','43'], 'Expected exactly qids 0 and 43 in original order')
    return {r['qid']:r for r in rows}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample-root', type=Path, required=True)
    parser.add_argument('--scorer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, scorer, out = args.sample_root.resolve(), args.scorer.resolve(), args.output.resolve()
    require(not out.exists(), 'Output directory already exists. Choose a new directory.')
    require(out != base and base not in out.parents, 'Keep outputs outside the original sample directory.')
    require(sha(scorer) == SCORER_SHA, 'Existing scorer SHA-256 differs; do not replace it, report the mismatch.')
    # Bind scripts and the shared prompt before reading or scoring any answers.
    package = load(ROOT/'package_hashes.json')
    for name, expected in package['sha256'].items():
        require(sha(ROOT/name) == expected, f'Package file hash mismatch: {name}')
    fixture = load(base/'audit/sample_ids.json')
    require(fixture['revision'] == REVISION and fixture['qids'] == ['0','43'], 'Wrong sample version or ids')
    s0 = index_by_qid(load(base/'generation/s0_inputs.json'))
    candidates = index_by_qid(load(base/'generation/retrieved_candidates.json'))
    gt = index_by_qid(load(base/'scoring/gt_images.json'))
    assets = load(base/'audit/assets.json')
    by_position = {a['position_key']:a for a in assets}
    require(len(by_position) == len(assets), 'Duplicate asset position keys')
    provenance = []
    decode_log = {}
    manifests = {}
    for condition in ['S0','S1','S2']:
        rows = []
        for qid in ['0','43']:
            original = s0[qid]
            require(original['condition'] == 'S0' and original['evidence'] == [], 'Invalid original S0')
            require(set(original['choices']) == set('ABCD'), 'Invalid choices')
            require(candidates[qid]['source'] == 'official_published_retrieved_images_not_A', 'Unexpected candidate source')
            pool = [] if condition == 'S0' else (candidates[qid]['ordered_candidates'] if condition == 'S1' else gt[qid]['ordered_gt_images'])
            expected_pool = 0 if condition == 'S0' else (5 if condition == 'S1' or qid == '0' else 1)
            require(len(pool) == expected_pool, 'Unexpected pool size for this two-fixture smoke protocol')
            count = 0 if condition == 'S0' else (1 if qid == '43' else 5)
            require(len(pool) >= count, 'Insufficient evidence; no padding permitted')
            evidence = pool[:count]
            refs = [original['query_image']] + evidence
            expected_field = 'retrieved_images' if condition == 'S1' else 'gt_images'
            for i, ref in enumerate(refs):
                require(ref['position_key'] in by_position, 'Unknown image reference')
                a = by_position[ref['position_key']]
                field = 'image' if i == 0 else expected_field
                require(a['qid'] == qid and a['field'] == field and a['index'] == max(0,i-1), 'Image order/field mismatch')
                require(ref['path'] == a['file'] and ref['sha256'] == a['sha256'], 'Asset mapping mismatch')
                image_path = (base/ref['path']).resolve()
                require(base in image_path.parents, 'Image path escapes sample directory')
                require(sha(image_path) == ref['sha256'], 'Image SHA-256 mismatch')
                if ref['sha256'] not in decode_log:
                    decode_log[ref['sha256']] = decode(image_path,a['size'])
            text = TEMPLATE.format(question=original['question'], **original['choices'])
            # This is an abstract multimodal request, not a vendor-specific API payload.
            request = {'messages':[{'role':'user', 'content':[
                *[{'type':'image','image_index':i} for i in range(len(refs))], {'type':'text','text':text}]}]}
            row = {**original, 'evidence':evidence, 'condition':condition, 'protocol_version':PROTOCOL,
                   'template_version':TEMPLATE_VERSION, 'model_request':request,
                   'image_order':[{'image_index':i, **ref} for i,ref in enumerate(refs)]}
            no_answers(row)
            rows.append(row)
            provenance.append({'condition':condition,'qid':qid,'scenario':'Scope' if qid == '0' else 'Incomplete',
                               'source':{'S0':'none','S1':'official_clip_candidates','S2':'official_gt_images'}[condition],
                               'evidence_count':count,'total_images':len(refs),'protocol_version':PROTOCOL,
                               'model_boundary':'Only model_request plus resolved image bytes, never this provenance or file/position names, goes to the model.'})
        manifests[condition] = rows
    out.mkdir(parents=True)
    write(out/'prompt_template.json', {'version':TEMPLATE_VERSION,'text':TEMPLATE,'image_binding':'image_index resolves image_order against --sample-root; query image always index 0; no image bytes embedded in text', 'model_boundary':'No condition, source, position_key, path or scoring metadata is included in model_request.'})
    write(out/'selection_provenance.json', {'protocol_version':PROTOCOL,'formal_experiment_protocol':False,
          'fixture_scope':'two existing samples only', 'top3_and_A_evidence':'pending', 'rows':provenance})
    summary = []
    for condition, rows in manifests.items():
        manifest = out/f'inputs/{condition}.json'
        write(manifest, rows)
        run_dir = out/'synthetic'/condition
        run_dir.mkdir(parents=True)
        pred = run_dir/'predictions.synthetic.jsonl'
        generation = subprocess.run([sys.executable,'-B',str(ROOT/'synthetic_generate.py'),'--inputs',str(manifest),'--output',str(pred)],capture_output=True,text=True,encoding='utf-8',check=True)
        # Independent scorer is unchanged. Only this subprocess is given the answer file.
        score = run_dir/'score.synthetic.json'
        scoring = subprocess.run([sys.executable,'-B',str(scorer),'--answers',str(base/'scoring/answers.json'),
                                  '--predictions',str(pred),'--output',str(score)],capture_output=True,text=True,encoding='utf-8',check=True)
        result = load(score)
        require(result['parser_version'] == 'strict_choice_v1' and [r['qid'] for r in result['per_question']] == ['0','43'], 'Scorer output mismatch')
        result.update({'synthetic':True,'generator':'fixed_A_v1','condition':condition,'protocol_version':PROTOCOL,
                       'warning':'PIPELINE SMOKE ONLY; not model performance or evidence effectiveness.'})
        write(score,result)
        write(run_dir/'execution.json', {'synthetic':True,'generation_stdout':generation.stdout,'scoring_stdout':scoring.stdout})
        summary.append({'condition':condition, 'synthetic':True, **result['overall']})
        print(f"{condition}: qids=0,43; evidence={','.join(str(len(r['evidence'])) for r in rows)}; SYNTHETIC accuracy={result['overall']['accuracy_percent']:.2f}%; coverage={result['overall']['coverage_percent']:.2f}%")
    hashes = {str(p.relative_to(out)).replace('\\','/'):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'run_evidence.json', {'synthetic':True,'environment':platform.platform(),'python':platform.python_version(),
          'dataset_revision':REVISION,'protocol_version':PROTOCOL,'template_version':TEMPLATE_VERSION,
          'scorer_sha256':sha(scorer),'sample_root':str(base),'scorer':str(scorer),
          'input_source_hashes':{name:sha(base/name) for name in ['generation/s0_inputs.json','generation/retrieved_candidates.json','scoring/gt_images.json','audit/assets.json','audit/sample_ids.json','scoring/answers.json']},
          'unique_selected_image_contents_decoded':len(decode_log),'decoder_by_sha256':decode_log,
          'summary':summary,'output_sha256':hashes,'model_loaded':False})
    print('PASS: two-fixture S0/S1/S2 synthetic pipeline; no model loaded.')
    print('Output:',out)

if __name__ == '__main__':
    # No network is needed by this process; the child scripts have no networking code.
    def deny(*args, **kwargs): raise RuntimeError('Offline smoke: network forbidden')
    socket.socket = deny
    main()
