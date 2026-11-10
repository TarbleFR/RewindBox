#!/usr/bin/env python3
"""Bind the 566 MeloNX engine claims (86c2b4d: LightningJit translation units, GC gen2 budget) to private IPA572.

572 replaces the 566 engine with the one of 8cc2348, which keeps every 566
engine change. The 567 receipt of the 566 engine (its engine, run and decoder
receipt, with the 567 Core) is checked unchanged on the delivered 567 tree
with the 566 engine's evidence, against derived_ipa(): this IPA with the 566
engine entries, which must then carry the 566 engine as its run packaged it
and, apart from those entries, the 565-equivalent bytes. The receipt names
build 572.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxjit572_delivery as delivery
import validate_melonx_jit567_ipa as jit567

jit566=jit567.jit566
jit566.IDENTITY='MeloNX-jit572-identity.json'
_expected567=jit567.expected

def expected():
 """The 566 engine receipt carried by build 567, computed on the delivered 567 tree with its engine, carried by build 572."""
 with delivery.as_567_engine():receipt=_expected567()
 assert receipt['build']==int(delivery.d567.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
jit566.expected=expected

def embed(app):
 jit566.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_567_engine():result=jit567.validate(derived,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated567EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest())

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
