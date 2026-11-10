#!/usr/bin/env python3
"""Bind the 566 MeloNX engine claims (86c2b4d: LightningJit translation units, GC gen2 budget) to private IPA576.

576 replaces the 572 engine with the one of 301e0f8, which keeps every 566
and 572 engine change. The 575 receipt of the 566 engine is checked unchanged
on the delivered 575 tree with the 572 engine's evidence, against
derived_ipa(): this IPA with the 572 engine entries; the 575 to 572
validators derive their own views in turn. The receipt names build 576.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxwarm576_delivery as delivery
import validate_melonx_jit575_ipa as jit575

jit566=jit575.jit566
jit566.IDENTITY='MeloNX-jit576-identity.json'
_expected575=jit575.expected

def expected():
 """The 566 engine receipt carried by build 575, computed on the delivered 575 tree with its engine, carried by build 576."""
 with delivery.as_575_engine():receipt=_expected575()
 assert receipt['build']==int(delivery.d575.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
jit566.expected=expected

def embed(app):
 jit566.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_575_engine():result=jit575.validate(derived,build)
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
