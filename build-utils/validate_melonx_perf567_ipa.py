#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the 566 engine (86c2b4d) to private IPA567.

567 ships the 566 MeloNX engine and hosts byte for byte and swaps only the
RPCS3 Core. The 566 validator therefore runs unchanged on the delivered 566
tree, which rpcs3cell567_delivery puts back for the whole check (and the 566
recipe its 565 engine view in turn). The embedded identity is the 558
receipt under its 567 name, naming build 567.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell567_delivery as delivery567
import validate_melonx_perf566_ipa as perf566

threading=perf566.threading
threading.IDENTITY='MeloNX-perf567-identity.json'
_expected566=perf566.expected

def expected():
 """The 558 receipt carried by build 566, computed on the delivered 566 tree, carried by build 567."""
 with delivery567.as_566():receipt=_expected566()
 assert receipt['build']==int(delivery567.d566.BUILD)
 return dict(receipt,build=int(delivery567.BUILD))
threading.expected=expected

def embed(app):
 with delivery567.as_566():perf566.embed(app)

def validate(ipa,build):
 with delivery567.as_566():result=perf566.validate(ipa,build)
 return dict(result,build567CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery567.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
