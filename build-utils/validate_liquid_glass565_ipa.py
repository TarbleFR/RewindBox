#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface receipt to private IPA565.

The 550 validator runs unchanged against the 565 recipe: its receipt (the
550 interface inputs and tests) is checked on the delivered 558 tree, which
rpcs3cell565_delivery puts back through the 564 view (and the 564 to 557
recipes their own views in turn). 565 ships no interface file. The embedded
identity names build 565, the 565 Core and the 564 engine.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import rpcs3cell565_delivery as delivery565
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery565
glass.IDENTITY='LiquidGlass-ui565-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery565.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
