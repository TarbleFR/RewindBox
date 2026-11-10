#!/usr/bin/env python3
"""Bind the 564 MeloNX engine (876a087) and its engine run to private IPA565.

565 ships the 564 engine byte for byte and swaps only the RPCS3 Core. The
564 checks run unchanged on the delivered 564 tree (engine evidence, packaged
identity and fingerprint, exports and journal literals, every non-engine
entry equal to the 563-equivalent IPA); the receipt names build 565 and the
565 Core. No game or iPhone runs here; no FPS gain is claimed.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell565_delivery as delivery
import validate_melonx_texture564_ipa as texture564

texture564.IDENTITY='MeloNX-texture565-identity.json'
_expected564=texture564.expected

def expected():
 """The 564 engine receipt, computed on the delivered 564 tree, carried by build 565 with the 565 Core."""
 with delivery.as_564():receipt=_expected564()
 assert receipt['build']==int(delivery.d564.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,
  rpcCore563Source=delivery.CORE563_SOURCE,rpcCore563Run=delivery.CORE563_RUN)
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 with delivery.as_564():result=texture564.validate(ipa,build)
 return dict(result,build565CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
