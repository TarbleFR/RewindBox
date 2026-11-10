#!/usr/bin/env python3
"""Bind the 566 MeloNX engine receipt (decoder units, GC budget) carried by build 579 to private IPA581.

581 swaps only the RPCS3 Core and keeps the 579 (577) engine. The 579
validator runs unchanged on this IPA inside the delivered 579 tree (as_579
in rpcs3cell581_delivery; its own 577 view and 576-equivalent derivation
follow); the receipt names build 581. No game or iPhone runs here; no FPS
gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell581_delivery as delivery
import validate_melonx_jit579_ipa as jit579

jit566=jit579.jit566
jit566.IDENTITY='MeloNX-jit581-identity.json'
_expected579=jit579.expected

def expected():
 """The receipt carried by build 579, computed on the delivered 579 tree, carried by build 581."""
 with delivery.as_579():receipt=_expected579()
 assert receipt['build']==int(delivery.d579.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
jit566.expected=expected

def embed(app):
 jit566.embed(app)

def validate(ipa,build):
 with delivery.as_579():result=jit579.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build581CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
