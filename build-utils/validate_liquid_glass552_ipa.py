#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface to private IPA552.

The 550 validator runs unchanged against the 552 recipe: the interface files
and their receipt are the 550 ones, bound to the 552 tree with the shipped
RPCS3 551 and MeloNX 552 files at their 550 versions; the embedded identity
names build 552, the 551 Core and the 552 MeloNX engine.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxparity552_delivery as delivery552
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery552
glass.IDENTITY='LiquidGlass-ui552-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery552.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
