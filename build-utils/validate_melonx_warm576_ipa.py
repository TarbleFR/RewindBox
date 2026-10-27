#!/usr/bin/env python3
"""Bind the 576 MeloNX engine (301e0f8: shader-cache warm-ups off the game's start, attachment-less framebuffers sized to the viewports, temporary FFT boot trace) and its engine run to private IPA576.

The engine run built and tested exactly the pinned engine inputs: the 572
engine checks again (session ownership, display, simulator runtime, texture
pool, journal, decoder with the switch case), with the three 576 adaptations
in the adapted source it compiled. The signed IPA must carry that engine as
package_runtime packaged it (identity, compiled payload fingerprint, every
572 export, the journal literals) and, apart from the engine entries, the
bytes of derived_ipa(), which the inherited MeloNX validators check. No game
or iPhone runs here; no launch time or FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxwarm576_delivery as delivery
import melonxwarm576_tree as tree

IDENTITY='MeloNX-warm576-identity.json'

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 return dict(build=int(delivery.BUILD),engineSource=delivery.MELONX_SOURCE,engineRun=delivery.MELONX_RUN,
  engineArtifact=delivery.MELONX_ARTIFACT[0],engine572Source=delivery.MELONX572_SOURCE,engine572Run=delivery.MELONX572_RUN,
  rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,evidence=delivery.engine_evidence(),
  inputs={p:sha(p) for p in sorted(tree.FIX576)},exports=delivery.EXPORTS576,coreText=delivery.CORE_TEXT576,
  temporaryBootTrace='010038b015560000',physicalDeviceTested=False,gameTested=False,launchTimeMeasured=False,
  fpsGainMeasured=False)

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
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
