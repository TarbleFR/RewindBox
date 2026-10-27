#!/usr/bin/env python3
"""Bind the 564 MeloNX engine claims (876a087: texture pool, bounded engine journal, crash record) to private IPA566.

566 replaces the 564 engine with the one of 86c2b4d, which keeps every 564
engine change. The 565 receipt of the 564 engine (its engine, run and test
receipts, with the 565 Core) is checked unchanged on the delivered 565 tree
with the 564 engine's evidence, against derived_ipa(): this IPA with the 564
engine entries, which must then carry the 564 engine as its run packaged it
and, apart from those entries, the 563-equivalent bytes. The receipt names
build 566.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxjit566_delivery as delivery
import validate_melonx_texture565_ipa as texture565

texture564=texture565.texture564
texture564.IDENTITY='MeloNX-texture566-identity.json'
_expected565=texture565.expected

def expected():
 """The 564 engine receipt carried by build 565, computed on the delivered 565 tree with its engine, carried by build 566."""
 with delivery.as_565_engine():receipt=_expected565()
 assert receipt['build']==int(delivery.d565.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_565_engine():result=texture565.validate(derived,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated565EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest())

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
