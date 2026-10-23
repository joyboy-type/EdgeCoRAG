# Conditional-performance extrapolation: locked analysis registration

Registered date: 2026-10-23 (Asia/Shanghai). Protocol ID: `conditional_extrapolation_20261023_v1`.

This is an analysis registered before computing the new splits, conditional estimates or prediction errors. The underlying frozen questions, outcomes and aggregate accuracies have already been observed. This is not a new blind test or a prospective preregistration of the historical experiments. No GPU inference is authorised or needed by this document.

## 1. Question and complete reporting commitment

Can within-model conditional proportions transfer (a) across held-out questions and (b) to a held-out evidence-selection strategy? The tests are separate and must be reported separately. Every model/strategy result, positive or negative, will be retained. Neither splits, thresholds, target strategies, aggregation weights nor denominators may be changed after inspecting results.

The identity `Acc = r*u + (1-r)*p` within the same data is not evidence of prediction. Here `u` and `p` must be estimated without the relevant validation outcomes. They are conditional correctness proportions, not causal evidence-use effects or isolated parametric knowledge.

## 2. Locked sources and units

Repository-relative public inputs:

- `logs/results_20261020/no_self_scored_outcomes.jsonl.gz`: archived per-question correctness, parse status and scenario; do not reparse or regenerate answers.
- `reports/paper_20261021/decomposition_20261021.json`: legacy full-sample S1 conditional proportions, used only as an explicitly labelled secondary baseline.
- `reports/next_stage_20261019/quality_closure_20261021/fixed_rag_matrix.csv`: read-only reconciliation reference, never modify.
- `reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`: read-only; new numbers must not be inserted.

Private sources under the project workspace (passed as an explicit `--work-dir`, ending in `work/next-experiment-20261019`):

- `continuous-complete-backup/frozen_test/results/generate-{model}/predictions.jsonl`: ordered `selected_ids`, `qid`, `selection_strategy`, answer and runtime provenance. The `closeout-manifest.json` pins their SHA256 values.
- `corrected-protocol-scoring/frozen_test__{model}__{strategy}.private.json`: `per_question[].{qid,scenario,correct,parse_status}` and `source_predictions_sha256`.
- `prepared/selection-frozen_test.proposed.json`: fixed question universe and retrieval-control binding.
- `prepared/no-self-frozen_test-ranks.jsonl`: `qid`, top-10 `corpus_ids`.
- Sibling `work/instance394-preflight/formal-retrieval-embeddinggemma2-backup/controls/retrieval-formal.approved.json`: `gold[qid]`, corpus identities and source binding.

Models: `qwen3vl_4b`, `qwen3vl_8b`, `gemma4_e2b`, `gemma4_e4b`, `qwen35_4b`. Strategies: `cosine`, `random`, `utility`. Only the frozen 1,033-question set is used. Smoke/dev outcomes are not added to estimation or validation. All three strategies and all models must share the same qid universe. The same ordered evidence identities must be used across generators for a given qid/strategy.

Clarification: for Qwen3-VL-4B, archived frozen cosine/random/utility correct counts are 618/615/623. P3 is a dev-selected fixed strategy, not a synonym for random; 711 belongs to post hoc P4 Oracle. Oracle outcomes are excluded from both tests.

Each source's actual path and file SHA256 will be recorded in the result JSON. Each qid list is stored and hashed as SHA256 of UTF-8 `qid + "\n"`, lexicographically sorted, including a final newline. Each numeric result inherits source IDs, estimate/validation qid-list IDs and explicit JSON fields identifying its numerator and denominator. No private answers or image contents are copied into the public results.

## 3. Hit and correctness definitions

For qid q and strategy s, `H(q,s) = 1` iff at least one identity in the original `gold[q]` list belongs to that record's three ordered `selected_ids`. This is selected-top-3 exact identity any-hit, not top-10 candidate-pool hit, semantic support or gold-inclusive MMDocRAG selection.

Missing gold identities in the corpus remain in their original lists and all questions remain in the denominator. Missing gold mappings, missing strategy records, duplicated identities/records, a wrong split, source-hash mismatch or inconsistent qid coverage are reported as data gaps and block the affected test; they are not filled or silently dropped.

`Y(q,m,s)` is the existing archived boolean correctness for model m and strategy s. Parsing and generation failures remain incorrect. Scores must reconcile to the raw-prediction hash and public archived outcomes. No answer extraction rules are changed.

For an estimation set E: `u_hat = sum(H*Y)/sum(H)` and `p_hat = sum((1-H)*Y)/sum(1-H)`. Record all four counts and both denominators. A zero estimation hit or miss denominator yields undefined parameters and an explicit non-estimable test, with no smoothing or borrowed values.

## 4. Test (a): held-out questions

Hash each complete qid string using `SHA256(UTF8("EdgeCoRAG-extrapolation-20261023:a:" + qid))`. Sort all frozen qids by `(hex_digest, qid)`. The first `floor(1033/2) = 516` are E; the remaining 517 are V. The split is identical for all five models and all strategies. Hash ranking fixes the sizes while preventing response-dependent selection. No outcome or scenario rebalancing, retries or alternative salts are allowed.

For each model and each strategy independently, estimate one pair `(u_hat,p_hat)` on E for that strategy. On V report the overall hit rate r, observed accuracy, prediction `r*u_hat + (1-r)*p_hat`, and signed residual `observed - predicted`.

Additionally, for each of the nine original scenarios in V, use that scenario's own hit rate `r_V,scenario` with the same E-estimated parameters, and compare to its observed accuracy. Scenario labels are taken from the archived scoring records. No scenario-specific estimation parameters are fitted.

## 5. Test (b): held-out strategy

Use all 1,033 frozen qids, but only cosine and utility outcomes for estimation. Pool their question-strategy records with equal weight: sum the hit-correct counts over both strategies and divide by their combined hit count to obtain u; do the analogous operation for p. Do not average the two conditional rates. Repeated qids across the two estimation strategies are repeated observations, not additional independent questions.

Validate only on random at the same qids, using random's own overall and per-scenario hit rates. Random outcomes are never read to estimate the primary parameters. This is an across-strategy test on previously seen questions, not across-question or independent-data validation. Cosine and utility have no held-out-strategy validation result; mark them `estimation_only`, never report in-sample fits as validation successes.

Report the same overall prediction/residual and per-scenario table as test (a), with one evaluation row per model for random. The two tests are not combined into a single pooled error.

## 6. Error aggregation, thresholds and decisions

All errors are in probability units, not percentages. For each model and validation strategy, define per-scenario residuals `e_j = observed_accuracy_j - predicted_accuracy_j` across the nine original scenarios. The primary RMSE is `sqrt(mean_j(e_j^2))` with equal scenario weights; maximum residual is `max_j(abs(e_j))`. This fixes what “one row per strategy” aggregates and prevents large scenarios hiding failures in smaller ones. Overall error is reported separately and is not substituted for these metrics.

No scenario is excluded for small size. If a scenario has no validation questions, report the gap and the row as non-estimable rather than changing the aggregation. A zero validation hit count is allowed because its prediction uses r=0; it does not require estimating a new u. All nine scenarios must be present to declare a row evaluable. No confidence intervals or hypothesis tests are newly computed in this analysis; prior cluster/question-level intervals are not mixed into these error metrics.

A row passes iff `RMSE <= 0.05 AND maximum_absolute_residual <= 0.10`, including equality. Report both measured errors and boolean comparisons, without rounding before classification. Otherwise it fails. These are stipulated practical tolerances, not a test of statistical equivalence or universality.

- Test (a) passes only if every one of its 15 model/strategy rows passes.
- Test (b) passes only if each of its five random-validation rows passes.
- If all required rows are available and both tests pass, the locked conclusion is: **“条件比例在同一模型内可跨题、跨策略外推”**. State explicitly that this is limited to these recorded models, strategies, benchmark, split and tolerances.
- If any evaluable row exceeds either tolerance, the locked conclusion is: **“条件比例不可外推，只能作区间描述”**. Identify whether the question dimension, strategy dimension, or both failed, and list all failing rows. Here “区间描述” does not add new intervals or assert that historical degenerate intervals are reliable.
- Missing required records or undefined parameters cannot be counted as passes; report incomplete evidence and do not claim extrapolation was validated. Do not manufacture a numeric failure metric for missing data.

## 7. Full-sample baselines (explicitly retrospective)

For every validation row report both baselines using exactly the same validation questions, scenario rates and error aggregation as the primary prediction:

1. `full_sample_target_strategy`: estimate u,p using that validation strategy's outcomes on all frozen qids. For (a) this includes V; for (b) it includes the held-out random outcomes. This is deliberately outcome-contaminated, corresponds to the criticised full-sample plug-in approach, and is not evidence of extrapolation. Its pooled fit is an identity; its scenario errors need not be zero.
2. `legacy_S1_full_sample`: read that model's `models.{model}.u` and `.p` from `decomposition_20261021.json` and apply them to the validation strategy's r. This preserves a direct comparison to the previous S1 full-sample parameters, while acknowledging the different evidence condition and prior exposure.

Report baseline u,p, predictions, residuals, scenario RMSE/max error, and primary-minus-baseline error differences. Neither baseline affects the primary pass/fail thresholds, split, targets or mandatory conclusion.

## 8. Execution order and outputs

1. Commit this file unchanged before implementing or calculating the new analysis. Report its git commit and file SHA256 in chat, then continue; do not amend this registration based on results.
2. Add a small standard-library analysis entry point and focused synthetic tests for split stability/no overlap, estimation weighting, exact selected-ID hits, missing-record rejection, scenario error aggregation and inclusive thresholds. Test before implementation. No GPU/model imports or dependencies are needed for the new analysis.
3. Validate bound source identities and coverage, then execute this exact protocol once. Do not inspect errors to choose a different variant.
4. Write `reports/paper_20261021/extrapolation_test_20261023.json` and `EXTRAPOLATION_TEST.md`, including all rows, baselines, failures, source hashes, ordered qid lists and list hashes, registration SHA256/commit and implementation hash. Do not overwrite earlier outputs on rerun.
5. Run repository tests and analysis tests before commits. Keep new tests separate from the existing suites' baseline counts. Verify `a-side/**`, `fixed_rag_matrix.csv` and `frozen_numbers.json` are unchanged. No manuscript edits or new GPU runs are included.

The registration file's SHA256 is recorded externally in the commit message/chat and final JSON to avoid a self-referential hash. This entire file is frozen at its registration commit.
