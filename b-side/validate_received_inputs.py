"""Read actual external bundle(s) with the existing runner contract; no backend.

This is input acceptance, never inference or accuracy. Does not read gold files.
Outputs a new external receipt, and retains any fixed-question input failures.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from batch_inputs import read, sha, load_task, external
from run_candidate import build_messages


def verify(data_root, bundle_names):
    reports = []
    for name in bundle_names:
        path = external(data_root, name); b = read(path)
        for condition in b['conditions']:
            # Receipt uses the read-only mechanism stage for every split; it is
            # not a development experiment or approval for formal quality runs.
            task = {'bundle': name, 'bundle_sha256': sha(path), 'stage': 'mechanism_test',
                    'condition': condition, **{k: b[k] for k in ['split', 'protocol_version', 'evidence_version']},
                    'split_manifest_sha256': b['split_manifest']['sha256']}
            _, _, media, rows = load_task(task, data_root, decode=True)
            failures = []
            for row in rows:
                if row['input_status'] != 'ok':
                    failures.append({'qid': row['qid'], 'status': row['input_status'], 'error': row.get('input_error')})
                    continue
                message = build_messages(row, media, lambda p: str(p))
                images = [p['image'] for p in message[0]['content'] if p['type'] == 'image']
                if images != [str((media/r['path']).resolve()) for r in row['image_order']]:
                    raise ValueError('Shared runner image order mismatch')
            reports.append({'bundle': name, 'bundle_sha256': sha(path), 'condition': condition,
                'fixed_denominator': len(rows), 'input_ok': len(rows)-len(failures), 'failures': failures,
                'image_counts': dict(Counter(len(r['image_order']) for r in rows)),
                'qid_order': [r['qid'] for r in rows], 'formal_split_approved': b['formal_split_approved']})
    return {'status': 'validated_inputs' if not any(r['failures'] for r in reports) else 'input_failures_retained',
            'backend': 'validate', 'conditions': reports, 'GPU_verified': False,
            'inference_or_accuracy_generated': False, 'gold_read_by_this_validator': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--bundle', nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.resolve() == Path(__file__).parent or Path(__file__).parent in a.output.resolve().parents:
        raise ValueError('Keep actual receipts external to code')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x', encoding='utf-8') as out:
        try:
            result = verify(a.data_root.resolve(), a.bundle)
        except Exception as e:
            out.write(json.dumps({'status': 'validation_failed', 'error': type(e).__name__+': '+str(e)})+'\n')
            raise
        out.write(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(result['status'])
    raise SystemExit(0 if result['status'] == 'validated_inputs' else 2)
