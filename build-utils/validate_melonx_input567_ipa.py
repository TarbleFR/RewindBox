#!/usr/bin/env python3
"""Bind the MeloNX keyboard and L3/R3 host files (9b40129) and their host run to private IPA567.

567 ships the 566 MeloNX host and engine byte for byte and swaps only the
RPCS3 Core. The 566 claims are checked unchanged on the delivered 566 tree;
the receipt names build 567 and the 567 Core.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell567_delivery as delivery
import validate_melonx_input566_ipa as input566

input564=input566.input564
input563=input566.input563
input563.IDENTITY='MeloNX-input567-identity.json'
_expected566=input566.expected

def expected():
 """The 566 receipt, computed on the delivered 566 tree, carried by build 567 with the 567 Core."""
 with delivery.as_566():receipt=_expected566()
 assert receipt['build']==int(delivery.d566.BUILD)
 return dict(receipt,build=int(delivery.BUILD),rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,
  rpcCore565Source=delivery.CORE565_SOURCE,rpcCore565Run=delivery.CORE565_RUN)
# The 563, 564 and 566 validators compare the embedded receipt with their module's expected().
input563.expected=expected
input564.expected=expected
input566.expected=expected

def embed(app):
 input563.embed(app)

def validate(ipa,build):
 with delivery.as_566():result=input566.validate(ipa,build)
 return dict(result,build567CoreOnly=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
