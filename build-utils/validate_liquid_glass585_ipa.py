#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface receipt to private IPA585.

The 550 validator runs unchanged against the 585 recipe: its receipt (the
550 interface inputs and tests) is checked on the delivered 558 tree, which
rpcs3cell585_delivery puts back through the 583 view (and the 583 to 557
recipes their own views in turn). 585 ships no interface file. The embedded
identity names build 585 and the 585 Core.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell585_delivery as delivery
import validate_liquid_glass550_ipa as glass

glass.delivery=delivery
glass.IDENTITY='LiquidGlass-ui585-identity.json'

def embed(app):
 glass.embed(app)

def validate(ipa,build):
 return glass.validate(ipa,build)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
