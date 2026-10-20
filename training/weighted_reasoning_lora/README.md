# Version B: weighted-reasoning LoRA for repository-repair agents

This package trains a text-only LoRA adapter on a frozen BF16 Gemma 4 31B QAT-unquantized base. It supports one 96GB GPU for validation and **2, 3, or 4 RTX PRO 6000 96GB GPUs** with DistributedDataParallel (DDP). It does not train the vision tower.

**Run the single-card smoke test first.** Training correctness does not establish improved bug-fixing accuracy. Real hardware validation results and limitations are in `VALIDATION.md`.

## Objective and data

For each model decision, the prompt is the recorded model-visible history (including runtime compaction and tool responses), and the only supervised completion is the current assistant response. The pinned native Gemma template serializes tool calls and thinking channels. Tool arguments are parsed into objects before rendering.

Token weights are **0 for prompt/history/tool outputs, 0.25 for thinking text, and 1 for the current assistant's action/content and protocol delimiters**. The causal shift is applied explicitly. The objective is `sum(weight * cross_entropy) / sum(weight)` over all ranks and all microbatches in the optimizer step. DDP's gradient averaging is compensated by the world-size factor; averaging separately normalized per-rank losses would be incorrect for unequal completion lengths.

The dataset is supplied through `DATASET_REPO` and `DATASET_REVISION` environment variables; no dataset identity is embedded in this public package. The raw release contains 332 attempts / 305 tasks. Only 200 test-verified successful trajectories feed the SFT views: **180 training tasks (2,951 decisions)** and **20 validation tasks (216 decisions)**. Test success is not exhaustive semantic review. Failed attempts and truncated responses remain available in the raw release but are not positive SFT targets. Never split individual decisions from the same task across train/validation.

`revisions.json` pins the model commit. Supply the full dataset commit SHA through `DATASET_REVISION`; bootstrap records both revisions in `run_revisions.json`. `prepare.py` refuses silently truncated examples: overlength or malformed examples are recorded in `preparation.json`. With the pinned release, all 3,167 eligible decisions fit the 24,576-token preparation ceiling; the longest training example is 19,825 tokens. This ceiling is **not a claim that arbitrary 24K examples fit in memory**.

## Environment

Validated image: `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, Python 3.12, PyTorch `2.8.0+cu128`, 96GB RTX PRO 6000 Blackwell Server Edition. Use a compatible NVIDIA driver and the CUDA 12.8 build of PyTorch; do not install an older CUDA build on Blackwell.

Store downloads, prepared data, logs, and checkpoints on persistent storage. Allow roughly 70GB for the base cache plus space for data and checkpoints. Each retained checkpoint includes approximately 0.5GB of adapter weights plus optimizer state. A frozen full model is replicated on every GPU: this package is BF16 LoRA, not NF4 QLoRA and not tensor parallelism.

```bash
cd training/weighted_reasoning_lora
export DATASET_REPO="YOUR_NAMESPACE/YOUR_DATASET"
export DATASET_REVISION="FULL_DATASET_COMMIT_SHA"
export TRAIN_ROOT=/workspace/weighted_reasoning_lora
export HF_HOME=$TRAIN_ROOT/hf_cache
# If model access needs authentication, set HF_TOKEN through your secret manager.
# Do not put a token in a command committed to Git.
bash bootstrap.sh
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export OMP_NUM_THREADS=1
REV=$(python -c 'import json; print(json.load(open("revisions.json"))["model"]["revision"])')
```

`bootstrap.sh` downloads the pinned model and data, prepares native-template weighted samples, and runs the numerical loss test. On an existing PyTorch image it preserves PyTorch and installs the pinned Python dependencies. It does not create cloud resources or delete data.

## First: single-card training gate

```bash
set -o pipefail
CUDA_VISIBLE_DEVICES=0 python -u train.py \
  --data "$TRAIN_ROOT/tokenized/train.jsonl" \
  --output "$TRAIN_ROOT/smoke" --revision "$REV" \
  --smoke --save-every 1 2>&1 | tee "$TRAIN_ROOT/smoke.log"
```

The smoke test selects the shortest, P95, and longest real training sequences, performs three optimizer steps, checks finite positive gradient norms and nonzero adapter updates, saves checkpoints, reloads the final adapter, and requires exactly matching evaluation logits. Success is an existing `SMOKE_PASS.json` with `passed: true`, not simply a running process or a falling loss on different samples. A failure must be fixed before the full job.

Memory measures: microbatch size 1, non-reentrant gradient checkpointing, nested 2,048-token feed-forward checkpoint chunks, BF16 autocast, and selective completion logits. Prompt tokens still participate in attention but do not receive direct loss. Cross-entropy FP32 conversion is chunked. The first unchunked implementation exhausted memory on the longest sample; do not remove the memory measures casually.

## 2-4 GPUs on one host

Run the distributed numerical gate first. This compares the distributed weighted gradient against a centralized reference on CPUs; it is not a GPU capacity test.

```bash
for N in 2 3 4; do
  OMP_NUM_THREADS=1 torchrun --standalone --nproc_per_node=$N test_weighting.py
done
```

Then launch a full epoch. `--steps 0` (default) computes the number of optimizer steps to cover the data. The last distributed batch may repeat a few examples to keep ranks synchronized.

```bash
N=3  # set to 2, 3, or 4
ACCUM=4
set -o pipefail
torchrun --standalone --nproc_per_node=$N train.py \
  --data "$TRAIN_ROOT/tokenized/train.jsonl" \
  --output "$TRAIN_ROOT/lora-b-${N}gpu" --revision "$REV" \
  --accum "$ACCUM" --lr 2e-5 --save-every 50 \
  2>&1 | tee "$TRAIN_ROOT/lora-b-${N}gpu.log"
```

| GPUs | Microbatch/GPU | Accumulation | Decisions/optimizer step |
|---|---:|---:|---:|
| 2 | 1 | 4 | 8 |
| 3 | 1 | 4 | 12 |
| 4 | 1 | 4 | 16 |

These settings change the global batch. For a controlled comparison with global batch 24, use accumulation 12 / 8 / 6 for 2 / 3 / 4 GPUs. All GPUs need 96GB; a 48GB RTX 6000 Ada is a different card and cannot use this BF16 recipe as written. Actual multi-GPU throughput depends on PCIe/NCCL and has not been measured by the single-card smoke test.

## One GPU on each of 2-4 hosts

Run `bootstrap.sh` on every host with the same pinned revisions. A shared filesystem is required for the output directory in the current checkpoint implementation, because each rank writes its own RNG state. The dataset/cache may be local copies. Set a private, mutually reachable rendezvous address; do not expose the rendezvous service publicly.

On every host, set `NNODES=2`, `3`, or `4`, and a distinct `NODE_RANK` from zero through `NNODES-1`:

```bash
export NNODES=3
export NODE_RANK=0   # use 1 and 2 on the other hosts
export MASTER_ADDR=10.0.0.10  # replace with rank-0 private address
export MASTER_PORT=29500
export SHARED_OUTPUT=/shared/lora-b-run

torchrun --nnodes="$NNODES" --nproc_per_node=1 \
  --node_rank="$NODE_RANK" --master_addr="$MASTER_ADDR" \
  --master_port="$MASTER_PORT" train.py \
  --data "$TRAIN_ROOT/tokenized/train.jsonl" \
  --output "$SHARED_OUTPUT" --revision "$REV" --accum 4
```

The same shared output path must be visible on every host. Without shared output storage, use a single multi-GPU host for this version. Multi-host operation and NCCL networking are implemented through standard torchrun/DDP but were not physically tested in this validation. DDP synchronizes only trainable adapter gradients, yet slow networking can still limit throughput.

## Checkpoints and restart

Each checkpoint contains `adapter/`, `training_state.pt`, and `rng.rankN.pt` for each rank. A `COMPLETE.json` marker is written only after all ranks finish writing. The output also contains `config.json` and per-rank `metrics.rankN.jsonl`. Keep the model/dataset revisions, GPU count, seed, accumulation, and data ordering unchanged when resuming.

```bash
torchrun --standalone --nproc_per_node=3 train.py \
  --data "$TRAIN_ROOT/tokenized/train.jsonl" \
  --output "$TRAIN_ROOT/lora-b-3gpu" --revision "$REV" --accum 4 \
  --resume "$TRAIN_ROOT/lora-b-3gpu/checkpoint-50"
```

This reloads optimizer and per-rank RNG state and reconstructs the deterministic sampler position. It rejects a different world size. Do not resume from an incomplete checkpoint or an adapter-only download. Reproducibility across different CUDA/library/hardware versions is not guaranteed. The smoke checkpoints from the initial memory debugging run are evidence artifacts, not recommended starting points for a full training run.

## Configuration and evaluation

LoRA: rank 16, alpha 16, dropout 0.05; language-model q/k/v/o and gate/up/down projections; frozen base/embedding/output/vision weights. Optimizer: AdamW, learning rate 2e-5, weight decay 0.01, gradient clipping 1.0, constant learning rate, seed 42. This is a deliberately small, inspectable starting recipe, not an optimized hyperparameter search. `--steps` can cap a development run.

The base is Google's QAT-unquantized half-precision release. It is not the compressed-tensors deployment checkpoint itself. A saved adapter's loading, parameter-name compatibility, tool serialization, and downstream quality must still be verified in the intended inference runtime. Do not claim that the training smoke test validates quantized deployment or improves agent success rate. The model and native-template choices are grounded in the [official model card](https://huggingface.co/google/gemma-4-31B-it-qat-q4_0-unquantized).

For model selection, compare frozen base and adapter under identical tools, timeout, thinking configuration, compaction, task order and generation sampling. Use held-out tasks and multiple seeds for close comparisons; never train on those evaluation tasks. Report task resolution rate, runtime, output/reasoning tokens, tool-call failures and timeout rate. Teacher-forcing loss alone is insufficient. This package deliberately does not launch an expensive downstream benchmark automatically.

## Files

- `prepare.py`: native-template conversion and per-token weights; rejects truncation.
- `train.py`: single-card/DDP training, memory controls, checkpoints, smoke gate.
- `test_weighting.py`: causal-loss weighting and distributed normalization tests.
- `test_template.py`: native-template target-mask tests.
- `bootstrap.sh`, `requirements.txt`, `revisions.json`: reproducible setup.
- `VALIDATION.md` and `validation/`: measured evidence and limits.

The example dataset variables must be replaced with the authorized dataset name and the 40-character commit SHA from its Files/History page. No credentials are included. The data retains mixed upstream licensing; see its dataset card before redistribution. All cloud lifecycle management remains outside these scripts.
