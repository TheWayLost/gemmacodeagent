"""Sandbox-only candidate storage; no host callbacks, model calls or gold data."""
import argparse,fcntl,hashlib,json,os,pathlib,shutil,signal,subprocess,sys,time
ROLE='B'
ROOT=pathlib.Path(os.environ.get('DUAL_TEST_WORKSPACE','/workspace')).resolve()
STORE=pathlib.Path(os.environ.get('DUAL_TEST_STORE','/tmp/w4_dual_reports')).resolve()
def git(repo,*args,check=True):
 r=subprocess.run(['git','-c','safe.directory=*','-C',str(repo),*args],capture_output=True,text=True,timeout=30)
 if check and r.returncode:raise RuntimeError(r.stderr[-2000:])
 return r.stdout

def write(p,x):
 q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2));os.replace(q,p)
def read(p):return json.loads(p.read_text())
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def protected(name):
 p=pathlib.PurePosixPath(name);b=p.name
 return any(v in {'test','tests','testing'} for v in p.parts[:-1]) or b.startswith('test_') or b.endswith('_test.py') or b in {'conftest.py','pytest.ini','pyproject.toml','tox.ini','setup.cfg','.pytest.ini','sitecustomize.py','usercustomize.py','_swegemma_stubs.py'} or b.endswith('.pth')
def init():
 STORE.mkdir(parents=True,exist_ok=True);p=STORE/'state.json'
 if not p.exists():write(p,{'base':git(ROOT,'rev-parse','HEAD').strip(),'started':time.monotonic(),'fallback':None,'applied_patch':''})
 return read(p)
def candidate(label,state):
 d=STORE/label;meta=d/'meta.json';repo=d/'repo'
 if not meta.exists():
  d.mkdir(exist_ok=True);git(ROOT,'clone','--shared','--quiet',str(ROOT),str(repo));git(repo,'checkout','--quiet','--detach',state['base'])
  now=time.monotonic();write(meta,{'label':label,'started':now,'deadline':min(now+720,state['started']+720),'calls':0,'finished':False,'patch_sha256':sha('')});(d/'patch.diff').write_text('')
 return d,repo,read(meta)
def capture(d,repo,state,meta):
 git(repo,'add','-N','--','.')
 names=git(repo,'diff','--name-only','-z',state['base']).split('\0');names=[n for n in names if n and not protected(n)]
 patch=git(repo,'diff','--binary',state['base'],'--',*names) if names else ''
 (d/'patch.diff').write_text(patch);meta['patch_sha256']=sha(patch);meta['patch_bytes']=len(patch.encode());write(d/'meta.json',meta)
 return patch

def install(patch,state):
 previous=state.get('applied_patch','');prior_added=state.get('applied_added',[])
 git(ROOT,'reset','--hard',state['base'])
 for name in prior_added:
  p=ROOT/name
  if not p.is_symlink() and p.is_file() and p.resolve().is_relative_to(ROOT):p.unlink()
  elif p.is_symlink():p.unlink()
 if patch:
  r=subprocess.run(['git','-c','safe.directory=*','-C',str(ROOT),'apply','--check','-'],input=patch,text=True,capture_output=True)
  if r.returncode:
   if previous:subprocess.run(['git','-C',str(ROOT),'apply','-'],input=previous,text=True,check=True,capture_output=True)
   raise RuntimeError('Patch check failed; previous fallback restored: '+r.stderr[-1000:])
  subprocess.run(['git','-C',str(ROOT),'apply','-'],input=patch,text=True,check=True,capture_output=True)
 git(ROOT,'add','-N','--','.')
 state['applied_patch']=patch;state['applied_added']=git(ROOT,'diff','--name-only','--diff-filter=A','-z',state['base']).strip('\0').split('\0') if patch else []
 write(STORE/'state.json',state)

def save_report(d,report):
 if not isinstance(report,str) or not report.strip() or len(report)>6000:raise ValueError('Write your own nonempty report, at most6000characters; do not pass a path.')
 (d/'report.md').write_text(report);write(d/'report_provenance.json',{'author':'solver_'+ROLE,'sha256':sha(report),'saved_monotonic':time.monotonic()})
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--action',required=True,choices=['status','begin','checkpoint','exec','finish','inspect','select']);ap.add_argument('--command',default='');ap.add_argument('--report');ap.add_argument('--candidate',choices=['A','B']);ap.add_argument('--part',choices=['patch','report'],default='patch');ap.add_argument('--offset',type=int,default=0);ap.add_argument('--limit',type=int,default=6000);a=ap.parse_args()
 STORE.mkdir(parents=True,exist_ok=True)
 with (STORE/'lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);state=init()
  if ROLE in ['A','B']:
   if a.action not in ['status','begin','checkpoint','exec','finish']:raise ValueError('Solver can only operate on its own candidate.')
   d,repo,m=candidate(ROLE,state)
   if a.report is not None:save_report(d,a.report)
   if a.action=='begin' and not m['finished']:
    m['segment']=min(7,m.get('segment',0)+1);m['segment_start_calls']=m['calls'];write(d/'meta.json',m)
   left=m['deadline']-time.monotonic();result={'candidate':ROLE,'seconds_left_for_operations':max(0,round(left,1)),'calls_remaining':max(0,56-m['calls']),'finished':m['finished']}
   result.update(segment=m.get('segment',1),segment_calls_remaining=max(0,8-(m['calls']-m.get('segment_start_calls',0))),final_segment=m.get('segment',1)>=7)
   if a.action=='begin':result['own_previous_report']=(d/'report.md').read_text() if (d/'report.md').exists() else None
   if a.action=='checkpoint':
    if not (d/'report.md').exists():raise ValueError('Write your own continuation report using report.')
    capture(d,repo,state,m);result['next']='Return CANDIDATE_'+ROLE+'_CONTINUE now. Another fresh invocation of this same solver will continue from your own report and repository.'
   if a.action=='exec':
    if m['finished'] or left<=0 or m['calls']>=56 or m['calls']-m.get('segment_start_calls',0)>=8:result['error']='Candidate operation budget exhausted. Write your own report. If time/global operations exhausted or final_segment, use finish; otherwise checkpoint. Then end with CANDIDATE_'+ROLE+'_SAVED.'
    elif not a.command:raise ValueError('command required')
    else:
     m['calls']+=1;write(d/'meta.json',m);env=dict(os.environ);env['PYTHONPATH']=str(repo/'src')+os.pathsep+str(repo);env['PWD']=str(repo);env['PYTHONDONTWRITEBYTECODE']='1'
     start=time.monotonic();proc=subprocess.Popen(['/bin/bash','-c',a.command],cwd=repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
     try:output,_=proc.communicate(timeout=max(.05,min(180,left)));result.update(exit_code=proc.returncode,output=output[-1500:])
     except subprocess.TimeoutExpired:
      os.killpg(proc.pid,signal.SIGKILL);output,_=proc.communicate();result.update(exit_code=124,timeout=True,output=output[-1500:])
     try:os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     with (d/'operations.jsonl').open('a') as f:f.write(json.dumps({'command':a.command,'seconds':time.monotonic()-start,**result},ensure_ascii=False)+'\n')
     patch=capture(d,repo,state,m)
     if patch and (ROLE=='A' or not state.get('applied_patch')):
      install(patch,state);state['fallback']=ROLE;write(STORE/'state.json',state)
   if a.action=='finish':
    if not (d/'report.md').exists():raise ValueError('No agent-authored report. Pass your own report text using --report.')
    if not m['finished']:capture(d,repo,state,m)
    m['finished']=True;write(d/'meta.json',m);result.update(finished=True,report_sha256=sha((d/'report.md').read_text()),patch_sha256=m['patch_sha256'])
   print(json.dumps(result,ensure_ascii=False));return
  if ROLE!='JUDGE' or a.action not in ['status','inspect','select']:raise ValueError('Invalid judge operation')
  if a.action=='status':
   result={}
   for label in ['A','B']:
    d=STORE/label;result[label]={'exists':(d/'meta.json').exists(),'report_exists':(d/'report.md').exists()}
    if (d/'meta.json').exists():result[label].update(read(d/'meta.json'))
   print(json.dumps(result));return
  if a.candidate is None:raise ValueError('candidate A/B required')
  d=STORE/a.candidate
  if a.action=='inspect':
   f=d/('patch.diff' if a.part=='patch' else 'report.md')
   if not f.exists():print(json.dumps({'missing':True,'candidate':a.candidate,'part':a.part}));return
   s=f.read_text();off=max(0,a.offset);limit=max(1,min(a.limit,6000));print(json.dumps({'candidate':a.candidate,'part':a.part,'sha256':sha(s),'total_chars':len(s),'offset':off,'next_offset':off+limit if off+limit<len(s) else None,'content':s[off:off+limit]},ensure_ascii=False));return
  if not (d/'patch.diff').exists():raise ValueError('Candidate missing')
  patch=(d/'patch.diff').read_text();install(patch,state);write(STORE/'selection.json',{'choice':a.candidate,'patch_sha256':sha(patch),'selected_by':'W4_verifier'});print(json.dumps({'selected':a.candidate,'patch_sha256':sha(patch),'next':'Call submit_patch() now.'}))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'error':type(e).__name__,'message':str(e)}));sys.exit(1)
