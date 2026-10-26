#!/usr/bin/env python3
"""Bind the MeloNX standalone parity of 553 to private IPA554.

The 553 parity validator runs unchanged: the 554 import files are Dart only
and shared with no MeloNX check, and the 553 receipts are bound to the 553
product tree computed from the 554 index (rpcs3import554_delivery rebinds
it before the 553 delivery loads). Only the embedded identity name changes.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3import554_delivery as delivery554
import validate_melonx_parity553_ipa as parity

parity.threading.IDENTITY='MeloNX-parity554-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery554.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:parity.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=parity.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
