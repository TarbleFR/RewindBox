"""Bind the MeloNX close-teardown fix, its rebuilt engine and host to private IPA544."""
import argparse,hashlib,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxclose544_delivery as close
import validate_melonx_pipeline540_ipa as pipeline

IDENTITY='MeloNX-close544-identity.json'
journal=pipeline.journal
audio=journal.previous
# Reuse the 540 pipeline, 539 journal and 537 audio validators with the 544
# engine and host. Their source comparisons stay active; only the changed
# MeloNX service and plugin are bound to the 544 re-run and host run.
for module in (pipeline,journal,audio.proof,audio.retained.proof):
 module.MELONX_SOURCE=close.MELONX_SOURCE
 module.MELONX_RUN=close.MELONX_RUN
audio.proof.HOST_SOURCE=close.HOST_SOURCE
audio.proof.HOST_RUN=close.HOST_RUN
audio.proof.validate_local_imports=close.validate_local_imports

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 teardown=json.loads((ROOT/'dist/melonx/gpu-teardown-checks.json').read_bytes())
 assert teardown['result']=='passed' and not teardown['failures']
 assert teardown['galDouble'] and teardown['physicalDeviceTested'] is False
 for p,h in teardown['inputs'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==close.at(close.MELONX_SOURCE,p),p
 control,fixed=teardown['control'],teardown['fixed']
 assert control['newTextureLargerThanCacheShare']['objectName']=='Ryujinx.Memory.Tracking.RegionHandle'
 assert fixed['newTextureLargerThanCacheShare']['threw'] is False
 assert fixed['consecutiveSessions']['cpuReferencesAfterEachSession']==[1]*5
 local=json.loads((ROOT/'build/delivery/melonx-close544-tests.json').read_text())
 assert local==close.validate_local_imports(json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text()))
 with zipfile.ZipFile(ROOT/'dist/melonx/embedded-adapted-source.zip') as z:
  cache=z.read('src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs').decode('utf-8-sig')
  assert 'if (_textures.First.Value == protectedTexture)' in cache and 'EnforceCapacity();' not in cache
  assert 'ConcurrentQueue<Action> DeferredActions' in z.read('src/Ryujinx.Graphics.Gpu/GpuContext.cs').decode('utf-8-sig')
  assert 'Interlocked.Exchange(ref _disposeRequested, 1) == 0' in z.read('src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs').decode('utf-8-sig')
 return dict(coreSource=close.MELONX_SOURCE,coreRun=close.MELONX_RUN,hostSource=close.HOST_SOURCE,hostRun=close.HOST_RUN,
  gpuTeardown=teardown,frontendInputs=local['inputs'],frontendSource=local['source'],
  sourceArchiveSHA256=sha('dist/melonx/embedded-adapted-source.zip'),
  physicalDeviceTested=False,smashCloseDeviceVerified=False)

def embed(app):
 pipeline.embed(app)
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 result=pipeline.validate(ipa,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert identity['host']==close.MELONX_SOURCE
  for p in ['build-utils/melonx/adapt_gpu_lifetime.py','build-utils/melonx/prepare_embedded.py']:
   assert identity['adaptations'][p]==sha(p),p
  core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  for text in ['Texture cache kept its texture in use above the ','Texture cache teardown skipped ']:
   assert audio.contains(core,text),text
  host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  assert b'isSessionQuarantined' in host
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in ['isSessionQuarantined','Native session quarantined; frontend audio remains paused.']:
   assert audio.contains(dart,text),text
 return dict(result,closeTeardown=receipt,compiledCloseCorrectionVerified=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=544);p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
