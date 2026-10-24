---
name: candidate-b
description: Operate solver B's private repository and save its own continuation/final reports.
---
Call run_skill_script(skill_name="candidate-b",file_path="scripts/control.py",args={...}).
- begin: call once per invocation; returns your previous self-authored report, segment number, remaining calls/time and finished flag. If finished, end immediately.
- exec with command: execute bash inside YOUR repository. Use relative paths, small targeted reads, and focused tests. Outputs retain their last1500characters. At most8 operations per segment and56 overall. PYTHONPATH points to this repository.
- checkpoint with report: save YOUR OWN continuation report (<=6000characters), then end with CANDIDATE_B_CONTINUE. Use when you need another segment. This does not freeze the patch.
- finish with report: save YOUR OWN final report (<=6000characters), freeze your patch, then end with CANDIDATE_B_SAVED. Use when done, final_segment=true and segment allowance exhausted, or time/global calls exhausted.
- status: inspect your remaining allowance.
Reports must describe actual observations and tests, not invented success. Never read the other solver or /workspace. Do not modify tests/test-runner configuration. No background processes. Remove scratch files from the candidate repository. Command deadlines are subordinate to the shared20minute evaluator timeout; save a report before ending. The launcher never writes your report.
