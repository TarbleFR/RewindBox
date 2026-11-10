#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the engine of 575 to private IPA576.

576 keeps every MeloNX host file of 575 and swaps only the engine (572 ->
301e0f8). The 575 validator (and the 573 to 549 chain under it) therefore
runs unchanged on the delivered 575 tree with the 572 engine's evidence
(as_575_engine in melonxwarm576_delivery), against derived_ipa(): this IPA
with the 572 engine entries, which must then carry the 572 engine as its run
packaged it and, apart from those entries, the bytes of this IPA. The
embedded identity is the 558 receipt under its 576 name, naming build 576.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxwarm576_delivery as delivery576
import validate_melonx_perf575_ipa as perf575

threading=perf575.threading
threading.IDENTITY='MeloNX-perf576-identity.json'
_expected575=perf575.expected

def expected():
 """The 558 receipt carried by build 575, computed on the delivered 575 tree with its engine, carried by build 576."""
 with delivery576.as_575_engine():receipt=_expected575()
 assert receipt['build']==int(delivery576.d575.BUILD)
 return dict(receipt,build=int(delivery576.BUILD))
threading.expected=expected

def embed(app):
 with delivery576.as_575_engine():perf575.embed(app)

def validate(ipa,build):
 derived=delivery576.derived_ipa(ipa)
 with delivery576.as_575_engine():result=perf575.validate(derived,build)
 engine=delivery576.validate_engine_ipa(ipa)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated575EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine576=engine,build576EngineSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery576.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
