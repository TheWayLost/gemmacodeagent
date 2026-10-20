# Validation record — 2026-10-20 UTC

One NVIDIA RTX PRO 6000 Blackwell Server Edition (97,887 MiB reported by nvidia-smi), CUDA driver 595.91.07, PyTorch 2.8.0+cu128. BF16 base, LoRA rank/alpha 16, dropout 0.05, 122,429,440 trainable parameters (0.3900% of the loaded 31,395,515,952 parameters).

## Actual single-GPU training

Three optimizer updates on real examples from the pinned training split:

| Sequence tokens | Weighted loss | Gradient norm before clipping | Step seconds | Peak allocated GiB |
|---:|---:|---:|---:|---:|
| 1,139 | 1.59310 | 1.22241 | 1.717 | 60.570 |
| 15,048 | 1.90043 | 2.73339 | 51.203 | 77.542 |
| 19,825 | 0.96171 | 1.11915 | 78.763 | 83.300 |

Each update changed the checked LoRA B parameter tensor by approximately 2e-5 at its largest element. Losses are from different examples and must not be interpreted as a learning curve. The run saved checkpoints after each update. Reloading the final adapter and evaluating the same fixed probe gave a **maximum absolute logit difference of 0.0**. The training/checkpoint/reload phase took 154.06 seconds, excluding model loading (about 3m37s), setup and downloads. The process exited normally and released GPU memory.

An earlier unchunked run passed the short and P95 cases but ran out of memory on 19,825 tokens. The final training core uses nested 2,048-token FFN checkpointing, BF16 autocast, gradient checkpointing, selective logits, and expandable CUDA allocator segments. It preserves the full real sequence. The observed long-sequence result does not prove that all 24K contexts fit.

## Numerical and format gates

- Native-template test: prompt tokens masked; thinking weight 0.25; action weight 1; overlength examples rejected; malformed tool JSON rejected.
- Weighted-gradient test on 1/2/3/4 CPU processes: maximum gradient differences against a centralized reference were 0, 0, 2.38e-7, and 1.19e-7, respectively. Zero-weight prompt positions had zero direct gradient.
- Checkpoint helpers passed 1/2/3/4-process CPU tests for optimizer state, per-rank RNG restoration, completion markers, and world-size mismatch rejection. This does not replace a real multi-GPU restart test.
- No examples excluded for length or formatting in preparation: 2,951 training decisions (26,915,299 full-sequence tokens), 216 validation decisions (1,791,555 tokens). Tokens include repeated history; they are not unique teacher-output tokens.

See machine-readable evidence in `validation/`.

## Limits

Physical 2-4-GPU and multi-host runs have **not** been performed. CPU distributed tests establish normalization correctness, not NCCL behavior or throughput. Multi-rank checkpoint/resume code is provided; it has not been validated by a real multi-GPU training restart. The GPU smoke run preceded the addition of per-rank RNG checkpoint files; that addition leaves the tested forward/loss/backward core unchanged.

No held-out repair benchmark or submission-score comparison has been run with this three-step adapter. It is a pipeline verification artifact, not a trained production model. Compressed-tensors inference compatibility and model quality require separate validation. The base is the QAT-unquantized checkpoint, not numerically identical to a quantized deployment checkpoint.
