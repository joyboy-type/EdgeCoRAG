"""Bounded synthetic checks; no model, benchmark answers or network used."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from score_minimal import evaluate, parse_choice

root = Path(__file__).resolve().parent
def prediction(qid, raw, error=None):
    return {'qid':qid, 'raw_output':raw, 'generation_error':error}

answers = [{'qid':str(i),'answer_choice':'A','scenario':s} for i,s in enumerate(['Scope','Scope','Obstruction','Obstruction','Incomplete','Incomplete','Scope','Scope'])]
predictions = [prediction('0',' A '), prediction('1','B'), prediction('2',''),
               prediction('3','A or B'), prediction('4','（A）'),
               prediction('5','A','Synthetic runtime failure'), prediction('6','(A)')]
result = evaluate(answers, predictions)
assert result['overall']['correct'] == 3 and result['overall']['total'] == 8
assert result['overall']['accuracy_percent'] == 37.5
assert result['overall']['coverage_percent'] == 87.5
assert result['overall']['status_counts'] == {'ok':4,'empty_output':1,'parse_failure':1,'generation_error':1,'missing_prediction':1}
assert set(result['scenarios']) == {'Scope','Obstruction','Incomplete'}
assert result['scenarios']['Obstruction']['total'] == 2
assert result['scenarios']['Obstruction']['correct'] == 0
assert result['scenarios']['Incomplete']['accuracy_percent'] == 50
for text in ['a','The answer is A.','(A）','A B','AA','[A]']:
    assert parse_choice(text) == (None, 'parse_failure'), text
for text in ['A',' (A) ','（A）']:
    assert parse_choice(text) == ('A','ok'), text
assert evaluate(answers, [])['overall']['status_counts']['missing_prediction'] == 8
for extra, label in [(prediction('0','A'),'Duplicate'),(prediction('unknown','A'),'Unknown')]:
    try:
        evaluate(answers, predictions+[extra])
        raise AssertionError('Expected error')
    except ValueError as exc:
        assert label in str(exc)

# Verify the actual CLI writes all results and rejects invalid ids without a score file.
with tempfile.TemporaryDirectory(prefix='edgecorag_score_check_') as temp:
    folder = Path(temp)
    a, p, o = [folder / n for n in ['answers.json','predictions.jsonl','result.json']]
    a.write_text(json.dumps(answers), encoding='utf-8')
    p.write_text(''.join(json.dumps(x)+'\n' for x in predictions), encoding='utf-8')
    command = [sys.executable,'-B',str(root/'score_minimal.py'),'--answers',str(a),'--predictions',str(p),'--output',str(o)]
    run = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    assert run.returncode == 0, run.stderr
    saved = json.loads(o.read_text(encoding='utf-8'))
    assert saved['overall'] == result['overall'] and saved['scenarios'] == result['scenarios']
    assert len(saved['per_question']) == 8
    for index, extra in enumerate([prediction('0','A'),prediction('unknown','A')]):
        p.write_text(''.join(json.dumps(x)+'\n' for x in predictions+[extra]), encoding='utf-8')
        bad = folder / f'rejected_{index}.json'
        run = subprocess.run(command[:-1]+[str(bad)], capture_output=True, text=True, encoding='utf-8')
        assert run.returncode == 2 and not bad.exists()
print('PASS: correct, wrong, empty, ambiguous, missing, generation failure, duplicate, unknown, strict parsing and saved overall/all scenarios.')
print('Synthetic fixture: 3/8 correct (37.50%); coverage 87.50%.')
