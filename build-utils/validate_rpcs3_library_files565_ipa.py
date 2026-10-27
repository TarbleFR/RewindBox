#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA565.

The 564 validator runs unchanged on the delivered 564 tree, which
rpcs3cell565_delivery puts back for each check (565 changes only the RPCS3
Core recipe), and the 564, 563 and 562 recipes their own views in turn. The
compiled Dart image of 565 is the 564 one and must still hold the same
installation, free-space, deletion and synchronization constants. The
embedded identity is the 557 receipt under its 565 name, naming build 565
(the receipt's own build stays in receiptBuild).
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3cell565_delivery as delivery565
import validate_rpcs3_library_files564_ipa as library564

library=library564.library
library.IDENTITY='RPCS3-library-files565-identity.json'
_expected564=library564.expected
d564=delivery565.d564
d563=d564.d563

def expected():
 """The 557 receipt carried by build 564, computed on the delivered 564 tree, carried by build 565."""
 with delivery565.as_564():receipt=_expected564()
 assert receipt['build']==int(d564.BUILD)
 return dict(receipt,build=int(delivery565.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery565.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
