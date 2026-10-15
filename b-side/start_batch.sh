#!/usr/bin/env bash
# Future rented Linux only; no install/download unless --allow-download is explicit.
set -euo pipefail
if [[ $# -lt 6 || $# -gt 8 ]]; then
  echo 'Usage: start_batch.sh CODE_DIR MATRIX DATA_ROOT RUN_ROOT CONTROL_PY ENV_MAP [--retry-failures] [--allow-download]' >&2
  exit 2
fi
code="$1"; matrix="$2"; data="$3"; run="$4"; py="$5"; env_map="$6"
shift 6
for extra in "$@"; do
  [[ "$extra" == '--retry-failures' || "$extra" == '--allow-download' ]] || { echo 'Unknown option' >&2; exit 2; }
done
command -v tmux >/dev/null
[[ -f "$matrix" && -f "$env_map" && -d "$data" && -x "$py" ]]
mkdir -p "$run"
args=(env PYTHONUTF8=1 CUDA_VISIBLE_DEVICES=0 "$py" -u -B "$code/run_batch.py" --matrix "$matrix" --data-root "$data" --run-root "$run" --env-map "$env_map" --backend hf --execute "$@")
printf -v command_text '%q ' "${args[@]}"
printf -v log_path '%q' "$run/batch-launch-$(date +%Y%m%d-%H%M%S)-$$.log"
tmux new-session -d -s "edgecorag-batch-$(date +%Y%m%d-%H%M%S)-$$" "$command_text > $log_path 2>&1"
echo "Started sequential model processes; results: $run"
echo 'Resume with the identical command/config and run root. Failed attempts retry only with --retry-failures.'
