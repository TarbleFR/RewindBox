#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the 564 engine (876a087) to private IPA565.

565 ships the 564 MeloNX engine and hosts byte for byte and swaps only the
RPCS3 Core. The 564 validator therefore runs unchanged on the delivered 564
tree, which rpcs3cell565_delivery puts back for the whole check (and the 564
recipe its 563 engine view in turn). The embedded identity is the 558
receipt under its 565 name, naming build 565.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell565_delivery as delivery565
import validate_melonx_perf564_ipa as perf564

threading=perf564.threading
threading.IDENTITY='MeloNX-perf565-identity.json'
_expected564=perf564.expected

def expected():
 """The 558 receipt carried by build 564, computed on the delivered 564 tree, carried by build 565."""
 with delivery565.as_564():receipt=_expected564()
 assert receipt['build']==int(delivery565.d564.BUILD)
 return dict(receipt,build=int(delivery565.BUILD))
threading.expected=expected

def embed(app):
 with delivery565.as_564():perf564.embed(app)

def validate(ipa,build):
 with delivery565.as_564():result=perf564.validate(ipa,build)
 return dict(result,build565CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery565.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
