import os, json, subprocess
from pathlib import Path
from adk_submission import VllmConfig,VllmServer
p=Path(__file__).resolve().parents[1]
name="gemma-4-31b-it-qat-w4a16-ct"
cfg=VllmConfig(model=str(p/"models"/name),host="127.0.0.1",port=8000,
tool_call_parser="gemma4",reasoning_parser="gemma4",max_model_len=32768,
dtype="bfloat16",gpu_memory_utilization=.90,enable_auto_tool_choice=True,
enable_lora=False,scheduler_reserve_full_isl=False,tensor_parallel_size=1,
limit_mm_per_prompt='{"image":0,"audio":0,"video":0}',
extra_args=["--served-model-name",name,"--max-num-seqs","32","--max-num-batched-tokens","4096"])
server=VllmServer(cfg)
cmd=server.build_cmd()
(p/"runs/server_command.json").write_text(json.dumps(cmd,indent=2))
with (p/"logs/vllm.log").open("a") as log:
 proc=subprocess.Popen(cmd,env=server.build_env(),stdout=log,stderr=log,start_new_session=True)
(p/"runs/vllm.pid").write_text(str(proc.pid))
print("vllm_pid",proc.pid,flush=True)
