#!/usr/bin/env bash
# Future rented Linux server only. No provisioning or dependency installation.
set -euo pipefail
if [[ $# -lt 4 || $# -gt 5 ]]; then
  echo "Usage: bash start_server_smoke.sh CODE_DIR DATA_DIR NEW_RUN_DIR VENV_PYTHON [allow-download]" >&2
  exit 2
fi
code_dir="$1"
data_dir="$2"
run_dir="$3"
runtime_python="$4"
command -v tmux >/dev/null || { echo "tmux is missing; no task started." >&2; exit 2; }
[[ -f "$code_dir/run_candidate.py" && -x "$runtime_python" && -d "$data_dir/inputs" ]] || { echo "Missing code, data or interpreter." >&2; exit 2; }
[[ ! -e "$run_dir" && ! -e "$run_dir.log" ]] || { echo "Run/output already exists; choose a new path." >&2; exit 2; }
mkdir -p "$(dirname "$run_dir")"
args=(env CUDA_VISIBLE_DEVICES=0 PYTHONUTF8=1 "$runtime_python" -u -B "$code_dir/run_candidate.py"
  --sample-root "$data_dir" --inputs-root "$data_dir/inputs" --answers "$data_dir/scoring/answers.json"
  --output "$run_dir" --backend qwen)
if [[ -f "$data_dir/bundle.json" ]]; then
  [[ -d "$data_dir/source/samples" ]] || { echo "A-derived samples directory missing." >&2; exit 2; }
  args=(env CUDA_VISIBLE_DEVICES=0 PYTHONUTF8=1 "$runtime_python" -u -B "$code_dir/run_candidate.py"
    --sample-root "$data_dir/source/samples" --inputs-root "$data_dir/inputs"
    --bundle-manifest "$data_dir/bundle.json" --answers "$data_dir/scoring/answers.json"
    --output "$run_dir" --backend qwen --conditions S0 S1 S2)
fi
if [[ $# -eq 5 ]]; then
  [[ "$5" == "allow-download" ]] || { echo "Unknown fifth argument." >&2; exit 2; }
  args+=(--allow-download)
fi
printf -v command_text '%q ' "${args[@]}"
printf -v log_path '%q' "$run_dir.log"
session="edgecorag-smoke-$(date +%Y%m%d-%H%M%S)-$$"
tmux new-session -d -s "$session" "$command_text > $log_path 2>&1"
echo "Session: $session"
echo "Log: $run_dir.log"
echo "Outputs: $run_dir"
echo "Disconnecting SSH leaves this tmux task running. Stopping/destroying the server does not."
