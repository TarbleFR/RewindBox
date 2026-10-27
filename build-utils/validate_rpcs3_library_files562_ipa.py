#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA562.

The 558 validator runs unchanged on the delivered 558 tree, which
melonxinput562_delivery puts back through the 561 view (562 changes only the
MeloNX host). The compiled Dart image of 562 is the 561 one and must still
hold the same installation, free-space, deletion and synchronization
constants. The embedded identity is the 557 receipt under its 562 name.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import melonxinput562_delivery as delivery562
import validate_rpcs3_library_files558_ipa as library558

library=library558.library
library.IDENTITY='RPCS3-library-files562-identity.json'
_expected558=library558.expected

def expected():
 """The 557 receipt carried by build 558, computed on the delivered 558 tree, carried by build 562."""
 with delivery562.as_558():receipt=_expected558()
 assert receipt['build']==int(delivery562.d558.BUILD)
 return dict(receipt,build=int(delivery562.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery562.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
