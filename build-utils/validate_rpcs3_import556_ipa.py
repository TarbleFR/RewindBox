#!/usr/bin/env python3
"""Bind the RPCS3 library-file import (554) to private IPA556.

556 changes no RPCS3 file: the 554 import receipt is checked on the delivered
554 tree (as_554 in melonxperf556_delivery), its shipped Dart files must keep
their 554 bytes in the pinned 556 tree, and the compiled 556 Dart image must
still hold the constants of the installation prompt and progress.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import melonxperf556_delivery as delivery
import validate_rpcs3_import554_ipa as import554
from validate_liquid_glass550_ipa import contains

IDENTITY='RPCS3-import556-identity.json'

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 with delivery.as_554():previous=import554.expected()
 for p in delivery.SHIPPED554:assert (ROOT/p).read_bytes()==delivery.at(delivery.FIX_SOURCE554,p),p
 return dict(build=int(delivery.BUILD),importFiles=sorted(delivery.SHIPPED554),
  inputs={p:sha(p) for p in sorted(delivery.SHIPPED554)},import554=previous,
  physicalDeviceTested=False,importFixDeviceVerified=False)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2,ensure_ascii=False)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert info['CFBundleVersion']==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in import554.DART_MARKERS:assert contains(dart,text),text
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),identity=receipt,
  compiledDartMarkers=import554.DART_MARKERS,physicalDeviceTested=False,importFixDeviceVerified=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
