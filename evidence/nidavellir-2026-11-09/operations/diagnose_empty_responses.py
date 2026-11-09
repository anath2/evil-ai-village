from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json,threading,time,sys
from dotenv import load_dotenv
meta=json.loads(Path('.village/latest-communication-study.json').read_text());root=Path(meta['root']);src=Path(meta['source'])
sys.path.insert(0,str(src));sys.path.insert(0,str(src/'src'))
from scripts.study_communication import StudyAgent,build_config,INSTRUCTION,GOAL,Pacer
from village.cybergym import prepare_task
from village.models import AdaptionClient
from village.tools import action_format_error
study=json.loads((root/'pilot/study.json').read_text());notes={n['name']:n['text'] for n in study['preparations']['deepseek-97']}
output=root/'response-diagnostic';output.mkdir(exist_ok=False)
cases=[]
for shared in (True,False):
 run_id='comm-deepseek-97-'+('on' if shared else 'off')
 for f in sorted((root/'pilot/.village/logs'/run_id).glob('worker-*.jsonl')):
  events=[json.loads(l) for l in f.read_text().splitlines()]
  if not any(e['type']=='api_error' and 'no reply' in str(e.get('error','')).lower() for e in events):continue
  cfg,_=build_config({'roster':'deepseek','seed':97,'board':shared},output)
  task=prepare_task(cfg,cfg.task.ids[0],output/'tasks'/run_id/f.stem)
  a=StudyAgent(name=f.stem,model='deepseek-v4-flash',tier='study',task=task,goal=GOAL,client=None,sandbox=None,board=None)
  a.study_shared=shared
  a.runtime=[{'role':'user','content':INSTRUCTION+'\nYour independently generated initial finding (analysis only; no commands were run):\n'+notes[f.stem]}]
  path=(root/'pilot/.village'/(run_id+'-board.jsonl')) if shared else f.parent/'private-notes'/f.name
  all_posts={p['seq']:p for p in (json.loads(l) for l in path.read_text().splitlines())}
  pending=None;context=[];exact=True
  for e in events:
   if e['type']=='board_context':a.steps=e['step'];context=[all_posts[p['seq']] for p in e['visible']]
   elif e['type']=='turn':
    pending=e['text']
    if not e.get('tool'):
     a.runtime.extend([{'role':'assistant','content':pending[:2000]},{'role':'user','content':'OBSERVATION: could not parse an action. '+action_format_error(pending)+' Reply with exactly one complete <action>{"tool":"name","input":{}}</action> block.'}]);pending=None
   elif e['type']=='observation':
    exact &= len(e['observation'])<4000
    a.runtime.extend([{'role':'assistant','content':pending[:2000]},{'role':'user','content':'OBSERVATION:\n'+e['observation']}]);pending=None
   elif e['type']=='api_error':
    if 'no reply' in str(e.get('error','')).lower():
     a.board=SimpleNamespace(recent=lambda **kw:list(context))
     cases.append({'shared':shared,'worker':f.stem,'step':a.steps,'exact_context':exact,'messages':a._messages()});break
    a.runtime.append({'role':'user','content':'API error: '+e['error']})
load_dotenv('.env');tls=threading.local();records=[];lock=threading.Lock()
class Diagnostic(AdaptionClient):
 def _parse(self,model,data):
  d=data if isinstance(data,dict) else {};items=d.get('output') or []
  tls.data={'status':d.get('status'),'output_types':[i.get('type') for i in items],
   'content_types':[[p.get('type') for p in i.get('content',[])] for i in items],
   'refusal_present':any(p.get('type')=='refusal' for i in items for p in i.get('content',[])),
   'has_top_level_output_text':bool(d.get('output_text')),'output_tokens':(d.get('usage') or {}).get('output_tokens'),
   'extracted_text_characters':len(self._extract_text(d))}
  return super()._parse(model,data)
client=Diagnostic(budget_usd=.05,timeout=120,max_retries=1,model_concurrency=0);pacer=Pacer();client._client.event_hooks['request']=[pacer]
def run(case):
 tls.data={};row={k:v for k,v in case.items() if k!='messages'}
 try:client.chat('deepseek-v4-flash',case['messages'],temperature=.7,max_tokens=4096);row['completed']=True
 except Exception as e:row.update(completed=False,error_type=type(e).__name__)
 row['response_structure']=tls.data
 with lock:
  records.append(row);print(json.dumps(row),flush=True)
  (output/'metadata.json').write_text(json.dumps({'cases':records,'cost_usd':client.total_cost_usd,'note':'Reconstructed failure contexts; some observations may have been clipped in original logs. No tool actions executed and no raw response text published.'},indent=2)+'\n')
try:
 with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(run,cases))
finally:client.close()
print('diagnostic_cases',len(cases),flush=True)
