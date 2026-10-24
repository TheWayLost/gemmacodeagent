"""Build a reproducible Kaggle ZIP containing only declarative submission files."""
from pathlib import Path
import hashlib,json,zipfile
P=Path(__file__).resolve().parent;D=P/'submission';out=P/'submission.zip'
manifest={}
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(D.rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts:continue
  name=p.relative_to(D).as_posix();data=p.read_bytes();manifest[name]=hashlib.sha256(data).hexdigest()
  info=zipfile.ZipInfo(name,(2026,10,24,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,data)
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None and 'agent.yaml' in z.namelist()
 for name,sha in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==sha
r={'zip_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'zip_bytes':out.stat().st_size,'files':manifest}
(P/'package_manifest.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='files'}))
