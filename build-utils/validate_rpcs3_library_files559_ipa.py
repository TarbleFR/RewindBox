#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA559.

The 558 validator runs unchanged on the delivered 558 tree, which
rpcs3cell559_delivery puts back in place for each check (559 changes no
shipped file, only the RPCS3 Core recipe), and the 557 one on the delivered
557 tree in turn. The compiled Dart image of 559 must still hold the same
installation, free-space, deletion and synchronization constants. The
embedded identity is the 557 receipt under its 559 name, naming build 559
(the receipt's own build stays in receiptBuild).
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3cell559_delivery as delivery559
import validate_rpcs3_library_files558_ipa as library558

library=library558.library
library.IDENTITY='RPCS3-library-files559-identity.json'
_expected558=library558.expected

def expected():
 """The 557 receipt carried by build 558, computed on the delivered 558 tree, carried by build 559."""
 with delivery559.as_558():receipt=_expected558()
 assert receipt['build']==int(delivery559.d558.BUILD)
 return dict(receipt,build=int(delivery559.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery559.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:library.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=library.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
