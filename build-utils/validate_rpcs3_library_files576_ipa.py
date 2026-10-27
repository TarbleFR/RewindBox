#!/usr/bin/env python3
"""Bind the 554/557 library-file fix and the RPCS3 import receipts to private IPA576.

576 ships every library and import file of 575 unchanged and swaps only the
MeloNX engine, which these checks do not read. The 575 receipt is computed on
the delivered 575 tree (as_575 in melonxwarm576_delivery) and checked on the
same views as 575 checked it; the receipt names build 576.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import melonxwarm576_delivery as delivery576
import validate_rpcs3_library_files575_ipa as library575

library=library575.library
library.IDENTITY='RPCS3-library-files576-identity.json'
_expected575=library575.expected
delivery575=library575.delivery575
delivery573=library575.delivery573
delivery572=library575.delivery572
d567=library575.d567
d566=library575.d566
d565=library575.d565
d564=library575.d564
d563=library575.d563

def expected():
 """The 557 receipt carried by build 575, computed on the delivered 575 tree, carried by build 576."""
 with delivery576.as_575():receipt=_expected575()
 assert receipt['build']==int(delivery575.BUILD)
 return dict(receipt,build=int(delivery576.BUILD))
library.expected=expected

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery576.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery576.as_575(),delivery575.as_573(),delivery573.as_572(),delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery576.as_575(),delivery575.as_573(),delivery573.as_572(),delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
