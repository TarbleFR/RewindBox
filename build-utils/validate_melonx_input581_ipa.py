#!/usr/bin/env python3
"""Bind the 563 MeloNX input receipt (keyboard, L3/R3 and the controller relay) carried by build 579 to private IPA581.

581 swaps only the RPCS3 Core. The 579 receipt is computed on the delivered
579 tree (as_579 in rpcs3cell581_delivery) and the 579 validator runs
unchanged on this IPA; the receipt names build 581.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell581_delivery as delivery
import validate_melonx_input579_ipa as input579
input577=input579.input577
input576=input579.input576
input575=input579.input575
input573=input579.input573
input572=input579.input572
input567=input579.input567
input566=input579.input566
input564=input579.input564
input563=input579.input563
input563.IDENTITY='MeloNX-input581-identity.json'
_expected579=input579.expected

def expected():
 """The 579 receipt, computed on the delivered 579 tree, carried by build 581."""
 with delivery.as_579():receipt=_expected579()
 assert receipt['build']==int(delivery.d579.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
# The 563 to 579 validators compare the embedded receipt with their module's expected().
for module in (input563,input564,input566,input567,input572,input573,input575,input576,input577,input579):
 module.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 with delivery.as_579():result=input579.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build581CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
