#!/usr/bin/env python3
"""Bind the 577 MeloNX engine receipt (cfa5116/afd0d4b: kernel wakeups, GC memory-load threshold, Hogwarts code arena request, per-title pipeline cache; no FFT trace) with its engine run, and the controller relay of d1f7b8d, carried by build 581, to private IPA582.

582 replaces the 577 engine with the one of e55ca25, which keeps the four
577 adaptations. The 581 receipt is computed on the delivered 581 tree with
the 577 engine's evidence, and derived_ipa() (this IPA with the 577 engine
entries) must carry that engine as package_runtime packaged it and, apart
from the engine entries, the bytes of the 577 recipe's 576-equivalent. The
receipt names build 582. No game or iPhone runs here; no launch time or FPS
gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxentry582_delivery as delivery
import validate_melonx_sync581_ipa as sync581

IDENTITY='MeloNX-sync582-identity.json'

def expected():
 with delivery.as_581_engine():receipt=sync581.expected()
 assert receipt['build']==int(delivery.d581.BUILD)
 return dict(receipt,build=int(delivery.BUILD))

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
 derived=delivery.derived_ipa(ipa)
 d581=delivery.d581
 with delivery.as_581_engine(),d581.as_579(),d581.d579.as_577():engine=d581.d577.validate_engine_ipa(derived)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  validated581EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine577=engine,
  physicalDeviceTested=False,gameTested=False,launchTimeMeasured=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
