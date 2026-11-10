#!/usr/bin/env python3
"""Bind the 564 MeloNX engine claims (876a087: texture pool, bounded engine journal, crash record) to private IPA572.

572 replaces the 566 engine with the one of 8cc2348, which keeps every 564
engine change. The 567 receipt of the 564 engine claims is checked unchanged
on the delivered 567 tree with the 566 engine's evidence, against
derived_ipa(): this IPA with the 566 engine entries (and, through the 566
recipe, the 565 tree with the 564 engine's evidence against its own derived
IPA). The receipt names build 572.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxjit572_delivery as delivery
import validate_melonx_texture567_ipa as texture567

texture564=texture567.texture564
texture564.IDENTITY='MeloNX-texture572-identity.json'
_expected567=texture567.expected

def expected():
 """The 564 engine receipt carried by build 567, computed on the delivered 567 tree with its engine, carried by build 572."""
 with delivery.as_567_engine():receipt=_expected567()
 assert receipt['build']==int(delivery.d567.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_567_engine():result=texture567.validate(derived,build)
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
