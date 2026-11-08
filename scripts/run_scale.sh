#!/usr/bin/env bash
# Detached-friendly wrapper for scripts/scale_society.py.
#
#   bash scripts/run_scale.sh --count 100 --active 8 --budget 3.0
#
# Writes combined output to .village/scale-society.log and records an exit marker.
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
mkdir -p .village

{
  echo "=== start $(date -Is) host=$(hostname) pid=$$ ==="
  uv run python scripts/scale_society.py "$@"
  code=$?
  echo "=== end $(date -Is) exit=${code} ==="
} >.village/scale-society.log 2>&1
exit "${code:-1}"
