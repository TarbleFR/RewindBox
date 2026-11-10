#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA567.

The 566 validator runs unchanged on the delivered 566 tree, which
rpcs3cell567_delivery puts back for each check (567 changes only the RPCS3
Core recipe), and the 566 to 562 recipes their own views in turn. The
compiled Dart image of 567 is the 566 one and must still hold the same
installation, free-space, deletion and synchronization constants. The
embedded identity is the 557 receipt under its 567 name, naming build 567.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3cell567_delivery as delivery567
import validate_rpcs3_library_files566_ipa as library566

library=library566.library
library.IDENTITY='RPCS3-library-files567-identity.json'
_expected566=library566.expected
d566=delivery567.d566
d565=d566.d565
d564=d566.d564
d563=d566.d563

def expected():
 """The 557 receipt carried by build 566, computed on the delivered 566 tree, carried by build 567."""
 with delivery567.as_566():receipt=_expected566()
 assert receipt['build']==int(d566.BUILD)
 return dict(receipt,build=int(delivery567.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery567.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
