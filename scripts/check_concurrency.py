#!/usr/bin/env python3
"""CPU-only tests of the actual global slot gate; never touches production locks/GPU."""
import argparse,fcntl,json,os,subprocess,sys,tempfile,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'src'))

def wait_until(predicate,seconds=15):
 end=time.monotonic()+seconds
 while not predicate():
  if time.monotonic()>end:raise TimeoutError('Timed out waiting for gate workers')
  time.sleep(.03)

def worker(root,capacity,mode):
 os.environ['GEMMA_SLOT_DIR']=str(root/'slots')
 os.environ['GEMMA_EVAL_SLOTS']=str(capacity)
 from global_eval_slots import Slot
 if mode=='mismatch':
  try:
   with Slot():pass
  except RuntimeError as e:
   if 'Slot capacity differs' in str(e):return
   raise
  raise AssertionError('Mismatched capacity was accepted')
 with Slot():
  if mode in ['holder','recovery']:
   (root/mode).write_text(str(os.getpid()))
   if mode=='holder':time.sleep(120)
   return
  def event(delta):
   with (root/'audit.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    path=root/'count';n=int(path.read_text()) if path.exists() else 0
    n+=delta;assert 0<=n<=capacity,f'Gate overflow/underflow: {n}/{capacity}'
    path.write_text(str(n))
    with (root/'events.jsonl').open('a') as out:
     out.write(json.dumps({'pid':os.getpid(),'delta':delta,'count':n,'time':time.monotonic()})+'\n')
  event(1)
  try:
   wait_until(lambda:(root/'release').exists())
   time.sleep(.12)
  finally:event(-1)

def run_capacity(root,capacity):
 root.mkdir();processes=[];logs=[]
 def spawn(mode,cap=capacity):
  log=(root/f'worker-{len(processes)}.log').open('w+');logs.append(log)
  p=subprocess.Popen([sys.executable,__file__,'--worker',str(root),str(cap),mode],stdout=log,stderr=log)
  processes.append(p);return p
 try:
  count=2*capacity+4
  for _ in range(count):spawn('normal')
  # Hold the first full wave until saturation is observed, rather than relying on timing.
  wait_until(lambda:(root/'count').exists() and (root/'count').read_text()==str(capacity))
  (root/'release').touch()
  deadline=time.monotonic()+20
  for p in processes:
   assert p.wait(timeout=max(.1,deadline-time.monotonic()))==0,'Worker failed'
  events=[json.loads(l) for l in (root/'events.jsonl').read_text().splitlines()]
  assert len(events)==2*count and int((root/'count').read_text())==0
  assert max(e['count'] for e in events)==capacity
  for pid in {e['pid'] for e in events}:
   assert [e['delta'] for e in events if e['pid']==pid]==[1,-1]
  mismatch=spawn('mismatch',2 if capacity==1 else 1)
  assert mismatch.wait(timeout=10)==0,'Capacity mismatch was not rejected'
  return {'capacity':capacity,'workers':count,'observed_peak':capacity,'all_completed':True,'mismatch_rejected':True}
 finally:
  for p in processes:
   if p.poll() is None:p.kill()
  for p in processes:p.wait()
  for log in logs:
   log.seek(0);text=log.read()
   if text:print(text,file=sys.stderr)
   log.close()

def crash_recovery(root):
 root.mkdir();processes=[]
 try:
  holder=subprocess.Popen([sys.executable,__file__,'--worker',str(root),'1','holder']);processes.append(holder)
  wait_until(lambda:(root/'holder').exists());holder.kill();holder.wait()
  recovered=subprocess.Popen([sys.executable,__file__,'--worker',str(root),'1','recovery']);processes.append(recovered)
  assert recovered.wait(timeout=10)==0 and (root/'recovery').exists()
 finally:
  for p in processes:
   if p.poll() is None:p.kill()
   p.wait()

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--capacities',nargs='+',type=int,default=[1,2,3,4,8])
 ap.add_argument('--output',type=Path,help='Optional JSON report')
 ap.add_argument('--worker',nargs=3,help=argparse.SUPPRESS)
 a=ap.parse_args()
 if a.worker:worker(Path(a.worker[0]),int(a.worker[1]),a.worker[2]);return 0
 if not a.capacities or len(set(a.capacities))!=len(a.capacities) or any(c<1 or c>8 for c in a.capacities):ap.error('capacities must be unique integers from 1 to 8')
 (R/'tmp').mkdir(exist_ok=True);report={'passed':False,'gpu_capacity_tested':False,'cases':[]}
 try:
  with tempfile.TemporaryDirectory(prefix='gate-check-',dir=R/'tmp') as directory:
   root=Path(directory)
   for cap in a.capacities:
    row=run_capacity(root/str(cap),cap);report['cases'].append(row)
    print(f'PASS capacity={cap}: peak={cap}, {row["workers"]} workers completed, mismatch rejected',flush=True)
   crash_recovery(root/'crash');report['crash_recovery']=True
   print('PASS crash recovery: killed holder released its slot',flush=True)
  report['passed']=True
 except Exception as e:
  report['error']=repr(e);print('FAIL: '+repr(e),file=sys.stderr,flush=True)
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(('PASS' if report['passed'] else 'FAIL')+' OVERALL: CPU scheduling gate only; GPU VRAM/throughput NOT tested.',flush=True)
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
