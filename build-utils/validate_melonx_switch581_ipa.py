#!/usr/bin/env python3
"""Bind the 572 MeloNX engine receipt (8cc2348: a LightningJit unit ends at a jump past the other cases of a switch) carried by build 579 to private IPA581.

581 keeps the 579 (577) engine and swaps only the RPCS3 Core. The 579
receipt is computed on the delivered 579 tree; on this IPA, the 577
recipe's 576-equivalent and the 576 recipe's 575-equivalent must carry the
572 engine as the 572 recipe validated it. The receipt names build 581 and
the 581 Core. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell581_delivery as delivery
import validate_melonx_switch579_ipa as switch579

IDENTITY='MeloNX-switch581-identity.json'

def expected():
 with delivery.as_579():receipt=switch579.expected()
 assert receipt['build']==int(delivery.d579.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
 d579=delivery.d579
 d577=d579.d577
 with delivery.as_579(),d579.as_577():
  derived=d577.derived_ipa(ipa)
  with d577.as_576_engine():
   derived575=d577.d576.derived_ipa(derived)
   with d577.d576.as_575_engine(),d577.d575.as_573(),d577.d573.as_572():engine=d577.d572.validate_engine_ipa(derived575)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  validated576EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),
  validated575EquivalentSHA256=hashlib.sha256(derived575.read_bytes()).hexdigest(),engine572=engine,
  physicalDeviceTested=False,gameTested=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
