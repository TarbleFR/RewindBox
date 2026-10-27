#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the engine of 576 to private IPA577.

577 keeps every MeloNX host file and the engine of 576 and changes only Dart
interface files, the gamepads bridge and the RPCS3 input bridge. The 576
validator (and the 575 to 549 chain under it) runs unchanged on the delivered
576 tree (as_576 in interface577_delivery). The embedded identity is the 558
receipt under its 577 name, naming build 577.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import interface577_delivery as delivery
import validate_melonx_perf576_ipa as perf576

threading=perf576.threading
threading.IDENTITY='MeloNX-perf577-identity.json'
_expected576=perf576.expected

def expected():
 """The 558 receipt carried by build 576, computed on the delivered 576 tree, carried by build 577."""
 with delivery.as_576():receipt=_expected576()
 assert receipt['build']==int(delivery.d576.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
threading.expected=expected
perf576.expected=expected

def embed(app):
 with delivery.as_576():perf576.embed(app)

def validate(ipa,build):
 with delivery.as_576():return dict(perf576.validate(ipa,build),build577InterfaceAndController=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
