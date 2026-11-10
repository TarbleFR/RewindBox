#!/usr/bin/env python3
"""Bind the 566 MeloNX engine claims (86c2b4d: LightningJit translation units, GC gen2 budget) to private IPA575.

575 keeps the 572 engine (8cc2348, which keeps every 566 engine change) and
swaps only the RPCS3 Core. The 573 receipt of the 566 engine is checked
unchanged on the delivered 573 tree (as_573 in rpcs3cell575_delivery),
against this IPA; the 573 and 572 validators derive their views in turn. The
receipt names build 575.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell575_delivery as delivery
import validate_melonx_jit573_ipa as jit573

jit566=jit573.jit566
jit566.IDENTITY='MeloNX-jit575-identity.json'
_expected573=jit573.expected

def expected():
 """The 566 engine receipt carried by build 573, computed on the delivered 573 tree, carried by build 575."""
 with delivery.as_573():receipt=_expected573()
 assert receipt['build']==int(delivery.d573.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
jit566.expected=expected

def embed(app):
 jit566.embed(app)

def validate(ipa,build):
 with delivery.as_573():result=jit573.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build575CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
