# EdgeCoRAG — English draft v0

Target: ACL (main / Findings), double-blind, 8-page limit + unlimited references.
Numbers are cited by frozen id from `reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`.

---

## Title (working)

**When Retrieved Evidence Does Not Help: A Frozen-Protocol Audit of Multimodal RAG on Vision-Centric QA**

Alternatives considered: "The Retrieval Ceiling: Separating Retrieval Quality from Evidence Utilisation in Multimodal RAG".

---

## Abstract

Retrieval-augmented generation (RAG) for multimodal question answering is often justified by the claim that external visual evidence compensates for a model's limited visual knowledge. We test that claim under a frozen protocol rather than proposing a new method. Using MRAG-Bench, five vision-language models (Gemma 4 E2B/E4B, Qwen3-VL 4B/8B, Qwen3.5 4B), and four evidence conditions (no retrieval, shared top-3 retrieval, ground-truth evidence, and a held-out distractor subset), we measure the effect of evidence on 1,033 evaluation questions with paired comparisons and failure-retaining scoring.

We find a layered picture. First, giving every model the same retrieved top-3 images does not reliably help: the S1−S0 change ranges from −2.52 to +2.90 percentage points across the five models, and four of the five paired intervals cross zero `[T2.qwen3vl_4b.S1_minus_S0_pp]`. Second, ground-truth evidence does help, by +6.39 to +10.36 points over no retrieval `[T2.qwen3vl_4b.S2_minus_S0_pp]`. Third, the retrieval stage imposes a hard ceiling: the gold image appears in the retrieved top-3 for only 516 of 1,033 questions `[retrieval.top3_hit]`, so half of the evaluation set cannot benefit from retrieval at all. Fourth, conditional on a hit, models differ substantially in utilisation, answering correctly between 219 and 343 of those 516 questions `[T3.gemma4_e2b.命中且答对]`, `[T3.qwen3vl_8b.命中且答对]`.

We report these as a boundary rather than a method: under our protocol the benefit of multimodal RAG is governed by retrieval hit rate and per-model utilisation, not by the presence of a retriever. We further show that a post hoc oracle over evidence-selection strategies leaves +6.87 to +10.55 points on the table `[gate.qwen3vl_4b.delta_pp]`, but we do not claim this is deployable, because no routing policy is evaluated and routing cost is not measured. We release the frozen protocol, the 2×2 hit/correctness decomposition, and an instrumented cost pilot covering three models.

---

## 1. Introduction

Multimodal RAG is typically presented as a way to make smaller vision-language models competitive with larger ones: retrieve relevant images, place them in context, and let the model reason over them. The argument has two implicit premises — that retrieval surfaces the right evidence, and that the model can use it. This paper separates the two, because a system that fails the first premise cannot be rescued by improving the second.

We study a deliberately narrow but exhaustive setting. We freeze five vision-language models, four evidence conditions, one retrieval interface, one benchmark split, and one scoring rule, and then measure how accuracy changes when evidence changes. The protocol is frozen before evaluation: strategies and dimensions are selected on a 150-question development split, and the remaining 1,033 questions are evaluated once. Parsing failures, generation failures and budget exhaustion are scored as incorrect and retained in the denominator; nothing is retried or substituted.

The resulting evidence is best read as four layers, ordered by where in the pipeline the loss occurs.

**Layer 1: shared retrieval is not reliably beneficial.** Passing the same retrieved top-3 images to all five models changes accuracy by −2.52, −0.29, −0.87, +2.90 and +0.97 points respectively `[T2.qwen3vl_4b.S1_minus_S0_pp]` `[T2.qwen3vl_8b.S1_minus_S0_pp]` `[T2.gemma4_e2b.S1_minus_S0_pp]` `[T2.gemma4_e4b.S1_minus_S0_pp]` `[T2.qwen35_4b.S1_minus_S0_pp]`. Four of the five paired intervals cross zero; the single interval that excludes zero is +2.90 [+0.19, +5.71] for Gemma 4 E4B, and it is descriptive rather than corrected for multiplicity. We therefore do not claim that retrieval helps or hurts in general; we claim that in this protocol its effect is not distinguishable from zero for four of five models.

**Layer 2: correct evidence is beneficial.** Handing the model the annotated gold image improves accuracy by +6.39 to +10.36 points over no retrieval `[T2.gemma4_e2b.S2_minus_S0_pp]` `[T2.qwen3vl_8b.S2_minus_S0_pp]`, and by +3.68 to +11.81 points over shared retrieval `[T2_paired_intervals.md, S2−S1 rows]`, with no interval crossing zero. The evidence itself carries signal; the loss is upstream.

**Layer 3: retrieval imposes a ceiling.** The gold image is present in the retrieved top-3 for 516 questions and absent for 517 `[retrieval.top3_hit]` `[retrieval.top3_miss]`. For the 517 questions no model can benefit from retrieval under this interface, regardless of its reasoning ability.

**Layer 4: conditional on a hit, models differ in utilisation.** Among the 516 hit questions, the number answered correctly ranges from 219 for Gemma 4 E2B to 343 for Qwen3-VL 8B `[T3.gemma4_e2b.命中且答对]` `[T3.qwen3vl_8b.命中且答对]` — between roughly 42% and 66% of the same evidence. This is the part of the gap that is attributable to the model rather than to the retriever, and it is invisible in an aggregate accuracy table.

These four layers motivate our main artefact: a 2×2 decomposition of every evaluated question by whether the gold image was retrieved and whether the model answered correctly, with retrieval harm reported as a separate overlay rather than folded into the four cells. The decomposition makes retrieval quality and evidence utilisation separately readable, and it shows that aggregate accuracy conflates them.

We also examine whether the retrieval interface is stable enough to be a fixed component at all. Re-encoding the same 4,712-image corpus and 1,203 queries with batch size 16 and batch size 1 on a different software stack yields identical rankings — zero order changes, zero set changes `[a18.changed_order]` `[a18.changed_set]` — so the interface can be treated as frozen rather than re-tuned per environment.

Finally, we report what we cannot support. A post hoc oracle over three evidence-selection strategies improves on the best fixed strategy by +6.87 to +10.55 points `[gate.qwen3vl_4b.delta_pp]`, with rescue rates of 21.2%–23.6% `[gate.qwen3vl_4b.rescue_union_pct]`. This is headroom, not a result: no routing policy is trained or evaluated, routing cost is not measured, and the oracle is chosen after seeing outcomes. We therefore read it as a motivation for future work and an explicit bound on what our negative findings do and do not imply.

**Contributions.** (i) A frozen, failure-retaining evaluation protocol for multimodal RAG on vision-centric QA, with all selection decisions confined to a development split. (ii) A 2×2 hit-by-correctness decomposition that separates retrieval quality from evidence utilisation, plus an independent harm overlay. (iii) A cross-stack re-encoding check showing the retrieval interface is invariant to batch size, and a documented corpus-identity reconciliation between a published index and the study corpus. (iv) An instrumented cost pilot, explicitly scoped, with its own measurement limits stated.

**What we do not claim.** We do not claim a deployable router; that oracle headroom is realisable. We do not claim that retrieval is harmful in general; our intervals are descriptive and four of five cross zero. We do not claim a verified quality–cost Pareto frontier; the quality and cost measurements use different pools, splits and answer lengths, and we say so wherever a figure could be misread.

---

## 2. Related Work

**Multimodal RAG benchmarks.** MRAG-Bench (Hu et al., ICLR 2025) evaluates vision-centric question answering with a 1,353-question multiple-choice test set and explicitly separates direct answering from answering with candidate evidence; our S0 and S1 conditions are a direct application of that separation. VisDoM (Suri et al., NAACL 2025) targets visually rich multi-document QA, and MMDocRAG (Dong et al., NeurIPS 2025 D&B) studies evidence omission and cross-page fusion at document scale. Both differ from our setting in corpus structure (multi-page documents rather than a flat image pool) and in scoring (open-ended answers judged by an LLM rather than multiple-choice). We therefore do not report semantic accuracy on them and treat them as external-validation targets in future work.

**Evidence selection and utility.** Utility-MRAG (Luo et al., ACL 2026) ranks candidate visual evidence by its information gain on the downstream model's output distribution, estimated with a lightweight surrogate. It is the closest methodological relative of our evidence conditions, and the natural comparison point for our fixed-selection strategies. We do not reproduce the authors' surrogate. Our utility score is the raw logit of the token "True" from the same model that will consume the evidence `[utility.completed]`, which is not equivalent to a softmax over candidates: it is monotone in a single token's logit rather than in a normalised distribution, and it is not comparable across candidate sets of different size. We accordingly claim only a formal resemblance, and we state this limitation wherever the utility strategy appears.

**Routing and cost.** RAGRouter (Zhang et al., NeurIPS 2025) learns to route queries across RAG systems of different sizes, and presupposes two things our study questions: a learnable routing signal and a measurable per-path cost. Our gate analysis (Section 5) finds post hoc headroom of +6.87 to +10.55 points `[gate.qwen3vl_4b.delta_pp]` over the best fixed evidence strategy, but we deliberately stop short of claiming a router, because we neither train one nor measure the cost of invoking one.

**Query-side robustness.** V-QPP (Zeng et al., ICML 2026) benchmarks agentic query pre-processing and shows that visual input corruption degrades retrieval. Our distractor subset (S3) is a small, label-aware robustness probe in the same spirit; we report it as a diagnostic and do not draw general robustness conclusions from it.

**Reproducibility and artifact identity.** A recurring difficulty in reproducing retrieval results is that the same published number can refer to different objects. We encountered this directly: the published 18,955-row index and our study corpus of 4,712 unique images are defined over different byte encodings, and a naive hash intersection returns zero even though 4,282 images are shared `[index.intersection_q95]`. We report the reconciliation explicitly, and we restrict all quantitative statements in this paper to the study corpus.

---

## 3. Method

### 3.1 Data and splits

We use MRAG-Bench, whose public test split contains 1,353 multiple-choice questions, each with a query image and a candidate image pool. We fix a three-way split before any evaluation: 20 questions for pipeline smoke tests, 150 for development-time selection (evidence-selection strategy and embedding dimension), and the remaining 1,033 for evaluation. No selection step ever consults evaluation-set labels. All reported results use the 1,033-question split with a denominator of 1,033 per model and condition `[T1.qwen3vl_4b.S0.n]`.

### 3.2 Evidence conditions

- **S0 (no retrieval).** The model receives the question and the query image only.
- **S1 (shared retrieval).** Every model receives the same top-3 images in the same order, produced by one frozen retriever over one frozen corpus snapshot.
- **S2 (gold evidence).** The model receives the annotated gold image(s). This bounds what the model could achieve if retrieval were perfect; it is not a deployable condition.
- **S3 (distractor subset).** On a small approved subset, evidence is replaced by distractor or near-duplicate images. This is a diagnostic probe only.

S1 and S2 differ in evidence count (three images versus typically five). We therefore use the S1/S2 contrast to separate retrieval quality from evidence quality qualitatively, never as a same-denominator causal estimate, and we flag the difference wherever both are discussed.

### 3.3 Retrieval interface

The retriever is EmbeddingGemma-2 at revision `914f7f89142e33e77833254d9c9b90c3cef7303b`, run in fp32 with TF32 disabled and re-normalisation at the float32 level. Ranking uses `lexsort(-score, identity)`; the query image itself is removed before the top-k is taken, and ties are broken by image identity. The corpus consists of 4,712 unique images obtained by decoding the dataset's original bytes and re-encoding them as JPEG quality 95, so corpus identity is defined over the re-encoded bytes.

Because a retrieval interface is only useful as a fixed component if it is stable, we re-encode the same corpus and 1,203 queries on a second software stack with batch size 16 and batch size 1. Rankings are identical: zero order changes, zero set changes, zero top-3 changes `[a18.changed_order]` `[a18.changed_set]` `[a18.changed_top3]`. We report the interface as batch-invariant and treat it as frozen for the remainder of the study.

### 3.4 Scoring

Answers are extracted with a single fixed multiple-choice parser that validates the number of options per question; a response that cannot be parsed is scored incorrect and recorded as a parsing failure rather than retried or repaired. Generation uses greedy decoding with a fixed maximum length and a fixed seed. All conditions share the same prompt template and the same image ordering rules.

### 3.5 The 2×2 decomposition

For every evaluation question we record two binary facts: whether the gold image is present in the retrieved top-3, and whether the model answered correctly under S1. Crossing them yields four cells — miss-and-correct, miss-and-wrong, hit-and-wrong, hit-and-correct — which partition the 1,033 questions exactly `[T3.gemma4_e2b.命中且答对]`. Because hit is a property of the retriever rather than the model, the hit/miss marginals are identical across all five models (516/517 `[retrieval.top3_hit]` `[retrieval.top3_miss]`), which we use as a consistency check.

Retrieval harm is defined separately as the fraction of questions answered correctly under S0 but incorrectly under S1, and is reported as an overlay `[harm.qwen3vl_4b.pct]`. It overlaps the 2×2 cells by construction and is never summed with them.

### 3.6 Statistics

Comparisons are paired at the question level. Intervals resample the 564 query–gold-image connected components rather than individual questions, with 10,000 resamples and seed 42. All intervals are descriptive and were not pre-registered; we additionally report Holm-compatible joint rectangles, which coincide numerically with Bonferroni. We write "cannot exclude no difference" for intervals that cross zero, and we never interpret a descriptive interval as evidence of a universal effect.

### 3.7 Cost instrumentation

The cost pilot records, per request: a cold-start flag, pre-processing time, query-encoding time, retrieval time, generation time, end-to-end time, index residency (CPU RSS and GPU memory deltas separately), device-level peak memory sampled from `nvidia-smi` (kept separate from the PyTorch allocator peak), and model-switch cost. Corpus encoding is treated as an offline cost and never mixed into online latency. The pilot covers three models, 20 questions and one repeat per cell, with two generated tokens per request; every cost claim in this paper is scoped to that measurement and is labelled as such.

---

## 4. Results

### 4.1 Shared retrieval does not reliably improve accuracy

Table 1 reports accuracy for the five models under S0, S1 and S2 on the 1,033-question evaluation split.

| Model | S0 | S1 | S2 |
|---|---:|---:|---:|
| Qwen3-VL 4B | 621 | 595 | 717 |
| Qwen3-VL 8B | 583 | 580 | 690 |
| Gemma 4 E2B | 375 | 366 | 441 |
| Gemma 4 E4B | 397 | 427 | 493 |
| Qwen3.5 4B | 553 | 563 | 601 |

Paired differences tell the same story more sharply. S1−S0 is −2.52, −0.29, −0.87, +2.90 and +0.97 points respectively, and four of the five intervals cross zero. The only interval excluding zero belongs to Gemma 4 E4B (+2.90, [+0.19, +5.71]), and it is descriptive and uncorrected. We therefore conclude that under this interface shared retrieval is not distinguishable from no retrieval for four of five models, and is at most weakly positive for the fifth.

S2−S0, by contrast, is uniformly and substantially positive: +9.29, +10.36, +6.39, +9.29 and +4.65 points, none crossing zero. Replacing retrieved evidence with gold evidence is worth between 4.6 and 10.4 points, which is larger than the entire S1−S0 effect for every model. The evidence itself is informative; the retrieval step is where the benefit is lost.

### 4.2 Half the evaluation set cannot benefit from retrieval

The gold image appears in the retrieved top-3 for 516 of 1,033 questions and is absent for the other 517 `[retrieval.top3_hit]` `[retrieval.top3_miss]`. Because retrieval is shared, this ratio is a property of the retriever and is identical for all five models. Any accuracy ceiling computed over the full split inherits this bound: roughly half of the questions are unreachable by any evidence-use improvement.

### 4.3 Utilisation, not retrieval, explains most between-model variance

Table 2 crosses retrieval outcome with correctness. The hit and miss marginals are identical across models by construction, so every difference is in the interior of the table.

| Model | Miss & correct | Miss & wrong | Hit & wrong | Hit & correct |
|---|---:|---:|---:|---:|
| Qwen3-VL 4B | 259 | 258 | 180 | 336 |
| Qwen3-VL 8B | 237 | 280 | 173 | 343 |
| Gemma 4 E2B | 147 | 370 | 297 | 219 |
| Gemma 4 E4B | 191 | 326 | 280 | 236 |
| Qwen3.5 4B | 239 | 278 | 192 | 324 |

Two quantities follow. First, among the 516 hit questions, correct answers range from 219 (Gemma 4 E2B) to 343 (Qwen3-VL 8B), i.e. from 42% to 66% utilisation of the same evidence. Second, among the 517 miss questions, 147 to 259 are nonetheless answered correctly, which bounds how much of the reported accuracy can be attributed to retrieval at all: a substantial share of correct answers comes from the model's parametric knowledge.

This decomposition also shows why aggregate accuracy is misleading in this setting. Qwen3-VL 4B and Gemma 4 E4B differ by 168 questions in the hit-and-correct cell but by only 14 questions in aggregate S1 accuracy, because the two models compensate in opposite directions in the other cells.

### 4.4 Retrieval harm is real but modest

Defining harm as correct under S0 and incorrect under S1, harm rates are 10.16%, 7.65%, 10.84%, 8.33% and 9.68% `[harm.qwen3vl_4b.pct]`. This is a genuine cost of retrieval: between roughly one in thirteen and one in nine questions is made worse by adding evidence. Harm is an overlay on the 2×2 table, not a fifth cell, because a harmed question is by definition one of the wrong-answer cells.

### 4.5 The evidence-selection oracle leaves headroom, but not a result

A post hoc oracle over three fixed evidence-selection strategies (cosine similarity, random selection, and utility ranking) improves on the best fixed strategy by +8.52 points for Qwen3-VL 4B, with a descriptive interval of [6.81, 10.18] `[gate.qwen3vl_4b.delta_pp]` and a Holm-compatible rectangle of [5.83, 11.08]. Across models the gain ranges from +6.87 to +10.55 points, and the union of questions rescued by at least one path is 21.2%–23.6% `[gate.qwen3vl_4b.rescue_union_pct]`. The oracle is selected after observing outcomes and is not a policy. We report it because it bounds what a perfect selector could have achieved under this interface, and because it is the honest counterweight to our negative S1−S0 result: the absence of a gain from retrieval is not evidence that no better selection exists.

### 4.6 Cost pilot

The cost pilot covers three models, 20 questions, one repeat, and two generated tokens per request. End-to-end latency is 394 ms (P50) / 461 ms (P95) for Gemma 4 E2B, 464/535 ms for Gemma 4 E4B, and 531/654 ms for Qwen3-VL 4B. First-request query encoding costs 494 ms and pre-processing 179 ms; peak device memory across the session is 18.85 GB; loading a new model after a switch costs 8.37 s. Index construction is 588.16 s of corpus encoding plus 6.8 ms of loading.

Two observations follow, both scoped to this pilot. First, at two generated tokens the online cost is dominated by encoding and pre-processing rather than by generation, so any cost claim about "small models are cheaper" must be qualified by answer length. Second, index construction dominates the total cost by two orders of magnitude compared with per-query latency, which means amortisation assumptions matter more than per-request optimisations in this regime.

---

## 5. Discussion and Limitations

**What the results support.** Under a frozen interface and a failure-retaining protocol, adding retrieved evidence does not reliably improve accuracy on vision-centric QA. The loss is located upstream of the model: half the questions never receive the gold image, and among those that do, utilisation varies by more than 20 points across models. Improving retrieval hit rate and improving evidence utilisation are therefore separate research problems, and the 2×2 decomposition separates them in a single table.

**What the results do not support.** We do not claim that retrieval is harmful in general, that any particular selection strategy is optimal, or that the oracle headroom is realisable. We do not claim a verified quality–cost Pareto frontier: our quality measurements and our cost pilot use different pools, different splits and different answer lengths, and we state this at every figure.

**Limitations.** (1) *Single benchmark.* All quantitative results are on MRAG-Bench; MMDocRAG and VisDoM are discussed but not evaluated with semantic scoring, so no cross-dataset claim is made. (2) *Unreproduced utility.* Our utility score is a raw single-token logit, not the softmax-normalised surrogate of Utility-MRAG; the two are formally similar but not equivalent, and no equivalence test is performed. (3) *Partial distractor study.* The distractor subset is small, label-aware and AI-assisted rather than human-audited, so it supports diagnostics only. (4) *Scoped cost measurement.* The pilot covers three of five models, 20 questions and two generated tokens; it cannot support a full cost curve. (5) *Vocabulary asymmetry.* The five models use different visual tokenisers, so evidence images are not token-equivalent across models; we equalise image content and ordering, not token budgets. (6) *Descriptive statistics.* All intervals are descriptive and unregistered; four of five S1−S0 intervals cross zero, which we report as "cannot exclude no difference" rather than as a null result.

---

## 6. Ethics Statement

The study uses a public benchmark and public model weights; no human subjects, no private data and no user-generated content are involved. All evaluations run on released artifacts, and no model is fine-tuned. The main ethical risk of this line of work is over-claiming: negative or null results about retrieval can be misread as evidence that retrieval is useless, and oracle-based headroom can be misread as a deployable gain. We mitigate this by stating both the frozen scope of every measurement and the specific claims we decline to make, and by keeping descriptive and confirmatory language separate throughout.
