#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the 572 engine (8cc2348) to private IPA572.

572 keeps every MeloNX host file of 567 and swaps only the engine. The 567
validator (and the 566, 565, 564, 563, 562, 558, 553 parity and 549 chain
under it) therefore runs unchanged on the delivered 567 tree with the 566
engine's evidence (as_567_engine in melonxjit572_delivery), against
derived_ipa(): this IPA with the engine entries package_runtime writes for the
566 engine on that tree, every other entry byte for byte; the 566 validator
under it derives its own 565-equivalent. The actual IPA must carry the 572
engine, packaged from its own run, and differ from the derived one only in
those entries. The embedded identity is the 558 receipt under its 572 name,
naming build 572.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxjit572_delivery as delivery572
import validate_melonx_perf567_ipa as perf567

threading=perf567.threading
threading.IDENTITY='MeloNX-perf572-identity.json'
_expected567=perf567.expected

def expected():
 """The 558 receipt carried by build 567, computed on the delivered 567 tree with its engine, carried by build 572."""
 with delivery572.as_567_engine():receipt=_expected567()
 assert receipt['build']==int(delivery572.d567.BUILD)
 return dict(receipt,build=int(delivery572.BUILD))
threading.expected=expected

def embed(app):
 with delivery572.as_567_engine():perf567.embed(app)

def validate(ipa,build):
 derived=delivery572.derived_ipa(ipa)
 with delivery572.as_567_engine():result=perf567.validate(derived,build)
 engine=delivery572.validate_engine_ipa(ipa)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated567EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine572=engine,build572EngineSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery572.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
