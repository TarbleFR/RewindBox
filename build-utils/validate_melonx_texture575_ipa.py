#!/usr/bin/env python3
"""Bind the 564 MeloNX engine claims (texture pool, journal) to private IPA575.

575 keeps the 572 engine and swaps only the RPCS3 Core. The 573 receipt is
checked unchanged on the delivered 573 tree (as_573 in
rpcs3cell575_delivery), against this IPA; the 573 and 572 validators derive
their views in turn. The receipt names build 575.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell575_delivery as delivery
import validate_melonx_texture573_ipa as texture573

texture564=texture573.texture564
texture564.IDENTITY='MeloNX-texture575-identity.json'
_expected573=texture573.expected

def expected():
 """The 564 engine receipt carried by build 573, computed on the delivered 573 tree, carried by build 575."""
 with delivery.as_573():receipt=_expected573()
 assert receipt['build']==int(delivery.d573.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 with delivery.as_573():result=texture573.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build575CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
