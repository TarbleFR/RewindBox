#!/usr/bin/env python3
"""Bind the MeloNX keyboard, the L3/R3 entry and the engine callback registry of 576 to private IPA577.

577 keeps every MeloNX host file and the engine of 576 and changes only Dart
interface files, the gamepads bridge and the RPCS3 input bridge. The 576
receipt is computed on the delivered 576 tree (as_576 in
interface577_delivery) and the 576 validator runs unchanged there, against
its own 575-equivalent of this IPA. The receipt names build 577.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import interface577_delivery as delivery
import validate_melonx_input576_ipa as input576
input563=input576.input563
input563.IDENTITY='MeloNX-input577-identity.json'
_expected576=input576.expected

def expected():
 """The 576 receipt, computed on the delivered 576 tree, carried by build 577."""
 with delivery.as_576():receipt=_expected576()
 assert receipt['build']==int(delivery.d576.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
# The 563 to 576 validators compare the embedded receipt with their module's expected().
for module in (input563,input576.input564,input576.input566,input576.input567,input576.input572,input576.input573,
               input576.input575,input576):
 module.expected=expected

def embed(app):
 with delivery.as_576():input576.embed(app)

def validate(ipa,build):
 with delivery.as_576():return dict(input576.validate(ipa,build),build577InterfaceAndController=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
