# EdgeCoRAG B v1.6.0 — phase-one integration

Based on main 235482612d7791a883e585fa5b2f16228bfabd5c. Only b-side/ is added;
root README/.gitignore and A files are preserved. This is NOT completion of all
rental preparation. No weights, real processor/model loading or GPU inference
were run. Actual offline results are in offline_checks.json; older accepted
sample/scorer/synthetic suites were not rerun.

## A status and frozen main contract

A split v2 is RECEIVED:20/150/150/1033, file hashes/counts/disjointness/1353 coverage
and seven named B questions in dev were independently checked. Do not keep saying
A has not repaired the split. v2 uses per-question fallback:cross-split source/
image dependence is NOT isolated. Aggregate label exposure is disclosed separately
from named per-question debugging. configs/debug_question_ids.json retains at
least0,1,2,3,4,24,43; it does not claim global exhaustiveness. The20 smoke list/hash
index were read as metadata only, not as question/answer/image content.

A's smoke_20 index, report and rebuild script are in main. B has NOT received or
reconstructed its actual external files. A's37/37 report is not B validation.
The source builder applies project environment settings and deletes existing
outputs; it was read, not executed. Its streaming still reads/downloads data and
its original5/1 selection needs the following explicit new conversion. Request
A's actual package/location or a controlled verified rebuild; do not run TLS
bypass or arbitrary environment/download scripts. Full formal evidence and
semantic-reviewed D1 are not present in the accepted B inputs yet.

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

## Receiving A material and generating neutral inputs

External layout:data/main/{bundle.json,split.json,inputs/,scoring/,audit/,media/};
S3 subset may be a separate data/s3/ bundle. No real inputs/answers/images in Git.
Use verify_external_package.py --root ACTUAL_A_PACKAGE --hash-index
repo/a-side/data/smoke_20_file_hashes.csv [--decode] for read-only receipt. It never
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
Windows next step is only hash-checking this new code package in a NEW stage;
actual A media receipt and formal binding remain a separate second phase.
