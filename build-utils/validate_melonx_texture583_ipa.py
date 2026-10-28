#!/usr/bin/env python3
"""Bind the 564 MeloNX engine receipt (texture pool, journal) carried by build 582 to private IPA583.

583 keeps the 582 product and engine and swaps only the RPCS3 Core. The 582
validator runs unchanged on this IPA inside the delivered 582 tree (as_582
in rpcs3cell583_delivery; the 582 recipe derives its 581-equivalent and the
581 to 566 validators their own views in turn); the receipt names build 583.
No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell583_delivery as delivery
import validate_melonx_texture582_ipa as texture582

texture564=texture582.texture564
texture564.IDENTITY='MeloNX-texture583-identity.json'
_expected582=texture582.expected

def expected():
 """The receipt carried by build 582, computed on the delivered 582 tree, carried by build 583."""
 with delivery.as_582():receipt=_expected582()
 assert receipt['build']==int(delivery.d582.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 with delivery.as_582():result=texture582.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build583CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
