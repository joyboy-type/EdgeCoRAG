# EdgeCoRAG B v1.10.0 — final binding and bounded runtime closeout

Based on B9e81c89 and A c0e0931d8ad8d640e9c8002516fea43a70049831. Only b-side/ changes.
Cloud Linux receipt is not a user Mac/Windows result or GPU validation. Keep PR1
draft pending HQ review. No experiment model, weights, processor or CUDA loaded.

## Current HQ closeout decision and Windows handoff

HQ accepted the existing image_model_assisted S3 subsets ONLY as limited
supplemental robustness experiments: dev5 development/mechanism, holdout2/150,
frozen29/1033. The smoke subset remains0/20. Original CSV/observations and their
hashes are immutable. No new image review, old suite or real material reception
was repeated in v1.10.0. Serving revision is unavailable, contact-sheet resolution
limited, reviewer is not human, and audits were label-aware. No representative,
entity-isolated, answer-blind or universal semantic-independence claim is made.
Historical receipt files below retain their original HQ_pending states; this
section and configs/final_binding_v1.json record the later explicit authorization.

Preserve actual evidence order, including88 stronger semantic-order violations
and114 unresolved groups. Four near-duplicate-failed frozen groups remain out.
All S0/S1/S2 use their original full split. Main S1 never shrinks to the S3 list.
S1/S3 analysis restricts the existing S1 predictions to the SAME predeclared
S3 qids, with parent/subset denominators, coverage and domain-bias caveats.

Final task plan (configs/task_matrix_draft.json; hashes/models/budgets pinned):

| Global phase | Tasks | Question-runs, excluding warmups/retries |
| --- | ---: | ---: |
| smoke |25 =10 single/multi one-question probes +15 full S0/S1/S2 tasks |310 |
| development |17 =15 full-dev S0/S1/S2 + E2B/E4B explicit dev5 S3 tasks |2260 |
| internal_holdout |17 quality combinations |2254 =15*150+2*2 |
| frozen_test |17 quality combinations |15553 =15*1033+2*29 |
| performance |85 =5 repeats of17 conditions, never accuracy rows |1550 |

Total161 tasks /21927 question-runs; FORMAL quality alone17807. No GPU-hour or
capacity claim. All five models must complete every development task successfully
before either formal phase. Smoke S3 has NO task and is not declared completed.
E2B/E4B S3 startup validation is explicitly development/dev5. The existing
performance repeat budget is retained: S0/S1/S2 use smoke20; S3 uses dev5 with
25 measurements per model and NO P95. These are generation-only measurements,
not retrieval, independent questions, stability evidence or extra quality scores.
Quality, performance, probes and warmups are separately identified.

mechanism_test is a read-only input-acceptance API stage ONLY. Production matrices
containing it (alone or mixed) now fail explicitly. Every admitted task maps to a
scheduled global phase or an explicit --through-phase deferred ID. Zero worker
exit without a complete unique per-task receipt cannot complete a phase.
Default condition analysis requires identical nonempty model_id/model_revision
and emits both identities. No implicit cross-model condition effect is allowed.

### Final external reconstruction, after HQ reviews/merges this exact delta

The small code ZIP contains b-side/ only. Data stay outside code, using the SAME
12 published ZIPs: config release.assets includes exact asset IDs, byte counts,
SHA256 and URLs. Reuse already verified archives/extractions, no new evidence
build. No cloud /workspace or Mac /Users location is a deployment dependency.
The existing receiver extracts fresh packages; NEVER rerun against existing roots
or call A finalize. New binding outputs must not overwrite previous data/results.

Windows PowerShell (replace these explicit deployment paths once; use existing
audit Python/Pillow environment, not Anaconda base):

```powershell
$code = "D:\EdgeCoRAG-B\final-code\b-side"
$external = "D:\EdgeCoRAG-B\evidence-v1"
$py = "D:\EdgeCoRAG-B\.venv\Scripts\python.exe"
# Only when original packages are absent: export the fixed asset manifest.
& $py -X utf8 -B "$code/finalize_binding.py" --asset-manifest "$external/assets.json"
# Supply the existing12 ZIPs in $external/archives. Download only genuinely absent
# assets after HQ transfer approval; --download is explicit on this receiver.
& $py -X utf8 -B "$code/receive_release_packages.py" --manifest "$external/assets.json" --root "$external"
# If packages already exist, skip the receiver and use their existing root here.
& $py -X utf8 -B "$code/finalize_binding.py" --packages "$external/packages" --archives "$external/archives" --data-root "$external/bound-v110" --media-mode hardlink
```

Use --media-mode copy only if hardlinks are unsupported or cross-volume; it does
not alter image content/ordering. Hardlinks keep shared source bytes without
unnecessary duplicate directories. Finalizer verifies all ZIP SHA/size, full
package pins, the unchanged filled CSV and basis snapshots; reconstructs exact
v2 text/hash; invokes the existing condition adapter; checks eligible qids and
actual selected evidence ID order; builds the probe views; then calls the existing
binder. It never reads model results or rejudges semantics. A changed subset or
order fails; no silent filtering, filling or standard relaxation. Ordinary input
failures stay in their full denominators and binding_receipt lists them explicitly.

Output layout (external, no images/answers committed):
- integrated/<split>/main/{bundle.json,inputs/,scoring/,media/,audit/}
- integrated/<split>/s3/... only for dev/holdout/frozen eligible subsets
- probes/preflight_single/ and probes/preflight_multi/, each one fixed smoke qid
- fixed_lists/, binding.json, bound_matrix.json, selection_manifest.json,
  binding_receipt.json (all generated metadata/review hashes), or binding.failure.json.

selection_manifest pins actual ordered IDs/image hashes per qid/condition;
binding_receipt pins the reconstructed matrix and generated metadata. Static code
config/ZIP hashes and external data hashes are DISTINCT. Generated bundle/matrix
hashes are recomputed at the destination and must be retained with results; do not
reuse old unapproved v1.9 bundle hashes. Checklist serialization order is now fixed
so process hash randomization cannot silently change a binding. This cloud
closeout used artificial fixtures/config checks only: renewed destination binding
against real media has not been falsely reported as executed here.

### Linux launch, disconnect, resume and retrieval

After HQ-approved transfer and per-family environments/cache setup (unchanged
locks, registry revisions and budgets below), set code/data/run/control_python and
an EXTERNAL env_map.local.json mapping qwen3vl/gemma4/qwen35 to their environment
Python executables. Windows is only the SSH operator. No install/weights/GPU action
is performed by this delivery.

```bash
# First authorized GPU session: whole-fleet smoke then development, in tmux.
# Explicitly stop before formal evaluation until all development tasks pass.
command=("$control_python" -u -B "$code/run_batch.py" --matrix "$data/bound_matrix.json" --data-root "$data" --run-root "$run" --env-map "$env_map" --backend hf --execute --through-phase development)
printf -v cmd '%q ' "${command[@]}"
tmux new-session -d -s edgecorag-development "$cmd > /tmp/edgecorag-development-launch.log 2>&1"
# Inspect every model/phase/task state and saved development scores/errors.
# Then SAME code/config/run root continues formal phases and performance:
bash "$code/start_batch.sh" "$code" "$data/bound_matrix.json" "$data" "$run" "$control_python" "$env_map"
# Same command resumes successful attempts without generation. For diagnosed
# failures only, append --retry-failures; OOM never auto-shrinks budget/precision.
# Retrieve immutable result archive after the tmux process has ended:
tar -czf "$run.tar.gz" -C "$(dirname "$run")" "$(basename "$run")"
sha256sum "$run.tar.gz"
```

From Windows use scp -P PORT USER@HOST:REMOTE_ARCHIVE D:/EdgeCoRAG-B/results/.
Keep all attempts/errors/configuration, batch_identity, matrix/selection/binding
receipt and states. Run paired/coverage summaries locally after ending the GPU
lease. Existing RUN timing boundaries/three warmups/CUDA sync remain unchanged;
no cross-hardware addition or P95 from25 repeats. CUDA import/loading/VRAM/OOM/
processor compatibility and actual five-model results remain UNVERIFIED.

## A status and frozen main contract

A split v2 is RECEIVED:20/150/150/1033, file hashes/counts/disjointness/1353 coverage
and seven named B questions in dev were independently checked. Do not keep saying
A has not repaired the split. v2 uses per-question fallback:cross-split source/
image dependence is NOT isolated. Aggregate label exposure is disclosed separately
from named per-question debugging. configs/debug_question_ids.json now records all
150 authorized dev targets, including the prior seven; it does not claim global
exhaustiveness. Candidate source-image exposure is logged separately from source
question/answer access. The former metadata-only smoke status is historical. New label-aware audit
exposure is separate from engineering/dev tuning; see the registry below.

All12 Release ZIPs have actual receipt records: dev reuses accepted v1.8.0
(no redownload/retest); the other9 were received this round outside code. See
reception/all_20261016/summary.json and release_assets.json. New indexed image
positions decoded:14751, not14751 unique contents. Full-file pins bind metadata,
JSONL, original CSV/checklists as well as images. Original packages are unchanged.
A builders/finalizer were not run.

All1874 new final S3 candidate positions were visually reviewed with target
question/options/gold, query and all supplied GT thumbnails. Method is
image_model_assisted, reviewer is B/Codex conversation assistant, NOT human. Exact
serving model ID/revision is unavailable. Hash-bound contact-sheet previews have
limited resolution; unresolved fine distinctions/comparison help remain unknown.
No model predictions were viewed and no prompt/budget/model tuning occurred.
Candidate source-image exposures and label-aware target audits are recorded in
reception/all_20261016/label_aware_audit_registry.json. This is not label blindness
and global exposure completeness remains false. Legacy engineering qids remain
separate; do not use the audit list as a tuning list or automatically redraw splits.

Historical v1.9 proposed S3 subsets (now accepted only within current HQ limits): smoke0/20, dev5/150 (prior receipt),
internal_holdout2/150 (415,1009), frozen_test29/1033. All retained groups have
three visually judged nonsupportive candidates and pass query/allGT/mutual exact
and dHash<=6 guards. Unknown/support/blank are excluded; these guards do not prove
universal semantic independence. Existing S1/S3 analysis uses identical subset
qids while retaining full S1. Coverage and narrow domain composition limit claims.
Smoke has no eligible S3: do not silently pad/skip/relabel it to pass all17 tasks.
The original receipt did not grant approval; current HQ scope is recorded above. GPU readiness is still unverified.

Actual ID/rank/CSV-position order passed. Stronger wrong-option/source-qid/GT
ordering was checkable for513 groups:88 violate the claimed ordering;114 groups
remain unresolved without physically cached dev source labels. Original order
was preserved. A builder pass2 follows dataset traversal; finalizer does not
reorder. B independently checked allGT and within-group near duplicates;4 frozen
groups are blocked. Details and script hashes are in each ordering_audit.json
and mechanical_receipt.json, not inferred from A guide prose.

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

## Reuse all-split assets and filled review snapshots (v1.9.0)

No large media, answers or generated bundles are committed. Release URLs/IDs, ZIP
size/SHA and expanded-size bounds are pinned in reception/all_20261016/release_assets.json.
Keep existing caches; do not redownload unchanged dev. Existing receiver accepts
a manifest containing only the required split assets, and refuses existing
extraction roots. For missing archives only, --download is explicit; no rebuild.
Original checklist is preserved; select a new filled snapshot explicitly. Never
run A finalize against filled reviews. Example after supplying archives/packages:

```bash
split=internal_holdout
review="$code/reception/all_20261016/$split/review_batch_001"
python -B "$code/integrate_condition_packages.py" \
  --s1 "$packages/${split}_s1" --s2 "$packages/${split}_s2" \
  --s3 "$packages/${split}_s3" --split "$repo/a-side/splits/$split.v2.txt" \
  --package-pins "$code/reception/all_20261016/$split/full_package_pins.json" \
  --review-checklist "$review/review_checklist.B_model_assisted.csv" \
  --review-method image_model_assisted \
  --review-model 'OpenAI Codex conversation assistant; exact serving model ID/revision not exposed by runtime' \
  --media-mode copy --output "$new_external_output"
```

Use smoke_20/review_batch_001, frozen_test/review_batch_002 and prior
dev_20261016/review_checklist.B_model_assisted.csv respectively. These are offline
reconstruction paths, not formal quality approval. The validator uses
mechanism_test for all splits, so reading a holdout is not labeled development.
Legacy reconstruction remains unapproved by default; the finalizer above applies the now-explicit HQ limitations acknowledgment.
Fixed parent main S0/S1/S2 lists remain intact; only S3 has an explicit eligible
subset. Raw review sheets/answers stay external. Review CSV, observation
snapshots, source package pins and per-file metadata hashes are committed.

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
Historical v1.8 reports used S3_formal_admitted for subset construction. New
reports distinguish S3_review_gated_subset_constructed from actual formal
approval; bundles remain unapproved until HQ acceptance.
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
Windows waits for HQ review/merge of the v1.10 closeout delta, then reconstructs the pinned final bindings with the current entry above. All-cut offline receipt is complete;
CUDA loading, memory/OOM and real performance remain unverified.
