#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface receipt to private IPA556.

The 550 validator runs unchanged against the 556 recipe: its receipt (the
550 interface inputs and tests) is checked on the delivered 554 tree, which
melonxperf556_delivery puts back in place for the check (556 replaces
MeloNXInternalBridgePlugin.swift, an input the 550 MeloNX receipt hashes;
the 556 receipt hashes its 556 version). The embedded identity names build
556, the 551 Core and the 556 MeloNX engine; the compiled interface markers
are read from the 556 Dart image.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxperf556_delivery as delivery556
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery556
glass.IDENTITY='LiquidGlass-ui556-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery556.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
