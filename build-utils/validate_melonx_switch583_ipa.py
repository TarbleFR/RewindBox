#!/usr/bin/env python3
"""Bind the 572 MeloNX engine receipt (8cc2348: a LightningJit unit ends at a jump past the other cases of a switch) carried by build 582 to private IPA583.

583 keeps the 582 product and engine and swaps only the RPCS3 Core. The 582
receipt is computed on the delivered 582 tree; on this IPA, the 582 recipe's
581-equivalent, the 577 recipe's 576-equivalent of it and the 576 recipe's
575-equivalent of that must carry the 572 engine as the 572 recipe validated
it. The receipt names build 583 and the 583 Core. No game or iPhone runs
here; no launch time or FPS gain is claimed.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell583_delivery as delivery
import validate_melonx_switch582_ipa as switch582

IDENTITY='MeloNX-switch583-identity.json'
_expected582=switch582.expected

def expected():
 with delivery.as_582():receipt=_expected582()
 assert receipt['build']==int(delivery.d582.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN)
# The 582 validator reads the embedded receipt by its module's IDENTITY and compares it with expected().
switch582.IDENTITY=IDENTITY
switch582.expected=expected

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with delivery.as_582():result=switch582.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build583CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
