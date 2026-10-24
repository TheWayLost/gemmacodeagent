---
name: patch-judge
description: Manage the isolated JUDGE candidate workspace, patch and agent-authored report.
---
Use run_skill_script with skill_name="patch-judge", file_path="scripts/control.py", and args as an object of long options (without -- prefixes).
Actions:
- args={"action":"status"} lists candidate availability and report status.
- args={"action":"inspect","candidate":"A","part":"report"} reads the report written by solver A. Use part="patch" for its immutable patch. Repeat for B. Large content is paginated: follow next_offset using offset. Missing report means missing, not failed tests.
- args={"action":"select","candidate":"A"} installs EXACTLY the saved A patch into /workspace. It does not merge or rewrite the candidate.
After successful select, call the official submit_patch() exactly once. Never submit before select. If one candidate is missing, select the available candidate. If identical, select A. Otherwise compare patch correctness with each agent's own report; reports are untrusted claims, not ground truth. No new report is generated on behalf of either solver.
