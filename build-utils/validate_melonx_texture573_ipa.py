#!/usr/bin/env python3
"""Bind the 564 MeloNX engine claims (texture pool, journal) to private IPA573.

573 keeps the 572 engine and swaps only the RPCS3 Core. The 572 receipt is
checked unchanged on the delivered 572 tree (as_572 in
rpcs3cell573_delivery), against this IPA; the 572 validator derives its
567-equivalent in turn. The receipt names build 573.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell573_delivery as delivery
import validate_melonx_texture572_ipa as texture572

texture564=texture572.texture564
texture564.IDENTITY='MeloNX-texture573-identity.json'
_expected572=texture572.expected

def expected():
 """The 564 engine receipt carried by build 572, computed on the delivered 572 tree, carried by build 573."""
 with delivery.as_572():receipt=_expected572()
 assert receipt['build']==int(delivery.d572.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 with delivery.as_572():result=texture572.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build573CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
