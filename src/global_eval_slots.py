"""Eight host-wide flock leases; crash-safe, no PID reuse or stale JSON leases."""
import fcntl,os,time
from pathlib import Path
class Slot:
 def __enter__(self):
  root=Path(os.environ.get('GEMMA_SLOT_DIR','/root/autodl-tmp/gemma-eval-slots'));root.mkdir(parents=True,exist_ok=True)
  while True:
   for i in range(8):
    f=(root/str(i)).open('a+')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:f.close();continue
    self.file=f;return self
   time.sleep(.25)
 def __exit__(self,*args):self.file.close()
