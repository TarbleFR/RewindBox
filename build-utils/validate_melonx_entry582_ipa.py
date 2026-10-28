#!/usr/bin/env python3
"""Bind the 582 MeloNX engine (6d8929d, e72895b and e55ca25: a LightningJit translation unit ends where another translation already starts, unless that splits a loop around it or a short forward skip; guest code read a page at a time; a unit ends before an unmapped page) with its engine run, and the Switch discovery fix of 32a0da6/63fdb7e, to private IPA582.

The engine run built and tested exactly the pinned engine inputs: the 572
engine checks again (session ownership, display, simulator runtime, texture
pool, journal, decoder with the switch case) and the decoder probe's 582
cases, with the entry stops and the page reader in the adapted source it
compiled. The signed IPA must carry that engine as package_runtime packaged
it (identity, compiled payload fingerprint, every 572 export, the journal
literals) and, apart from the engine entries, the bytes of derived_ipa(),
which the inherited MeloNX validators check. The discovery fix is compiled
into the application by this delivery from the sources 32a0da6 and 63fdb7e
committed: the MeloNX bridge's cancellable fingerprint channel and the
scanner that uses it. No game or iPhone runs here; no launch time, compile
time or FPS gain is claimed on a device.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxentry582_delivery as delivery
import melonxentry582_tree as tree

IDENTITY='MeloNX-entry582-identity.json'
# Dart constants of the scanner (the bridge method it calls, its digest check) and the bridge's
# own literals of the fingerprint channel (queue label, method, error code); each is longer than
# a Swift small string, so it is stored as bytes.
DART_MARKERS=['cancelFingerprint','Invalid MeloNX fingerprint']
BRIDGE_MARKERS=['com.neogamelab.neostation.melonx.fingerprint','cancelFingerprint','fingerprintFailed']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 return dict(build=int(delivery.BUILD),engineSource=delivery.MELONX_SOURCE,engineRun=delivery.MELONX_RUN,
  engineArtifact=delivery.MELONX_ARTIFACT[0],engineCommits=tree.ENGINE_COMMITS,engine577Source=delivery.MELONX577_SOURCE,
  engine577Run=delivery.MELONX577_RUN,rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,
  evidence=delivery.engine_evidence(),inputs={p:sha(p) for p in sorted(tree.FIX582)},
  switchDiscovery={p:sha(p) for p in sorted(tree.APP582)},switchDiscoverySources=tree.APP582,
  switchDiscoveryCommits=tree.APP_COMMITS,exports=delivery.EXPORTS582,coreText=delivery.CORE_TEXT582,
  physicalDeviceTested=False,gameTested=False,launchTimeMeasured=False,fpsGainMeasured=False)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in DART_MARKERS:assert text.encode() in dart or text.encode('utf-16le') in dart,text
  bridge=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  for text in BRIDGE_MARKERS:assert text.encode() in bridge,text
 engine=delivery.validate_engine_ipa(ipa)
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  engine=engine,compiledDartMarkers=DART_MARKERS,compiledBridgeMarkers=BRIDGE_MARKERS,physicalDeviceTested=False,
  gameTested=False,launchTimeMeasured=False,fpsGainMeasured=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
