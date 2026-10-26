#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), its engine (8f83748) and iPhone host (e2c9437) to private IPA559.

559 ships the 558 MeloNX engine, host and frontend byte for byte; it swaps
only the RPCS3 Core. The 558 validator (and the 553 parity and 549 chain
under it) therefore runs unchanged: its receipt is computed on the delivered
558 tree, which rpcs3cell559_delivery puts back in place, and the signed IPA
must still carry every 558 MeloNX claim. The embedded identity is the 558
receipt under its 559 name, naming build 559.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell559_delivery as delivery559
import validate_melonx_perf558_ipa as perf558

threading=perf558.threading
threading.IDENTITY='MeloNX-perf559-identity.json'
_expected558=perf558.expected

def expected():
 """The 558 receipt, computed on the delivered 558 tree, carried by build 559."""
 with delivery559.as_558():receipt=_expected558()
 assert receipt['build']==int(delivery559.d558.BUILD)
 return dict(receipt,build=int(delivery559.BUILD))
threading.expected=expected

def embed(app):
 perf558.embed(app)

def validate(ipa,build):
 return dict(perf558.validate(ipa,build),build559CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery559.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
