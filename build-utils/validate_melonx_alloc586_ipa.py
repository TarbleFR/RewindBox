#!/usr/bin/env python3
"""Bind the MeloNX engine of 75a13f7 (6314127, d8cd5f6, ac16f1c, 6edcd57 and 75a13f7: the GPU thread no longer allocates an array per copy; JIT units laid out off word alignment ignore the entry stops and the jump look-ahead; the render thread blocks instead of spinning while a new program compiles, and depth-only passes hit their warm-up; a queued texture write-back skips guest memory unmapped since; bindless handles read through SHFL bind) with its engine run to private IPA586.

The engine run built and tested exactly the pinned engine inputs: the 572
engine checks again (session ownership, display, simulator runtime, texture
pool, journal, decoder with the switch case), the decoder probe's 582 cases,
its unmapped page read as zeros and its misaligned units, with the
allocation changes, the shader waits, the misaligned-unit guards, the
write-back guard and the bindless look-through in the adapted source it
compiled. The signed IPA must carry that engine as
package_runtime packaged it (identity, compiled payload fingerprint, every
572 export, the journal literals) and, apart from the engine entries, the
bytes of derived_ipa(), which the inherited validators check. No game or
iPhone runs here; no launch time, frame time, memory or FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rewind586_delivery as delivery
import rewind586_tree as tree

IDENTITY='MeloNX-alloc586-identity.json'

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 return dict(build=int(delivery.BUILD),engineSource=delivery.MELONX_SOURCE,engineRun=delivery.MELONX_RUN,
  engineArtifact=delivery.MELONX_ARTIFACT[0],engineCommits=tree.ENGINE_COMMITS,engine582Source=delivery.MELONX582_SOURCE,
  engine582Run=delivery.MELONX582_RUN,rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,
  evidence=delivery.engine_evidence(),inputs={p:sha(p) for p in sorted(tree.FIX586)},added=sorted(set(tree.ADDED)&set(tree.FIX586)),
  exports=delivery.EXPORTS586,coreText=delivery.CORE_TEXT586,physicalDeviceTested=False,gameTested=False,
  launchTimeMeasured=False,fpsGainMeasured=False)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
 engine=delivery.validate_engine_ipa(ipa)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  engine=engine,physicalDeviceTested=False,gameTested=False,launchTimeMeasured=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
