#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface receipt to private IPA559.

The 550 validator runs unchanged against the 559 recipe: its receipt (the
550 interface inputs and tests) is checked on the delivered 558 tree, which
rpcs3cell559_delivery puts back in place for the check (and the 558 and 557
recipes their own views in turn). 559 ships no interface file. The embedded
identity names build 559, the 559 Core and the 558 MeloNX engine; the
compiled interface markers are read from the 559 Dart image.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import rpcs3cell559_delivery as delivery559
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery559
glass.IDENTITY='LiquidGlass-ui559-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery559.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
