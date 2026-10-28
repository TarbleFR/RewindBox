#!/usr/bin/env python3
"""Bind the 563 MeloNX input receipt (keyboard, L3/R3, the engine callback registry and the controller relay) carried by build 583 to private IPA585.

585 swaps only the RPCS3 Core. The 583 receipt is computed on the delivered
583 tree (as_583 in rpcs3cell585_delivery) and the 583 validator runs
unchanged on this IPA; the receipt names build 585.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell585_delivery as delivery
import validate_melonx_input583_ipa as input583
input582=input583.input582
input581=input583.input581
input579=input583.input579
input577=input583.input577
input576=input583.input576
input575=input583.input575
input573=input583.input573
input572=input583.input572
input567=input583.input567
input566=input583.input566
input564=input583.input564
input563=input583.input563
input563.IDENTITY='MeloNX-input585-identity.json'
_expected583=input583.expected

def expected():
 """The 583 receipt, computed on the delivered 583 tree, carried by build 585."""
 with delivery.as_583():receipt=_expected583()
 assert receipt['build']==int(delivery.d583.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
# The 563 to 583 validators compare the embedded receipt with their module's expected().
for module in (input563,input564,input566,input567,input572,input573,input575,input576,input577,input579,input581,input582,input583):
 module.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 with delivery.as_583():result=input583.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build585CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
