# Fixed16 results at shutdown, 2026-10-17

80 completed task-model evaluations on the SAME 16 tasks, Budget-Fit v5 900s / thinking 6000. These are pilot deployment results, not the complete 129-task evaluation.

| Model | Resolved | Rate | Mean task minutes | Explicit deadline failures |
|---|---:|---:|---:|---:|
| Kaggle Gemma 4 W4A16 | 9/16 | 56.25% | 8.78 | 0 |
| Qwen3.5-9B FP8 | 7/16 | 43.75% | 7.72 | 1 |
| Qwen3.5-9B + SWE-Gym LoRA | 4/16 | 25.00% | 8.35 | 1 |
| Qwen3.8-27B FP8 | 5/16 | 31.25% | 12.12 | 10 |
| Coder390 FP8 | 7/16 | 43.75% | 12.07 | 8 |

Means include successes and failures. No explicit timeout error does not imply success. Qwen 9B base hit 160 turns twice; LoRA hit that limit seven times and had one API/template error (No user query found in messages). Do not attribute all of its deficit to weights. The adapter uses rank32/alpha64; tensor prefixes were remapped for vLLM and bitwise preservation checked.

Coder390 improves the observed count by 2/16 (12.5 percentage points) over its base, with similar mean time and two fewer deadline failures. This is suggestive, not conclusive: small sample, stochastic rollouts, quantization protected-layer differences and deadline contention limit causal interpretation. SWE-Gym LoRA is lower by 3/16 (18.75 points) under this harness; it did not demonstrate a benefit in this pilot. Original Gemma has the strongest observed pilot score, but cross-family sampling/quantization differ.

EfficientThink was cancelled; interrupted trials are excluded. Teich Agent-Distill and Capybara have no scored tasks; downloads were stopped by request. Their runtime FP8 loading is unvalidated. All download chunks remain on the original persistent disk, but are not uploaded to GitHub.

Archive: `/root/autodl-tmp/codeagent/gemma4/archives/model_comparison_20261017_234228/` includes completed task traces, state/protocol snapshots, summary, paused-download inventory and SHA256 manifest. `current_results.json` provides per-task outcomes. Raw traces remain private on the persistent disk; GitHub contains code/manifests and aggregate/task-level metrics only. Power-off preserves the disk only according to your cloud storage retention settings: retain the data volume if releasing the instance.
