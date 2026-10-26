#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA558.

The 557 validator runs unchanged on the delivered 557 tree, which
melonxperf558_delivery puts back in place for each check (558 changes no
file of 557 or 554, but replaces MeloNX files of the 553 parity that the
product trees cover, and adds its recipe). Its receipt carries the 554
import receipt, checked on the delivered 554 tree by the 557 recipe in
turn. The compiled Dart image of 558 must still hold the constants of the
installation prompt and progress (554) and of the free-space option, the
library-file deletion and the synchronization of rows whose file is gone
(557). Only the embedded identity name changes.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import melonxperf558_delivery as delivery558
import validate_rpcs3_library_files557_ipa as library

library.IDENTITY='RPCS3-library-files558-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery558.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:
  with delivery558.as_557():library.embed(a.embed)
 else:
  assert a.ipa and a.report
  with delivery558.as_557():result=library.validate(a.ipa,a.build_number)
  a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
