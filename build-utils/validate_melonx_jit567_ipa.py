#!/usr/bin/env python3
"""Bind the 566 MeloNX engine (86c2b4d: LightningJit translation units, GC gen2 budget) and its engine run to private IPA567.

567 ships the 566 engine byte for byte and swaps only the RPCS3 Core. The 566
checks run unchanged on the delivered 566 tree (engine evidence, packaged
identity and fingerprint, exports and journal literals, every non-engine
entry equal to the 565-equivalent IPA); the receipt names build 567 and the
567 Core. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell567_delivery as delivery
import validate_melonx_jit566_ipa as jit566

jit566.IDENTITY='MeloNX-jit567-identity.json'
_expected566=jit566.expected

def expected():
 """The 566 engine receipt, computed on the delivered 566 tree, carried by build 567 with the 567 Core."""
 with delivery.as_566():receipt=_expected566()
 assert receipt['build']==int(delivery.d566.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCore567Source=delivery.CORE_SOURCE,rpcCore567Run=delivery.CORE_RUN)
jit566.expected=expected

def embed(app):
 jit566.embed(app)

def validate(ipa,build):
 with delivery.as_566():result=jit566.validate(ipa,build)
 return dict(result,build567CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
