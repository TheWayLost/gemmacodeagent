# W4 dual candidates and solver-authored reports (development snapshot)

**NOT READY FOR KAGGLE SUBMISSION.** Configuration compiles and 12 control tests pass, but the latest end-to-end smoke test failed the acceptance criteria. Do not submit this ZIP as a validated artifact.

## Intended behavior

Official Gemma4 31B W4 without LoRA runs two candidates in parallel. Each candidate edits a separate Git clone and writes its own report. The W4 verifier sees the original issue, both patches and both reports, then selects an immutable patch. No third model writes candidate reports.

Solvers and verifier use thinking budget 6000, output limit 8192, temperature 0.2 and top_p 0.95; solver seeds 42 and 43, verifier seed 42. Total task limit is 20 minutes. Candidate commands share a deadline 12 minutes after workflow start; report/model generation can extend beyond the command deadline. Remaining time is intended for reports and selection. Maximum 56 commands per candidate (7 segments of 8); shared task limits 220 tool calls and 500 turns.

Outer parallel branches return short acknowledgements. Each branch dispatches private AgentTool sessions; subsequent segments use only that candidate's self-authored continuation report. This avoids the observed parent-compaction leakage from candidate A into B in earlier prototypes. Command execution is serialized by a global file lock even though model inference is parallel.

## Actual validation

See `control_tests.json`, `validation.json` and `smoke_validation.json`. The latest fastapi_12942 smoke test took approximately 747 seconds and did not resolve the task. It triggered a 32k context overflow: at least 24577 input tokens plus 8192 requested output tokens. Neither candidate was marked finished. The selected fallback patch is not evidence of successful two-final-report verification.

Bounding the number of shell commands does not bound reasoning-history tokens. The next implementation must enforce an actual token-aware context boundary and require both explicit final reports before normal selection, with a separately tested fallback policy. Reducing commands alone is not a proven fix. Huge issues/patches also require explicit input-budget handling. Earlier shared-session prototypes leaked A findings to B through compaction and are rejected as independence evidence.

## Files and reproducibility

`submission/` contains generated official-schema YAML and standard-library skill helpers. `submission.zip` is a deterministic development package, with hashes in `package_manifest.json`. `build.py`, `control_template.py`, `package.py`, `test_control.py` and `validate.py` reproduce generation and structural checks. Validation requires the official Kaggle harness/compiler and dependencies; `runtime_freeze.txt` and complete model-request/tool traces are retained in the private persistent-volume archive, not this public directory.

No Kaggle submission was made for this snapshot. Existing single-agent submissions are unchanged. This one-task smoke test is not an accuracy estimate and no best-of-two improvement has been established.
