#!/usr/bin/env python3
"""Bind the 576 MeloNX engine receipt (301e0f8: shader-cache warm-ups off the game's start, attachment-less framebuffers sized to the viewports) carried by build 581 to private IPA582.

582 replaces the 577 engine with the one of e55ca25, which keeps the 576
warm-up and framebuffer changes. The 581 receipt is computed on the
delivered 581 tree with the 577 engine's evidence; on this IPA, derived_ipa()
(the 577 engine entries) gives the 581-equivalent, and the 577 recipe's
576-equivalent of it must carry the 576 engine as the 576 recipe validated
it. The receipt names build 582. No game or iPhone runs here; no launch time
or FPS gain is claimed.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxentry582_delivery as delivery
import validate_melonx_warm581_ipa as warm581

IDENTITY='MeloNX-warm582-identity.json'

def expected():
 with delivery.as_581_engine():receipt=warm581.expected()
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
 d577=d581.d577
 with delivery.as_581_engine(),d581.as_579(),d581.d579.as_577():
  derived576=d577.derived_ipa(derived)
  with d577.as_576_engine():engine=d577.d576.validate_engine_ipa(derived576)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  validated581EquivalentSHA256=hashlib.sha256(derived.read_bytes()).hexdigest(),
  validated576EquivalentSHA256=hashlib.sha256(derived576.read_bytes()).hexdigest(),engine576=engine,
  physicalDeviceTested=False,gameTested=False,launchTimeMeasured=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
