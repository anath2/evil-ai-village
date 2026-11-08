#!/usr/bin/env bash
# Run a village experiment, suitable for a detached tmux/nohup session.
#
#   bash scripts/run_experiment.sh <config> [logfile]
#
# Writes combined stdout/stderr to <logfile> (default .village/run-<config>.log)
# and records an exit marker so a poller can detect completion.
set -uo pipefail

CONFIG="${1:?usage: run_experiment.sh <config> [logfile]}"
NAME="$(basename "${CONFIG%.yaml}")"
LOG="${2:-.village/run-${NAME}.log}"

cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
mkdir -p .village

{
  echo "=== start $(date -Is) config=${CONFIG} host=$(hostname) pid=$$ ==="
  uv run python run.py run --config "${CONFIG}"
  code=$?
  echo "=== end $(date -Is) exit=${code} ==="
} >"${LOG}" 2>&1
exit "${code:-1}"
