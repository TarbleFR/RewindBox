#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the 566 engine (86c2b4d) to private IPA566.

566 keeps every MeloNX host file of 564 and swaps only the engine. The 564
validator (and the 563, 562, 558, 553 parity and 549 chain under it)
therefore runs unchanged on the delivered 564 tree with the 564 engine's
evidence (as_564_engine in melonxjit566_delivery), against derived_ipa(): this
IPA with the engine entries package_runtime writes for the 564 engine on that
tree, every other entry byte for byte; the 564 validator derives its own
563-equivalent from it. The actual IPA must carry the 566 engine, packaged
from its own run, and differ from the derived one only in those entries. The
embedded identity is the 558 receipt under its 566 name, naming build 566.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxjit566_delivery as delivery566
import validate_melonx_perf564_ipa as perf564

threading=perf564.threading
threading.IDENTITY='MeloNX-perf566-identity.json'
_expected564=perf564.expected

def expected():
 """The 558 receipt carried by build 564, computed on the delivered 564 tree with its engine, carried by build 566."""
 with delivery566.as_564_engine():receipt=_expected564()
 assert receipt['build']==int(delivery566.d564.BUILD)
 return dict(receipt,build=int(delivery566.BUILD))
threading.expected=expected

def embed(app):
 with delivery566.as_564_engine():perf564.embed(app)

def validate(ipa,build):
 derived=delivery566.derived_ipa(ipa)
 with delivery566.as_564_engine():result=perf564.validate(derived,build)
 engine=delivery566.validate_engine_ipa(ipa)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated564EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine566=engine,build566EngineSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery566.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
