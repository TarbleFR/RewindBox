#!/usr/bin/env python3
"""Bind the compiled Liquid Glass interface to private IPA (glass.BUILD) and its exact sources."""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import liquidglass_ui_delivery as glass

IDENTITY='LiquidGlass-ui-identity.json'
# Dart string constants survive AOT compilation; each one names a compiled
# part of the new interface: the preference key, the settings screen, the
# preview, the tab bar options and the translated section titles.
DART_MARKERS=['rewindbox_interface_style_v1','interface-style-preview','interface-style-apply','interface-style-reset',
 'main-menu-capsule-blur','main-menu-tab-indicator','glass-segment-thumb','Interface utilisateur','Liquid Glass','Flottante','使用者介面']
# The native catalogue pages read the same preference and apply system materials.
NATIVE_MARKERS=['flutter.rewindbox_interface_style_v1','liquidGlass']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 local=glass.validate_local_evidence()
 return dict(source=local['source'],build=int(glass.BUILD),hostTree=glass.HOST_TREE,rpcCoreSource=glass.CORE_SOURCE,rpcCoreRun=glass.CORE_RUN,
  hostFixed=sorted(glass.HOST_FIXED),liquidGlassChanged=sorted(glass.ui_changed()),
  inputs={p:sha(p) for p in sorted(set(local['inputs'])|glass.ui_changed())},
  tests=local['tests'],passedTests=local['passedTests'],analyzerIssues=local['analyzerIssues'],
  physicalDeviceTested=False,interfaceDeviceReviewed=False)

def contains(data,text):
 return text.encode('utf-8') in data

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
  for framework,marker in [('neo_cheat_catalog','flutter.rewindbox_interface_style_v1'),('neo_texture_catalog','flutter.rewindbox_interface_style_v1')]:
   binary=z.read(root+f'Frameworks/{framework}.framework/{framework}')
   assert contains(binary,marker),(framework,marker)
   assert contains(binary,'liquidGlass'),(framework,'style')
 return dict(result='passed',build=build,identity=receipt,compiledDartMarkers=DART_MARKERS,compiledNativeMarkers=NATIVE_MARKERS,
  physicalDeviceTested=False,interfaceDeviceReviewed=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(glass.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
