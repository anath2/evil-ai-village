from pathlib import Path
import json, subprocess, sys, time
from datetime import datetime,timezone
root=Path(__file__).resolve().parent
meta=json.loads((root/'launch.json').read_text())
repo=root.parents[1]; source=Path(meta['source']); python=str(repo/'.venv/bin/python')
def status(value,**extra):
 meta.update(status=value,updated_utc=datetime.now(timezone.utc).isoformat(),**extra)
 for p in (root/'launch.json',repo/'.village/latest-fast-population.json'):
  tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(meta,indent=2)+'\n');tmp.replace(p)
 print(value,flush=True)
def phase(name,count,steps,budget,limit):
 command=[python,'-u',str(source/'scripts/scale_society.py'),'--count',str(count),'--active','28','--steps',str(steps),'--budget',str(budget),'--timeout','120','--retries','2','--model-concurrency','0','--request-spacing','1.6','--roster-seed','20261109','--max-output-tokens','8192','--time-budget','1800','--task','mock:impossible','--output',str(root/name)]
 status(name+'_running',phase_command=command)
 try:
  with (root/(name+'.log')).open('w') as log:
   result=subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=limit)
  if result.returncode:raise RuntimeError(name+' subprocess exit '+str(result.returncode))
  metrics=json.loads((root/name/'metrics.json').read_text())
  return metrics
 finally:
  subprocess.run([python,str(root/'cleanup.py'),str(source)],check=True)
try:
 canary=phase('canary',28,1,.25,480)
 okay=canary.get('completion_rate')==1 and canary.get('errors',999)/max(1,canary.get('calls',0))<=.1
 (root/'canary-gate.json').write_text(json.dumps({'passed':okay,'canary_metrics':canary,'scope':'Operational readiness only; not action validity or behavioral outcomes'},indent=2)+'\n')
 if not okay:
  status('canary_failed_no_main');sys.exit(2)
 metrics=phase('main',500,6,10,9000)
 status('main_returned',completion_rate=metrics.get('completion_rate'),cost_usd=metrics.get('cost_usd'))
except BaseException as error:
 if meta['status']!='canary_failed_no_main':status('stopped_incomplete',error_type=type(error).__name__)
 raise
