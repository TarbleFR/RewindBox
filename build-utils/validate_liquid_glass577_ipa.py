#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface receipt to private IPA577.

The 550 validator runs unchanged against the 577 recipe: its receipt (the 550
interface inputs and tests) is checked on the delivered 558 tree, which
interface577_delivery puts back through the 576 view (and the 576 to 557
recipes their own views in turn). 577 changes five 550 interface files; their
577 versions, tests and compiled markers are bound by
validate_interface577_ipa. The 550 markers checked here remain compiled. The
embedded identity names build 577.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import interface577_delivery as delivery577
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery577
glass.IDENTITY='LiquidGlass-ui577-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery577.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
