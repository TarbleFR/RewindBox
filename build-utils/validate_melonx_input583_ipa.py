#!/usr/bin/env python3
"""Bind the 563 MeloNX input receipt (keyboard, L3/R3, the engine callback registry and the controller relay) carried by build 582 to private IPA583.

583 swaps only the RPCS3 Core. The 582 receipt is computed on the delivered
582 tree (as_582 in rpcs3cell583_delivery) and the 582 validator runs
unchanged on this IPA (its 581-equivalent and the engine exports of this
IPA's own engine); the receipt names build 583.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell583_delivery as delivery
import validate_melonx_input582_ipa as input582
input581=input582.input581
input579=input582.input579
input577=input582.input577
input576=input582.input576
input575=input582.input575
input573=input582.input573
input572=input582.input572
input567=input582.input567
input566=input582.input566
input564=input582.input564
input563=input582.input563
input563.IDENTITY='MeloNX-input583-identity.json'
_expected582=input582.expected

def expected():
 """The 582 receipt, computed on the delivered 582 tree, carried by build 583."""
 with delivery.as_582():receipt=_expected582()
 assert receipt['build']==int(delivery.d582.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
# The 563 to 582 validators compare the embedded receipt with their module's expected().
for module in (input563,input564,input566,input567,input572,input573,input575,input576,input577,input579,input581,input582):
 module.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 with delivery.as_582():result=input582.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build583CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
