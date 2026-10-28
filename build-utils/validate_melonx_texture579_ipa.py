#!/usr/bin/env python3
"""Bind the 564 MeloNX engine receipt (texture pool, journal) carried by build 577 to private IPA579.

579 swaps only the RPCS3 Core and keeps the 577 engine. The 577 validator
runs unchanged on this IPA inside the delivered 577 tree (as_577 in
rpcs3cell579_delivery; its own 576-equivalent derivation follows); the
receipt names build 579. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell579_delivery as delivery
import validate_melonx_texture577_ipa as texture577

texture564=texture577.texture564
texture564.IDENTITY='MeloNX-texture579-identity.json'
_expected577=texture577.expected

def expected():
 """The receipt carried by build 577, computed on the delivered 577 tree, carried by build 579."""
 with delivery.as_577():receipt=_expected577()
 assert receipt['build']==int(delivery.d577.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 with delivery.as_577():result=texture577.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build579CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
