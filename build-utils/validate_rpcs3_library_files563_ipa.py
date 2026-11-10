#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA563.

The 562 validator runs unchanged on the delivered 562 tree, which
rpcs3cell563_delivery puts back for each check (563 changes only the RPCS3
Core recipe), and the 562 recipe its 561 and 558 views in turn. The compiled
Dart image of 563 is the 562 one and must still hold the same installation,
free-space, deletion and synchronization constants. The embedded identity is
the 557 receipt under its 563 name, naming build 563 (the receipt's own build
stays in receiptBuild).
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3cell563_delivery as delivery563
import validate_rpcs3_library_files562_ipa as library562

library=library562.library
library.IDENTITY='RPCS3-library-files563-identity.json'
_expected562=library562.expected

def expected():
 """The 557 receipt carried by build 562, computed on the delivered 562 tree, carried by build 563."""
 with delivery563.as_562():receipt=_expected562()
 assert receipt['build']==int(delivery563.d562.BUILD)
 return dict(receipt,build=int(delivery563.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery563.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery563.as_562(),delivery563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery563.as_562(),delivery563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
