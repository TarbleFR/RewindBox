#!/usr/bin/env python3
"""Bind the 566 MeloNX engine claims (86c2b4d: LightningJit translation units, GC gen2 budget) to private IPA577.

577 replaces the 576 engine with the one of cfa5116, which keeps every 566
and 572 engine change (its GC change adds the memory-load threshold to the
566 gen2 budget). The 576 receipt of the 566 engine is checked unchanged on
the delivered 576 tree with the 576 engine's evidence, against
derived_ipa(): this IPA with the 576 engine entries; the 576 to 572
validators derive their own views in turn. The receipt names build 577.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxsync577_delivery as delivery
import validate_melonx_jit576_ipa as jit576

jit566=jit576.jit566
jit566.IDENTITY='MeloNX-jit577-identity.json'
_expected576=jit576.expected

def expected():
 """The 566 engine receipt carried by build 576, computed on the delivered 576 tree with its engine, carried by build 577."""
 with delivery.as_576_engine():receipt=_expected576()
 assert receipt['build']==int(delivery.d576.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
jit566.expected=expected

def embed(app):
 jit566.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_576_engine():result=jit576.validate(derived,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated576EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest())

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
