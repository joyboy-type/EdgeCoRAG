# EdgeCoRAG — English draft v1 (A→B→C main line)

Target: ACL (main / Findings), double-blind, 8-page limit + unlimited references.
Revision basis: `reports/paper_20261021/OUTLINE_CLAIMS_20261024.md`;
new numbers only from `r1_equal_count_20261024.json`, `r2_dimension_compress_20261024.json`,
`r3_normal_output_cost_20261024.json`. Frozen numbers unchanged.

---

## Title (working)

**When Retrieved Evidence Does Not Help: A Frozen-Protocol Audit of Multimodal RAG on Vision-Centric QA**

---

## Abstract

Multimodal retrieval-augmented generation is routinely justified by the claim that retrieved visual evidence compensates for a model's limited visual knowledge. We audit that claim under a frozen protocol: five vision-language models, four evidence conditions, one retrieval interface, 1,033 questions, and failure-retaining scoring. Matching the image count at three, correct evidence still yields a net gain of +5.96 to +10.36 percentage points over retrieved evidence, with every interval above zero, although only two of five models meet a pre-registered 70% retention criterion relative to the five-image reference. The binding constraints are availability and utilisation: the gold image reaches the retrieved top-3 for 516 of 1,033 questions (49.95%), and on that shared hit set the models answer correctly between 42.44% and 66.47% of the time. Finally, truncating the index from 768 to 256 dimensions changes no retrieval metric by more than 1.50 percentage points while cutting vector payload to one third.

---

## 1. Introduction

Multimodal RAG is typically presented as a remedy for a model's limited visual knowledge: retrieve relevant images, place them in context, and let the model reason over them. The argument carries two implicit premises. The first is that retrieval surfaces the evidence a question actually needs; the second is that the model can exploit that evidence once surfaced. These premises are almost never tested in isolation. They are usually collapsed into one aggregate comparison — accuracy with retrieval versus accuracy without — which conflates the quality of the retriever with the competence of the reader.

The cost of that conflation is visible in the originating benchmark. MRAG-Bench reports that adding ground-truth evidence raises human accuracy from 38.47% to 71.63%, an absolute gain of 33.16 percentage points, whereas the same intervention raises GPT-4o from 68.68% to 74.50%, a gain of only 5.82 points (Hu et al., 2025; author-reported, 1,353 multiple-choice questions, top-5 retrieval). The evidence is identical by construction, yet the gains differ by more than a factor of five. An evaluation that reports only the post-retrieval score records this difference without explaining it, and a system built on such an evaluation cannot know whether its next unit of effort should go to retrieving better images or to making the model use the images it already has.

We treat the question as an empirical audit rather than a method proposal. We introduce no new retriever, generator, or router. We freeze a protocol — five vision-language models, four evidence conditions, one retrieval interface, one benchmark split — and report three measurements in a fixed order.

**A. Correct evidence at matched image count.** The natural objection to any ground-truth condition is that it supplies more images than retrieval does. We therefore hold the count fixed at three: on the 956 questions whose gold set contains five images, we compare three retrieved images against the first three gold images in their original order. The net gain survives count matching, at +5.96 to +10.36 percentage points with every interval above zero. Against a pre-registered retention criterion, however, only two of the five models retain at least 70% of the five-image net gain at the interval's lower bound. The gain is therefore not an artefact of image count, but it is not uniform across models either.

**B. Availability and utilisation.** Having established that correct evidence helps, we ask how much of it the interface actually delivers and how much of what it delivers the models use. The gold image reaches the retrieved top-3 for 516 of 1,033 questions — 49.95% — and the same 516 questions are hit for all five models, because the hit event is a property of the retriever. On that shared hit set, conditional accuracy ranges from 42.44% (Gemma 4 E2B) to 66.47% (Qwen3-VL 8B). Roughly half the evaluation set is unreachable under this interface, and among the reachable half the models differ by more than 24 percentage points.

**C. Index compression.** Finally we ask whether the retrieval side can be made cheaper without changing what it returns. On the current 4,712-image pool with all 1,203 queries freshly encoded in FP32, truncating the 768-dimensional embeddings to 256 and renormalising changes no retrieval metric by more than 1.50 points — probability-scaled points for the hit and recall metrics, percentage-point units for MRR — across top-1, top-5, top-10, macro Recall@5 and full MRR, while the corpus matrix payload falls to one third. We report each metric separately rather than the aggregate, because the top-1 loss (−1.50) and the top-5 gain (+0.33) point in opposite directions.

**Contributions.** (i) A frozen, failure-retaining protocol for multimodal RAG in which all selection decisions are confined to a 150-question development split and the 1,033 evaluation questions are scored once. (ii) An equal-image-count control that separates the effect of evidence correctness from the effect of evidence count, together with a pre-registered retention criterion applied uniformly to all five models. (iii) A joint availability-and-utilisation reading on a shared hit set, with the hit set verified to be identical across models rather than merely equal in size. (iv) A compression audit on the current pool that reports five retrieval metrics and the theoretical vector payload separately, with a stated tolerance rule.

**What we do not claim.** We do not claim a causal effect of evidence correctness; the comparison is observational and conditions on the same questions. We do not claim that image count is irrelevant; we claim only that the net gain persists when count is held fixed on the 956-question subset. We do not claim that retrieval is harmful or useful in general; the paired intervals that cross zero are reported as "cannot exclude no difference". We do not claim statistical equivalence for the compressed index; the tolerance rule is a pre-registered loss threshold, not an equivalence test. We do not reproduce the Utility-MRAG surrogate and claim only a formal resemblance. Finally, we do not report a long-answer cost curve: our two-budget probe produced no length separation, and we record that as a limitation rather than an estimate.

---

## 2. Related Work

**Multimodal RAG benchmarks.** MRAG-Bench (Hu et al., ICLR 2025) establishes a vision-centric protocol in which candidate images are supplied to a reader and scored by multiple-choice accuracy, and explicitly separates direct answering from answering with candidate evidence; our S0 and S1 conditions are a direct application of that separation. MMDocRAG (Dong et al., NeurIPS 2025, Datasets and Benchmarks) extends the setting to visually rich documents with citation-aware evaluation, VisDoM (Suri et al., NAACL 2025) targets multi-document question answering over visually rich elements, and VQQP (Zeng et al., ICML 2026) benchmarks visual query pre-processing as a separate stage. These works define what to measure under retrieval; they report aggregate post-retrieval accuracy and therefore do not separate the retriever's contribution from the reader's. We keep MRAG-Bench as the substrate and report the separation that the aggregate leaves implicit.

**Evidence selection and utility.** Utility-MRAG (Luo et al., ACL 2026) ranks candidate visual evidence by its estimated information gain on the downstream model's output distribution, using a lightweight surrogate. We did not reproduce that surrogate, and we do not claim to. Our utility score, used only in an appendix-level diagnostic, is the raw logit of the token "True" from the consuming model; it is monotone in a single token's logit rather than in a normalised distribution over candidates, and it is not comparable across candidate sets of different size. We therefore describe the two as formally similar and state the difference wherever the score appears.

**Routing and cost.** RAGRouter (Zhang et al., NeurIPS 2025) learns to route queries across retrieval-augmented systems and presupposes a learnable routing signal plus a measurable per-path cost. Our audit supports neither premise: with availability at 49.95% and utilisation varying by model, the routing signal would have to be estimated per model and per question, and our cost probe did not produce a length-dependent cost curve. We accordingly make no routing claim, deployable or otherwise.

**Relevance versus utilisation.** The distinction between retrieving something relevant and retrieving something useful predates multimodal RAG; the classical retrieve-then-read decomposition treats recall and reader accuracy as separate factors. What our setting adds is a measured property rather than a conceptual one: under shared retrieval the hit event is identical across models, so the two factors can be estimated on the same denominator without a modelling assumption. The closest prior work is Pandey (2026), a preprint that separates retrieval-quality failure from utilisation failure in text-only RAG by conditioning on the model's parametric knowledge. We do not claim to have first identified the phenomenon. Our contribution is narrower: we verify the shared-hit-set property in the multimodal setting, apply it to an equal-image-count control, and report per-model conditional accuracy as an observed proportion rather than as a model constant.

**Reproducibility and artifact identity.** A recurring difficulty in reproducing retrieval results is that the same published number can refer to different objects. We encountered this directly: the published 18,955-row index and our study corpus of 4,712 unique images are defined over different byte encodings, and a naive hash intersection returns zero even though 4,282 images are shared after key mapping. We report the reconciliation explicitly and restrict all quantitative statements to the study corpus.

---

## 3. Method

### 3.1 Data and splits

We use MRAG-Bench, whose public test split contains 1,353 multiple-choice questions, each with a query image and a candidate image pool. We fix a three-way split before any evaluation: 20 questions for pipeline smoke tests, 150 for development-time selection (evidence-selection strategy and embedding dimension), and the remaining 1,033 for evaluation. No selection step consults evaluation-set labels. All main denominators are stated per analysis: 1,033 for the availability read, 956 for the equal-count control, and 1,203 for the compression audit.

### 3.2 Evidence conditions

- **S0 (no retrieval).** The question and the query image only.
- **S1 (retrieved evidence).** Three images from one frozen retriever over one frozen corpus snapshot, in a fixed order, identical for all five models.
- **S2 (gold evidence, five images).** The annotated gold images in their stored order. For the 77 `Incomplete` questions the annotated set contains a single image rather than five.
- **S2@3 (gold evidence, three images).** The first three gold images in stored order, with no reordering, selection or padding. Used only in the equal-count control.
- **S3 (distractor subset).** A small label-aware subset in which evidence is replaced by distractor images. It is a diagnostic probe; its counts are too small to carry a main-text claim and it is reported only in the appendix.

The count structure matters and we state it wherever it applies. Of the 1,033 questions, 956 have five gold images and 77 have one. The equal-count control is therefore defined on the 956-question subset, where S1 supplies three images and S2@3 supplies three. The full 1,033-question version of the same contrast is not count-matched (956×3 plus 77×1) and is reported only as a secondary table in the appendix.

### 3.3 Retrieval interface

The retriever is EmbeddingGemma-2 at revision `914f7f89142e33e77833254d9c9b90c3cef7303b`, run in FP32 with TF32 disabled and L2 renormalisation performed at the float32 level. Ranking uses `lexsort(-score, identity)`; the query image itself is removed before the top-k is taken and ties break on image identity. The corpus consists of 4,712 unique images obtained by decoding the dataset's original bytes and re-encoding them as JPEG quality 95, so corpus identity is defined over the re-encoded bytes.

We verified that the interface is stable enough to be treated as a fixed component. Re-encoding the same corpus and 1,203 queries on a second software stack with batch size 16 and batch size 1 yields zero order changes, zero set changes and zero top-3 changes. We report this as a receipt-level reading of the interface, not as a general invariance theorem.

### 3.4 Compression protocol

For the compression audit we reuse the stored 4,712×768 FP32 corpus matrix and encode all 1,203 registered queries under the same protocol, because the archived query matrix contained only five rows and could not be reused. Each dimension `d ∈ {128, 256, 512, 768}` is obtained by truncating both matrices to the first `d` columns, renormalising each row to unit L2 norm in float32, taking float32 dot products, and sorting by score descending with identity as the tie-break. Exact query self-matches are excluded under the same rule for all four dimensions. Retrieval metrics are top-1, top-5 and top-10 any-hit, macro Recall@5 with out-of-pool gold retained in the denominator, and full MRR computed over the complete ordering rather than truncated at 10. The pre-registered tolerance rule is: a dimension fails if any of the five metrics drops by strictly more than 0.03 (three percentage points, or three percentage-point units for MRR); a drop of exactly 0.03 does not trigger.

### 3.5 Scoring

Answers are extracted with one fixed multiple-choice parser that validates the option count per question. A response that cannot be parsed is scored incorrect and recorded as a parsing failure; it is never retried or repaired. Generation uses greedy decoding with a fixed maximum length and a fixed seed, and all conditions share one prompt template and one image-ordering rule.

### 3.6 Availability and utilisation

For each question and model we record whether the gold image is present in the retrieved top-3 and whether the answer is correct. Because the retriever is shared, the hit set is identical across models — we verify that it is the same set of questions, not merely the same count. We write `r` for the availability, `516/1,033 = 49.95%`, and `u(m)` for the conditional accuracy of model `m` on that shared hit set. `u(m)` is an observed proportion on this hit set; it is not a model constant, and we do not use it to predict accuracy on other question sets or under other strategies.

### 3.7 Statistics

Three interval practices appear in this paper and are never interchanged.

For the equal-count control (Table A1) and for the supporting retrieved/gold contrasts (Table S1), intervals are question-level, scenario-stratified paired bootstrap with 2,000 resamples and seed 42, reported at the 95% percentile with linear interpolation. They are descriptive and carry no multiplicity correction. They are not the 564-component cluster intervals used elsewhere in the project, and the two are never substituted for one another.

For availability and utilisation (Tables B1 and B2), intervals are question-level bootstrap with 10,000 resamples and seed 42, descriptive. This family is not scenario-stratified and must not be mixed with the 2,000-resample family above.

For the compression audit (Tables C1 and C2), no interval is computed; the pre-registered tolerance rule is applied to point estimates and the table captions say so.

We write "cannot exclude no difference" for any interval that crosses zero, and we avoid the words "significant", "equivalent" and "proven" throughout, because none of the three interval families supports those readings.

---

## 4. Results

### 4.1 A — Correct evidence at matched image count

Table A1 reports the equal-count contrast on the 956 questions whose gold set contains five images. S1 supplies three retrieved images; S2@3 supplies the first three gold images in stored order. Both conditions therefore place three evidence images in context, in addition to the query image.

**Table A1.** Equal-image-count contrast, denominator 956 questions, three evidence images in both conditions (query image additional). Intervals are question-level scenario-stratified paired bootstrap (2,000 resamples, seed 42), descriptive, 95% percentile, in percentage points. `Δ5` is the original five-image gold contrast on the same 956 questions, for reference only.

| Model | S1 correct | S2@3 correct | Δ3 pp [95% interval] | Δ5 pp | Point ratio | Lower-bound ratio | Criterion |
|---|---:|---:|---|---:|---:|---:|---|
| Qwen3-VL 4B | 567 | 665 | +10.25 [+7.53, +12.87] | +12.03 | 85.22% | 62.61% | not met |
| Gemma 4 E2B | 351 | 408 | +5.96 [+3.24, +8.58] | +7.85 | 76.00% | 41.33% | not met |
| Gemma 4 E4B | 403 | 462 | +6.17 [+3.45, +8.68] | +7.11 | 86.76% | 48.53% | not met |
| Qwen3-VL 8B | 560 | 659 | +10.36 [+7.95, +12.66] | +10.88 | 95.19% | 73.08% | met |
| Qwen3.5 4B | 540 | 605 | +6.80 [+4.18, +9.52] | +3.56 | 191.18% | 117.57% | met |

All five net gains are positive and every interval lies strictly above zero. The five-image gold gain on the same 956 questions is larger for four models and smaller for one; the point ratios therefore range from 76.00% to 191.18%. The pre-registered criterion, fixed before execution, requires both a positive lower bound and a lower-bound ratio of at least 70% against the same-956-question five-image reference. Under that criterion, Qwen3-VL 8B (73.08%) and Qwen3.5 4B (117.57%) meet retention and the other three do not. A ratio above 100% means only that the three-image net difference is larger than the five-image net difference on the same questions; it is a descriptive ratio of two net differences, not a causal contribution and not evidence that fewer images are better.

Table A2 gives the transition composition of the same contrast, which the net gain alone hides.

**Table A2.** Transition composition for the equal-count contrast, denominator 956 questions per model, three evidence images in both conditions. Percentages are of the 956-question denominator; intervals are the same 2,000-resample scenario-stratified paired bootstrap in percentage points. Rescue = S1 wrong and S2@3 correct; harm = S1 correct and S2@3 wrong; unchanged = identical correctness, split into same-correct and same-wrong.

| Model | Rescue | Harm | Unchanged | Same correct / same wrong |
|---|---:|---:|---:|---|
| Qwen3-VL 4B | 139, 14.54% [12.24, 16.74] | 41, 4.29% [3.03, 5.54] | 776, 81.17% [78.66, 83.68] | 526 / 250 |
| Gemma 4 E2B | 118, 12.34% [10.36, 14.44] | 61, 6.38% [4.92, 7.95] | 777, 81.28% [78.87, 83.58] | 290 / 487 |
| Gemma 4 E4B | 115, 12.03% [9.94, 14.02] | 56, 5.86% [4.50, 7.43] | 785, 82.11% [79.71, 84.42] | 347 / 438 |
| Qwen3-VL 8B | 128, 13.39% [11.40, 15.48] | 29, 3.03% [1.99, 4.18] | 799, 83.58% [81.28, 85.88] | 531 / 268 |
| Qwen3.5 4B | 123, 12.87% [10.77, 14.96] | 58, 6.07% [4.71, 7.53] | 775, 81.07% [78.56, 83.47] | 482 / 293 |

Two readings follow. First, the net gains are not produced by uniform improvement: every model has both rescues and harms, and the harm rates range from 3.03% to 6.38% of the same 956 questions. Second, the composition differs even when the net gain is nearly identical. Gemma 4 E2B and Gemma 4 E4B post net gains of +5.96 and +6.17 points, separated by roughly two questions, yet their transition compositions are not close: E2B rescues 118 and harms 61, E4B rescues 115 and harms 56, and their same-correct counts differ by 57 questions (290 versus 347). The two models reach almost the same net figure by moving different numbers of questions in opposite directions from different starting points. A net-gain table cannot show that, and a single aggregate accuracy figure certainly cannot.

The secondary table in the appendix repeats the contrast over all 1,033 questions. That version is not count-matched — the 77 `Incomplete` questions carry one image in both conditions — and we do not use it for the main claim, because the question composition differs from the 956-question subset by construction.

### 4.2 B — Availability and utilisation

Table B1 reports the availability of the interface and the conditional accuracy of each model on the shared hit set.

**Table B1.** Availability and post-hit accuracy. Denominator for availability is 1,033 questions; the hit set is 516 questions and is identical across the five models (same question set, not merely the same count). Conditional accuracy is correct answers over 516. Intervals are question-level bootstrap (10,000 resamples, seed 42), descriptive, 95% percentile.

| Quantity | Value | 95% interval |
|---|---:|---|
| Availability `r` = 516 / 1,033 | 49.95% | [46.95%, 52.95%] |
| Qwen3-VL 4B: 336 / 516 | 65.12% | [60.97%, 69.25%] |
| Qwen3-VL 8B: 343 / 516 | 66.47% | [62.35%, 70.46%] |
| Qwen3.5 4B: 324 / 516 | 62.79% | [58.53%, 66.88%] |
| Gemma 4 E4B: 236 / 516 | 45.74% | [41.39%, 50.09%] |
| Gemma 4 E2B: 219 / 516 | 42.44% | [38.22%, 46.64%] |

Two facts stand out. First, the interface does not deliver the gold image for slightly more than half of the evaluation set: 517 of 1,033 questions are hit for no model, no matter how well the model reasons. Second, among the questions where the evidence is delivered, the models disagree by a wide margin: 42.44% to 66.47%, a spread of 24.03 percentage points on the identical 516 questions. That spread is a range across five per-model proportions on one question set. It is not a pooled estimate, not a confidence interval for a common quantity, and not a model constant that can be transferred to other question sets or other strategies.

Table B2 crosses the hit event with correctness to show where the accuracy actually comes from.

**Table B2.** Hit-by-correctness partition, denominator 1,033 questions per model. Hit = gold image in retrieved top-3 (516 questions, identical across models); miss = 517 questions. Cells sum to 1,033 within each row.

| Model | Miss & correct | Miss & wrong | Hit & wrong | Hit & correct |
|---|---:|---:|---:|---:|
| Qwen3-VL 4B | 259 | 258 | 180 | 336 |
| Qwen3-VL 8B | 237 | 280 | 173 | 343 |
| Gemma 4 E2B | 147 | 370 | 297 | 219 |
| Gemma 4 E4B | 191 | 326 | 280 | 236 |
| Qwen3.5 4B | 239 | 278 | 192 | 324 |

The miss-and-correct column is the part of the accuracy that owes nothing to the retrieved evidence, and it ranges from 147 to 259 questions, i.e. from 14.2% to 25.1% of the evaluation set. The hit-and-correct column ranges from 219 to 343. Aggregate accuracy combines these two columns with the two wrong-answer columns, and because the miss marginals are fixed at 517 for every model, every between-model difference is necessarily interior to the table. The split is exact: Qwen3-VL 4B leads Gemma 4 E4B by 168 questions in aggregate S1 accuracy (595 versus 427), and that gap decomposes without remainder into 100 questions of hit-and-correct (336 versus 236) and 68 questions of miss-and-correct (259 versus 191). An aggregate table reports only the sum. A reader who observes a 168-question gap cannot tell from it whether the lower-scoring model retrieves worse, uses delivered evidence worse, or knows less without evidence, because the total is compatible with many splits of the same size.

### 4.3 C — Index compression on the current pool

Table C1 reports all four dimensions on the current 4,712-image pool with all 1,203 queries encoded under one protocol.

**Table C1.** Dimension compression on the current pool. Denominator 1,203 questions; gold annotations are typically five images per question and one for `Incomplete`. This is pure retrieval ranking: `k` in top-k is the evaluation cut-off, not a generation input count, and no 3-image or 5-image generation condition is set here. Payload is the theoretical byte size of the corpus matrix (`4712 × d × 4`), not an index file size, not GPU memory and not end-to-end cost.

| Dimension | top-1 | top-5 | top-10 | Macro Recall@5 | Full MRR | Payload (MiB) |
|---|---:|---:|---:|---:|---:|---:|
| 128 | 424/1,203 | 791/1,203 | 904/1,203 | 0.290316 | 0.489136 | 2.3008 |
| 256 | 433/1,203 | 819/1,203 | 931/1,203 | 0.307190 | 0.501250 | 4.6016 |
| 512 | 447/1,203 | 814/1,203 | 927/1,203 | 0.306692 | 0.507150 | 9.2031 |
| 768 | 451/1,203 | 815/1,203 | 925/1,203 | 0.307190 | 0.507917 | 13.8047 |

Table C2 gives the five-metric comparison at the pre-registered operating point of 256 against the 768 baseline. No new interval is computed for this comparison; the pre-registered rule is a point-estimate tolerance.

**Table C2.** Five-metric comparison, 256 versus 768 dimensions, denominator 1,203. Differences are probability × 100; the MRR row is in percentage-point units, which is not the same as an accuracy percentage point.

| Metric | 256 | 768 | Difference |
|---|---:|---:|---:|
| top-1 any-hit | 0.359933500 | 0.374896093 | −1.496259 |
| top-5 any-hit | 0.680798005 | 0.677472984 | +0.332502 |
| top-10 any-hit | 0.773898587 | 0.768911056 | +0.498753 |
| Macro Recall@5 | 0.307190357 | 0.307190357 | +0.000000 |
| Full MRR | 0.501249913 | 0.507917366 | −0.666745 |

All five differences are strictly smaller than the pre-registered 3 percentage-point tolerance, so the 256-dimensional index does not fail the rule on this question set. The largest loss is the top-1 any-hit rate, at 1.50 points, and it is reported alongside a top-5 gain and a top-10 gain because the metrics do not move together. We do not describe the result as lossless or statistically equivalent: the rule is a declared threshold, applied once, and it does not exclude the possibility that a different pool or a different query distribution would cross it. The 128- and 512-dimensional rows are reported in full in the appendix; 256 is the pre-registered operating point, not a dimension selected after seeing the table.

The corresponding payload figures are 4,825,088 bytes at 256 dimensions against 14,475,264 bytes at 768, exactly one third. That is a statement about the corpus matrix elements only. It is not a measurement of index file size, of resident GPU memory, of switching cost, or of any end-to-end saving.

### 4.4 Supporting measurements

**Retrieved evidence versus no retrieval.** Table S1 reports the two contrasts that motivate the count-controlled design in A. It is placed here rather than in the main sequence because the two contrasts are not count-matched: S1 delivers three images while S2 delivers typically five.

**Table S1.** Retrieved and gold evidence against no retrieval, denominator 1,033 questions, split `frozen_test`. S1 supplies three retrieved images; S2 supplies the annotated gold set, typically five images and one for the 77 `Incomplete` questions. Intervals are question-level, scenario-stratified paired bootstrap (2,000 resamples, seed 42) — the same family used in Table A1 — reported at the 95% percentile with linear interpolation, descriptive, without multiplicity correction, in percentage points. They are not the 564-component cluster intervals used elsewhere in the project.

| Model | S1 − S0 pp [95% interval] | S2 − S0 pp [95% interval] |
|---|---|---|
| Qwen3-VL 4B | −2.52 [−5.13, +0.19] | +9.29 [+6.68, +12.29] |
| Qwen3-VL 8B | −0.29 [−2.61, +2.13] | +10.36 [+7.74, +12.97] |
| Gemma 4 E2B | −0.87 [−3.49, +1.84] | +6.39 [+3.58, +9.20] |
| Gemma 4 E4B | +2.90 [+0.19, +5.71] | +9.29 [+6.39, +12.20] |
| Qwen3.5 4B | +0.97 [−1.74, +3.78] | +4.65 [+1.65, +7.74] |

Four of the five `S1 − S0` intervals cross zero, so for those four models we cannot exclude no difference between retrieving three images and retrieving nothing; we do not convert that into a claim that retrieval is neutral or harmful. The single interval excluding zero belongs to Gemma 4 E4B at +2.90 [+0.19, +5.71], and it is descriptive and uncorrected for multiplicity, so we also decline to call it a benefit. `S2 − S0` is positive for every model, between +4.65 and +10.36 points, with no interval crossing zero. The asymmetry between the two contrasts is what motivates A: because S1 and S2 also differ in image count, the `S2 − S0` reading cannot by itself separate the value of correct evidence from the value of extra images, and the equal-count control supplies that separation.

**Short-answer cost profile.** On the same RTX 4090, with a fixed 20-question set, three images of cosine evidence plus the query image, and one formal request per question per budget, end-to-end P50/P95 latency is 507.5/642.9 ms for Qwen3-VL 4B, 495.2/534.3 ms for Gemma 4 E2B, and 493.8/564.0 ms for Gemma 4 E4B at a 2-token cap. At a 256-token cap the corresponding figures are 543.3/640.2, 479.4/522.5 and 496.5/576.8 ms. Sampled peak device memory is 11.538, 12.548 and 17.851 GiB respectively. These are descriptive statistics over 20 questions, not a latency distribution and not a cost model; the pipeline is the instrumented E3 route, which supplies fixed cosine evidence and is not the official S1 condition.

**Interface and identity receipts.** Two infrastructure readings support the frozen-protocol claim and are reported for that purpose only. Re-encoding the corpus and 1,203 queries with batch size 16 versus batch size 1 produced zero order, set and top-3 changes. Reconciling the published 18,955-row index against the 4,712-image study corpus by mapped byte identity yields 4,282 shared images and 430 absent, of which 415 are query images and 15 carry a gold role. The reconciliation depends on the q95 byte domain; a raw-byte intersection returns zero and must not be used.

---

## 5. Discussion

The three measurements answer different questions and only jointly constrain the design space.

A establishes that the value of correct evidence is not an artefact of supplying more images: at three images against three images, all five models gain between +5.96 and +10.36 points. But the retention analysis shows that this value is not uniformly convertible. Against the five-image reference on the same questions, three of five models retain less than 70% at the interval's lower bound. A practitioner who has budget for three images cannot assume that two thirds of the five-image benefit survives; on this question set, for three of five models, it does not.

B explains where the remaining value is lost. The interface delivers the gold image for 49.95% of questions, so half the evaluation set is unreachable through better reasoning alone. Among the reachable half, conditional accuracy spans 42.44% to 66.47%. The two constraints are of different kinds: availability is a property of the retriever and is common to all models, while utilisation is a property of the model and varies with it. An aggregate table reports only the sum of two different sources of correct answers, those obtained from delivered evidence and those obtained without it, and the model with the highest utilisation need not be the model with the highest aggregate accuracy. In our data Qwen3-VL 4B posts a higher aggregate S1 accuracy than Qwen3-VL 8B (595 versus 580) despite a lower utilisation on the shared hit set (65.12% versus 66.47%), because its miss-and-correct count is 22 questions higher (259 versus 237) and its hit-and-correct count 7 questions lower (336 versus 343).

C shows that embedding width is a comparatively cheap lever on this pool. Truncating to 256 dimensions moves no retrieval metric by more than 1.50 points — the largest movement is a 1.50-point top-1 loss — while the corpus matrix payload falls to one third. We stop short of the natural inference. A sub-tolerance change in five retrieval metrics does not imply that accuracy, index size in bytes, resident memory or end-to-end cost are unaffected, because none of those quantities was measured in this audit. What C does establish is narrower and still useful: on this pool, the choice of embedding width is not where a large and easily detectable loss is hiding, so a design decision about index width can be made on the retrieval metrics alone without a hidden accuracy penalty of the size that A and B report.

Taken together, the measurements argue against the single aggregate question "does retrieval help". Under this interface, retrieved evidence does not reliably improve accuracy, while correct evidence does — and the gap between those two statements is exactly the availability and utilisation gap that B measures. The practical implication is that a multimodal RAG system should be evaluated on at least two numbers, how often the needed evidence is delivered and how often the model converts delivered evidence into a correct answer, rather than on one accuracy figure that mixes them with parametric knowledge.

---

## 6. Limitations

**No length-dependent cost was measured.** We attempted to estimate the marginal cost of longer answers by running the same 20 questions and the same three-model set at a 2-token and a 256-token cap. Both budgets produced a mean of 2.00 generated tokens for all three models, a ratio of 1.00, below the pre-registered 3× threshold. Under the pre-registered rule this is recorded as "length not effective": the marginal cost per 100 additional output tokens is not estimable and is reported as null rather than zero. The reason is visible in the task and the prompt, which ask for a single option letter and permit native end-of-sequence; we did not force continuation and did not rerun to manufacture length. No long-answer cost claim is made anywhere in this paper.

**Single benchmark.** All quantitative results are on MRAG-Bench. MMDocRAG and VisDoM are discussed but not evaluated with semantic scoring under this protocol, so no cross-dataset claim is made.

**Unreproduced utility surrogate.** Our utility score is a raw single-token logit, not the normalised surrogate of Utility-MRAG. The two are formally similar only, and no equivalence test is performed.

**Partial distractor subset.** The S3 distractor subset is small, label-aware and AI-assisted rather than human-audited; it supports a diagnostic appendix, not a main-text claim.

**Scoped cost measurement.** The cost profile covers three of five models, 20 questions, three cosine evidence images and one formal request per cell. It is a short-answer profile on one device and it cannot support a cost curve, a quality–cost frontier, or any device- or energy-level claim. Energy figures, where reported, are GPU power samples over the request window and are not whole-system measurements.

**Descriptive statistics.** All intervals in this paper are descriptive and none is corrected for multiplicity. The equal-count control uses 2,000-resample scenario-stratified intervals; availability and utilisation use 10,000-resample question-level intervals; the compression audit uses a point-estimate tolerance rule with no interval. These three families are not interchangeable and are never combined.

**Composition and hardware boundaries.** The equal-count control covers 956 of 1,033 questions; the remaining 77 are single-image `Incomplete` questions and are reported separately, without mechanism attribution. The new generation runs for the equal-count control used an RTX 4090 session, while the S1 records it is paired against are historical; the pairing is at the question level and the cross-hardware difference is retained as an interpretive boundary, not as a claim of bit-identical reproduction.

**Proportions are not constants.** The per-model conditional accuracies in B are observed proportions on this hit set. We do not treat them as model constants, do not extrapolate them to other question sets or strategies, and do not attribute them to a mechanism.

---

## 7. Ethics Statement

The study uses a public benchmark and public model weights; no human subjects, no private data and no user-generated content are involved. All evaluations run on released artifacts and no model is fine-tuned. The main ethical risk of this line of work is over-claiming: null or boundary results about retrieval can be misread as evidence that retrieval is useless, and post hoc or counterfactual quantities can be misread as deployable gains. We mitigate this by stating the frozen scope of every measurement, by keeping descriptive and confirmatory language separate, and by listing the specific claims we decline to make.

---

## Appendix (to be assembled)

- A1/A2 on the full 1,033 questions and on the 77 single-image questions, clearly marked as not count-matched.
- C1 full four-dimension table with per-split breakdown (smoke 20 / dev 150 / frozen 1,033).
- S3 distractor subset counts (dev 5 / holdout 2 / frozen 29) with the AI-assisted, label-aware disclosure.
- Judge-based five-dimension scores for the development split, reported separately from multiple-choice accuracy.
- Reproduction commands and input digests for every table.
