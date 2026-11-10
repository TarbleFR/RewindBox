#!/usr/bin/env python3
"""Bind the 558 MeloNX performance receipt (threading, frame pacing) carried by build 581 to private IPA582.

582 swaps the engine (577 -> e55ca25, whose sources change no file compiled
into the application) and changes the Switch discovery (two Dart files and
the MeloNX bridge), which these checks do not read. The 581 validator (and
the 579 to 549 chain under it) therefore runs unchanged on the delivered 581
tree with the 577 engine's evidence (as_581_engine in
melonxentry582_delivery), against derived_ipa(): this IPA with the 577
engine entries, which must then carry the 577 engine as its run packaged it
and, apart from those entries, the bytes of this IPA. The embedded identity
is the 558 receipt under its 582 name, naming build 582. No game or iPhone
runs here; no FPS gain is claimed.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxentry582_delivery as delivery
import validate_melonx_perf581_ipa as perf581

threading=perf581.threading
threading.IDENTITY='MeloNX-perf582-identity.json'
_expected581=perf581.expected

def expected():
 """The 558 receipt carried by build 581, computed on the delivered 581 tree with its engine, carried by build 582."""
 with delivery.as_581_engine():receipt=_expected581()
 assert receipt['build']==int(delivery.d581.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
threading.expected=expected

def embed(app):
 with delivery.as_581_engine():perf581.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_581_engine():result=perf581.validate(derived,build)
 engine=delivery.validate_engine_ipa(ipa)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated581EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine582=engine,build582EngineSwap=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
