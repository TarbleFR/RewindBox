"""Bind MeloNX backend threading and the in-game FPS counter, their rebuilt engine and host to private IPA549."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxthreading549_delivery as delivery
import validate_melonx_close544_ipa as close544

IDENTITY='MeloNX-threading549-identity.json'
close,pipeline,journal,audio=close544.close,close544.pipeline,close544.journal,close544.audio
at=delivery.at
# The 547 delivery's engine; 549 changes its session file in one place only.
PREVIOUS_ENGINE='d9f35c2783f7368d31b61f644d970f41bb7bc47b'
THREADING_OFF=b'            GraphicsBackend = GraphicsBackend.Vulkan, BackendThreading = BackendThreading.Off,\n'
THREADING_ON=b'''            // Backend (GPU) threading on by default, matching the standalone
            // MeloNX app, which forces BackendThreading.On before every launch.
            // Off serialized guest FIFO, Vulkan->Metal submission, pipeline
            // compilation and present on one thread and caused the slowdowns the
            // standalone did not have. An explicit per-game value still overrides.
            GraphicsBackend = GraphicsBackend.Vulkan, BackendThreading = BackendThreading.On,
'''
# Reuse the 544 close, 540 pipeline, 539 journal and 537 audio validators with
# the 549 engine and host. Their source comparisons stay active against
# 9bf068b; the changed frontend files are bound to the 549 re-run instead.
for module in (close,pipeline,journal,audio.proof,audio.retained.proof):
 module.MELONX_SOURCE=delivery.MELONX_SOURCE
 module.MELONX_RUN=delivery.MELONX_RUN
close.HOST_SOURCE=audio.proof.HOST_SOURCE=delivery.HOST_SOURCE
close.HOST_RUN=audio.proof.HOST_RUN=delivery.HOST_RUN
close.validate_local_imports=audio.proof.validate_local_imports=delivery.validate_local_imports
# Changed 549 files carry the 549 evidence below, not the retained 518/533 records.
audio.retained.proof.PRODUCT=audio.retained.proof.PRODUCT-delivery.PRODUCT549

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def local():
 receipt=json.loads((ROOT/'build/delivery/melonx-threading549-tests.json').read_text())
 assert receipt==delivery.validate_local_imports(json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text()))
 return receipt

def journal_expected():
 """539 journal proof, re-run by the 549 engine; only the threading default changed."""
 receipt=json.loads((ROOT/'docs/evidence/melonx-effective-graphics-journal.json').read_bytes())
 assert receipt['result']=='passed' and receipt['summary'].startswith('PASS 26 ')
 assert not receipt['gpuRenderingTested'] and not receipt['deviceTested']
 for p,h in receipt['inputs'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(delivery.MELONX_SOURCE,p),p
 old=at(PREVIOUS_ENGINE,journal.SESSION)
 assert old.count(THREADING_OFF)==1 and b'FormattableString.Invariant($"Applied graphics: resolution=' in old
 assert old.replace(THREADING_OFF,THREADING_ON,1)==(ROOT/journal.SESSION).read_bytes()
 return dict(coreSource=delivery.MELONX_SOURCE,coreRun=delivery.MELONX_RUN,regression=receipt,
  physicalDeviceTested=False,graphicsImprovementClaimed=False)

def close_expected():
 """544 close teardown proof with the 549 engine and the 549 frontend re-run."""
 teardown=json.loads((ROOT/'dist/melonx/gpu-teardown-checks.json').read_bytes())
 assert teardown['result']=='passed' and not teardown['failures']
 assert teardown['galDouble'] and teardown['physicalDeviceTested'] is False
 for p,h in teardown['inputs'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(delivery.MELONX_SOURCE,p),p
 control,fixed=teardown['control'],teardown['fixed']
 assert control['newTextureLargerThanCacheShare']['objectName']=='Ryujinx.Memory.Tracking.RegionHandle'
 assert fixed['newTextureLargerThanCacheShare']['threw'] is False
 assert fixed['consecutiveSessions']['cpuReferencesAfterEachSession']==[1]*5
 frontend=local()
 with zipfile.ZipFile(ROOT/'dist/melonx/embedded-adapted-source.zip') as z:
  cache=z.read('src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs').decode('utf-8-sig')
  assert 'if (_textures.First.Value == protectedTexture)' in cache and 'EnforceCapacity();' not in cache
  assert 'ConcurrentQueue<Action> DeferredActions' in z.read('src/Ryujinx.Graphics.Gpu/GpuContext.cs').decode('utf-8-sig')
  assert 'Interlocked.Exchange(ref _disposeRequested, 1) == 0' in z.read('src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs').decode('utf-8-sig')
 return dict(coreSource=delivery.MELONX_SOURCE,coreRun=delivery.MELONX_RUN,hostSource=delivery.HOST_SOURCE,hostRun=delivery.HOST_RUN,
  gpuTeardown=teardown,frontendInputs=frontend['inputs'],frontendSource=frontend['source'],
  sourceArchiveSHA256=sha('dist/melonx/embedded-adapted-source.zip'),
  physicalDeviceTested=False,smashCloseDeviceVerified=False)

journal.expected=journal_expected
close544.expected=close_expected

def expected():
 frontend=local()
 with zipfile.ZipFile(ROOT/'dist/melonx/embedded-adapted-source.zip') as z:
  window=z.read('src/Ryujinx.Library/Window/WindowBase.cs').decode('utf-8-sig')
 # Threaded teardown: the render loop reports drained; the renderer is
 # released from the controlling thread, not inside the render worker.
 assert '_embeddedLifetime.NotifyRenderDrained();' in window
 return dict(build=549,coreSource=delivery.MELONX_SOURCE,coreRun=delivery.MELONX_RUN,coreArtifact=delivery.MELONX_ARTIFACT[0],
  hostSource=delivery.HOST_SOURCE,hostRun=delivery.HOST_RUN,hostArtifact=delivery.HOST_ARTIFACT[0],
  engine=delivery.engine_evidence(),frontendSource=frontend['source'],frontendInputs=frontend['inputs'],
  productTrees=frontend['productTrees'],changedProduct=sorted(delivery.PRODUCT549),
  backendThreadingDefault='On',fpsCounter='Device.Statistics game FPS in the RAM overlay title row',
  physicalDeviceTested=False,threadingDeviceVerified=False,fpsCounterDeviceVerified=False)

def embed(app):
 close544.embed(app)
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 result=close544.validate(ipa,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert identity['host']==delivery.MELONX_SOURCE
  assert 'neostation_melonx_performance_snapshot' in identity['exports']
  for p in sorted(delivery.PRODUCT549)+['build-utils/melonx/adapt_session.py']:
   if p.startswith(('native/','build-utils/')):assert identity['adaptations'][p]==sha(p),p
  core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  assert b'_neostation_melonx_performance_snapshot' in core
  assert audio.contains(core,'backendThreading')
  host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  assert b'neostation_melonx_performance_snapshot' in host
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in ['backendThreading','Backend threading','Multithreading du backend']:
   assert audio.contains(dart,text),text
 return dict(result,threading549=receipt,compiledThreadingAndFpsVerified=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=549);p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
