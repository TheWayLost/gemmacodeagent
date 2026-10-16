#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export GEMMA_RUNTIME_PROFILE=4090-48g
export GEMMA_EVAL_SLOTS="${CONCURRENCY:-1}"
[[ "$GEMMA_EVAL_SLOTS" =~ ^[1-4]$ ]] || { echo 'CONCURRENCY must be 1, 2, 3 or 4'; exit 1; }
export ADP_CONCURRENCY="$GEMMA_EVAL_SLOTS"
export HF_HOME="$PWD/cache/huggingface" XDG_CACHE_HOME="$PWD/cache" TMPDIR="$PWD/tmp"
mkdir -p logs runs tmp cache
mode="${1:-help}"; if [[ $# -gt 0 ]]; then shift; fi
case "$mode" in
 model) exec envs/eval/bin/python src/start_model_capacity.py --profile 4090-48g --concurrency "$GEMMA_EVAL_SLOTS" "$@" ;;
 eval)
  envs/eval/bin/python - <<'PY'
import json,os,urllib.request
from pathlib import Path
p=json.loads(Path('runs/server_profile.json').read_text())
assert p['profile']=='4090-48g' and p['eval_slots']==int(os.environ['GEMMA_EVAL_SLOTS']), 'Server profile/concurrency mismatch; restart with matching settings'
with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=10) as r:assert r.status==200
PY
  exec envs/eval/bin/python src/benchmark.py --workers "$GEMMA_EVAL_SLOTS" "$@" ;;
 *) echo 'Usage: CONCURRENCY=1 bash scripts/run_4090_48g.sh model [--dry-run] | eval --shards 1 --shard 0 --cohort paired20 --arms v5_6000 --run 4090-test'; exit 2 ;;
esac
