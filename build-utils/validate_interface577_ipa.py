#!/usr/bin/env python3
"""Bind the 48b9865 interface and controller files, their tests and their compiled markers to private IPA577.

48b9865 (maintainer request, 27 October 2026): the "Show system bubbles"
option of Settings › Themes › User interface (twelve languages), the menu
taking the controller back once a game session ends (the gamepads bridge
reinstalls its handler, the RPCS3 input bridge restores the one it replaced)
and the latched `⋯` menu of the playlists.

--record-tests (checks job) runs their analyzer-clean tests on the pinned 577
tree and writes build/delivery/interface577-tests.json, bound to the hashes
of every 577 file. --embed checks that receipt against the pinned tree and
embeds the identity; the signed IPA must carry it, name build 577 and contain
the compiled Dart and Objective-C markers of the change. No iPhone, game or
physical controller runs here.
"""
import argparse,hashlib,json,os,plistlib,re,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import interface577_delivery as delivery
import interface577_tree as tree

IDENTITY='Interface-controller577-identity.json'
RECEIPT=ROOT/'build/delivery/interface577-tests.json'
FLUTTER='3.47.2'
DART_TESTS=['test/select_layer_latch_test.dart','test/system_bubbles_option_test.dart',
 'test/ios_gamepad_navigation_test.dart','test/interface_style_settings_test.dart','test/interface_style_locale_test.dart',
 'test/interface_style_screen_test.dart','test/console_bubble_transition_test.dart','test/system_bubble_render_test.dart',
 'test/airplay_navigation_test.dart','test/navigation512_switch_test.dart','test/gamepad_navigation_manager_test.dart',
 'test/select_tap_test.dart','test/library_reader_gamepad_test.dart']
PYTHON_TESTS=['test/game_audio_handoff_test.py','test/game_close_status_test.py']
# Literal Dart constants survive AOT compilation (Latin-1 one byte per
# character, others UTF-16): the preference field, the selection marker key,
# the translated option, the reclaim channel call and its log line.
DART_MARKERS=['showSystemBubbles','system-selection-marker','Afficher les bulles des systèmes','顯示系統泡泡',
 'reclaimGamepads','Controller input returned to the menu.']
# The RPCS3 input bridge keeps the handler it replaces (Objective-C property metadata).
BRIDGE='Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge'
BRIDGE_MARKERS=[b'previousExtendedHandler',b'previousMicroHandler']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def inputs():
 return {p:sha(p) for p in sorted(tree.FIX577)}

def record_tests():
 """Runs the 577 tests on the pinned tree; nothing is recorded unless all pass."""
 tree.verify()
 version=subprocess.check_output(['flutter','--version','--machine'],cwd=ROOT,text=True)
 assert json.loads(version[version.index('{'):])['frameworkVersion']==FLUTTER
 log=subprocess.run(['flutter','test','--no-pub','--concurrency=1','--reporter','expanded',*DART_TESTS],cwd=ROOT,
  text=True,capture_output=True)
 sys.stdout.write(log.stdout[-4000:]);sys.stderr.write(log.stderr[-4000:])
 assert log.returncode==0,'577 Dart tests failed'
 summary=re.findall(r'\+(\d+)(?: ~(\d+))?: All tests passed!',log.stdout)
 assert summary,'no test summary'
 passed=int(summary[-1][0])
 for test in PYTHON_TESTS:subprocess.run([sys.executable,test],cwd=ROOT,check=True)
 receipt=dict(result='passed',source=tree.SOURCE577,flutter=FLUTTER,dartTests=DART_TESTS,pythonTests=PYTHON_TESTS,
  passedDartTests=passed,inputs=inputs(),physicalDeviceTested=False,controllerTested=False)
 RECEIPT.parent.mkdir(parents=True,exist_ok=True);RECEIPT.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')
 print(json.dumps(receipt,indent=2,ensure_ascii=False))

def tests():
 local=json.loads(RECEIPT.read_bytes())
 assert local['result']=='passed' and local['source']==tree.SOURCE577 and local['flutter']==FLUTTER
 assert local['dartTests']==DART_TESTS and local['pythonTests']==PYTHON_TESTS and local['passedDartTests']>=60
 assert local['inputs']==inputs(),'577 test receipt is not bound to the pinned files'
 assert local['physicalDeviceTested'] is False and local['controllerTested'] is False
 return local

def expected():
 return dict(build=int(delivery.BUILD),source=tree.SOURCE577,hostTree=delivery.HOST_TREE,
  rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,melonxSource=delivery.MELONX_SOURCE,
  melonxRun=delivery.MELONX_RUN,replaced=tree.REPLACED,shipped=tree.SHIPPED577,tests=tests(),
  dartMarkers=DART_MARKERS,bridgeMarkers=[m.decode() for m in BRIDGE_MARKERS],
  physicalDeviceTested=False,controllerTested=False,gameTested=False)

def contains(data,text):
 forms=[text.encode('utf-8'),text.encode('utf-16le')]
 try:forms.append(text.encode('latin-1'))
 except UnicodeEncodeError:pass
 return any(form in data for form in forms)

def inspect(dart,bridge):
 for text in DART_MARKERS:assert contains(dart,text),text
 for marker in BRIDGE_MARKERS:assert marker in bridge,marker

def embed(app):
 receipt=expected()
 inspect((app/'Frameworks/App.framework/App').read_bytes(),(app/BRIDGE).read_bytes())
 (app/IDENTITY).write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  inspect(z.read(root+'Frameworks/App.framework/App'),z.read(root+BRIDGE))
  assert any(n.startswith(root+'Frameworks/gamepads_darwin.framework/') for n in z.namelist()),'gamepads bridge not embedded'
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  compiledDartMarkers=DART_MARKERS,compiledBridgeMarkers=receipt['bridgeMarkers'],physicalDeviceTested=False,
  controllerTested=False,gameTested=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--record-tests',action='store_true')
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.record_tests:record_tests()
 elif a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
