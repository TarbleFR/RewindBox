#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface receipt to private IPA558.

The 550 validator runs unchanged against the 558 recipe: its receipt (the
550 interface inputs and tests) is checked on the delivered 554 tree, which
melonxperf558_delivery puts back in place for the check through the 557
recipe (558 replaces MeloNXInternalBridgePlugin.swift, an input the 550
MeloNX receipt hashes, and 557 search_screen.dart and sqlite_service.dart;
the 558 and 557 receipts hash their own versions). The embedded identity
names build 558, the 551 Core and the 558 MeloNX engine; the compiled
interface markers are read from the 558 Dart image.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxperf558_delivery as delivery558
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery558
glass.IDENTITY='LiquidGlass-ui558-identity.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery558.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:glass.embed(a.embed)
 else:
  assert a.ipa and a.report
  result=glass.validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
