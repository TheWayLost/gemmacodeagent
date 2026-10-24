from pathlib import Path
import json,yaml
from adk_submission import compile_submission,ModelRegistry,GenerationConstraints,NumericRange
from swegemma.config import build_submission_limits
from google.adk.models.lite_llm import LiteLlm
from google.adk.flows.llm_flows.contents import _get_current_turn_contents
from google.adk.events import Event
from google.genai import types
P=Path(__file__).resolve().parent;D=P/'submission'
models=ModelRegistry();models.register('gemma-4-31b-it-qat-w4a16-ct',LiteLlm(model='openai/gemma-4-31b-it-qat-w4a16-ct',api_base='http://127.0.0.1:8002/v1',api_key='EMPTY'))
def submit_patch()->str:return 'test'
def get_status()->str:return 'test'
a=compile_submission(D,tool_registry={'submit_patch':submit_patch,'get_status':get_status},model_registry=models,limits=build_submission_limits()[0],generation_constraints=GenerationConstraints(allowed_fields=None,max_output_tokens=NumericRange(1,32768),thinking_budget=NumericRange(0,32768)))
assert len(a.sub_agents)==2
solvers=[]
for master in a.sub_agents[0].sub_agents:
 group_tools=[t for t in master.tools if hasattr(t,"agent")]
 assert len(group_tools)==1
 loop=group_tools[0].agent
 assert loop.max_iterations==7
 launcher=loop.sub_agents[0]
 assert launcher.generate_content_config.thinking_config.thinking_budget==0
 nested=[t for t in launcher.tools if hasattr(t,'agent')]
 assert len(nested)==1 and nested[0].skip_summarization
 solvers.append(nested[0].agent)
actors=solvers+[a.sub_agents[1]]
for x in actors:
 assert x.generate_content_config.thinking_config.thinking_budget==6000
 assert x.model.model=='openai/gemma-4-31b-it-qat-w4a16-ct'
 assert x.include_contents=='none'
r={'compiled':True,'solvers_in_private_AgentTool_sessions':True,'outer_parallel_receives_only_group_acknowledgements':True,'segments_per_solver':7,'max_commands_per_segment':8,'models':[x.model.model for x in actors],'thinking_budgets':[x.generate_content_config.thinking_config.thinking_budget for x in actors],'launcher_thinking_budget':0,'max_time_minutes':yaml.safe_load((D/'eval_config.yaml').read_text())['evaluation']['max_time_minutes']}
(P/'validation.json').write_text(json.dumps(r,indent=2));print(r)
