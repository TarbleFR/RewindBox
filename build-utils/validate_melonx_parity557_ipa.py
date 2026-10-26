#!/usr/bin/env python3
"""Bind the MeloNX standalone parity of 553 to private IPA557.

The 553 parity validator runs unchanged on the delivered 554 tree, which
rpcs3libraryfiles557_delivery puts back in place for each check: the 553
MeloNX re-run receipt hashes sqlite_service.dart, which 557 changes (the
ROM folder saves are queued), and its product trees are the 553 ones
computed from the 554 index. The 557 files touch no MeloNX source. Only the
embedded identity name changes.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3libraryfiles557_delivery as delivery557
import validate_melonx_parity553_ipa as parity

parity.threading.IDENTITY='MeloNX-parity557-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery557.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery557.as_554():parity.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery557.as_554():result=parity.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
