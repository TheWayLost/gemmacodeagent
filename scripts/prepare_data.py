"""Download only this shard's snapshots, with frozen size/SHA checks. Requires own Kaggle access."""
import argparse,concurrent.futures as cf,hashlib,json,os,requests,time
from pathlib import Path
from urllib.parse import quote
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--shards',type=int,default=3);p.add_argument('--shard',type=int,required=True);p.add_argument('--cohort',default='valid55');a=p.parse_args();assert 0<=a.shard<a.shards
plan=json.loads((R/'protocols'/f'{a.cohort}.json').read_text());ids=plan['tasks'][a.shard::a.shards]
manifest=json.loads((R/'environment/data_manifest.json').read_text());names=['tasks.jsonl']+['snapshots/'+t+'.tgz' for t in ids]
def get(name):
 record=manifest[name];dest=R/'data'/('tasks.jsonl' if name=='tasks.jsonl' else 'matched56_snapshots/'+Path(name).name);dest.parent.mkdir(parents=True,exist_ok=True)
 def valid(path):return path.exists() and path.stat().st_size==record['size'] and hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
 if valid(dest):return
 url='https://www.kaggle.com/api/v1/competitions/data/download/gemma-4-developer-agent/'+quote(name,safe='')
 for attempt in range(5):
  try:
   with requests.get(url,headers={'Authorization':'Bearer '+os.environ['KAGGLE_API_TOKEN']},stream=True,timeout=(30,180)) as response:
    response.raise_for_status()
    with dest.with_suffix('.part').open('wb') as f:
     for chunk in response.iter_content(4*1024*1024):f.write(chunk)
   assert valid(dest.with_suffix('.part')),'Checksum mismatch'
   dest.with_suffix('.part').replace(dest);print(name,flush=True);return
  except Exception:
   if attempt==4:raise
   time.sleep(2**attempt)
with cf.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(get,names))
