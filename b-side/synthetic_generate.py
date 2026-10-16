"""Fixed synthetic outputs. Reads only an input manifest, never answer files."""
import argparse
import json
from pathlib import Path

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    rows = json.loads(args.inputs.read_text(encoding='utf-8'))
    if [r['qid'] for r in rows] != ['0', '43']:
        raise ValueError('Expected exactly the two fixture ids in order.')
    with args.output.open('x', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps({'qid':row['qid'], 'raw_output':'A', 'generation_error':None,
                                'synthetic':True, 'generator':'fixed_A_v1', 'condition':row['condition']})+'\n')
    print(f'SYNTHETIC fixed_A_v1: wrote {len(rows)} records')

if __name__ == '__main__':
    main()
