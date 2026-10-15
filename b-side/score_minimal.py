"""Offline MRAG-Bench B-side minimal scorer. Python standard library only."""
import argparse
import json
from collections import Counter
from pathlib import Path

PARSER_VERSION = 'strict_choice_v1'
CHOICES = set('ABCD')

def parse_choice(raw):
    text = raw.strip()
    if not text:
        return None, 'empty_output'
    if text in CHOICES:
        return text, 'ok'
    if len(text) == 3 and (text[0], text[2]) in {('(', ')'), ('（', '）')} and text[1] in CHOICES:
        return text[1], 'ok'
    return None, 'parse_failure'

def evaluate(answers, predictions):
    if not isinstance(answers, list) or not answers:
        raise ValueError('Answer file must be a nonempty JSON list defining the fixed question set.')
    gold = {}
    for item in answers:
        if not isinstance(item, dict):
            raise ValueError('Each answer must be an object.')
        qid = item.get('qid')
        if not isinstance(qid, str) or not qid:
            raise ValueError('Answer qid must be a nonempty string.')
        if qid in gold:
            raise ValueError(f'Duplicate answer qid: {qid}')
        if not isinstance(item.get('answer_choice'), str) or item['answer_choice'] not in CHOICES:
            raise ValueError(f'Invalid answer_choice for {qid}')
        if not isinstance(item.get('scenario'), str) or not item['scenario']:
            raise ValueError(f'Invalid scenario for {qid}')
        gold[qid] = item
    received = {}
    for item in predictions:
        if not isinstance(item, dict):
            raise ValueError('Each prediction must be an object.')
        qid = item.get('qid')
        if not isinstance(qid, str) or not qid:
            raise ValueError('Prediction qid must be a nonempty string.')
        if qid not in gold:
            raise ValueError(f'Unknown prediction qid: {qid}')
        if qid in received:
            raise ValueError(f'Duplicate prediction qid: {qid}')
        if 'raw_output' not in item or not isinstance(item['raw_output'], str):
            raise ValueError(f'raw_output must be a string for {qid}; use an empty string on generation failure.')
        if 'generation_error' not in item or not (item['generation_error'] is None or isinstance(item['generation_error'], str) and bool(item['generation_error'].strip())):
            raise ValueError(f'generation_error must be null or a nonempty string for {qid}')
        received[qid] = item
    rows = []
    for qid, answer in gold.items():
        prediction = received.get(qid)
        choice = None
        raw = None if prediction is None else prediction['raw_output']
        error = None if prediction is None else prediction['generation_error']
        if prediction is None:
            status = 'missing_prediction'
        elif error is not None:
            status = 'generation_error'
        else:
            choice, status = parse_choice(raw)
        rows.append({'qid':qid, 'scenario':answer['scenario'], 'raw_output':raw,
                     'parsed_choice':choice, 'parse_status':status, 'parser_version':PARSER_VERSION,
                     'generation_error':error, 'correct':status == 'ok' and choice == answer['answer_choice']})
    def summarize(items):
        counts = Counter(r['parse_status'] for r in items)
        total = len(items)
        correct = sum(r['correct'] for r in items)
        present = total - counts['missing_prediction']
        return {'total':total, 'correct':correct, 'incorrect':total-correct,
                'accuracy_percent':100*correct/total, 'received':present,
                'coverage_percent':100*present/total, 'valid_parsed':counts['ok'],
                'valid_parse_rate_percent':100*counts['ok']/total,
                'status_counts':{s:counts[s] for s in ['ok','empty_output','parse_failure','generation_error','missing_prediction']}}
    return {'parser_version':PARSER_VERSION, 'denominator':'fixed_answer_file_question_set',
            'coverage_definition':'received records / fixed questions; includes recorded generation failures',
            'valid_parse_rate_definition':'successfully parsed records / fixed questions',
            'overall':summarize(rows),
            'scenarios':{s:summarize([r for r in rows if r['scenario']==s]) for s in sorted({r['scenario'] for r in rows})},
            'per_question':rows}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answers', required=True, type=Path)
    parser.add_argument('--predictions', required=True, type=Path, help='JSONL; one record per received prediction')
    parser.add_argument('--output', required=True, type=Path, help='New JSON file; refuses to overwrite existing files')
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Output already exists. Choose a new filename to avoid confusing old and new results.')
        answers = json.loads(args.answers.read_text(encoding='utf-8-sig'))
        lines = args.predictions.read_text(encoding='utf-8-sig').splitlines()
        predictions = [json.loads(line) for line in lines if line.strip()]
        result = evaluate(answers, predictions)
        result['input_files'] = {'answers':str(args.answers), 'predictions':str(args.predictions)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        overall = result['overall']
        print(f"OK: {overall['correct']}/{overall['total']}; accuracy={overall['accuracy_percent']:.2f}%; coverage={overall['coverage_percent']:.2f}%")
        print(f'Saved: {args.output}')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'ERROR: {exc}\n')

if __name__ == '__main__':
    main()
