#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the 564 engine (876a087) to private IPA564.

564 keeps every MeloNX host file of 563 and swaps only the engine. The 563
validator (and the 562, 558, 553 parity and 549 chain under it) therefore
runs unchanged on the delivered 563 tree with the 558 engine's evidence
(as_563_engine in melonxtexture564_delivery), against derived_ipa(): this IPA
with the engine entries package_runtime writes for the 558 engine on that
tree, every other entry byte for byte. The actual IPA must carry the 564
engine, packaged from its own run, and differ from the derived one only in
those entries. The embedded identity is the 558 receipt under its 564 name,
naming build 564.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxtexture564_delivery as delivery564
import validate_melonx_perf563_ipa as perf563

threading=perf563.threading
threading.IDENTITY='MeloNX-perf564-identity.json'
_expected563=perf563.expected

def expected():
 """The 558 receipt carried by build 563, computed on the delivered 563 tree with its engine, carried by build 564."""
 with delivery564.as_563_engine():receipt=_expected563()
 assert receipt['build']==int(delivery564.d563.BUILD)
 return dict(receipt,build=int(delivery564.BUILD))
threading.expected=expected

def embed(app):
 with delivery564.as_563_engine():perf563.embed(app)

def validate(ipa,build):
 derived=delivery564.derived_ipa(ipa)
 with delivery564.as_563_engine():result=perf563.validate(derived,build)
 engine=delivery564.validate_engine_ipa(ipa)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated563EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine564=engine,build564EngineSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery564.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
