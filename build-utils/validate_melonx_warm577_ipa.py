#!/usr/bin/env python3
"""Bind the 576 MeloNX engine (301e0f8: shader-cache warm-ups off the game's start, attachment-less framebuffers sized to the viewports, temporary FFT boot trace) and its engine run to private IPA577.

577 keeps that engine and changes only Dart interface files, the gamepads
bridge and the RPCS3 input bridge. The 576 validator runs unchanged on the
delivered 576 tree (as_576 in interface577_delivery): the signed IPA must
carry the engine as package_runtime packaged it and, apart from the engine
entries, the bytes of its 575-equivalent. The receipt names build 577. No game
or iPhone runs here; no launch time or FPS gain is claimed.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import interface577_delivery as delivery
import validate_melonx_warm576_ipa as warm576

warm576.IDENTITY='MeloNX-warm577-identity.json'
_expected576=warm576.expected

def expected():
 with delivery.as_576():receipt=_expected576()
 assert receipt['build']==int(delivery.d576.BUILD)
 return dict(receipt,build=int(delivery.BUILD))
warm576.expected=expected

def embed(app):
 with delivery.as_576():warm576.embed(app)

def validate(ipa,build):
 with delivery.as_576():return warm576.validate(ipa,build)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
