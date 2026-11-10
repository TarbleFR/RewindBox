#!/usr/bin/env python3
"""Bind the 566 MeloNX engine (86c2b4d: LightningJit translation units, GC gen2 budget) and its engine run to private IPA566.

The engine run built and tested exactly the pinned engine inputs: the 564
engine checks again (with a simulator homebrew that now executes the new unit
ends) and the decoder test (the real LightningJit decoder and compiler,
upstream vs adapted). The signed IPA must carry that engine as package_runtime
packaged it (identity, compiled payload fingerprint, every 564 export, the
journal literals) and, apart from the engine entries, the bytes of
derived_ipa(), which the inherited MeloNX validators check. No game or iPhone
runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxjit566_delivery as delivery
import melonxjit566_tree as tree

IDENTITY='MeloNX-jit566-identity.json'

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 return dict(build=int(delivery.BUILD),engineSource=delivery.MELONX_SOURCE,engineRun=delivery.MELONX_RUN,
  engineArtifact=delivery.MELONX_ARTIFACT[0],engine564Source=delivery.MELONX564_SOURCE,engine564Run=delivery.MELONX564_RUN,rpcCore563Source=delivery.CORE563_SOURCE,
  rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,evidence=delivery.engine_evidence(),
  inputs={p:sha(p) for p in sorted(tree.FIX566) if p not in tree.DOCS566},exports=delivery.EXPORTS566,
  coreText=delivery.CORE_TEXT566,physicalDeviceTested=False,gameTested=False,fpsGainMeasured=False)

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
  engine=engine,physicalDeviceTested=False,gameTested=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
