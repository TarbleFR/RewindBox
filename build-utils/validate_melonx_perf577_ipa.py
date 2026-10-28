#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), the 558 host (e2c9437) and the engine of 576 to private IPA577.

577 swaps the engine (301e0f8 -> cfa5116) and changes one MeloNX host file
(the controller relay, which these checks do not read). The 576 validator
(and the 575 to 549 chain under it) therefore runs unchanged on the
delivered 576 tree with the 576 engine's evidence (as_576_engine in
melonxsync577_delivery), against derived_ipa(): this IPA with the 576 engine
entries, which must then carry the 576 engine as its run packaged it and,
apart from those entries, the bytes of this IPA. The embedded identity is
the 558 receipt under its 577 name, naming build 577.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxsync577_delivery as delivery577
import validate_melonx_perf576_ipa as perf576

threading=perf576.threading
threading.IDENTITY='MeloNX-perf577-identity.json'
_expected576=perf576.expected

def expected():
 """The 558 receipt carried by build 576, computed on the delivered 576 tree with its engine, carried by build 577."""
 with delivery577.as_576_engine():receipt=_expected576()
 assert receipt['build']==int(delivery577.d576.BUILD)
 return dict(receipt,build=int(delivery577.BUILD))
threading.expected=expected

def embed(app):
 with delivery577.as_576_engine():perf576.embed(app)

def validate(ipa,build):
 derived=delivery577.derived_ipa(ipa)
 with delivery577.as_576_engine():result=perf576.validate(derived,build)
 engine=delivery577.validate_engine_ipa(ipa)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated576EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine577=engine,build577EngineSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery577.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
