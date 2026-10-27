#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), its engine (8f83748) and iPhone host (e2c9437) to private IPA562.

562 keeps the 558 MeloNX engine and adds the keyboard and L3/R3 host files
(their own receipt: validate_melonx_input562_ipa.py). The 558 validator (and
the 553 parity and 549 chain under it) therefore runs on the delivered 561
tree, which melonxinput562_delivery puts back for the whole check (the 558
Swift files, strings and generated controller strings in place of the 562
ones), and its receipt on the delivered 558 tree through the 561 view. The
signed IPA must still carry every 558 MeloNX claim; the 562 host is a
superset of the 558 one. The embedded identity names build 562.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxinput562_delivery as delivery562
import validate_melonx_perf558_ipa as perf558

threading=perf558.threading
threading.IDENTITY='MeloNX-perf562-identity.json'
_expected558=perf558.expected

def expected():
 """The 558 receipt, computed on the delivered 558 tree, carried by build 562."""
 with delivery562.as_558():receipt=_expected558()
 assert receipt['build']==int(delivery562.d558.BUILD)
 return dict(receipt,build=int(delivery562.BUILD))
threading.expected=expected

def embed(app):
 with delivery562.as_561():perf558.embed(app)

def validate(ipa,build):
 with delivery562.as_561():result=perf558.validate(ipa,build)
 return dict(result,build559CoreOnly=True,build560CoreOnly=True,build561CoreOnly=True,build562KeyboardHost=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery562.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
