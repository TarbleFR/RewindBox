#!/usr/bin/env python3
"""Bind the 564 MeloNX engine claims (texture pool, engine journal) to private IPA576.

576 replaces the 572 engine with the one of 301e0f8, which keeps every 564
engine change. The 575 receipt of the 564 engine is checked unchanged on the
delivered 575 tree with the 572 engine's evidence, against derived_ipa():
this IPA with the 572 engine entries. The receipt names build 576.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxwarm576_delivery as delivery
import validate_melonx_texture575_ipa as texture575

texture564=texture575.texture564
texture564.IDENTITY='MeloNX-texture576-identity.json'
_expected575=texture575.expected

def expected():
 """The 564 engine receipt carried by build 575, computed on the delivered 575 tree with its engine, carried by build 576."""
 with delivery.as_575_engine():receipt=_expected575()
 assert receipt['build']==int(delivery.d575.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
texture564.expected=expected

def embed(app):
 texture564.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_575_engine():result=texture575.validate(derived,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated575EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest())

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
