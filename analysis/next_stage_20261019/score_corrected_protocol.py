"""Offline strict scoring of the verified corrected-protocol archive; no inference."""
import csv
import datetime
import hashlib
import json
import pathlib
import statistics
import sys
from zoneinfo import ZoneInfo

from analysis_paths import settings
PATHS = settings(__name__, __doc__, own_parser=False)

HERE = PATHS.work_dir
PROJECT = PATHS.project_root
ROOT = HERE / 'continuous-complete-backup'
PRIVATE = HERE / 'corrected-protocol-scoring'
OUTPUT = PATHS.output_dir or HERE / "scored-public"
OLD = PATHS.legacy_root
REPO = PATHS.repo
MODELS = ['qwen3vl_4b', 'qwen3vl_8b', 'gemma4_e2b', 'gemma4_e4b', 'qwen35_4b']
STRATEGIES = ['cosine', 'random', 'utility']
LABELS = dict(zip(MODELS, ['Qwen3-VL 4B', 'Qwen3-VL 8B', 'Gemma E2B', 'Gemma E4B', 'Qwen3.5 4B']))

def read(p):
    return json.loads(p.read_text())

def jl(p):
    return [json.loads(s) for s in p.read_text().splitlines()]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def dump(p, value):
    with p.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)

def csvsave(name, rows):
    with (OUTPUT / name).open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main():
    if OLD is None: raise ValueError("--legacy-root is required for historical scoring")
    assert not PRIVATE.exists(), 'Scoring output exists; do not overwrite'
    PRIVATE.mkdir()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    verification = read(HERE / 'continuous-complete-backup-verified.json')
    assert verification['status'] == 'complete_archive_and_all_18_stages_verified'
    assert sha(HERE / 'no-self-continuous-complete.private.tar.gz') == verification['archive_sha256']
    manifest = read(ROOT / 'closeout-manifest.json')
    hashes = {r['path']: r['sha256'] for r in manifest['files']}
    scorer_path = REPO / 'b-side/score_minimal.py'
    assert sha(scorer_path) == sha(OLD / 'runtime-v1.10.1/b-side/score_minimal.py')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(REPO / 'b-side'))
    import score_minimal as scorer
    import analyze_batch as analysis
    matrix = OLD / 'bound-v1.10.0/bound_matrix.json'
    assert sha(matrix) == '630eee8d4032fa0aede73eef89612801ff521785e045bdfc0f14ffaea094c555'
    bindings = read(matrix)['task_items']
    summary, timings, scenes, pairs, effects, coverage = [], [], [], [], [], []
    scores, sources, selections = {}, {}, {}
    old_scores = PROJECT / 'work/instance394-preflight/formal-selection-scoring-20261019'
    for cohort, n in [('smoke_20', 20), ('dev', 150), ('frozen_test', 1033)]:
        bound = OLD / 'bound-v1.10.0/integrated' / cohort / 'main'
        bundle_path = bound / 'bundle.json'
        bound_stage = {'smoke_20': 'smoke', 'dev': 'development', 'frozen_test': 'quality'}[cohort]
        tasks = [t for t in bindings if t['split'] == cohort and t['stage'] == bound_stage and t['condition'] == 'S0']
        assert len(tasks) == 5 and all(sha(bundle_path) == t['bundle_sha256'] for t in tasks)
        bundle = read(bundle_path)
        answers_path = bound / bundle['answers']['path']
        inputs_path = bound / bundle['conditions']['S0']['path']
        assert sha(answers_path) == bundle['answers']['sha256']
        assert sha(inputs_path) == bundle['conditions']['S0']['sha256']
        answer_map = {r['qid']: r for r in read(answers_path)}
        old_inputs = {r['qid']: r for r in read(inputs_path)}
        pkg = read(ROOT / cohort / 'controls' / ('selection-' + cohort + '.approved.json'))
        qids = [r['qid'] for r in pkg['queries']]
        assert len(qids) == len(set(qids)) == n and set(qids) == set(answer_map)
        for q in pkg['queries']:
            prior = old_inputs[q['qid']]
            assert all(q[k] == prior[k] for k in ['question', 'choices'])
            assert q['query_image']['sha256'] == prior['query_image']['sha256']
        answers = [answer_map[q] for q in qids]
        sources[cohort] = {'answers_sha256': sha(answers_path), 'answers_path': str(answers_path), 'bundle_sha256': sha(bundle_path)}
        for model in MODELS:
            pred_path = ROOT / cohort / 'results' / ('generate-' + model) / 'predictions.jsonl'
            receipt = read(pred_path.parent / 'receipt.json')
            split_path = bound / bundle['split_manifest']['path']
            assert sha(split_path) == bundle['split_manifest']['sha256']
            assert sha(pred_path) == hashes[str(pred_path.relative_to(ROOT))]
            rows = jl(pred_path)
            assert [(r['qid'], r['selection_strategy']) for r in rows] == [(q, s) for q in qids for s in STRATEGIES]
            for strategy in STRATEGIES:
                selected = [r for r in rows if r['selection_strategy'] == strategy]
                converted = [{'qid': r['qid'], 'raw_output': r['final_output'], 'generation_error': r.get('final_extraction_error')} for r in selected]
                score = scorer.evaluate(answers, converted)
                recount = sum(scorer.parse_choice(r['final_output'])[0] == answer_map[r['qid']]['answer_choice'] and not r.get('final_extraction_error') for r in selected)
                overall = score['overall']
                assert overall['total'] == n and recount == overall['correct']
                assert sum(s['total'] for s in score['scenarios'].values()) == n
                assert sum(s['correct'] for s in score['scenarios'].values()) == recount
                assert sum(overall['status_counts'].values()) == n
                score.update(source_predictions_sha256=sha(pred_path), source_answers_sha256=sha(answers_path), cohort=cohort, model=model, strategy=strategy, model_id=receipt['model_id'], model_revision=receipt['revision'], synthetic=False, stage=bound_stage, dataset_revision=bundle['dataset_revision'], split_manifest_sha256=sha(split_path), template_version='shared_visual_mcq_v1', protocol_version='no_query_sha_self_match_corrected_v1_20261019')
                dump(PRIVATE / (cohort + '__' + model + '__' + strategy + '.private.json'), score)
                scores[cohort, model, strategy] = score
                summary.append({'cohort': cohort, 'model': model, 'strategy': strategy, 'n': n, 'correct': recount, 'accuracy_percent': 100 * recount / n, 'strict_failures': n - overall['valid_parsed'], **overall['status_counts']})
                for scene, vals in score['scenarios'].items():
                    scenes.append({'cohort': cohort, 'model': model, 'strategy': strategy, 'scenario': scene, 'n': vals['total'], 'correct': vals['correct'], 'accuracy_percent': vals['accuracy_percent']})
                ts = [r['timing']['end_to_end_seconds'] for r in selected]
                timings.append({'cohort': cohort, 'model': model, 'strategy': strategy, 'n': n, 'generation_p50_seconds': statistics.median(ts), 'generation_p95_seconds': analysis.quantile(ts, .95), 'allocator_process_peak_allocated_gib': max(r['cuda_memory']['process_allocator_peak_allocated'] for r in selected) / 2**30, 'allocator_process_peak_reserved_gib': max(r['cuda_memory']['process_allocator_peak_reserved'] for r in selected) / 2**30, 'scope': 'generation only; cumulative allocator process peaks, not per-strategy/device-wide peak; RTX3090 BF16, no performance repetitions'})
                chosen = {r['qid']: tuple(r['selected_ids']) for r in selected}
                if (cohort, strategy) in selections:
                    assert selections[cohort, strategy] == chosen
                selections[cohort, strategy] = chosen
                if cohort == 'frozen_test':
                    old = read(old_scores / (model + '__' + strategy + '.private.json'))
                    assert old['source_answers_sha256'] == sha(answers_path)
                    effects.append({'model': model, 'strategy': strategy, 'n': n, 'old_protocol_correct': old['overall']['correct'], 'old_protocol_accuracy_percent': old['overall']['accuracy_percent'], 'no_self_correct': recount, 'no_self_accuracy_percent': 100 * recount / n, 'no_self_minus_old_pp': 100 * (recount - old['overall']['correct']) / n, 'interpretation': 'observed-data protocol replication; old results include query self-match confound; not independent blind test or causal proof'})
            if cohort == 'frozen_test':
                for left, right in [('cosine', 'random'), ('cosine', 'utility'), ('random', 'utility')]:
                    a, b = scores[cohort, model, left], scores[cohort, model, right]
                    v = analysis.paired(a, b, repetitions=2000, seed=42)
                    aa = {r['qid']: r['correct'] for r in a['per_question']}
                    bb = {r['qid']: r['correct'] for r in b['per_question']}
                    wins = sum(bb[q] and not aa[q] for q in qids)
                    losses = sum(aa[q] and not bb[q] for q in qids)
                    assert abs(v['difference_right_minus_left'] - (wins - losses) / n) < 1e-12
                    assert wins - losses == b['overall']['correct'] - a['overall']['correct']
                    pairs.append({'model': model, 'left': left, 'right': right, 'n': n, 'delta_pp': 100 * (wins - losses) / n, 'ci_low_pp': 100 * v['percentile_CI_95'][0], 'ci_high_pp': 100 * v['percentile_CI_95'][1], 'wins': wins, 'losses': losses, 'unchanged': n - wins - losses, 'resamples': 2000, 'seed': 42, 'method': v['method']})
    ret = read(PROJECT / 'work/instance394-preflight/formal-frozen-test-backup/controls/retrieval-formal.approved.json')
    ranks = jl(ROOT / 'frozen_test/controls/ranks.jsonl')
    qids = [r['qid'] for r in ranks]
    gold = {q: set(ret['gold'][q]) for q in qids}
    pool = {r['qid']: r['corpus_ids'] for r in ranks}
    for strategy in ['pool_top10'] + STRATEGIES:
        ids = pool if strategy == 'pool_top10' else selections['frozen_test', strategy]
        hits = sum(bool(set(ids[q]) & gold[q]) for q in qids)
        coverage.append({'strategy': strategy, 'n': 1033, 'exact_gt_hit_questions': hits, 'exact_gt_hit_percent': 100 * hits / 1033, 'scope': 'exact image identity coverage, not semantic relevance or sufficiency; one shared selection across five models'})
    assert sum(r['n'] for r in summary) == 18045
    csvsave('无自匹配协议_准确率汇总.csv', summary)
    csvsave('无自匹配协议_1033题成对比较.csv', pairs)
    csvsave('无自匹配协议_时延与显存.csv', timings)
    csvsave('无自匹配协议_与旧协议对照.csv', effects)
    csvsave('无自匹配协议_精确证据覆盖.csv', coverage)
    csvsave('无自匹配协议_场景汇总.csv', scenes)
    validation = {'status': 'share_with_caveats', 'scored_predictions': 18045, 'fixed_denominators': {'smoke_20': 20, 'dev': 150, 'frozen_test': 1033}, 'scoring_jobs': len(summary), 'frozen_scored_predictions': 15495, 'parser': scorer.PARSER_VERSION, 'parser_sha256': sha(scorer_path), 'bound_matrix_sha256': sha(matrix), 'source_archive_sha256': verification['archive_sha256'], 'answer_sources': sources, 'independent_strict_recounts': 'passed_all45', 'scenario_subtotals': 'passed_all45', 'paired_marginal_reconciliation': 'passed_all15', 'selection_shared_across_generators': True, 'strict_failures': sum(r['strict_failures'] for r in summary), 'holdout_evaluated': False, 'holdout_answer_files_or_predictions_read': False, 'inference_or_server_access': False, 'parameters_changed': False, 'quality_used_to_tune': False, 'as_of': datetime.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'caveats': ['Previously observed data; corrected-protocol replication, not new blind evaluation.', 'Fixed random seed; no selection-seed or performance repeats.', 'Paired scenario-stratified question bootstrap; source/image dependence unresolved;15 comparisons unadjusted.', 'Generation timing excludes retrieval, utility, initialization, switching and archival; not edge-device end-to-end cost.', 'CUDA figures are cumulative process allocator peaks, not device-wide measurements.', 'Exact GT identity is not semantic evidence relevance or sufficiency.']}
    dump(PRIVATE / 'validation.json', validation)
    dump(PRIVATE / 'summary.json', {'quality': summary, 'paired': pairs, 'old_protocol_comparison': effects, 'evidence_coverage': coverage, 'timing': timings})
    print(json.dumps({'validation': validation, 'frozen_quality': [r for r in summary if r['cohort'] == 'frozen_test'], 'utility_vs_cosine': [r for r in pairs if r['left'] == 'cosine' and r['right'] == 'utility'], 'coverage': coverage}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
