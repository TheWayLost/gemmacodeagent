# Six-model comparison on 3 or 4 PRO 6000 servers

Runs **all 129 tasks**, not only the development subset: **774 task-model evaluations** across Qwen3.8-27B FP8, Coder390 FP8, EfficientThink FP8, Qwen3.5-9B runtime FP8, its SWE-Gym LoRA, and the original Kaggle Gemma 4 W4A16 checkpoint. The two newly queued Gemma fine-tunes are excluded.

## Validation status

See `reports/current_results.json` for dated partial pilot results. Qwen3.8 base and both 9B arms completed 16 tasks. Kaggle Gemma passed tool/budget/concurrency gates and is being evaluated. Coder390 and EfficientThink are not yet end-to-end validated. Partition logic is checked for disjoint exhaustive coverage; a full multi-server run has not yet been performed.

## Prepare each server

One 96 GiB PRO 6000 per server. Run the parent repository's `scripts/setup.sh` following its README for the pinned evaluator, rootfs, calibrated wheels and Kaggle Gemma weights. A generic PyPI evaluator is not equivalent. Keep everything on persistent storage.

```bash
export CODEAGENT_ROOT=/root/autodl-tmp/codeagent/gemma4
cd /path/to/gemmacodeagent
export PACKAGE="$PWD/experiments/distributed_model_comparison"
mkdir -p "$CODEAGENT_ROOT/tmp/mm"
# Supply your own KAGGLE_API_TOKEN if competition artifacts are missing.
"$CODEAGENT_ROOT/envs/eval/bin/python" "$PACKAGE/prepare_all.py"
"$CODEAGENT_ROOT/envs/eval/bin/python" "$PACKAGE/check_partition.py"
```

Artifacts and weights are hash-checked. Large model files prefer ModelScope when accessible; pinned HF hashes remain authoritative. A 150 GiB disk requires rotating completed weight caches; logs/results remain. Use `MM_KEEP_WEIGHTS=1` only with more space.

## Run the 16-task gate first

```bash
"$CODEAGENT_ROOT/envs/eval/bin/python" "$PACKAGE/run.py" --scope pilot16 --concurrency 16
```

Each model must pass tool calling, thinking-budget enforcement and concurrency checks before scoring. Infrastructure failures stop the run; do not silently replace failures with successful retries.

## Full evaluation on 3 servers

Run one command per server, with distinct indices:

```bash
# Server 1
"$CODEAGENT_ROOT/envs/eval/bin/python" -u "$PACKAGE/run.py" --scope all --workers 3 --worker-index 0 --concurrency 16
# Server 2
"$CODEAGENT_ROOT/envs/eval/bin/python" -u "$PACKAGE/run.py" --scope all --workers 3 --worker-index 1 --concurrency 16
# Server 3
"$CODEAGENT_ROOT/envs/eval/bin/python" -u "$PACKAGE/run.py" --scope all --workers 3 --worker-index 2 --concurrency 16
```

Each server gets 43 tasks and all six models: 258 evaluations per server.

## Full evaluation on 4 servers

Use `--workers 4` and worker indices `0`, `1`, `2`, `3` on four servers. Task counts are 33/32/32/32, evaluation counts 198/192/192/192. **Do not mix 3-worker and 4-worker partitions.** Use tmux/nohup to survive SSH disconnection. Run only one evaluator per GPU.

Freed slots are filled immediately. Default concurrency 16 matches the expanded pilot; the health gate can select less. `--concurrency 32` tests 8/16/24/32, but changes per-task contention under the fixed deadline: record it as a separate condition.

## Protocol

Budget-Fit v5: 15 minutes, thinking budget 6000, 56 tool calls, 160 turns, max output 8192, temperature 0.2, top-p 0.95, context 32768, compaction 14336. Model-specific tool/reasoning parsers are required. Qwen uses vLLM generation defaults; Kaggle Gemma retains its checkpoint generation defaults including top-k. This is a deployment comparison, not identical token-level sampling.

Qwen uses FP8 (protected layers vary); Kaggle Gemma uses W4A16. No speculative decoding. The 9B pair shares a base. Gold/empty calibration distinguishes invalid environments from model failures. Report API/template errors separately. Small pilot results do not establish general training-method effects.

## Merge results

State files live under `$CODEAGENT_ROOT/runs/distributed_model_comparison/worker_INDEX_of_COUNT/`. Collect each `all_state.json` with unique names, then:

```bash
python "$PACKAGE/merge_results.py" results/server*.json --output results/merged.json
```

The merger rejects incomplete/mixed partitions, duplicates and missing tasks. Raw requests/responses, reasoning, patches and tests remain on each server under `runs/distributed_model_comparison/`. Never upload credentials or private teacher logs.
