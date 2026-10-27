#!/usr/bin/env python3
"""Bind the 554/557 library-file fix and the RPCS3 import receipts to private IPA577.

577 ships every library and import file of 576 unchanged; its Dart interface,
gamepads and RPCS3 input changes are not read by these checks. The 576
receipt is computed on the delivered 576 tree (as_576 in
interface577_delivery) and checked on the same views as 576 checked it; the
receipt names build 577.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import interface577_delivery as delivery577
import validate_rpcs3_library_files576_ipa as library576

library=library576.library
library.IDENTITY='RPCS3-library-files577-identity.json'
_expected576=library576.expected
delivery576=library576.delivery576
delivery575=library576.delivery575
delivery573=library576.delivery573
delivery572=library576.delivery572
d567=library576.d567
d566=library576.d566
d565=library576.d565
d564=library576.d564
d563=library576.d563

def expected():
 """The 557 receipt carried by build 576, computed on the delivered 576 tree, carried by build 577."""
 with delivery577.as_576():receipt=_expected576()
 assert receipt['build']==int(delivery576.BUILD)
 return dict(receipt,build=int(delivery577.BUILD))
library.expected=expected

def views():
 return (delivery577.as_576(),delivery576.as_575(),delivery575.as_573(),delivery573.as_572(),delivery572.as_567(),
         d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561())

if __name__=='__main__':
 import contextlib
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery577.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with contextlib.ExitStack() as stack:
   for view in views():stack.enter_context(view)
   library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with contextlib.ExitStack() as stack:
   for view in views():stack.enter_context(view)
   result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
