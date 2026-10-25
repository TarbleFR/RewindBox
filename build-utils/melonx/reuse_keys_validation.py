"""Reuse unchanged proofs; execute any group whose complete inputs changed."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE='e050961d6caabfabdef57dd140c774545976d0fd'
RUN=39978893582
GROUPS={
 'Verify the real Darwin signal ABI and preserve NativeAOT handlers':[
  'test/melonx_darwin_signal_test.py','native/melonx/EmbeddedDarwinSignals.cs',
  'native/melonx/EmbeddedRuntime.cs','build-utils/melonx/adapt_runtime.py','build-utils/melonx/source.json'],
 'Verify optional homebrew assets with the real LibHac loader':[
  'test/melonx_homebrew_test.py','native/melonx/EmbeddedHomebrewAssets.cs',
  'build-utils/melonx/adapt_session.py','build-utils/melonx/source.json','build-utils/melonx/libhac-reuse.json']}
jobs=json.loads(subprocess.check_output(['gh','api',f'repos/TarbleFR/RewindBox/actions/runs/{RUN}/jobs']))['jobs']
job=next(j for j in jobs if j['head_sha']==SOURCE and j['conclusion']=='success')
records=[]
commands={
 'Verify the real Darwin signal ABI and preserve NativeAOT handlers':
  ['python3','test/melonx_darwin_signal_test.py','.native-sources/MeloNX'],
 'Verify optional homebrew assets with the real LibHac loader':
  ['python3','test/melonx_homebrew_test.py','dist/melonx/libhac-feed/Ryujinx.LibHac.0.21.0-alpha.129.nupkg','.native-sources/MeloNX']}
for phase,paths in GROUPS.items():
 assert next(s for s in job['steps'] if s['name']==phase)['conclusion']=='success'
 inputs={};changed=False
 for path in paths:
  original=subprocess.check_output(['git','show',SOURCE+':'+path],cwd=ROOT)
  current=(ROOT/path).read_bytes()
  changed |= original!=current
  inputs[path]=hashlib.sha256(current).hexdigest()
 if changed:
  subprocess.run(commands[phase],cwd=ROOT,check=True)
  head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
  records.append(dict(phase=phase,source=head,inputs=inputs,reexecuted=True))
 else:
  records.append(dict(phase=phase,source=SOURCE,run=RUN,inputs=inputs,reexecuted=False))
out=ROOT/'dist/melonx/keys-unchanged-reuse.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(records,indent=2)+'\n')
print('PASS Darwin/homebrew evidence: unchanged groups reused; affected groups executed.')
