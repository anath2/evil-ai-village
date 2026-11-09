import json,subprocess,sys
from pathlib import Path
prefix=str(Path(sys.argv[1]).resolve())+"/"
ids=subprocess.check_output(["docker","ps","-aq","--filter","label=evil-ai-village.managed=true"],text=True).split()
if ids:
 data=json.loads(subprocess.check_output(["docker","inspect",*ids],text=True))
 selected=[r["Id"] for r in data if any(str(m.get("Source","")).startswith(prefix) for m in r.get("Mounts",[]))]
 if selected:subprocess.run(["docker","rm","-f",*selected],check=True)
 print("Phase-scoped residual containers removed:",len(selected))
