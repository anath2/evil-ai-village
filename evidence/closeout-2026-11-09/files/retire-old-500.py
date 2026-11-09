import json,subprocess,time,concurrent.futures
from pathlib import Path
repo=Path('/home/sindri/projects/evil-ai-village');path=repo/'.village/old-500-retirement.json';r=json.loads(path.read_text());r.update(removed=[],errors=[]);path.write_text(json.dumps(r,indent=2)+'\n')
def remove(cid):
 try:
  p=subprocess.run(['docker','rm','-f',cid],capture_output=True,text=True,timeout=45)
  return cid,p.returncode
 except subprocess.TimeoutExpired:return cid,124
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for n,(cid,code) in enumerate(pool.map(remove,r['container_ids']),1):
  r['removed' if code==0 else 'errors'].append(cid)
  if n%20==0:
   path.write_text(json.dumps(r,indent=2)+'\n');print('Removed',n,'/',len(r['container_ids']),flush=True)
r.update(status='containers_removed' if not r['errors'] else 'removal_errors',finished_unix=time.time());path.write_text(json.dumps(r,indent=2)+'\n')
print(r['status'],len(r['removed']),flush=True)
