#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface to private IPA551.

The 550 validator runs unchanged against the 551 recipe: the interface files
and their receipt are the 550 ones, bound to the 551 tree minus the shipped
RPCS3 551 files; the embedded identity names build 551 and the 551 Core.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import rpcs3cell551_delivery as delivery551
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery551
glass.IDENTITY='LiquidGlass-ui551-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery551.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
