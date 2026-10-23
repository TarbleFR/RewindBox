"""Reuse unchanged successful key/personal/launch tests from delivered Core517."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE='e0a1196d70469a28f04cc8a3628f43d484015581';RUN=40025760206
GROUPS={
 'Exercise key regression against the real pinned LibHac reader':['test/melonx_keys_native_test.py','native/melonx/EmbeddedKeyValidation.cs','test/fixtures/melonx_key_shape_517.json'],
 'Check affected personal configuration and LibHac API':['test/melonx_library_api_test.py','native/melonx/EmbeddedSaveTransfer.cs','native/melonx/EmbeddedPersonalOptions.cs','native/melonx/EmbeddedKeyValidation.cs'],
 'Execute the changed production launch preflight and diagnostic API':['test/melonx_launch_native_test.py','native/melonx/EmbeddedLaunchPreflight.cs','native/melonx/EmbeddedLaunchDiagnostics.cs','native/melonx/EmbeddedKeyValidation.cs']}
jobs=json.loads(subprocess.check_output(['gh','api',f'repos/TarbleFR/RewindBox/actions/runs/{RUN}/jobs']))['jobs']
job=next(j for j in jobs if j['head_sha']==SOURCE and j['conclusion']=='success');records=[]
for phase,paths in GROUPS.items():
 assert next(s for s in job['steps'] if s['name']==phase)['conclusion']=='success',phase
 inputs={}
 for p in paths+['build-utils/melonx/source.json','build-utils/melonx/libhac-reuse.json']:
  old=subprocess.check_output(['git','show',SOURCE+':'+p],cwd=ROOT)
  assert old==(ROOT/p).read_bytes(),p
  inputs[p]=hashlib.sha256(old).hexdigest()
 records.append(dict(phase=phase,source=SOURCE,run=RUN,inputs=inputs,reexecuted=False))
out=ROOT/'dist/melonx/display-reuse.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(records,indent=2)+'\n')
print('PASS unchanged Core517 key, personal and content preflight proofs; new memory/display and actual engine tested separately.')
