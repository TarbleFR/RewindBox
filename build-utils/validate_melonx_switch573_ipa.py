#!/usr/bin/env python3
"""Bind the 572 MeloNX engine (8cc2348: a LightningJit unit ends at a jump past the other cases of a switch) and its engine run to private IPA573.

573 keeps the 572 engine and swaps only the RPCS3 Core. The 572 receipt
(engine run, decoder receipt, engine inputs) is computed on the delivered
572 tree (as_572 in rpcs3cell573_delivery) and the actual IPA must carry that
engine as package_runtime packaged it and, apart from the engine entries,
the bytes of the 572 recipe's derived IPA. The receipt names build 573 and
the 573 Core. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell573_delivery as delivery
import validate_melonx_switch572_ipa as switch572

IDENTITY='MeloNX-switch573-identity.json'

def expected():
 with delivery.as_572():receipt=switch572.expected()
 assert receipt['build']==int(delivery.d572.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
 with delivery.as_572():engine=delivery.d572.validate_engine_ipa(ipa)
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
