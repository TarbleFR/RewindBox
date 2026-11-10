#!/usr/bin/env python3
"""Bind the 577 MeloNX engine receipt (kernel wakeups, GC memory-load threshold, code arena request, per-title pipeline cache; no FFT trace), its engine run and the controller relay source, carried by build 585, to private IPA586.

586 replaces the 582 engine with the one of ac16f1c and adds the Cheats &
Enhancements page and catalogues. The 585 receipt is computed on the
delivered 585 tree with the 582 engine's evidence; the 585 validator then
runs on derived_ipa() (this IPA with the 582 engine entries) with this
build's receipt in place of its own, and derives its own views in turn.
The receipt names build 586. No game or iPhone runs here; no launch time
or FPS gain is claimed.
"""
import argparse,contextlib,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rewind586_delivery as delivery
import validate_melonx_sync585_ipa as sync585

IDENTITY='MeloNX-sync586-identity.json'
_expected585=sync585.expected
# The 582 validator reads the embedded receipt by its module's IDENTITY and compares it with expected().
sync582=sync585.sync582

def expected():
 with delivery.as_585_engine():receipt=_expected585()
 assert receipt['build']==int(delivery.d585.BUILD)
 return dict(receipt,build=int(delivery.BUILD),engine586Source=delivery.MELONX_SOURCE,engine586Run=delivery.MELONX_RUN)
sync582.IDENTITY=IDENTITY
sync582.expected=expected

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 derived=delivery.derived_ipa(ipa)
 with delivery.as_585_engine():result=sync585.validate(derived,build)
 return dict(result,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
  validated585EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),build586=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
