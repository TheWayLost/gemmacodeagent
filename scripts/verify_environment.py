import hashlib,importlib.metadata as m,json
from pathlib import Path
records=json.loads((Path(__file__).resolve().parents[1]/'environment/installed_code_hashes.json').read_text());bad=[]
for name,expected in records.items():
 d=m.distribution(name)
 if d.version!=expected['version']:bad.append(name+':version')
 for rel,sha in expected['files'].items():
  p=d.locate_file(rel)
  if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:bad.append(name+':'+rel)
if bad:raise SystemExit('Environment differs from tested runtime; do NOT pool results:\n'+'\n'.join(bad[:40]))
print('All six critical package source trees match the tested runtime.')
