#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA564.

The 563 validator runs unchanged on the delivered 563 tree, which
melonxtexture564_delivery puts back for each check (564 changes only the
MeloNX engine), and the 563 and 562 recipes their own views in turn. The
compiled Dart image of 564 is the 563 one and must still hold the same
installation, free-space, deletion and synchronization constants. The
embedded identity is the 557 receipt under its 564 name, naming build 564
(the receipt's own build stays in receiptBuild).
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import melonxtexture564_delivery as delivery564
import validate_rpcs3_library_files563_ipa as library563

library=library563.library
library.IDENTITY='RPCS3-library-files564-identity.json'
_expected563=library563.expected
d563=delivery564.d563

def expected():
 """The 557 receipt carried by build 563, computed on the delivered 563 tree, carried by build 564."""
 with delivery564.as_563():receipt=_expected563()
 assert receipt['build']==int(d563.BUILD)
 return dict(receipt,build=int(delivery564.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery564.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
