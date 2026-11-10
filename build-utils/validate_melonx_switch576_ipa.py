#!/usr/bin/env python3
"""Bind the 572 MeloNX engine receipt (8cc2348: a LightningJit unit ends at a jump past the other cases of a switch) to private IPA576.

576 replaces the 572 engine with the one of 301e0f8, which keeps the 572
decoder change. The 575 receipt of the 572 engine (engine run, decoder
receipt, engine inputs) is computed on the delivered 575 tree with the 572
engine's evidence, and derived_ipa() (this IPA with the 572 engine entries)
must carry that engine as package_runtime packaged it and, apart from the
engine entries, the bytes of the 572 recipe's derived IPA. The receipt names
build 576. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxwarm576_delivery as delivery
import validate_melonx_switch575_ipa as switch575

IDENTITY='MeloNX-switch576-identity.json'

def expected():
 with delivery.as_575_engine():receipt=switch575.expected()
 assert receipt['build']==int(delivery.d575.BUILD)
 return dict(receipt,build=int(delivery.BUILD))

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
 derived=delivery.derived_ipa(ipa)
 with delivery.as_575_engine(),delivery.d575.as_573(),delivery.d573.as_572():engine=delivery.d572.validate_engine_ipa(derived)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  validated575EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine572=engine,
  physicalDeviceTested=False,gameTested=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
