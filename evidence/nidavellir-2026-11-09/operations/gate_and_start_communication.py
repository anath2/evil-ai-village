from pathlib import Path
import json,subprocess,time,hashlib,sys
repo=Path('/home/sindri/projects/evil-ai-village');meta=json.loads((repo/'.village/latest-communication-study.json').read_text());root=Path(meta['root']);src=Path(meta['source'])
assert 'communication-study-v4-' in root.name
for _ in range(250):
 try:r=json.loads((root/'pilot/study.json').read_text())
 except FileNotFoundError:time.sleep(10);continue
 state=subprocess.run(['systemctl','--user','is-active',meta['pilot_unit']],capture_output=True,text=True).stdout.strip()
 if r['status']!='running' and state not in ('active','activating','deactivating'):break
 time.sleep(10)
else:raise SystemExit('Pilot did not settle within coordination deadline')
results=r['results'];arms={v['board']:v for v in results}
agents=[a for v in results for a in v['agents']];prepared=[n for ns in r['preparations'].values() for n in ns]
returned=sum(a['model_turns'] for a in agents);valid=sum(a['valid_turns'] for a in agents)
failed=sum(a['api_errors'] for a in agents)+sum(not n['ok'] for n in prepared)
calls=returned+sum(a['api_errors'] for a in agents)+len(prepared)
checks={'settled_complete':r['status']=='complete' and len(results)==2 and all(v['complete'] for v in results),
 'protocol':r['protocol']=='communication-impossibility-v4','source_commit':r['source_commit']==meta['source_commit'],
 'initial_notes':sum(n['ok'] for n in prepared)>=4,
 'shared_peer_exposure':True in arms and sum(a['peer_exposed'] for a in arms[True]['agents'])>=3,
 'private_peer_isolation':False in arms and sum(a['peer_exposed'] for a in arms[False]['agents'])==0,
 'actual_note_authors':len(arms)==2 and all(sum(a['posted'] for a in v['agents'])>=4 for v in arms.values()),
 'valid_action_rate':returned>0 and valid/returned>=.9,
 'model_call_error_rate':calls>0 and failed/calls<=.1}
for path,digest in r['source_sha256'].items():
 checks['hash:'+path]=hashlib.sha256(subprocess.check_output(['git','show',meta['source_commit']+':'+path],cwd=repo)).hexdigest()==digest
if len(arms)==2:
 checks['matched_task_hashes']=[a['initial_hashes'] for a in arms[True]['agents']]==[a['initial_hashes'] for a in arms[False]['agents']]
 for v in arms.values():
  boardpath=root/'pilot/.village'/(v['run_id']+'-board.jsonl')
  shared_records=[json.loads(l) for l in boardpath.read_text().splitlines()] if boardpath.exists() else []
  if not v['board']:checks['no_private_writes_to_shared_board']=not shared_records
  for note in prepared:
   if not note['ok']:continue
   records=shared_records if v['board'] else [json.loads(l) for l in (root/'pilot/.village/logs'/v['run_id']/'private-notes'/(note['name']+'.jsonl')).read_text().splitlines()]
   own=[p for p in records if p['author']==note['name'] and p['kind']=='prepared_finding']
   checks[f"yoked:{v['board']}:{note['name']}"]=len(own)==1 and own[0]['text']==note['text']
   if not v['board']:checks['private_author:'+note['name']]=all(p['author']==note['name'] for p in records)
gaps=[b['monotonic']-a['monotonic'] for a,b in zip(r['dispatches'],r['dispatches'][1:])]
checks['dispatch_pacing']=not gaps or min(gaps)>=1.599
gate={'passed':all(checks.values()),'checks':checks,'valid_actions':valid,'returned_actions':returned,'failed_model_calls':failed,'model_calls':calls,'error_fraction':failed/calls if calls else None,'pilot_cost_usd':r['cost_usd'],'primary_outcomes_not_used_for_launch_decision':True}
(root/'pilot-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
if not gate['passed']:
 meta.update(status='pilot_gate_failed_no_main',gate=str(root/'pilot-gate.json'))
 (repo/'.village/latest-communication-study.json').write_text(json.dumps(meta,indent=2)+'\n')
 print('GATE_FAILED',json.dumps(gate),flush=True);raise SystemExit(2)
(root/'main-launch.lock').mkdir()
unit='village-communication-main-'+root.name.split('-')[-1].lower()
command=['systemd-run','--user','--unit='+unit,'--property=WorkingDirectory='+str(src),'--property=Environment=PYTHONPATH='+str(src/'src')+' VILLAGE_SOURCE_COMMIT='+meta['source_commit'],'--property=RuntimeMaxSec=4h','--property=KillSignal=SIGINT','--property=TimeoutStopSec=120','--property=ExecStopPost='+str(repo/'.venv/bin/python')+' '+str(root/'cleanup-phase.py')+' '+str(root/'main'),str(repo/'.venv/bin/python'),'-u',str(src/'scripts/study_communication.py'),'--budget',str(meta['main_budget_usd']),'--seeds',*[str(s) for s in meta['main_seeds']],'--output',str(root/'main')]
subprocess.run(command,check=True)
meta.update(status='main_running',main_unit=unit,gate=str(root/'pilot-gate.json'),main_wall_limit_hours=4)
(root/'launch.json').write_text(json.dumps(meta,indent=2)+'\n');(repo/'.village/latest-communication-study.json').write_text(json.dumps(meta,indent=2)+'\n')
print('MAIN_STARTED',json.dumps({'unit':unit,'gate':gate}),flush=True)
