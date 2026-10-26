#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), its engine (8f83748) and iPhone host (e2c9437) to private IPA558.

The 553 parity validator and its 549 chain (544 close, 540 pipeline, 539
journal, 537 audio, 533 memory, 518 presentation) run against the 558 engine
and host on the pinned 558 tree, as 553 rebound 549: the MeloNX product set
gains the 558 files, the frontend receipt is the 558 MeloNX re-run on the
pinned tree (the 537 import inputs that 557 changed are bound to the 557
receipt), and the engine evidence is the 558 one (its RAM graph proof is the
553 host's, whose inputs are unchanged). The receipts bound to the delivered
557 tree are checked there (as_557 in melonxperf558_delivery). On top, the
signed IPA must carry the 558 claims: the audio pacing export in the engine
and the host, the per-second [MeloNX:perf] journal, the emulation-priority
choice and its strings, and the Dart log fixes.
"""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxperf558_delivery as delivery558
import melonxperf558_tree as tree558
d553=delivery558.d553
# Rebind before the 553 validator wires the 549 chain to these values.
for name in ('MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','HOST_SOURCE','HOST_RUN','HOST_ARTIFACT'):
 setattr(d553,name,getattr(delivery558,name))
d553.PRODUCT=d553.PRODUCT|delivery558.MELONX558
d553.validate_melonx_rerun=delivery558.validate_melonx_rerun558
d553.engine_evidence=delivery558.engine_evidence
import validate_melonx_parity553_ipa as parity
from verify_ipa import macho

threading=parity.threading
threading.IDENTITY='MeloNX-perf558-identity.json'
audio=parity.audio
EXPORTS=['_neostation_melonx_audio_pacing']
# Host literals longer than Swift's 15-byte inline strings, so stored as bytes.
HOST_MARKERS=[b'neostation_melonx_audio_pacing',b'RewindBox.MeloNX.Perf',b'[MeloNX:perf] begin: every ',
 b'[MeloNX:perf] end: ',b' late DSP episodes (',b'RewindBoxMeloNXEmulationPriority',b'; engine thread QoS ',
 b'emulationPriorityPreference',b'Emulation priority',b'Default (MeloNX app)',b'Applies when the next game starts.',
 'Priorité de l’émulation'.encode('utf-8')]
CORE_TEXT=['Audio pacing snapshot needs']
DART_MARKERS=['Log file copy is incomplete','Migration aborted: the log file could not be moved (','setvbuf']

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def perf_expected():
 local=delivery558.validate_perf_tests()
 return dict(build=int(delivery558.BUILD),source=delivery558.SOURCE558,hostTree=delivery558.HOST_TREE,
  melonxSource=delivery558.MELONX_SOURCE,melonxRun=delivery558.MELONX_RUN,melonxArtifact=delivery558.MELONX_ARTIFACT[0],
  hostSource=delivery558.HOST_SOURCE,hostRun=delivery558.HOST_RUN,hostArtifact=delivery558.HOST_ARTIFACT[0],
  graphSource=delivery558.HOST_SOURCE553,graphRun=delivery558.HOST_RUN553,
  melonxChanged=sorted(delivery558.MELONX558),dartChanged=sorted(delivery558.DART558),replaced=tree558.REPLACED,
  inputs={p:sha(p) for p in sorted(delivery558.SHIPPED558)},exports=delivery558.EXPORTS558,
  tests={k:v.get('passed') for k,v in local['tests'].items()},
  fullSuite={k:local['fullSuite'][k] for k in ('passed','failed','passed557','failed557')},
  productTrees=tree558.product_trees(),productTrees557=tree558.product_trees_557(),
  measurementOnly=True,stutterFixClaimed=False,physicalDeviceTested=False)

_expected553=threading.expected
def expected():
 return dict(_expected553(),build=int(delivery558.BUILD),perf558=perf_expected())
threading.expected=expected

def embed(app):
 parity.embed(app)

def validate(ipa,build):
 result=parity.validate(ipa,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(z.read(root+threading.IDENTITY))['perf558']
  identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert identity['host']==delivery558.MELONX_SOURCE
  for name in delivery558.EXPORTS558:assert name in identity['exports'],name
  for p in sorted(delivery558.ENGINE558):
   if p in identity['adaptations']:assert identity['adaptations'][p]==sha(p),p
  for p in ('native/melonx/EmbeddedAudioPacing.cs','native/melonx/EmbeddedAudioPacingExport.cs',
            'build-utils/melonx/adapt_audio_pacing.py','build-utils/melonx/prepare_embedded.py'):
   assert identity['adaptations'][p]==sha(p),p
  core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  symbols=set(macho(core)['definedSymbols'])
  for name in EXPORTS:assert name in symbols,name
  for text in CORE_TEXT:assert audio.contains(core,text),text
  host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  for marker in HOST_MARKERS:assert marker in host,marker
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in DART_MARKERS:assert audio.contains(dart,text),text
 return dict(result,perf558=receipt,compiledMeasurementVerified=True,measurementOnly=True,
  stutterFixClaimed=False,physicalDeviceTested=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery558.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
