# R3 draft: Evidence-selection trade-offs under a shared candidate budget

We compare cosine, utility, and random selection while holding the candidate pool and evidence budget fixed: each strategy selects three images from the same ten candidates. On the frozen question set, Qwen3-VL-4B answers 623, 618, and 615 of 1,033 questions correctly with utility, cosine, and random selection, respectively.[1] These observed counts motivate a paired comparison; their ordering alone does not establish a strategy advantage.

| Contrast | Accuracy difference (pp) | Paired 95% interval (pp) | Improved / regressed questions |
|---|---:|---:|---:|
| Utility − cosine | +0.48 | [−1.45, +2.42] | 56 / 51 |
| Utility − random | +0.77 | [−1.26, +2.90] | 65 / 57 |

All numerical entries are from [1], `results[0:2]`; the denominator is 1,033 paired questions. We resample questions with replacement 10,000 times using seed 42, sharing each sampled index set between the two contrasts, and report unadjusted percentile intervals.[1, `method`] Both intervals include zero: we **cannot exclude no difference** for either comparison. The net gains of five and eight correct answers reflect offsetting per-question changes, rather than uniformly improved answers.[1, `results[*].delta_correct/improvements/regressions`] The paired transition counts and intervals therefore provide a more complete characterization of strategy choice than the aggregate ranking.

The scope is this model, frozen question set, and recorded generation run. These question-level intervals do not account for dependence within shared-image components; the existing component-cluster analysis is a separate uncertainty calculation.[2] The dev-selected path (P3) selects utility for this model and is not an independent random-selection baseline; the post hoc Oracle is not a deployable policy.[3] We do not infer a universal strategy ordering or a deployable selection gain from these comparisons. Nor do we claim to reproduce the original Utility-MRAG strategy ranking: the archived evidence lacks its paired utility-versus-cosine/random values under matching pool and selection budgets.[4]

[1] `reports/paper_20261021/r3_paired_bootstrap_20261023.json`: `results`, `method`, `provenance`, `paired_correctness`. Its input paths and hashes bind the private predictions and existing strict-choice scores. Analysis was registered in commit `9563209` before resampling; see `R3_PAIRED_BOOTSTRAP_20261023.md` for verification and reproduction.

[2] `reports/next_stage_20261019/quality_closure_20261021/source_cluster_ci.csv`: component-based intervals are distinct from the question-level intervals above.

[3] `reports/next_stage_20261019/quality_closure_20261021/fixed_rag_matrix.csv`: `model=qwen3vl_4b, split=frozen_test`, `path/selected_strategy/post_hoc_oracle`.

[4] `reports/paper_20261021/DATA_AUDIT_20261023.md`, archived-paper comparison; `reports/next_stage_20261017/B_paper_table_evidence.csv`, P009/P010. These archived cells compare zero-shot and utility conditions, not a matched cosine/random baseline.
