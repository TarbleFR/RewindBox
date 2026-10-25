#!/usr/bin/env python3
"""Bind the compiled e12f1d4 interface to private IPA550, its exact sources and its pinned product tree."""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import liquidglass550_delivery as delivery

IDENTITY='LiquidGlass-ui550-identity.json'
# Literal Dart constants survive AOT compilation (interpolated keys do not);
# non-Latin-1 constants are stored as UTF-16. Each names a compiled part of
# the interface: the preference key and settings screen, the preview and its
# working controls, the one-line header's clock, the LB/RB glyphs, the
# floating side menu, the NeoStation style and translated titles.
DART_MARKERS=['rewindbox_interface_style_v1','interface-style-','interface-style-unsaved','interface-style-preview-tabs',
 'interface-style-preview-style-chip','interface-style-preview-revert','interface-style-preview-menu',
 'header-clock','main-menu-tab-bumpers','side-menu-rail','main-menu-tab-indicator','glass-segment-thumb',
 'neoStation','showSideMenuPanel','focusIndicator','Interface utilisateur','Pastille pleine','Couleurs et focus','狀態列']
# The native catalogue pages read the same preference; NeoStation keeps them opaque.
NATIVE_MARKERS=['flutter.rewindbox_interface_style_v1','liquidGlass','neoStation']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 local=delivery.validate_interface()
 ui=sorted(delivery.shipped_interface())
 return dict(source=local['source'],build=int(delivery.BUILD),hostTree=delivery.HOST_TREE,
  rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,melonxSource=delivery.MELONX_SOURCE,
  interfaceChanged=ui,inputs=local['inputs'],productTrees=local['productTrees'],
  tests=local['tests'],passedTests=local['passedTests'],analyzerIssues=local['analyzerIssues'],
  physicalDeviceTested=False,interfaceDeviceReviewed=False)

def contains(data,text):
 # Dart stores Latin-1 constants one byte per character, others as UTF-16.
 forms=[text.encode('utf-8'),text.encode('utf-16le')]
 try:forms.append(text.encode('latin-1'))
 except UnicodeEncodeError:pass
 return any(form in data for form in forms)

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
  for framework in ('neo_cheat_catalog','neo_texture_catalog'):
   binary=z.read(root+f'Frameworks/{framework}.framework/{framework}')
   for marker in NATIVE_MARKERS:assert contains(binary,marker),(framework,marker)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),identity=receipt,
  compiledDartMarkers=DART_MARKERS,compiledNativeMarkers=NATIVE_MARKERS,physicalDeviceTested=False,interfaceDeviceReviewed=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
