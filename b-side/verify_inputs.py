"""Offline, standard-library-only verification of the unpacked sample package."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sample-root', type=Path, required=True)
args = parser.parse_args()
root = args.sample_root.resolve()
inputs = json.loads((root / 'generation/s0_inputs.json').read_text(encoding='utf-8'))
assets = json.loads((root / 'audit/assets.json').read_text(encoding='utf-8'))
expected = json.loads((root / 'audit/sample_ids.json').read_text(encoding='utf-8'))['qids']
ids = [x['qid'] for x in inputs]
assert len(ids) == len(set(ids)) and set(ids) == set(expected)
for item in inputs:
    assert set(item) == {'qid','question','choices','query_image','evidence','condition'}
    assert set(item['choices']) == set('ABCD')
    assert isinstance(item['qid'], str) and item['condition'] == 'S0' and not item['evidence']
for asset in assets:
    path = (root / asset['file']).resolve()
    assert path.is_relative_to(root.resolve())
    data = path.read_bytes()
    assert len(data) == asset['bytes']
    assert hashlib.sha256(data).hexdigest() == asset['sha256']
print(f'PASS: {len(ids)} S0 inputs; {len(assets)} image positions; hashes match. No model or network used.')
