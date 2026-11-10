#!/usr/bin/env python3
"""Bind the 558 MeloNX performance receipt (threading, frame pacing) carried by build 577 to private IPA579.

579 keeps the 577 product and swaps only the RPCS3 Core. The 577 validator
runs unchanged on the delivered 577 tree (as_577 in rpcs3cell579_delivery;
the 577 recipe derives its own 576-equivalent in turn) and the receipt names
build 579. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell579_delivery as delivery
import validate_melonx_perf577_ipa as perf577

threading=perf577.threading
threading.IDENTITY='MeloNX-perf579-identity.json'
_expected577=perf577.expected

def expected():
 """The 558 receipt carried by build 577, computed on the delivered 577 tree, carried by build 579."""
 with delivery.as_577():receipt=_expected577()
 assert receipt['build']==int(delivery.d577.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
threading.expected=expected

def embed(app):
 with delivery.as_577():perf577.embed(app)

def validate(ipa,build):
 with delivery.as_577():result=perf577.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build579CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
