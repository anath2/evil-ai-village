from pathlib import Path
import subprocess,json,time,concurrent.futures
repo=Path('/home/sindri/projects/evil-ai-village');meta=json.loads((repo/'.village/latest-fast-population.json').read_text());root=Path(meta['root']);prefix=str(root/'source/.village/workspaces')+'/'
assert subprocess.check_output(['systemctl','--user','show',meta['unit'],'-p','FreezerState','--value'],text=True).strip()=='frozen'
starts=set();ends=set()
for f in (root/'source/.village/logs').glob('*/*.jsonl'):
 for l in f.read_text().splitlines():
  try:r=json.loads(l)
  except ValueError:continue
  if r.get('type')=='start':starts.add(r['agent'])
  if r.get('type')=='end':ends.add(r['agent'])
active=starts-ends
ids=subprocess.check_output(['docker','ps','-q','--filter','label=evil-ai-village.managed=true'],text=True).split()
record={'started_unix':time.time(),'active_agents_preserved':sorted(active),'selected':[],'stopped':[],'errors':[]};path=root/'idle-container-relief.json'
for offset in range(0,len(ids),30):
 lines=subprocess.check_output(['docker','inspect','--format','{{.Id}} {{range .Mounts}}{{.Source}} {{end}}',*ids[offset:offset+30]],text=True).splitlines()
 for line in lines:
  parts=line.split();cid=parts[0];mounts=[p for p in parts[1:] if p.startswith(prefix)]
  if not mounts:continue
  agent=Path(mounts[0]).name
  if agent in active:continue
  assert agent.startswith('a') and agent[1:].isdigit(),agent
  record['selected'].append(cid)
path.write_text(json.dumps(record,indent=2)+'\n');print('Stopping faster-run inactive containers:',len(record['selected']),flush=True)
def stop(cid):
 try:return cid,subprocess.run(['docker','stop','--timeout','0',cid],capture_output=True,timeout=45).returncode
 except subprocess.TimeoutExpired:return cid,124
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for n,(cid,code) in enumerate(pool.map(stop,record['selected']),1):
  record['stopped' if code==0 else 'errors'].append(cid)
  if n%25==0:
   path.write_text(json.dumps(record,indent=2)+'\n');print('Stopped',n,flush=True)
record['containers_to_restart']=record['stopped'];record['finished_unix']=time.time();path.write_text(json.dumps(record,indent=2)+'\n');print('DONE',len(record['stopped']),'errors',len(record['errors']),flush=True)
