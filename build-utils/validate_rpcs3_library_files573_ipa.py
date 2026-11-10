#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA573.

573 ships every library file of 572 and swaps only the RPCS3 Core. The 572
receipt is computed on the delivered 572 tree (as_572 in
rpcs3cell573_delivery), whose own views give back the 567 to 561 trees in
turn, as 572 checked it. The receipt names build 573.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3cell573_delivery as delivery573
import validate_rpcs3_library_files572_ipa as library572

library=library572.library
library.IDENTITY='RPCS3-library-files573-identity.json'
_expected572=library572.expected
delivery572=library572.delivery572
d567=library572.d567
d566=library572.d566
d565=library572.d565
d564=library572.d564
d563=library572.d563

def expected():
 """The 557 receipt carried by build 572, computed on the delivered 572 tree, carried by build 573."""
 with delivery573.as_572():receipt=_expected572()
 assert receipt['build']==int(delivery572.BUILD)
 return dict(receipt,build=int(delivery573.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery573.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery573.as_572(),delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery573.as_572(),delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
