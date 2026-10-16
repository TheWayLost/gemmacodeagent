import hashlib,json,tarfile,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parents[1];m=json.loads((R/'environment/calibration_asset.json').read_text());p=R/'tmp/calibration-v1.tar.gz';p.parent.mkdir(exist_ok=True)
if not p.exists():urllib.request.urlretrieve(m['url'],p)
assert p.stat().st_size==m['size'] and hashlib.sha256(p.read_bytes()).hexdigest()==m['sha256'],'Calibration asset checksum mismatch'
with tarfile.open(p) as t:
 # Our rootfs needs absolute guest symlinks; verify all archive names stay inside R.
 for x in t:
  assert not Path(x.name).is_absolute() and '..' not in Path(x.name).parts
 t.extractall(R,filter='fully_trusted')
print('Calibration rootfs and per-task wheels installed')
