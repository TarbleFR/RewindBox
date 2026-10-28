#!/usr/bin/env python3
"""Bind the 558 MeloNX performance receipt (threading, frame pacing) carried by build 583 to private IPA585.

585 keeps the 583 product and engine and swaps only the RPCS3 Core. The 583
validator runs unchanged on the delivered 583 tree (as_583 in
rpcs3cell585_delivery; the 583 and 582 recipes derive their own views in
turn) and the receipt names build 585. No game or iPhone runs here; no FPS
gain is claimed.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell585_delivery as delivery
import validate_melonx_perf583_ipa as perf583

threading=perf583.threading
threading.IDENTITY='MeloNX-perf585-identity.json'
_expected583=perf583.expected

def expected():
 """The 558 receipt carried by build 583, computed on the delivered 583 tree, carried by build 585."""
 with delivery.as_583():receipt=_expected583()
 assert receipt['build']==int(delivery.d583.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
threading.expected=expected

def embed(app):
 with delivery.as_583():perf583.embed(app)

def validate(ipa,build):
 with delivery.as_583():result=perf583.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build585CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
