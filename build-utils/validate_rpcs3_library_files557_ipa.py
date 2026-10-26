#!/usr/bin/env python3
"""Bind the library-file fix (557) and the RPCS3 import (554) to private IPA557.

The receipt names the 557 source, the shipped Dart files with their digests,
the tests that ran on the pinned tree and the product trees, and carries the
554 import receipt, checked on the delivered 554 tree (as_554). The compiled
Dart image must hold the constants of the installation prompt and progress
(554) and of the free-space option, the library-file deletion and the
synchronization of rows whose file is gone (557), which exist nowhere else.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
sys.path.insert(0,str(ROOT/'build-utils'))
import rpcs3libraryfiles557_delivery as delivery
import rpcs3libraryfiles557_tree as tree
import validate_rpcs3_import554_ipa as import554
from validate_liquid_glass550_ipa import contains

IDENTITY='RPCS3-library-files557-identity.json'
# Literal Dart constants survive AOT compilation (only the literal parts of an
# interpolated string do); non-Latin-1 constants are stored as UTF-16.
DART_MARKERS=['rpcs3-library-file-free-space','promptFreeSpaceKey','Then delete the original file to free {size}',
 'Supprimer ensuite le fichier d’origine pour libérer {size}','安装后删除原始文件，释放 {size}',
 'rpcs3_library_file_complete','RPCS3 library file: deleted ','its row joined ',
 'RPCS3 library file: deleted the installation of ']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 local=delivery.validate_library_file_tests()
 with delivery.as_554():previous=import554.expected()
 return dict(build=int(delivery.BUILD),source=delivery.FIX_SOURCE557,hostTree=delivery.HOST_TREE,
  rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,
  libraryFilesChanged=sorted(delivery.SHIPPED557),replaced=tree.REPLACED,inputs={p:sha(p) for p in sorted(delivery.SHIPPED557)},
  tests={key:local['tests'][key]['passedTests'] for key,_,_ in delivery.LIBRARY_TESTS},
  fullSuite={k:local['fullSuite'][k] for k in ('passed','failed','passed554','failed554')},
  analyzerIssues=local['analyzerIssues'],productTrees=tree.product_trees(),productTrees554=tree.product_trees_554(),
  import554=previous,physicalDeviceTested=False,libraryFileFixDeviceVerified=False)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2,ensure_ascii=False)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert info['CFBundleVersion']==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in import554.DART_MARKERS+DART_MARKERS:assert contains(dart,text),text
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),identity=receipt,
  compiledDartMarkers=import554.DART_MARKERS+DART_MARKERS,physicalDeviceTested=False,libraryFileFixDeviceVerified=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
