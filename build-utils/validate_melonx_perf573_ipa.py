#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the 572 engine (8cc2348) to private IPA573.

573 keeps every MeloNX file of 572 (host and engine) and swaps only the
RPCS3 Core, which the MeloNX checks do not read. The 572 validator (and the
567 to 549 chain under it) therefore runs unchanged on the delivered 572
tree (as_572 in rpcs3cell573_delivery), against this IPA. The embedded
identity is the 558 receipt under its 573 name, naming build 573.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell573_delivery as delivery573
import validate_melonx_perf572_ipa as perf572

threading=perf572.threading
threading.IDENTITY='MeloNX-perf573-identity.json'
_expected572=perf572.expected

def expected():
 """The 558 receipt carried by build 572, computed on the delivered 572 tree, carried by build 573."""
 with delivery573.as_572():receipt=_expected572()
 assert receipt['build']==int(delivery573.d572.BUILD)
 return dict(receipt,build=int(delivery573.BUILD))
threading.expected=expected

def embed(app):
 with delivery573.as_572():perf572.embed(app)

def validate(ipa,build):
 with delivery573.as_572():result=perf572.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build573CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery573.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
