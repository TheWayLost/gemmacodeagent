#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HF_HOME="$PWD/cache/huggingface" XDG_CACHE_HOME="$PWD/cache" TMPDIR="$PWD/tmp"
mkdir -p cache tmp logs runs envs models
unset PIP_NO_INDEX PIP_FIND_LINKS
python3.12 -m venv envs/bootstrap
envs/bootstrap/bin/pip install uv requests kagglehub
# Competition wheelhouse is patched: never substitute stock PyPI vLLM.
envs/bootstrap/bin/python - <<'PY'
import kagglehub,pathlib
p=kagglehub.dataset_download('metric/gemma-4-developer-agent-wheelhouse/versions/31')
r=pathlib.Path('wheelhouse');r.symlink_to(pathlib.Path(p).resolve(),target_is_directory=True) if not r.exists() else None
PY
envs/bootstrap/bin/uv venv --python python3.12 envs/eval
# Find the actual nested wheel directory in the downloaded dataset.
mapfile -t WHEEL_DIRS < <(find -L wheelhouse -name '*.whl' -printf '%h\n' | sort -u)
LINKS=();for d in "${WHEEL_DIRS[@]}"; do LINKS+=(--find-links "$d");done
envs/bootstrap/bin/uv pip install --python envs/eval/bin/python "${LINKS[@]}" --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match -r environment/requirements.lock
envs/eval/bin/python scripts/verify_environment.py
envs/bootstrap/bin/python scripts/fetch_calibration.py
