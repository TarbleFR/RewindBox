#!/usr/bin/env python3
"""Bind the 557 RPCS3 library-files receipt carried by build 583 to private IPA585.

585 swaps only the RPCS3 Core; the library-file host sources are the 583
(582, 581, 579, 577) ones. The receipt is computed on the delivered 583 tree
(as_583, then the 583, 582, 581, 579 and 577 recipes' own views down to 561)
and names build 585.
"""
import argparse,contextlib,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell585_delivery as delivery
import validate_rpcs3_library_files583_ipa as library583

library=library583.library
library.IDENTITY='RPCS3-library-files585-identity.json'
_expected583=library583.expected
delivery583=library583.delivery

def expected():
 """The 557 receipt carried by build 583, computed on the delivered 583 tree, carried by build 585."""
 with delivery.as_583():receipt=_expected583()
 assert receipt['build']==int(delivery583.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
library.expected=expected

def views():
 return (delivery.as_583(),)+library583.views()

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
