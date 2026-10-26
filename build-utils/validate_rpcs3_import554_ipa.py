#!/usr/bin/env python3
"""Bind the RPCS3 library-file import (554) to private IPA554.

The receipt names the 554 source, the shipped Dart files with their digests,
the tests that ran on the pinned tree and the product trees; the compiled
Dart image must hold the constants of the installation prompt and progress
(their keys and translated titles), which exist nowhere else in the app.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3import554_delivery as delivery
import rpcs3import554_tree as tree
from validate_liquid_glass550_ipa import contains

IDENTITY='RPCS3-import554-identity.json'
# Literal Dart constants survive AOT compilation (interpolated strings do
# not); non-Latin-1 constants are stored as UTF-16.
DART_MARKERS=['rpcs3-library-file-prompt','rpcs3-library-file-install','rpcs3-library-file-cancel',
 'rpcs3-library-file-progress','rpcs3_library_file_prompt','rpcs3_library_file_progress',
 'Install this game in RPCS3?','Installer ce jeu dans RPCS3 ?','Installer et jouer',
 'インストールしてプレイ','安裝並開始遊戲']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 local=delivery.validate_import_tests()
 return dict(build=int(delivery.BUILD),source=delivery.FIX_SOURCE554,hostTree=delivery.HOST_TREE,
  rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,
  importChanged=sorted(delivery.SHIPPED554),inputs={p:sha(p) for p in sorted(delivery.SHIPPED554)},
  tests={key:local['tests'][key]['passedTests'] for key,_,_ in delivery.IMPORT_TESTS},
  analyzerIssues=local['analyzerIssues'],productTrees=tree.product_trees(),productTrees553=tree.product_trees_553(),
  physicalDeviceTested=False,importFixDeviceVerified=False)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert info['CFBundleVersion']==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in DART_MARKERS:assert contains(dart,text),text
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),identity=receipt,
  compiledDartMarkers=DART_MARKERS,physicalDeviceTested=False,importFixDeviceVerified=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
