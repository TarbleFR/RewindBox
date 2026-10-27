#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA566.

The 565 validator runs unchanged on the delivered 565 tree, which
melonxjit566_delivery puts back for each check (566 changes only the MeloNX
engine), and the 565 to 562 recipes their own views in turn. The compiled
Dart image of 566 is the 565 one and must still hold the same installation,
free-space, deletion and synchronization constants. The embedded identity is
the 557 receipt under its 566 name, naming build 566.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import melonxjit566_delivery as delivery566
import validate_rpcs3_library_files565_ipa as library565

library=library565.library
library.IDENTITY='RPCS3-library-files566-identity.json'
_expected565=library565.expected
d565=delivery566.d565
d564=delivery566.d564
d563=delivery566.d563

def expected():
 """The 557 receipt carried by build 565, computed on the delivered 565 tree, carried by build 566."""
 with delivery566.as_565():receipt=_expected565()
 assert receipt['build']==int(d565.BUILD)
 return dict(receipt,build=int(delivery566.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery566.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
