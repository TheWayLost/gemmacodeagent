from pathlib import Path
from huggingface_hub import snapshot_download
R=Path(__file__).resolve().parents[1]
snapshot_download('google/gemma-4-31B-it-qat-w4a16-ct',revision='52f3f65bc7a02d555763bc923bd1d9094898219d',local_dir=R/'models/gemma-4-31b-it-qat-w4a16-ct',max_workers=8)
import hashlib
p=R/'models/gemma-4-31b-it-qat-w4a16-ct/model.safetensors';h=hashlib.sha256()
with p.open('rb') as f:
 for c in iter(lambda:f.read(8*1024*1024),b''):h.update(c)
assert h.hexdigest()=='1b9b1d622a93f02c0d33f98e502f233b5d707443af6ddc464ed0bf5498506c20'
print('Model checkpoint verified')
