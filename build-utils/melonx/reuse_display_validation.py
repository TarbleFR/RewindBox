"""Reuse unchanged key/personal proofs; execute the changed launch diagnostics."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE='e0a1196d70469a28f04cc8a3628f43d484015581';RUN=40025760206
GROUPS={
 'Exercise key regression against the real pinned LibHac reader':['test/melonx_keys_native_test.py','native/melonx/EmbeddedKeyValidation.cs','test/fixtures/melonx_key_shape_517.json'],
 'Check affected personal configuration and LibHac API':['test/melonx_library_api_test.py','native/melonx/EmbeddedSaveTransfer.cs','native/melonx/EmbeddedPersonalOptions.cs','native/melonx/EmbeddedKeyValidation.cs']}
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
print('PASS unchanged Core517 key/personal proofs; changed preflight/journal checks execute next.')
package=ROOT/'dist/melonx/libhac-feed/Ryujinx.LibHac.0.21.0-alpha.129.nupkg'
subprocess.run(['python3',str(ROOT/'test/melonx_launch_native_test.py'),str(package)],cwd=ROOT,check=True)
subprocess.run(['python3',str(ROOT/'test/melonx_launch_journal_test.py')],cwd=ROOT,check=True)
