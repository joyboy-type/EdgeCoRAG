"""Reproduce the local EdgeCoRAG readout; never invokes models, networks or servers."""
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

BACKUP = None  # Explicit local verified-backup root, provided by CLI.
OUT = Path(__file__).resolve().parent
MODELS = ['qwen3vl_4b', 'qwen3vl_8b', 'gemma4_e2b', 'gemma4_e4b', 'qwen35_4b']
LABELS = dict(zip(MODELS, ['Qwen3-VL 4B', 'Qwen3-VL 8B', 'Gemma4 E2B', 'Gemma4 E4B', 'Qwen3.5 4B']))
CONDITIONS = ['S0', 'S1', 'S2']
MATRIX_SHA = '630eee8d4032fa0aede73eef89612801ff521785e045bdfc0f14ffaea094c555'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_and_validate(backup=None):
    backup = BACKUP if backup is None else backup
    if backup is None: raise ValueError("Set an explicit verified-backup root")
    code = backup / 'runtime-v1.10.1/b-side'
    data = backup / 'bound-v1.10.0'
    run = backup / 'runs/v1.10.1'
    assert sha(data / 'bound_matrix.json') == MATRIX_SHA
    identity = read(run / 'batch_identity.json')
    assert all(sha(code / name) == digest for name, digest in identity['code'].items())
    scorer = {'__name__': 'offline_scorer'}
    exec(compile((code / 'score_minimal.py').read_text(), str(code / 'score_minimal.py'), 'exec'), scorer)
    matrix = read(data / 'bound_matrix.json')
    batch = read(run / 'batch_state.json')
    assert batch['status'] == 'requested_phases_completed' and batch['through_phase'] == 'performance'
    assert len(batch['completed_task_ids']) == len(set(batch['completed_task_ids'])) == 161
    tasks = []
    keys = set()
    warmup_count = 0
    for task in matrix['task_items']:
        folder = run / task['task_id']
        bundle_path = data / task['bundle']
        assert sha(bundle_path) == task['bundle_sha256']
        bundle = read(bundle_path)
        base = bundle_path.parent
        for reference in (bundle['answers'], bundle['conditions'][task['condition']], bundle['split_manifest']):
            assert sha(base / reference['path']) == reference['sha256']
        answers = read(base / bundle['answers']['path'])
        inputs = read(base / bundle['conditions'][task['condition']]['path'])
        predictions = jsonl(folder / 'predictions.jsonl')
        attempts = jsonl(folder / 'attempts.jsonl')
        state = read(folder / 'state.json')
        task_identity = read(folder / 'identity.json')
        assert state['exit_code'] == 0 and not state['failed_qids'] and not state['missing_qids']
        assert len(predictions) == len(attempts) == len(answers) == len(inputs) == task['fixed_denominator'] == state['fixed_total'] == state['received_unique']
        assert predictions == attempts
        assert [p['qid'] for p in predictions] == bundle['qids'] == [a['qid'] for a in answers] == [i['qid'] for i in inputs]
        assert len({p['qid'] for p in predictions}) == len(predictions)
        assert not (folder / 'errors.jsonl').exists() or not (folder / 'errors.jsonl').read_text().strip()
        warmup = read(folder / 'warmup.json')
        assert warmup['not_scored'] is True and len(warmup['records']) == 3
        assert all(not x.get('generation_error') for x in warmup['records'])
        warmup_count += 3
        runtime = warmup['runtime']
        assert runtime['quantization'] == 'none' and runtime['actual_dtype'] == 'torch.bfloat16'
        assert runtime['matmul_allow_tf32'] is False and runtime['cudnn_allow_tf32'] is False
        for p, row in zip(predictions, inputs):
            key = tuple(p['row_key'])
            assert key not in keys
            keys.add(key)
            assert key == (run.name, task['task_id'], p['qid'], p['model_id'], p['model_revision'], task['condition'], task['protocol_version'], task['repeat_index'], task['evidence_version'])
            assert p['config_fingerprint'] == task_identity['config_fingerprint'] and p['attempt'] == 1
            assert p['model_revision'] == task['model_revision'] and p['actual_dtype'] == 'torch.bfloat16'
            assert p['synthetic'] is False and p['input_status'] == 'ok'
            assert not p['generation_error'] and not p.get('oom') and not p.get('final_extraction_error')
            assert p['input_image_count'] == 1 + len(row['evidence'])
            assert p['evidence_ids_order'] == [e.get('evidence_id', e['position_key']) for e in row['evidence']]
            assert p['raw_output'] == p['prediction_raw']
            assert (p['parsed_choice'], p['parse_status']) == scorer['parse_choice'](p['final_output'])
            assert 0 <= p['generated_tokens'] <= 64
            assert p['timing']['generate_seconds'] > 0 and p['timing']['end_to_end_seconds'] >= p['timing']['generate_seconds']
        score = None
        if task['stage'] != 'performance':
            score = read(folder / 'score.json')
            recomputed = scorer['evaluate'](answers, [{'qid': p['qid'], 'raw_output': p['final_output'], 'generation_error': p['generation_error']} for p in predictions])
            assert all(score[k] == recomputed[k] for k in ('parser_version', 'denominator', 'overall', 'scenarios', 'per_question'))
            assert score['format_failure_count'] == sum(p['parse_status'] != 'ok' for p in predictions)
        else:
            assert not (folder / 'score.json').exists()
        tasks.append({'task': task, 'score': score, 'predictions': predictions, 'runtime': runtime, 'bundle': bundle})
    counts = Counter()
    formats = Counter()
    for item in tasks:
        stage = item['task']['stage']
        counts[stage] += len(item['predictions'])
        formats[stage] += sum(p['parse_status'] != 'ok' for p in item['predictions'])
    assert len(keys) == 21927 and counts['quality'] == 17807 and counts['performance'] == 1550
    assert sum(formats.values()) == 132 and warmup_count == 483
    audit = {'status': 'PASS', 'tasks': 161, 'question_runs': 21927, 'rescored_tasks': 76,
             'question_runs_by_stage': dict(counts), 'format_failures_by_stage': dict(formats),
             'warmups_excluded': warmup_count, 'matrix_sha256': MATRIX_SHA,
             'backup_archive_sha256': '98bf99c45ecdd1a44029747885e9c3e49f860b95ae95079ea0c5c123b33ffc85',
             'no_inference_or_server_access': True}
    return tasks, audit


def approved_analysis_module():
    # This module imports the runner. The runner only defines functions; HF libraries are lazy-loaded.
    path = BACKUP / 'runtime-v1.10.1/b-side'
    sys.path.insert(0, str(path))
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('approved_analysis', path / 'analyze_batch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compute(tasks, resamples=2000, seed=42):
    analysis = approved_analysis_module()
    quality, scenarios, comparisons, subsets = [], [], [], []
    scores = {}
    for item in tasks:
        t, s = item['task'], item['score']
        if t['stage'] != 'quality':
            continue
        scores[t['model'], t['split'], t['condition']] = s
        o = s['overall']
        quality.append({'model_key': t['model'], 'model': LABELS[t['model']], 'split': t['split'], 'condition': t['condition'],
                        'n': o['total'], 'correct': o['correct'], 'accuracy': o['correct'] / o['total'],
                        'format_failures': s['format_failure_count'], 'valid_parse_rate': o['valid_parsed'] / o['total'],
                        'generation_errors': o['status_counts']['generation_error'], 'missing': o['status_counts']['missing_prediction']})
        for name, v in s['scenarios'].items():
            scenarios.append({'model_key': t['model'], 'model': LABELS[t['model']], 'split': t['split'], 'condition': t['condition'],
                              'scenario': name, 'n': v['total'], 'correct': v['correct'], 'accuracy': v['correct'] / v['total'],
                              'format_failures': v['status_counts']['parse_failure'] + v['status_counts']['empty_output']})
    for split in ('internal_holdout', 'frozen_test'):
        for model in MODELS:
            for left, right in [('S0', 'S1'), ('S1', 'S2'), ('S0', 'S2')]:
                a, b = scores[model, split, left], scores[model, split, right]
                paired = analysis.paired(a, b, repetitions=resamples, seed=seed)
                aa = {r['qid']: r for r in a['per_question']}
                bb = {r['qid']: r for r in b['per_question']}
                improvements = sum(not aa[q]['correct'] and bb[q]['correct'] for q in aa)
                regressions = sum(aa[q]['correct'] and not bb[q]['correct'] for q in aa)
                delta = paired['difference_right_minus_left']
                assert abs(delta - (improvements - regressions) / len(aa)) < 1e-12
                comparisons.append({'model_key': model, 'model': LABELS[model], 'split': split, 'comparison': right + ' − ' + left,
                                    'n': paired['n_questions'], 'delta_pp': 100 * delta,
                                    'ci_low_pp': 100 * paired['percentile_CI_95'][0], 'ci_high_pp': 100 * paired['percentile_CI_95'][1],
                                    'improvements': improvements, 'regressions': regressions, 'unchanged': len(aa) - improvements - regressions,
                                    'resamples': resamples, 'seed': seed, 'method': paired['method']})
            if model.startswith('gemma4'):
                result = analysis.paired_S1_S3_subset(scores[model, split, 'S1'], scores[model, split, 'S3-pure'], repetitions=resamples, seed=seed)
                subsets.append({'model_key': model, 'model': LABELS[model], 'split': split,
                                'parent_n': result['parent_denominator'], 'paired_n': result['paired_denominator'], 'coverage': result['coverage'],
                                's1_subset_accuracy': result['S1_subset_accuracy'], 's3_subset_accuracy': result['S3_subset_accuracy'],
                                'delta_pp': 100 * result['difference_right_minus_left'],
                                'ci_low_pp': 100 * result['percentile_CI_95'][0], 'ci_high_pp': 100 * result['percentile_CI_95'][1],
                                'review_method': result['S3_review_method']})
    performance, performance_long, memory, failures = [], [], [], []
    for model in MODELS:
        items = [i for i in tasks if i['task']['model'] == model]
        all_predictions = [p for i in items for p in i['predictions']]
        hardware = {p['timing_hardware_id'] for p in all_predictions}
        assert len(hardware) == 1
        memory.append({'model_key': model, 'model': LABELS[model], 'hardware_id': next(iter(hardware)),
                       'peak_allocated_gib': max(p['cuda_memory']['process_allocator_peak_allocated'] for p in all_predictions) / 2**30,
                       'peak_reserved_gib': max(p['cuda_memory']['process_allocator_peak_reserved'] for p in all_predictions) / 2**30})
        for condition in CONDITIONS + (['S3-pure'] if model.startswith('gemma4') else []):
            rows = [p for i in items if i['task']['stage'] == 'performance' and i['task']['condition'] == condition for p in i['predictions']]
            assert len(rows) == (25 if condition == 'S3-pure' else 100)
            result = analysis.performance(rows, minimum_n=100)
            assert len(result['groups']) == 1 and result['observations'] == len(rows)
            metrics = result['metrics']
            record = {'model_key': model, 'model': LABELS[model], 'condition': condition, 'n_observations': len(rows),
                      'unique_questions': len({p['qid'] for p in rows}), 'repeats': len({p['repeat_index'] for p in rows}),
                      'generate_p50_ms': 1000 * metrics['generate_seconds']['p50'],
                      'end_to_end_p50_ms': 1000 * metrics['end_to_end_seconds']['p50'],
                      'generate_p95_ms': None if metrics['generate_seconds']['p95'] is None else 1000 * metrics['generate_seconds']['p95'],
                      'end_to_end_p95_ms': None if metrics['end_to_end_seconds']['p95'] is None else 1000 * metrics['end_to_end_seconds']['p95'],
                      'mean_generated_tokens': statistics.mean(p['generated_tokens'] for p in rows),
                      'budget_exhausted_count': sum(p['budget_exhausted'] for p in rows),
                      'format_failures': sum(p['parse_status'] != 'ok' for p in rows), 'hardware_id': next(iter(hardware))}
            performance.append(record)
            for metric, field in [('Generate', 'generate_p50_ms'), ('Preprocess + generate', 'end_to_end_p50_ms')]:
                performance_long.append({**record, 'scope': metric, 'p50_ms': record[field]})
    for item in tasks:
        t = item['task']
        for p in item['predictions']:
            if p['parse_status'] != 'ok':
                failures.append({'task_id': t['task_id'], 'model_key': t['model'], 'model': LABELS[t['model']], 'stage': t['stage'], 'split': t['split'],
                                 'condition': t['condition'], 'qid': p['qid'], 'parse_status': p['parse_status'],
                                 'generated_tokens': p['generated_tokens'], 'budget_exhausted': p['budget_exhausted'],
                                 'input_images': p['input_image_count'], 'final_output': p['final_output']})
    assert len(failures) == 132 and sum(r['format_failures'] for r in quality) == 99
    return {'quality': quality, 'scenarios': scenarios, 'paired_comparisons': comparisons, 's3_subsets': subsets,
            'performance': performance, 'performance_long': performance_long, 'memory': memory, 'format_failures': failures}


def save_tables(results, audit):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'analysis_results.json').write_text(json.dumps({'audit': audit, **results}, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'validation_receipt.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    for name, rows in results.items():
        if not rows:
            continue
        with (OUT / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def build_sql_sources(tasks):
    """Independent SQL aggregation of raw question-run records, not a cached-score reshape."""
    import os
    import sqlite3
    import tempfile
    handle, temp = tempfile.mkstemp(prefix='.analysis-', suffix='.sqlite', dir=OUT)
    os.close(handle)
    try:
        with sqlite3.connect(temp) as conn:
            conn.execute('CREATE TABLE question_runs (task_id TEXT, model_key TEXT, model TEXT, model_order INTEGER, split TEXT, stage TEXT, condition TEXT, qid TEXT, repeat_index INTEGER, scenario TEXT, parse_status TEXT, parsed_choice TEXT, gold_choice TEXT, correct INTEGER, format_failure INTEGER, generate_ms REAL, end_to_end_ms REAL, generated_tokens INTEGER, hardware_id TEXT, PRIMARY KEY(task_id,qid))')
            rows = []
            for item in tasks:
                t = item['task']
                bundle_path = BACKUP / 'bound-v1.10.0' / t['bundle']
                answers = read(bundle_path.parent / item['bundle']['answers']['path'])
                gold = {a['qid']: a for a in answers}
                for p in item['predictions']:
                    a = gold[p['qid']]
                    rows.append((t['task_id'], t['model'], LABELS[t['model']], MODELS.index(t['model']), t['split'], t['stage'], t['condition'], p['qid'], t['repeat_index'], a['scenario'], p['parse_status'], p['parsed_choice'], a['answer_choice'], int(p['parse_status'] == 'ok' and p['parsed_choice'] == a['answer_choice']), int(p['parse_status'] != 'ok'), 1000 * p['timing']['generate_seconds'], 1000 * p['timing']['end_to_end_seconds'], p['generated_tokens'], p['timing_hardware_id']))
            conn.executemany('INSERT INTO question_runs VALUES (' + ','.join('?' for _ in range(19)) + ')', rows)
            assert conn.execute('SELECT count(*) FROM question_runs').fetchone()[0] == 21927
        os.replace(temp, OUT / 'analysis.sqlite')
    finally:
        if Path(temp).exists():
            Path(temp).unlink()
    quality_sql = """SELECT model_key, model, split, condition,
       COUNT(*) AS n,
       SUM(CASE WHEN parse_status = 'ok' AND parsed_choice = gold_choice THEN 1 ELSE 0 END) AS correct,
       1.0 * SUM(CASE WHEN parse_status = 'ok' AND parsed_choice = gold_choice THEN 1 ELSE 0 END) / COUNT(*) AS accuracy,
       SUM(format_failure) AS format_failures,
       1.0 * SUM(format_failure) / COUNT(*) AS format_rate,
       1.0 * SUM(CASE WHEN parse_status = 'ok' THEN 1 ELSE 0 END) / COUNT(*) AS valid_parse_rate
FROM main.question_runs
WHERE stage = 'quality' AND split = 'frozen_test' AND condition IN ('S0','S1','S2')
GROUP BY model_key, model, split, condition
ORDER BY MIN(model_order), condition;"""
    performance_sql = """WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY model_key, condition ORDER BY end_to_end_ms, task_id, qid) AS rn,
            COUNT(*) OVER (PARTITION BY model_key, condition) AS n
  FROM main.question_runs
  WHERE stage = 'performance' AND condition IN ('S0','S1','S2')
)
SELECT model_key, model, condition, MAX(n) AS n_observations,
       COUNT(DISTINCT qid) AS unique_questions, COUNT(DISTINCT repeat_index) AS repeats,
       AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN end_to_end_ms END) AS end_to_end_p50_ms,
       SUM(format_failure) AS format_failures, AVG(generated_tokens) AS mean_generated_tokens,
       MAX(hardware_id) AS hardware_id
FROM ranked
GROUP BY model_key, model, condition
ORDER BY MIN(model_order), condition;"""
    sql = {'frozen_quality': quality_sql, 'performance_median': performance_sql}
    datasets = {}
    with sqlite3.connect(OUT / 'analysis.sqlite') as conn:
        conn.row_factory = sqlite3.Row
        for name, query in sql.items():
            datasets[name] = [dict(row) for row in conn.execute(query)]
            (OUT / (name + '.sql')).write_text(query + '\n')
    (OUT / 'sql_sources.json').write_text(json.dumps({'queries': sql, 'datasets': datasets}, ensure_ascii=False, indent=2) + '\n')
    return datasets


def build_report_queries(tasks, results):
    import sqlite3
    with sqlite3.connect(OUT / 'analysis.sqlite') as conn:
        conn.execute('DROP TABLE IF EXISTS bootstrap_intervals')
        conn.execute('CREATE TABLE bootstrap_intervals (model_key TEXT, split TEXT, comparison TEXT, ci_low_pp REAL, ci_high_pp REAL, method TEXT, resamples INTEGER, seed INTEGER, PRIMARY KEY(model_key,split,comparison))')
        conn.executemany('INSERT INTO bootstrap_intervals VALUES (?,?,?,?,?,?,?,?)', [(r['model_key'],r['split'],r['comparison'],r['ci_low_pp'],r['ci_high_pp'],r['method'],r['resamples'],r['seed']) for r in results['paired_comparisons']])
        conn.execute('DROP TABLE IF EXISTS memory_observations')
        conn.execute('CREATE TABLE memory_observations (task_id TEXT, qid TEXT, model_key TEXT, model TEXT, allocated_bytes INTEGER, reserved_bytes INTEGER, PRIMARY KEY(task_id,qid))')
        conn.executemany('INSERT INTO memory_observations VALUES (?,?,?,?,?,?)', [(i['task']['task_id'],p['qid'],i['task']['model'],LABELS[i['task']['model']],p['cuda_memory']['process_allocator_peak_allocated'],p['cuda_memory']['process_allocator_peak_reserved']) for i in tasks for p in i['predictions']])
    def pivot_query(split, extra=''):
        return f"""SELECT model_key, model, SUM(CASE WHEN condition='S0' THEN 1 ELSE 0 END) AS n,
       printf('%.2f%%',100.0*SUM(CASE WHEN condition='S0' THEN correct ELSE 0 END)/SUM(condition='S0')) AS S0,
       printf('%.2f%%',100.0*SUM(CASE WHEN condition='S1' THEN correct ELSE 0 END)/SUM(condition='S1')) AS S1,
       printf('%.2f%%',100.0*SUM(CASE WHEN condition='S2' THEN correct ELSE 0 END)/SUM(condition='S2')) AS S2
FROM main.question_runs
WHERE stage='quality' AND split='{split}' AND condition IN ('S0','S1','S2') {extra}
GROUP BY model_key, model ORDER BY MIN(model_order);"""
    paired_sql = """WITH contrasts(left_condition,right_condition,comparison) AS
 (VALUES ('S0','S1','S1 − S0'),('S1','S2','S2 − S1'))
SELECT l.model_key,l.model,c.comparison,COUNT(*) AS n,
       100.0*AVG(r.correct-l.correct) AS delta_pp,
       printf('%+.2f',100.0*AVG(r.correct-l.correct)) AS delta,
       printf('[%+.2f, %+.2f]',b.ci_low_pp,b.ci_high_pp) AS interval,
       b.ci_low_pp,b.ci_high_pp,
       SUM(l.correct=0 AND r.correct=1) AS improvements,
       SUM(l.correct=1 AND r.correct=0) AS regressions
FROM contrasts c
JOIN main.question_runs l ON l.condition=c.left_condition AND l.stage='quality' AND l.split='frozen_test'
JOIN main.question_runs r ON r.model_key=l.model_key AND r.split=l.split AND r.qid=l.qid
 AND r.stage=l.stage AND r.condition=c.right_condition
JOIN main.bootstrap_intervals b ON b.model_key=l.model_key AND b.split=l.split AND b.comparison=c.comparison
GROUP BY l.model_key,l.model,c.comparison ORDER BY MIN(l.model_order),c.comparison;"""
    s3_sql = """WITH subset AS (
 SELECT s.model_key,s.model,s.split,COUNT(*) AS paired_n,
 (SELECT COUNT(*) FROM main.question_runs p WHERE p.model_key=s.model_key AND p.split=s.split AND p.stage='quality' AND p.condition='S1') AS parent_n,
 AVG(r.correct) AS s1_subset_accuracy,AVG(s.correct) AS s3_subset_accuracy
 FROM main.question_runs s JOIN main.question_runs r
 ON r.model_key=s.model_key AND r.split=s.split AND r.qid=s.qid AND r.stage='quality' AND r.condition='S1'
 WHERE s.stage='quality' AND s.condition='S3-pure'
 GROUP BY s.model_key,s.model,s.split)
SELECT *,printf('%.2f%%',100.0*paired_n/parent_n) AS coverage_text,
 printf('%.2f%%',100*s1_subset_accuracy) AS s1_text,printf('%.2f%%',100*s3_subset_accuracy) AS s3_text,
 printf('%+.2f',100*(s3_subset_accuracy-s1_subset_accuracy)) AS delta
FROM subset ORDER BY model_key,split;"""
    performance_sql = """WITH ranked AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY model_key,condition ORDER BY end_to_end_ms,task_id,qid) AS rn,
 COUNT(*) OVER(PARTITION BY model_key,condition) AS n
 FROM main.question_runs WHERE stage='performance'), stats AS (
 SELECT model_key,model,condition,MAX(n) AS n_observations,COUNT(DISTINCT qid) AS unique_questions,
 AVG(CASE WHEN rn IN ((n+1)/2,(n+2)/2) THEN end_to_end_ms END) AS p50,
 CASE WHEN MAX(n)>=100 THEN
 SUM(CASE WHEN rn=CAST((n-1)*0.95 AS INTEGER)+1 THEN end_to_end_ms*(1-((n-1)*0.95-CAST((n-1)*0.95 AS INTEGER))) ELSE 0 END)+
 SUM(CASE WHEN rn=CAST((n-1)*0.95 AS INTEGER)+2 THEN end_to_end_ms*((n-1)*0.95-CAST((n-1)*0.95 AS INTEGER)) ELSE 0 END)
 ELSE NULL END AS p95
 FROM ranked GROUP BY model_key,model,condition)
SELECT *,printf('%.1f',p50) AS p50_text,CASE WHEN p95 IS NULL THEN '不报告（n=25）' ELSE printf('%.1f',p95) END AS p95_text
FROM stats ORDER BY model_key,condition;"""
    memory_sql = """SELECT model_key,model,MAX(allocated_bytes)/1073741824.0 AS peak_allocated_gib,
 MAX(reserved_bytes)/1073741824.0 AS peak_reserved_gib,
 printf('%.2f',MAX(allocated_bytes)/1073741824.0) AS allocated_text,
 printf('%.2f',MAX(reserved_bytes)/1073741824.0) AS reserved_text
FROM main.memory_observations GROUP BY model_key,model ORDER BY model_key;"""
    source = read(OUT / 'sql_sources.json')
    queries = {'frozen_lookup':pivot_query('frozen_test'), 'holdout_lookup':pivot_query('internal_holdout'),
               'incomplete_lookup':pivot_query('frozen_test',"AND scenario='Incomplete'"),
               'paired_lookup':paired_sql,'s3_lookup':s3_sql,'performance_lookup':performance_sql,'memory_lookup':memory_sql}
    with sqlite3.connect(OUT / 'analysis.sqlite') as conn:
        conn.row_factory = sqlite3.Row
        for name, query in queries.items():
            source['queries'][name] = query
            source['datasets'][name] = [dict(row) for row in conn.execute(query)]
            (OUT / (name + '.sql')).write_text(query + '\n')
    (OUT / 'sql_sources.json').write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n')
    return source['datasets']


def make_figures(results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.labelcolor': '#262b33', 'text.color': '#262b33',
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    figure_dir = OUT / 'figures'
    figure_dir.mkdir(exist_ok=True)
    colors = ['#206095', '#E8BD6F', '#A64B2A']
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.2), sharey=True)
    for ax, split, label, n in zip(axes, ['internal_holdout', 'frozen_test'], ['Internal holdout', 'Frozen test'], [150, 1033]):
        x = np.arange(5)
        for j, cond in enumerate(CONDITIONS):
            values = [next(r['accuracy'] * 100 for r in results['quality'] if r['model_key'] == m and r['split'] == split and r['condition'] == cond) for m in MODELS]
            bars = ax.bar(x + (j - 1) * .25, values, .24, label=cond, color=colors[j], edgecolor='#394452', linewidth=.5, hatch=['', '//', '..'][j])
            ax.bar_label(bars, labels=[f'{v:.1f}' for v in values], fontsize=8, padding=3)
        ax.set_xticks(x, ['Qwen3-VL\n4B', 'Qwen3-VL\n8B', 'Gemma4\nE2B', 'Gemma4\nE4B', 'Qwen3.5\n4B'])
        ax.set_ylim(0, 82)
        ax.set_title(f'{label} accuracy (n={n:,} per condition)', fontsize=11)
        ax.grid(axis='y', alpha=.18)
        ax.set_axisbelow(True)
    axes[0].set_ylabel('Strict accuracy (%)')
    axes[1].legend(ncol=3, loc='upper left', frameon=False)
    fig.suptitle('Quality accuracy by model and evidence condition', fontsize=14, x=.07, ha='left')
    fig.text(.07, .025, 'S0: query only | S1: published top-3 retrieval | S2: actual GT evidence. Format failures count as incorrect.', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .93))
    save_figure(fig, figure_dir / 'quality_accuracy')
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.9), sharey=True)
    for ax, comparison, color in zip(axes, ['S1 − S0', 'S2 − S1'], ['#206095', '#A64B2A']):
        rows = [next(r for r in results['paired_comparisons'] if r['split'] == 'frozen_test' and r['model_key'] == m and r['comparison'] == comparison) for m in MODELS]
        y = np.arange(5)
        values = np.array([r['delta_pp'] for r in rows])
        errors = np.array([[r['delta_pp'] - r['ci_low_pp'] for r in rows], [r['ci_high_pp'] - r['delta_pp'] for r in rows]])
        ax.errorbar(values, y, xerr=errors, fmt='o', capsize=4, color=color, markersize=6)
        for yy, row in zip(y, rows):
            ax.annotate(f"{row['delta_pp']:+.2f}", (row['ci_high_pp'] + .4, yy), fontsize=9, va='center')
        ax.axvline(0, color='#6d7278', lw=.8, ls='--')
        ax.set_title(comparison.replace('−', '-'))
        ax.set_xlabel('Paired accuracy difference (percentage points)')
        ax.set_yticks(y, [LABELS[m] for m in MODELS])
        ax.grid(axis='x', alpha=.18)
        ax.set_xlim(min(0, min(r['ci_low_pp'] for r in rows)) - 2, max(r['ci_high_pp'] for r in rows) + 3.2)
    axes[0].invert_yaxis()
    fig.suptitle('Frozen-test paired differences and 95% bootstrap intervals', fontsize=14, x=.09, ha='left')
    fig.text(.09, .02, 'n=1,033 paired questions; 2,000 scenario-stratified resamples, seed=42. Descriptive; source clustering not modeled.', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .92))
    save_figure(fig, figure_dir / 'paired_differences')
    fig, ax = plt.subplots(figsize=(9.6, 5.2))
    x = np.arange(5)
    for j, cond in enumerate(CONDITIONS):
        values = [next(r['end_to_end_p50_ms'] for r in results['performance'] if r['model_key'] == m and r['condition'] == cond) for m in MODELS]
        ax.bar(x + (j - 1) * .25, values, .24, label=cond, color=colors[j], edgecolor='#394452', linewidth=.5, hatch=['', '//', '..'][j])
    ax.set_xticks(x, [LABELS[m] for m in MODELS])
    ax.set_ylabel('Median preprocessing + generation (ms)')
    ax.set_title('Offline evidence-generation latency on RTX 4090', loc='left', pad=22)
    ax.text(0, 1.015, '100 observations per model/condition: 20 questions × 5 repeats; warmups excluded; retrieval not measured.', transform=ax.transAxes, fontsize=9)
    ax.grid(axis='y', alpha=.18)
    ax.set_axisbelow(True)
    ax.legend(ncol=3, frameon=False)
    fig.tight_layout()
    save_figure(fig, figure_dir / 'performance_latency')
    return [str(p) for p in sorted(figure_dir.glob('*.png'))]


def save_figure(fig, stem):
    import matplotlib.pyplot as plt
    for suffix in ('.png', '.svg', '.pdf'):
        fig.savefig(stem.with_suffix(suffix), dpi=180, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-root', type=Path, required=True, help='Extracted verified backup; read only')
    parser.add_argument('--output-dir', type=Path, required=True, help='New local output directory')
    args = parser.parse_args()
    BACKUP = args.backup_root.resolve()
    OUT = args.output_dir.resolve()
    if OUT == BACKUP or BACKUP in OUT.parents:
        parser.error('Output must be outside immutable backup')
    if OUT.exists() and any(OUT.iterdir()):
        parser.error('Use a new empty output directory')
    OUT.mkdir(parents=True, exist_ok=True)
    tasks, audit = load_and_validate(BACKUP)
    results = compute(tasks)
    save_tables(results, audit)
    build_sql_sources(tasks)
    build_report_queries(tasks, results)
    make_figures(results)
    print(json.dumps(audit, ensure_ascii=False))
