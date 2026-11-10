#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface receipt to private IPA567.

The 550 validator runs unchanged against the 567 recipe: its receipt (the
550 interface inputs and tests) is checked on the delivered 558 tree, which
rpcs3cell567_delivery puts back through the 566 view (and the 566 to 557
recipes their own views in turn). 567 ships no interface file. The embedded
identity names build 567, the 567 Core and the 566 engine.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import rpcs3cell567_delivery as delivery567
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery567
glass.IDENTITY='LiquidGlass-ui567-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery567.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
