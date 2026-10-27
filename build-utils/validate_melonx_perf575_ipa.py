#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the 572 engine (8cc2348) to private IPA575.

575 keeps every MeloNX file of 573 (host and engine, those of 572) and swaps
only the RPCS3 Core, which the MeloNX checks do not read. The 573 validator
(and the 572 to 549 chain under it) therefore runs unchanged on the
delivered 573 tree (as_573 in rpcs3cell575_delivery), against this IPA. The
embedded identity is the 558 receipt under its 575 name, naming build 575.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell575_delivery as delivery575
import validate_melonx_perf573_ipa as perf573

threading=perf573.threading
threading.IDENTITY='MeloNX-perf575-identity.json'
_expected573=perf573.expected

def expected():
 """The 558 receipt carried by build 573, computed on the delivered 573 tree, carried by build 575."""
 with delivery575.as_573():receipt=_expected573()
 assert receipt['build']==int(delivery575.d573.BUILD)
 return dict(receipt,build=int(delivery575.BUILD))
threading.expected=expected

def embed(app):
 with delivery575.as_573():perf573.embed(app)

def validate(ipa,build):
 with delivery575.as_573():result=perf573.validate(ipa,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),build575CoreSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery575.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
