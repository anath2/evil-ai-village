from pathlib import Path
import json,subprocess
from datetime import datetime,timezone
root=Path(__file__).resolve().parent;meta=json.loads((root/'launch.json').read_text());repo=root.parents[1];source=Path(meta['source']);python=str(repo/'.venv/bin/python')
def status(value,**extra):
 meta.update(status=value,updated_utc=datetime.now(timezone.utc).isoformat(),**extra)
 for p in (root/'launch.json',repo/'.village/latest-ajit-settings-run.json'):
  tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(meta,indent=2)+'\n');tmp.replace(p)
 print(value,flush=True)
command=[python,'-u',str(source/'scripts/scale_society.py'),'--count','500','--active','8','--budget','3.0','--timeout','120','--retries','5','--model-concurrency','4','--time-budget','1800','--output',str(root/'main')]
try:
 status('main_running',phase_command=command)
 with (root/'main.log').open('w') as log:
  result=subprocess.run(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,timeout=9000)
 if result.returncode:raise RuntimeError('runner exit '+str(result.returncode))
 metrics=json.loads((root/'main/metrics.json').read_text());status('main_returned',completion_rate=metrics.get('completion_rate'),cost_usd=metrics.get('cost_usd'))
except BaseException as error:
 status('stopped_incomplete',error_type=type(error).__name__);raise
finally:subprocess.run([python,str(root/'cleanup.py'),str(source)],check=True)
