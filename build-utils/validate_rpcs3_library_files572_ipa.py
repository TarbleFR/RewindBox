#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA572.

The 567 validator runs unchanged on the delivered 567 tree, which
melonxjit572_delivery puts back for each check (572 changes only the MeloNX
engine), and the 567 to 562 recipes their own views in turn. The compiled
Dart image of 572 is the 567 one and must still hold the same installation,
free-space, deletion and synchronization constants. The embedded identity is
the 557 receipt under its 572 name, naming build 572.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import melonxjit572_delivery as delivery572
import validate_rpcs3_library_files567_ipa as library567

library=library567.library
library.IDENTITY='RPCS3-library-files572-identity.json'
_expected567=library567.expected
d567=delivery572.d567
d566=d567.d566
d565=d566.d565
d564=d566.d564
d563=d566.d563

def expected():
 """The 557 receipt carried by build 567, computed on the delivered 567 tree, carried by build 572."""
 with delivery572.as_567():receipt=_expected567()
 assert receipt['build']==int(d567.BUILD)
 return dict(receipt,build=int(delivery572.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery572.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
