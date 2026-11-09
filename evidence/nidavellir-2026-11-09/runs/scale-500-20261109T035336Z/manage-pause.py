import pathlib,subprocess,sys,time,os,signal,json
unit='evil-ai-village-500-20261109t035336z.service'
root=pathlib.Path('/home/sindri/projects/evil-ai-village/.village/scale-500-20261109T035336Z')
assert os.geteuid()==0
pid=int(subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True))
assert pid==1759486 and pathlib.Path(f'/proc/{pid}').stat().st_uid==1000
resume='--resume' in sys.argv
started=int(subprocess.check_output(['systemctl','show',unit,'-p','ActiveEnterTimestampMonotonic','--value'],text=True))/1000000
limit=str(int(time.monotonic()-started+14400))+'s' if resume else 'infinity'
p=pathlib.Path('/run/systemd/system')/(unit+'.d')/'90-village-pause.conf'
p.parent.mkdir(parents=True,exist_ok=True);p.write_text('[Service]\nRuntimeMaxSec='+limit+'\n')
subprocess.run(['systemctl','daemon-reload'],check=True)
actual=subprocess.check_output(['systemctl','show',unit,'-p','RuntimeMaxUSec','--value'],text=True).strip()
if not resume:assert actual=='infinity',actual
if resume:os.kill(pid,signal.SIGCONT)
record=json.loads((root/'pause.json').read_text());record.update(state='running' if resume else 'paused',service_runtime_limit=actual,verified_at_unix=time.time())
(root/'pause.json').write_text(json.dumps(record,indent=2)+'\n')
print(record['state']+'; runtime limit '+actual,flush=True)
