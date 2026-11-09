from pathlib import Path
import json,subprocess,time,concurrent.futures
repo=Path('/home/sindri/projects/evil-ai-village')
record={'started_unix':time.time(),'stopped':[],'errors':[],'kept_active':[]}
out=repo/'.village/idle-container-relief-20261109.json'
root=repo/'.village/scale-500-20261109T035336Z';started=set();ended=set()
for f in (root/'source/.village/logs').glob('*/*.jsonl'):
 for line in f.read_text().splitlines():
  try:r=json.loads(line)
  except ValueError:continue
  if r.get('type')=='start':started.add(r['agent'])
  if r.get('type')=='end':ended.add(r['agent'])
active=started-ended
items=[]
for row in json.loads((repo/'.village/old-500-container-inventory.json').read_text()):
 agent=Path(row['mounts'][0]['Source']).name
 if agent in active:record['kept_active'].append(row['id']);continue
 items.append({'id':row['id'],'scope':'original','agent':agent})
record['selected']=items;out.write_text(json.dumps(record,indent=2)+'\n')
print('Stopping original idle containers:',len(items),flush=True)
def stop(item):
 try:
  r=subprocess.run(['docker','stop','--timeout','0',item['id']],capture_output=True,text=True,timeout=45)
  return item,r.returncode
 except subprocess.TimeoutExpired:return item,124
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for n,(item,code) in enumerate(pool.map(stop,items),1):
  record['stopped' if code==0 else 'errors'].append(item)
  out.write_text(json.dumps(record,indent=2)+'\n')
  if n%20==0:print('Stopped',n,'/',len(items),flush=True)
record['finished_unix']=time.time();out.write_text(json.dumps(record,indent=2)+'\n')
(root/'idle-container-relief.json').write_text(json.dumps({'record':str(out),'containers_to_restart':[r['id'] for r in record['stopped']],'note':'Restart retained containers before resuming original harness. Active agents were preserved.'},indent=2)+'\n')
print('DONE',len(record['stopped']),'errors',len(record['errors']),flush=True)
