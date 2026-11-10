#!/usr/bin/env python3
"""Bind the MeloNX keyboard and L3/R3 host files (9b40129) and their host run to private IPA563.

563 ships the 562 MeloNX host byte for byte and swaps only the RPCS3 Core,
so the 562 claims hold unchanged; the receipt names build 563 and the 563
Core. The signed IPA must carry the 562 host: the keyboard answer and its journal
texts, the engine callback-registry binding, the L3/R3 menu entry with its
preference key and twelve-language strings (Swift literals longer than 15
bytes, so stored as bytes). The packaged engine (the 558 one) must export the
callback registry the host binds. The embedded identity binds the shipped
562 files, as pinned, to the host run that typechecked them against the
iPhone SDK and ran the UIKit keyboard probe. No game or iPhone runs here.
"""
import argparse,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rpcs3cell563_delivery as delivery
from verify_ipa import macho

IDENTITY='MeloNX-input563-identity.json'
HOST_MARKERS=[b'Unreadable keyboard request; the guest keeps waiting.',
 b'This engine has no callback registry; games cannot ask for text.',
 b'Empty answer: the game keeps its initial text.',b'RegisterCallback',
 b'rewindbox.melonx.stickButton',b'Stick buttons (L3/R3)',
 'Boutons des sticks (L3/R3)'.encode('utf-8'),'テキスト入力'.encode('utf-8'),'Inserimento testo'.encode('utf-8')]
ENGINE_EXPORTS=['_RegisterCallback','_InvokeCallback']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def expected():
 files=sorted(delivery.SHIPPED562|{'build-utils/melonx/ui-strings.json'})
 return dict(build=int(delivery.BUILD),source=delivery.HOST562_SOURCE,hostRun=delivery.HOST562_RUN,
  hostArtifact=delivery.HOST562_ARTIFACT[0],engineSource=delivery.MELONX_SOURCE,engineRun=delivery.MELONX_RUN,
  rpcCoreSource=delivery.CORE_SOURCE,rpcCoreRun=delivery.CORE_RUN,inputs={p:sha(p) for p in files},
  hostEvidence=delivery.host_evidence(),hostMarkers=[m.decode('utf-8') for m in HOST_MARKERS],engineExports=ENGINE_EXPORTS,
  physicalDeviceTested=False,gameTested=False)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2,ensure_ascii=False)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  for marker in HOST_MARKERS:assert marker in host,marker
  core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  symbols=set(macho(core)['definedSymbols'])
  for name in ENGINE_EXPORTS:assert name in symbols,name
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(ipa.read_bytes()).hexdigest(),identity=receipt,
  compiledHostMarkers=receipt['hostMarkers'],engineExports=ENGINE_EXPORTS,physicalDeviceTested=False,gameTested=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
