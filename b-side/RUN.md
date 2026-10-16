# EdgeCoRAG B v1.8.0 — actual dev receipt and assisted review

Based on B7ccef5e + merged A main c0e0931d8ad8d640e9c8002516fea43a70049831. Only b-side/ is changed;
root README/.gitignore and A files are preserved. This is NOT completion of all
rental preparation. No weights, real processor/model loading or GPU inference
were run. Actual offline results are in offline_checks.json; older accepted
sample/scorer/synthetic suites were not rerun.

## A status and frozen main contract

A split v2 is RECEIVED:20/150/150/1033, file hashes/counts/disjointness/1353 coverage
and seven named B questions in dev were independently checked. Do not keep saying
A has not repaired the split. v2 uses per-question fallback:cross-split source/
image dependence is NOT isolated. Aggregate label exposure is disclosed separately
from named per-question debugging. configs/debug_question_ids.json now records all
150 authorized dev targets, including the prior seven; it does not claim global
exhaustiveness. Candidate source-image exposure is logged separately from source
question/answer access. The20 smoke list/hash
index were read as metadata only, not as question/answer/image content.

A round3 reports four splits with separate S1/S2/S3 packages. Only the three dev
Release assets were received and checked in cloud Linux, not on the user's Mac.
See reception/dev_20261016/ for actual ZIP IDs/SHA/size, full-file metadata hashes,
receipt, visual-review records and proposed subset. Other cuts were not received;
frozen-test content was not downloaded/opened. A builders/finalizer were not run.
Image content digests exclude JSONL/CSV/reviews; B full-file pins bind those too.
S1/S2 use official_retrieved_top3 and gt_evidence respectively; never rename a
pool to pretend it is an old official_top5 package. Exact source/digest references
and A's two differing dataset locks are in configs/a_delivery_refs.json.
A's S3 rule label 不支持 is construction-only, NOT accepted semantic confirmation.
Final evidence must be reviewed against target question/query/allGT. Same bytes
and dHash guards cover query/allGT AND mutual final3; hashes are not semantic proof.
B viewed all254 supplied dev S3 candidate positions against85 target panels and
actual GT thumbnails, using the conversation assistant's visual capability, NOT
human adjudication or an external paid API. Exact serving model revision is not
exposed.45 were supportive,194 unknown,15 nonsupportive under the recorded visual
judgment; the latter form5 complete groups (5/150=3.33%). This development subset
requires HQ review, not a declaration of formal S3 acceptance or zero causal help.

configs/protocol_main_v1.json is authorized and frozen pre-rental:
- S0:evidence0 ->1 image.
- S1:published MRAG original ranks0,1,2, INCLUDING Incomplete ->4 images.
  Not our independent retrieval. Old unused-prompt flags do not govern this rule.
- S2:all actual GT in original order, normal5/Incomplete1 ->6/2 images.
  No top3 truncation, padding or GT duplication.
- S3-pure:A semantic-reviewed D1, exactly3 ->4 images. Undetermined cannot count
  as pure. An eligible subset is fixed before generation; S1/S3 comparison uses
  exactly that subset and reports parent/subset denominators and coverage.

Five models S0/S1/S2 plus E2B/E4B S3-pure =17 combinations PER formal split.
Quality stages internal_holdout and frozen_test are scored separately, never
pooled. Cost question-runs per split=15*N+2*N_S3. Smoke/dev/performance/warmups/
retries are additional. Optional Qwen3.5-9B, other S3, D2, independent retrieval,
official5/1 supplementary setting, ablations and second data are not prerequisites.

## Separate condition-package integration (no acquisition)

Use only actual externally supplied read-only package roots. No script here
fetches a dataset or reconstructs missing images. Output must be a new external
directory. For Windows use an existing audit venv and `--media-mode copy`;
hardlink requires source/output on the same volume. No inference deps are needed.

```bash
python -B "$code/integrate_condition_packages.py" \
  --s1 "$packages/dev_s1" --s2 "$packages/dev_s2" --s3 "$packages/dev_s3" \
  --split "$repo/a-side/splits/dev.v2.txt" --output "$external/dev-v17" \
  --media-mode copy
```

## Actual dev receipt, reproducible without rebuilding

Reuse existing supplied ZIPs under EXTERNAL_ROOT/archives/. This stdlib entry
checks pinned archive size/SHA and safely extracts only into NEW package folders:

```bash
python -B "$code/receive_release_packages.py" --manifest "$code/reception/dev_20261016/release_assets.json" --root "$external"
```

Only add --download when acquiring those exact3 dev archives is authorized and
they are absent locally. About447MiB of ZIPs; expanded original files488473196B.
It never enumerates other releases/splits, builds data, rewrites existing folders,
or calls A finalize. For later cuts supply a newly approved explicit asset-pin
manifest to the SAME entry; do not change dev pins or auto-fetch frozen content.

The original A checklist stays blank and immutable. The reviewed six-field CSV
in reception/dev_20261016/ has NO correct choices/questions/images; it is a B
model-assisted revision, not A/human confirmation. Its hash, original checklist,
automatic CSV, source ZIP and entire source package are separately bound.

```bash
python -B "$code/integrate_condition_packages.py" \
  --s1 "$external/packages/dev_s1" --s2 "$external/packages/dev_s2" --s3 "$external/packages/dev_s3" \
  --split "$repo/a-side/splits/dev.v2.txt" --output "$external/dev-reviewed" \
  --package-pins "$code/reception/dev_20261016/full_package_pins.json" \
  --review-checklist "$code/reception/dev_20261016/review_checklist.B_model_assisted.csv" \
  --review-method image_model_assisted \
  --review-model 'OpenAI Codex conversation assistant; exact serving model ID/revision not exposed by runtime' \
  --media-mode copy
python -B "$code/validate_received_inputs.py" --data-root "$external/dev-reviewed" \
  --bundle main/bundle.json s3/bundle.json --output "$external/new-input-receipt.json"
```

Use an existing audit venv (Pillow only needed here, no inference installation);
this cloud receipt used Python3.12.14/Pillow12.3.0, separate from unchanged pinned
model environments. On Windows invoke the existing audit python.exe with
`-X utf8 -B`, use the same arguments on one line, and `--media-mode copy`.
The validator reads generation inputs through the actual runner/shared-message
contract and preserves failures; it reads no scoring answers or model backend.
S0/S1/S2 each retain150; reviewed S3 retains5, with matching S1 subset comparisons.
The adapter's legacy S3_formal_admitted field denotes its review gate ONLY; dev
bundle formal_split_approved remains false and HQ_accepted=false in the receipt.
No model predictions or accuracy/performance results were produced this round.

Own committed metadata is sufficient to locate/verify the external Release media.
Review-only contact sheets contain scoring context: NEVER copy them into prompts
or Git. Stable evidence identity is original path + content SHA, not a sheet URL.
Sorting was checked by actual array/rank/evidence IDs; only9 nonempty groups had
all source answers already in dev for the stronger wrong-option order check.
Other source questions/answers were not opened. The global semantic sort claim
is unverified. B's actual query/allGT/mutual dHash gate found no blockers; this is
not proof of semantic unrelatedness, nor a guarantee all perceptual duplicates
are detected. None of the received source bytes was rewritten.

Layout: main/{bundle.json,split.json,inputs/S0.json,S1.json,S2.json,
scoring/answers.json,media/<package-name>/<original-path>,audit/};
audit/condition_integration.json and s3_review_adapter.json retain source hashes
and diagnostic candidates. If zero confirmed eligible D1 questions, NO runnable
s3/ bundle is emitted. This does not block main/ adapter receipt; it blocks S3
acceptance. All conditions retain the fixed list even for missing condition/media.
If every package lacks the same question/gold, integration fails explicitly;
never fabricate answers or omit that qid. CLI writes a failure receipt beside output.

Optional `--package-pins "$external/full-package-pins.json"` supplies
{"S1":"<B full-file manifest SHA>","S2":"<...>","S3":"<...>"} after independent
receipt review. The receipt defines its canonical full-file digest; A's narrower
content_digest is separately checked, not interchangeable. Unpinned packages
cannot approve formal bundles. Split approval still requires explicit limitations
acknowledgment and HQ review; no auto-approval from an adapter pass.

With actual image-grounded review, add `--confirmations "$external/review.json"`.
See existing configs/s3_interface.json for fields. CSV-derived review_id is clearly
B-generated. Original CSV/package SHA and final evidence IDs are preserved. A rule
label alone stays candidate; unknown/rejected stays undetermined. Only documented
per-image confirmation plus duplicate guards yields the predeclared S3 subset.
Hashed basis artifacts and original CSV are retained for runtime verification.
S1/S3 uses exactly that subset; full S1 remains separate. Normal S1/S2 is3vs5,
Incomplete3vs1: the difference is not attributable solely to evidence quality.

For an actually filled A checklist, use `--review-checklist EXTERNAL_FILLED.csv`
instead of --confirmations, and explicitly declare `--review-method human_visual`
or `--review-method image_model_assisted --review-model ACTUAL_MODEL_REVISION`.
Optional per-row review_method/review_model columns must agree with CLI values.
When no --review-checklist is supplied, the package checklist is automatically
the active authority, even with --confirmations JSON. JSON must bind its current
source_checklist_sha256 and agree with its per-image verdict/method/reviewer/time/
basis and media identities. Blank/supports/unknown/incomplete entries cannot be
overridden by another confirmation. An explicitly selected revised checklist is
recorded alongside the original package checklist SHA; no source file is rewritten.
Both active CSV and JSON are runtime-hashed support artifacts.
Required original fields: qid,final_evidence_id,semantic_verdict,review_basis,
reviewer,reviewed_at. Time must be ISO8601 with timezone. Blank/unknown/automatic
labels, missing basis/reviewer/time/method or model identity do not admit S3.
These CLI values attest the actual review method; the adapter performs no review
and invokes no model. It does not assert a reviewer personally viewed every GT;
derived media identities bind the received target/context, and duplicate guards
are independent. Raw filled CSV is copied byte-for-byte to external audit, hashed
with converted JSON and original mechanical CSV, and never enters prompts.

NEVER rerun A finalize_s3_packages.py over filled reviews: it opens the checklist
with w and replaces it with blanks. B does not call it. A guide's all-GT dHash claim
is not supported by builder code; GT exact-byte and final-peer checks differ from
all-GT near checks. Finalizer's sorting declaration is not proof of reordering.
B validates actual array/rank/IDs and separately runs its all-GT/mutual guards on
receipt; it does not claim semantic source-order verification from metadata.
New finalized S3 null retrieval_rank is accepted; original positional rank stays.
S3 image digest uses sorted path+NUL+image SHA+LF; full package pins additionally
bind all JSONL, CSV, metadata and reviews. Filling a checklist changes the full pin.

The existing single-source prepare_batch_inputs.py remains for legacy A6 startup
and explicit sources. Use the multi-package entry above for new A delivery.
The17 required combinations, score/parser/shared text and model pins are unchanged.
No new full-suite rerun is required on receipt; targeted results are recorded in
offline_checks.json. Windows continues waiting for HQ's final approved data/package.

## Models, budgets, independent environments

model_registry.json pins all five official revisions/classes/processors. Existing
Qwen3-VL Transformers4.57.3 environment is retained; Gemma4 and Qwen3.5 each use
separate Transformers5.19.0 environments. All use Python3.12, torch2.8.0 cu128,
torchvision0.23.0,Pillow11.3.0. Requirements locks and official-source audit are
included. Dependencies were metadata-resolved only; not installed/import-tested.

MAIN parameters:uniform BF16,no quantization/offload,SDPA,thinking off,greedy,
64 new tokens,seed42. TF32 disabled; bitwise CUDA reproducibility is not claimed.
Qwen native min/max pixels50176/262144,use_fast=False; Gemma max_soft_tokens140.
Source bytes/order/shared text match across models; native resizing/token counts
can differ and are logged. This is not an equal-visual-token claim. Native BF16,
actual images/tokens/VRAM and APIs require GPU probes for EVERY model. Failure/OOM
stops; never silently shrink images/tokens or change dtype. A development-driven
change needs a new version/config fingerprint before formal tests, not test tuning.
Legacy run_candidate.py/start_server_smoke.sh remain the old A6 startup lane and
must NOT be used as the main protocol entry.

After rental AND installation authorization, for each family in qwen3vl/gemma4/qwen35:

```bash
python3.12 -m venv "$work/envs/$family"
py="$work/envs/$family/bin/python"
"$py" -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
"$py" -m pip install -r "$code/$lock"
"$py" -m pip check
CUDA_VISIBLE_DEVICES=0 "$py" -B "$code/model_preflight.py" --model "$model_key" --workdir "$work" --runtime
```

Use requirements-qwen.lock.txt,requirements-gemma4.lock.txt,requirements-qwen35.lock.txt
respectively. Preflight only imports/classes/tiny CUDA scalar, no weights.
Weight retrieval after authorization uses official HF snapshot_download with the
registry's exact repo/revision and asset allowlist*.json,*.jinja,*.safetensors,*.model.
Default runtime is local_files_only; --allow-download is explicit future permission.
Keep one shared HF_HOME persistent cache. Credentials/env_map.local.json stay
external. Exact weight-file bytes/hashes and storage terms are in registry/resource
configs. No card capacity or GPU-hours guarantee; measure actual representative
batches before extrapolation. A's E4B8GB observation does not size our rented GPU.

## Legacy single-source path and batch binding

The following single-source instructions are LEGACY or already unified-source only;
new separate A packages must use integrate_condition_packages.py above.
External layout:data/main/{bundle.json,split.json,inputs/,scoring/,audit/,media/};
S3 subset may be a separate data/s3/ bundle. No real inputs/answers/images in Git.
Use verify_external_package.py --root ACTUAL_A_PACKAGE --hash-index
ACTUAL_PACKAGE_FULL_FILE_HASH_INDEX [--decode] for read-only receipt. It never
downloads/repairs files; semantic D1 acceptance is a separate review artifact.

```bash
"$audit_py" -B "$code/prepare_batch_inputs.py" \
  --source-jsonl "$a/evidence_list.jsonl" --index-csv "$a/evidence_index.csv" \
  --split "$repo/a-side/splits/smoke_20.v2.txt" --derive-main-selection --output "$external/main"
```

This reads independent gold only to export scoring/answers.json; generation only
contains question,choices,query and selected images. S2 selection reads GT IDs,
not correctness/hit labels. It copies no media:deploy selected original files
under main/media/ with unchanged relative paths. Missing media stays a row failure;
duplicate/unknown/missing fixed qids are contract errors, not a smaller denominator.
Main selection/provenance is saved outside Git; CPU selection time/host is separate,
not our retrieval time. A source data stays unchanged.

For S3 add --s3-only --d1-review EXTERNAL_REVIEW.json using an index containing
D1 files. Review contract:by_qid[qid]={review_id,distractor_type:"D1",evidence:
[{evidence_id,semantic_status:"confirmed_unsupportive"},...]}. Exactly3 confirmed
refs are required. Others go to a diagnostic-only list/coverage; no percent cutoff.
The subset split records its parent hash; never select it using predictions.
For quality text-list imports, --acknowledge-split-limitations explicitly approves
known exposure/dependence limitations without claiming a complete registry or
source isolation. Such acceptance is a headquarters decision, not automatic.

An external binding JSON contains approved,scope(full_required or smoke_only),tasks.
Each task:task_id,model registry key,stage,condition,bundle relative to data root,
repeat_index. Protocol defaults to the frozen code config; deviations are rejected.
Full scope includes both formal splits,each17 unique combinations. Use smoke_only
for a limited accepted20-question startup package without claiming full readiness.

```bash
python -B "$code/bind_batch.py" --binding "$external/binding.json" --data-root "$data" --output "$external/bound_matrix.json"
python -B "$code/run_batch.py" --matrix "$external/bound_matrix.json"  # inspect only
```

## Same-card execution, restore and scoring

start_batch.sh uses existing tmux. One model process at a time within GLOBAL phases:
smoke -> development -> internal_holdout -> frozen_test -> performance. All models
finish the current phase before advancing. Within smoke,single/multi probes precede
condition tasks. A failure blocks the next phase; other independent models in the
current phase still run. Formal tests are never a parameter-tuning source.

```bash
bash "$code/start_batch.sh" "$code" "$external/bound_matrix.json" "$data" "$run" \
  "$control_python" "$external/env_map.local.json"
# To stop intentionally after development, invoke run_batch.py directly with
# the same --matrix/--data-root/--run-root/--env-map --backend hf --execute
# plus --through-phase development, under tmux.
```

SSH disconnect is safe for tmux; machine shutdown/deletion is not. Resume with
identical code/config/matrix/run root. Successful/completed records skip. OOM
remains blocked across ordinary resume; diagnose then explicitly --retry-failures.
No automatic budget/dtype fallback. Changed fingerprint requires a NEW run root.
Per-question attempts.jsonl is flushed/fsynced. Torn tails are backed up/recovered;
complete malformed lines,duplicate composite attempts and unknown IDs fail closed.
OS locks release on process death. Failure/retry history and fixed-list completeness
are retained. State/exit codes/logs are recorded per model AND phase.

predictions.jsonl keeps raw_output=prediction_raw,final_output,strict parser and
model-boundary versions,configuration/errors/ordered evidence. Independent scoring
uses scorer_projection.jsonl(final_output under scorer raw_output) and external
gold; strict_choice_v1 itself is unchanged. Empty/unparseable/failed/final missing
predictions are wrong. Every actual scenario incl Incomplete remains in overall.
Do not merge conditions/models/splits/repeat batches before scoring.

## Measurement and post-rental analysis

Warmup>=3 unscored per warmed task,CUDA sync before/after generate. Performance
uses5 repeats of20 smoke questions(100 measurements if complete); S3 may have a
smaller semantic subset and must report its smaller n/coverage. Performance repeats
have no accuracy file and never add quality observations. P50/P95 are descriptive;
100 repeated observations are not100 independent questions or proof of stable P95.
Use --performance-min-n100; fewer observations produce no P95.

Generate timing=prefill+decode,excludes CPU preprocessing/device transfer.
end_to_end=per-question image decode/processor/transfer/generate/final separation,
excludes bundle checks,model load,warmup and scoring. Published-candidate retrieval
time=null(not measured zero). Selection CPU time/host is separate; NEVER add A's
other-machine times. Process allocator peak is separate from unmeasured device
peak(null). Record actual dtype/processor/shapes/grid/tokens/budget exhaustion.

```bash
python -B "$code/analyze_batch.py" --left "$S1/score.json" --right "$S3/score.json" --S1-S3-subset --output "$new_analysis"
tar -czf "$run.tar.gz" -C "$(dirname "$run")" "$(basename "$run")"
sha256sum "$run.tar.gz"
# Windows receiver:scp -P PORT USER@HOST:REMOTE_ARCHIVE D:/EdgeCoRAG-B/incoming/
```

Analysis runs locally after releasing GPU. Paired scenario-stratified bootstrap
requires complete identical lists; S1/S3 subset mode checks predeclared parent
hash/coverage and preserves full S1 results. Optional source-cluster analysis
requires an evidenced external grouping basis; v2's fallback is not entity isolation.
Synthetic checks are not effectiveness evidence. Do not rerun old suites on receipt.
Windows waits for HQ final approval; this dev-receipt package is not the final
all-split experiment bundle. Remaining cuts, HQ review of assisted S3 judgments,
formal bindings and GPU checks remain pending.
