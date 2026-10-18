"""Reuse the exact successful Linux publisher; the later Apple step failed."""
import hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source='940afd3971180286171dfc4964bcf701e6588d56'
paths=['tools/cheats','test/cheats478_sources.py','test/cheats478_sources.mm','test/cheats478_pnach_accept.cpp',
    'native/cheats/catalogue','packages/neo_cheat_catalog/ios/Resources/manifest.json.gz']
subprocess.run(['git','diff','--exit-code',source,'HEAD','--',*paths],cwd=root,check=True)
def api(path):return json.loads(subprocess.check_output(['gh','api','repos/TarbleFR/neostation-ios/'+path],cwd=root,text=True))
job=api('actions/jobs/117650930284');assert job['conclusion']=='success' and job['name']=='publish' and job['run_id']==39119129264
parent=api('git/commits/'+source)['parents'][0]['sha']
assert parent=='8bb5ea9d38c18b16ade86219d56e0cc71ea05c0a'
log=subprocess.check_output(['gh','api','repos/TarbleFR/neostation-ios/actions/jobs/117650930284/logs','--allow-escape-sequences'],cwd=root,text=True)
assert parent in log and 'Ran 8 tests' in log and 'Published 60 FPS selections:' in log
receipt=json.loads((root/'docs/evidence/cheats478-sources.json').read_bytes())
assert hashlib.sha256((root/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()).hexdigest()==receipt['manifestSHA256']
out=root/'evidence/cheats478-source-reuse.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'source':source,'run':39119129264,'job':117650930284,
    'scope':'successful Linux publication, eight source cases, complete pack integrity and full FPS inventory; Apple is not reused',
    'logSHA256':hashlib.sha256(log.encode()).hexdigest()},indent=2)+'\n')
print('REUSED exact Linux publication and eight source checks; native/memory/SDK/UIKit execute below.')
