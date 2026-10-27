#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA575.

575 ships every library file of 573 and swaps only the RPCS3 Core. The 573
receipt is computed on the delivered 573 tree (as_573 in
rpcs3cell575_delivery), whose own views give back the 572 to 561 trees in
turn, as 573 checked it. The receipt names build 575.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3cell575_delivery as delivery575
import validate_rpcs3_library_files573_ipa as library573

library=library573.library
library.IDENTITY='RPCS3-library-files575-identity.json'
_expected573=library573.expected
delivery573=library573.delivery573
delivery572=library573.delivery572
d567=library573.d567
d566=library573.d566
d565=library573.d565
d564=library573.d564
d563=library573.d563

def expected():
 """The 557 receipt carried by build 573, computed on the delivered 573 tree, carried by build 575."""
 with delivery575.as_573():receipt=_expected573()
 assert receipt['build']==int(delivery573.BUILD)
 return dict(receipt,build=int(delivery575.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery575.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery575.as_573(),delivery573.as_572(),delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery575.as_573(),delivery573.as_572(),delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
