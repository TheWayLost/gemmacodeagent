#!/usr/bin/env python3
"""Real 48GB RTX4090 GPU qualification: long-context 1/2/3/4-way inference."""
import argparse,concurrent.futures as cf,datetime,fcntl,json,os,random,re,signal,socket,subprocess,sys,threading,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
NAME='gemma-4-31b-it-qat-w4a16-ct'

def metric(text,name):
 vals=[]
 for line in text.splitlines():
  if re.match(re.escape(name)+r'(?:\{|\s)',line):vals.append(float(line.split()[-1]))
 return sum(vals) if vals else None

def gpu_info(gpu):
 text=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-gpu=uuid,name,memory.total,memory.used','--format=csv,noheader,nounits'],text=True).strip()
 uuid,name,total,used=[x.strip() for x in text.split(',')]
 return {'uuid':uuid,'name':name,'total_mib':int(total),'used_mib':int(used)}

def stop_server(pid):
 if pid is None:return
 # PID came from this script's isolated startup directory; never inspect/kill port owners.
 try:os.killpg(pid,signal.SIGTERM)
 except ProcessLookupError:return
 for _ in range(100):
  try:
   os.killpg(pid,0)
  except ProcessLookupError:return
  time.sleep(.1)
 try:os.killpg(pid,signal.SIGKILL)
 except ProcessLookupError:pass

def wave(client,base,cap,round_id,pool_tokens,args,directory):
 import requests
 barrier=threading.Barrier(cap+1)
 def request(i):
  # Disable prefix caching AND randomize every request: shared KV blocks cannot inflate capacity.
  rng=random.Random(900000+cap*1000+round_id*10+i)
  prompt=[rng.choice(pool_tokens) for _ in range(args.input_tokens)]
  barrier.wait(timeout=60);start=time.monotonic()
  with requests.Session() as session:
   session.trust_env=False
   response=session.post(base+'/v1/completions',json={'model':NAME,'prompt':prompt,'max_tokens':args.output_tokens,'temperature':0.2,'ignore_eos':True,'seed':i+round_id*10},timeout=(15,args.request_timeout))
   response.raise_for_status();data=response.json()
  usage=data.get('usage',{});assert usage.get('completion_tokens')==args.output_tokens,'Truncated generation'
  assert usage.get('prompt_tokens')==args.input_tokens,'Unexpected prompt token count'
  return {'request':i,'seconds':time.monotonic()-start,'usage':usage}
 def metrics():
  response=client.get(base+'/metrics',timeout=5);response.raise_for_status();return response.text
 before=metric(metrics(),'vllm:num_preemptions_total')
 rows=[];errors=[];peak_running=0;peak_memory=0;metrics_seen=False;start=time.monotonic()
 with cf.ThreadPoolExecutor(max_workers=cap) as executor:
  futures=[executor.submit(request,i) for i in range(cap)];barrier.wait(timeout=60)
  while not all(f.done() for f in futures):
   try:
    value=metric(metrics(),'vllm:num_requests_running')
    if value is not None:metrics_seen=True;peak_running=max(peak_running,value)
    peak_memory=max(peak_memory,gpu_info(args.gpu)['used_mib'])
   except Exception as e:errors.append('Telemetry failed: '+str(e));break
   time.sleep(.5)
  for f in futures:
   try:rows.append(f.result())
   except Exception as e:errors.append(str(e))
 elapsed=time.monotonic()-start
 try:after=metric(metrics(),'vllm:num_preemptions_total')
 except Exception as e:after=None;errors.append(str(e))
 if not metrics_seen or peak_running<cap:errors.append(f'Only {peak_running}/{cap} requests observed running; queued requests do not prove capacity')
 if before is None or after is None:errors.append('Missing preemption metric; cannot certify capacity')
 elif after>before:errors.append(f'KV preemption count increased by {after-before}')
 result={'wave':round_id,'passed':not errors and len(rows)==cap,'seconds':elapsed,'peak_running':peak_running,'peak_gpu_mib':peak_memory,'output_tokens_per_second':sum(r['usage']['completion_tokens'] for r in rows)/elapsed,'requests':rows,'errors':errors}
 (directory/f'wave-{round_id}.json').write_text(json.dumps(result,indent=2));return result

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--gpu',default='0',help='Physical nvidia-smi index or UUID')
 ap.add_argument('--port',type=int,default=8124)
 ap.add_argument('--waves',type=int,default=3)
 ap.add_argument('--input-tokens',type=int,default=30000)
 ap.add_argument('--output-tokens',type=int,default=2048)
 ap.add_argument('--request-timeout',type=int,default=900)
 ap.add_argument('--startup-timeout',type=int,default=900)
 ap.add_argument('--output',type=Path)
 ap.add_argument('--dry-run',action='store_true',help='Print plan only; no GPU/model access and no capacity claim')
 a=ap.parse_args()
 if a.waves<3 or a.input_tokens<1 or a.output_tokens<1 or a.input_tokens+a.output_tokens>32768:ap.error('Need >=3 waves and total tokens <=32768')
 if min(a.request_timeout,a.startup_timeout)<=0:ap.error('Timeouts must be positive')
 plan={'capacities':[1,2,3,4],'waves':a.waves,'input_tokens':a.input_tokens,'output_tokens':a.output_tokens,'prefix_caching':False,'port':a.port}
 if a.dry_run:print(json.dumps(plan,indent=2));return 0
 import requests
 from transformers import AutoTokenizer
 (R/'runs').mkdir(exist_ok=True)
 lock=(R/'runs/4090-capacity.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 gpu=gpu_info(a.gpu)
 if '4090' not in gpu['name'] or not 45000<=gpu['total_mib']<=53000:raise SystemExit('Refusing: this qualification requires a real 48GB RTX4090. Found '+str(gpu))
 if gpu['used_mib']>2048:raise SystemExit('GPU is already in use. Stop your own GPU jobs before testing; this script will not stop them.')
 with socket.socket() as probe:
  if probe.connect_ex(('127.0.0.1',a.port))==0:raise SystemExit('Test port is occupied; refusing to reuse/stop another service')
 subprocess.run([sys.executable,str(R/'scripts/verify_environment.py')],check=True)
 out=(a.output or R/'runs'/('4090-capacity-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
 out.mkdir(parents=True,exist_ok=False)
 env={**os.environ,'CUDA_VISIBLE_DEVICES':gpu['uuid']};base=f'http://127.0.0.1:{a.port}'
 tokenizer=AutoTokenizer.from_pretrained(R/'models'/NAME,local_files_only=True)
 pool=tokenizer.encode('Inspect the repository source code function parameter result and apply a precise implementation fix. ',add_special_tokens=False)
 report={'plan':plan,'hardware':gpu,'results':[],'maximum_passed':0,'recommended':0,'qualification_scope':'Synthetic long-context inference only; follow with gold/empty and agent smoke test. Not a proof for every future workload.'}
 def save():
  (out/'report.json').write_text(json.dumps(report,indent=2))
 def interrupted(signum,frame):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,interrupted)
 client=requests.Session();client.trust_env=False
 try:
  for cap in [1,2,3,4]:
   directory=out/f'concurrency-{cap}';directory.mkdir();pid=None
   result={'concurrency':cap,'waves':[],'passed':False};print(f'TEST {cap}-way: loading local model; artifacts {directory}',flush=True)
   try:
    cmd=[sys.executable,str(R/'src/start_model_capacity.py'),'--profile','4090-48g','--concurrency',str(cap),'--port',str(a.port),'--state-dir',str(directory)]
    with (directory/'launcher.log').open('w') as log:
     proc=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=a.startup_timeout)
    if (directory/'vllm.pid').exists():pid=int((directory/'vllm.pid').read_text())
    assert proc.returncode==0 and pid,'Launcher failed; inspect launcher.log'
    deadline=time.monotonic()+a.startup_timeout
    while True:
     try:
      if client.get(base+'/health',timeout=5).status_code==200:break
     except requests.RequestException:pass
     if time.monotonic()>deadline:raise TimeoutError('Model did not become healthy')
     if not Path(f'/proc/{pid}').exists() or Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[0]=='Z':raise RuntimeError('Model exited at startup')
     time.sleep(2)
    # Short real chat smoke checks Gemma chat/thinking interface before capacity requests.
    response=client.post(base+'/v1/chat/completions',json={'model':NAME,'messages':[{'role':'user','content':'Return the number 2.'}],'max_tokens':128,'thinking_token_budget':6000,'chat_template_kwargs':{'enable_thinking':True}},timeout=(15,a.request_timeout));response.raise_for_status();assert response.json().get('choices')
    for index in range(a.waves):
     row=wave(client,base,cap,index,pool,a,directory);result['waves'].append(row)
     print(f'  wave {index+1}/{a.waves}: {"PASS" if row["passed"] else "FAIL"}, running={row["peak_running"]}, peakVRAM={row["peak_gpu_mib"]}MiB, output={row["output_tokens_per_second"]:.1f} tokens/s',flush=True)
     if not row['passed']:raise RuntimeError('; '.join(row['errors']))
    result['passed']=True
    result['aggregate_tokens_per_second']=cap*a.waves*a.output_tokens/sum(w['seconds'] for w in result['waves'])
   except Exception as e:result['error']=str(e);print(f'FAIL {cap}-way: {e}',flush=True)
   finally:
    if pid is None and (directory/'vllm.pid').exists():pid=int((directory/'vllm.pid').read_text())
    stop_server(pid)
   report['results'].append(result);save()
   # Conservative ramp: do not stress higher concurrency after a lower level failed.
   if not result['passed']:break
   report['maximum_passed']=cap;save()
   time.sleep(3)
 except KeyboardInterrupt:report['interrupted']=True;print('Interrupted; retained partial report.',flush=True)
 finally:
  client.close()
  passed=[r for r in report['results'] if r['passed']]
  if passed:
   best=max(passed,key=lambda r:(r['aggregate_tokens_per_second'],-r['concurrency']));report['recommended']=best['concurrency']
  save()
 cap=report['recommended']
 text=['# 48GB RTX4090 capacity report',f'Maximum passed: {report["maximum_passed"]} (only among levels actually tested).',f'Recommended concurrency by measured aggregate throughput: {cap}.',report['qualification_scope']]
 if cap:
  text+=['Use the SAME gemmacodeagent checkout and artifacts/submission.zip; no separate model/code download.',f'CONCURRENCY={cap} bash scripts/run_4090_48g.sh model',f'CONCURRENCY={cap} bash scripts/run_4090_48g.sh eval --cohort paired20 --shards 1 --shard 0 --ids requests_6644 --arms v5_6000 --run 4090-smoke-c{cap}',f'CONCURRENCY={cap} bash scripts/run_4090_48g.sh eval --cohort paired20 --shards 1 --shard 0 --arms v5_6000 --run 4090-20-c{cap}', 'Run the single-task gold/empty/agent smoke before the full benchmark.', 'Before changing production slot capacity, stop ALL benchmark processes and then remove the old capacity.txt as documented.']
 else:text+=['No supported concurrency was demonstrated. Do not launch the benchmark; inspect per-level launcher.log/vllm.log and wave errors.']
 (out/'RECOMMENDATION.txt').write_text('\n'.join(text)+'\n')
 print('\n'+'\n'.join(text)+f'\nFull report: {out}/report.json',flush=True)
 return 0 if cap and not report.get('interrupted') else 1
if __name__=='__main__':raise SystemExit(main())
