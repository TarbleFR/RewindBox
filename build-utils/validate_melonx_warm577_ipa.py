#!/usr/bin/env python3
"""Bind the 576 MeloNX engine receipt (301e0f8: shader-cache warm-ups off the game's start, attachment-less framebuffers sized to the viewports) to private IPA577.

577 replaces the 576 engine with the one of cfa5116, which keeps both 576
engine changes and removes the temporary FFT boot trace. The 576 receipt of
the 576 engine (engine run, adapted source, engine inputs) is computed on the
delivered 576 tree with the 576 engine's evidence, and derived_ipa() (this
IPA with the 576 engine entries) must carry that engine as package_runtime
packaged it and, apart from the engine entries, the bytes of the 576
recipe's derived IPA. The receipt names build 577. No game or iPhone runs
here; no launch time or FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxsync577_delivery as delivery
import validate_melonx_warm576_ipa as warm576

IDENTITY='MeloNX-warm577-identity.json'

def expected():
 with delivery.as_576_engine():receipt=warm576.expected()
 assert receipt['build']==int(delivery.d576.BUILD)
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
 with delivery.as_576_engine():engine=delivery.d576.validate_engine_ipa(derived)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  validated576EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),engine576=engine,
  physicalDeviceTested=False,gameTested=False,launchTimeMeasured=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
