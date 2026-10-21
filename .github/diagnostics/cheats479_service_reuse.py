"""Reuse only the successful unchanged service/memory components, not UIKit."""
import hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source='ce585c6bef0f3f714a7dc0f5c005191f74df4c9a'
paths=['packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
 'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h',
 'packages/neo_cheat_catalog/ios/Resources','native/cheats/catalogue',
 'test/cheats479_runtime.m','test/cheats479_regression.py','test/cheats477_runtime.m',
 'test/cheats477_regression.py','test/unified_catalog_runtime_native.m','test/fixtures/cheats477']
subprocess.run(['git','diff','--exit-code',source,'HEAD','--',*paths],cwd=root,check=True)
def api(path):return json.loads(subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/'+path],cwd=root,text=True))
job=api('actions/jobs/117670567809');assert job['head_sha']==source and job['conclusion']=='failure'
required={'Actual 478 negative control and 51652-file candidate benchmark','Changed shared installation and integrity behaviour','Changed full-index memory and iPhone SDK'}
assert required<={s['name'] for s in job['steps'] if s.get('conclusion')=='success'}
log=subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/actions/jobs/117670567809/logs','--allow-escape-sequences'],cwd=root,text=True)
assert '"initialPerFileChecks":0' in log and 'Foundation unified catalogue: 352 behavioral checks passed' in log and 'Full manifest memory: games=51652' in log
out=root/'evidence/cheats479-service-reuse.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'source':source,'run':39125808369,'job':117670567809,
 'scope':'successful unchanged service benchmark, 352 behavioural checks and full-index memory only; earlier UIKit failed, changed SDK/List run below',
 'logSHA256':hashlib.sha256(log.encode()).hexdigest()},indent=2)+'\n')
print('REUSED unchanged 479 service benchmark, 352 checks and full-index memory; changed SDK/UIKit run below.')
