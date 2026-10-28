#!/usr/bin/env python3
"""Bind the 566 MeloNX engine receipt (decoder units, GC budget) carried by build 581 to private IPA582.

582 replaces the 577 engine with the one of e55ca25, which keeps every 566
and 572 decoder change and adds the 582 entry stops on top of them. The 581
receipt of the 566 engine is checked unchanged on the delivered 581 tree
with the 577 engine's evidence, against derived_ipa(): this IPA with the
577 engine entries; the 581 to 572 validators derive their own views in
turn. The receipt names build 582. No game or iPhone runs here; no FPS gain
is claimed.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxentry582_delivery as delivery
import validate_melonx_jit581_ipa as jit581

jit566=jit581.jit566
jit566.IDENTITY='MeloNX-jit582-identity.json'
_expected581=jit581.expected

def expected():
 """The 566 engine receipt carried by build 581, computed on the delivered 581 tree with its engine, carried by build 582."""
 with delivery.as_581_engine():receipt=_expected581()
 assert receipt['build']==int(delivery.d581.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
jit566.expected=expected

def embed(app):
 jit566.embed(app)

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_581_engine():result=jit581.validate(derived,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated581EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest())

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
