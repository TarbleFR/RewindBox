#!/usr/bin/env python3
"""Bind the 558 MeloNX performance receipt (threading, frame pacing) carried by build 579 to private IPA581.

581 keeps the 579 product and swaps only the RPCS3 Core. The 579 validator
runs unchanged on the delivered 579 tree (as_579 in rpcs3cell581_delivery;
the 579 and 577 recipes derive their own views in turn) and the receipt
names build 581. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell581_delivery as delivery
import validate_melonx_perf579_ipa as perf579

threading=perf579.threading
threading.IDENTITY='MeloNX-perf581-identity.json'
_expected579=perf579.expected

def expected():
 """The 558 receipt carried by build 579, computed on the delivered 579 tree, carried by build 581."""
 with delivery.as_579():receipt=_expected579()
 assert receipt['build']==int(delivery.d579.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
threading.expected=expected

def embed(app):
 with delivery.as_579():perf579.embed(app)

def validate(ipa,build):
 with delivery.as_579():result=perf579.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build581CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
