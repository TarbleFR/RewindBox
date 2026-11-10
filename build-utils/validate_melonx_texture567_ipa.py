#!/usr/bin/env python3
"""Bind the 564 MeloNX engine claims (876a087: texture pool, bounded engine journal, crash record) to private IPA567.

567 ships the 566 engine (which keeps every 564 engine change) byte for byte
and swaps only the RPCS3 Core. The 566 receipt of the 564 engine claims is
checked unchanged on the delivered 566 tree (and, through it, on the 565
tree with the 564 engine's evidence against derived_ipa()); the receipt names
build 567 and the 567 Core.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell567_delivery as delivery
import validate_melonx_texture566_ipa as texture566

texture564=texture566.texture564
texture564.IDENTITY='MeloNX-texture567-identity.json'
_expected566=texture566.expected

def expected():
 """The 564 engine receipt carried by build 566, computed on the delivered 566 tree, carried by build 567 with the 567 Core."""
 with delivery.as_566():receipt=_expected566()
 assert receipt['build']==int(delivery.d566.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCore567Source=delivery.CORE_SOURCE,rpcCore567Run=delivery.CORE_RUN)
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 with delivery.as_566():result=texture566.validate(ipa,build)
 return dict(result,build567CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
