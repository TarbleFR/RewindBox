#!/usr/bin/env python3
"""Bind the 557 RPCS3 library-files receipt carried by build 577 to private IPA579.

579 swaps only the RPCS3 Core; the library-file host sources are the 577
ones. The receipt is computed on the delivered 577 tree (as_577, then the 577
recipe's own views down to 561) and names build 579.
"""
import argparse,contextlib,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell579_delivery as delivery
import validate_rpcs3_library_files577_ipa as library577

library=library577.library
library.IDENTITY='RPCS3-library-files579-identity.json'
_expected577=library577.expected
delivery577=library577.delivery577
delivery576=library577.delivery576
delivery575=library577.delivery575
delivery573=library577.delivery573
delivery572=library577.delivery572
d567=library577.d567
d566=library577.d566
d565=library577.d565
d564=library577.d564
d563=library577.d563

def expected():
 """The 557 receipt carried by build 577, computed on the delivered 577 tree, carried by build 579."""
 with delivery.as_577():receipt=_expected577()
 assert receipt['build']==int(delivery577.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
library.expected=expected

def views():
 return (delivery.as_577(),delivery577.as_576(),delivery576.as_575(),delivery575.as_573(),delivery573.as_572(),
         delivery572.as_567(),d567.as_566(),d566.as_565(),d565.as_564(),d564.as_563(),d563.as_562(),d563.d562.as_561())

def embed(app):
 with contextlib.ExitStack() as stack:
  for view in views():stack.enter_context(view)
  library.embed(app)

def validate(ipa,build):
 with contextlib.ExitStack() as stack:
  for view in views():stack.enter_context(view)
  return library.validate(ipa,build)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
