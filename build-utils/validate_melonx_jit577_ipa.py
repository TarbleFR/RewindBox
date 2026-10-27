#!/usr/bin/env python3
"""Bind the 566 MeloNX engine claims (LightningJit translation units, GC gen2 budget) to private IPA577.

577 keeps the engine of 576 and changes only Dart interface files, the
gamepads bridge and the RPCS3 input bridge. The 576 validator runs unchanged
on the delivered 576 tree (as_576 in interface577_delivery), which derives its
own 575-equivalent of this IPA in turn. The receipt names build 577.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import interface577_delivery as delivery
import validate_melonx_jit576_ipa as jit576

jit566=jit576.jit566
jit566.IDENTITY='MeloNX-jit577-identity.json'
_expected576=jit576.expected

def expected():
 """The receipt carried by build 576, computed on the delivered 576 tree, carried by build 577."""
 with delivery.as_576():receipt=_expected576()
 assert receipt['build']==int(delivery.d576.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
jit566.expected=expected
jit576.expected=expected

def embed(app):
 with delivery.as_576():jit576.embed(app)

def validate(ipa,build):
 with delivery.as_576():return jit576.validate(ipa,build)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
