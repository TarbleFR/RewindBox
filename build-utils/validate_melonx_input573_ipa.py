#!/usr/bin/env python3
"""Bind the MeloNX host and keyboard claims (562, 563, 564, 566, 567) to private IPA573.

573 ships the 562 MeloNX host and the 572 engine byte for byte and swaps only
the RPCS3 Core. The 572 claims are checked unchanged on the delivered 572
tree (as_572 in rpcs3cell573_delivery), against this IPA; the 572 validator
derives its 567-equivalent in turn. The receipt names build 573.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell573_delivery as delivery
import validate_melonx_input572_ipa as input572

input567=input572.input567
input566=input572.input566
input564=input572.input564
input563=input572.input563
input563.IDENTITY='MeloNX-input573-identity.json'
_expected572=input572.expected

def expected():
 """The 572 receipt, computed on the delivered 572 tree, carried by build 573."""
 with delivery.as_572():receipt=_expected572()
 assert receipt['build']==int(delivery.d572.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
input563.expected=expected
input564.expected=expected
input566.expected=expected
input567.expected=expected
input572.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 with delivery.as_572():result=input572.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build573CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
