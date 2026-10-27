#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), its engine (8f83748) and iPhone host (e2c9437) to private IPA563.

563 ships the 562 MeloNX engine and hosts byte for byte (the 558 engine, the
558 host and the 562 keyboard and L3/R3 files) and swaps only the RPCS3
Core. The 562 validator therefore runs unchanged on the delivered 562 tree,
which rpcs3cell563_delivery puts back for the whole check (and the 562 recipe
its 561 and 558 views in turn). The signed IPA must still carry every 558
MeloNX claim. The embedded identity is the 558 receipt under its 563 name,
naming build 563.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell563_delivery as delivery563
import validate_melonx_perf562_ipa as perf562

threading=perf562.threading
threading.IDENTITY='MeloNX-perf563-identity.json'
_expected562=perf562.expected

def expected():
 """The 558 receipt carried by build 562, computed on the delivered 562 tree, carried by build 563."""
 with delivery563.as_562():receipt=_expected562()
 assert receipt['build']==int(delivery563.d562.BUILD)
 return dict(receipt,build=int(delivery563.BUILD))
threading.expected=expected

def embed(app):
 with delivery563.as_562():perf562.embed(app)

def validate(ipa,build):
 with delivery563.as_562():result=perf562.validate(ipa,build)
 return dict(result,build563CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery563.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
