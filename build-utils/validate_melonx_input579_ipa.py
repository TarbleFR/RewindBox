#!/usr/bin/env python3
"""Bind the 563 MeloNX input receipt (keyboard, L3/R3 and the controller relay) carried by build 577 to private IPA579.

579 swaps only the RPCS3 Core. The 577 receipt is computed on the delivered
577 tree (as_577 in rpcs3cell579_delivery) and the 577 validator runs
unchanged on this IPA; the receipt names build 579.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell579_delivery as delivery
import validate_melonx_input577_ipa as input577
input576=input577.input576
input575=input577.input575
input573=input577.input573
input572=input577.input572
input567=input577.input567
input566=input577.input566
input564=input577.input564
input563=input577.input563
input563.IDENTITY='MeloNX-input579-identity.json'
_expected577=input577.expected

def expected():
 """The 577 receipt, computed on the delivered 577 tree, carried by build 579."""
 with delivery.as_577():receipt=_expected577()
 assert receipt['build']==int(delivery.d577.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
# The 563 to 577 validators compare the embedded receipt with their module's expected().
for module in (input563,input564,input566,input567,input572,input573,input575,input576,input577):
 module.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 with delivery.as_577():result=input577.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build579CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
