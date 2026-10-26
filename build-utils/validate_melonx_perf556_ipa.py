#!/usr/bin/env python3
"""Bind the MeloNX measurement build (cfce9f6), its engine (8f83748) and iPhone host (e2c9437) to private IPA556.

The 553 parity validator and its 549 chain (544 close, 540 pipeline, 539
journal, 537 audio, 533 memory, 518 presentation) run against the 556 engine
and host on the pinned 556 tree, as 553 rebound 549: the MeloNX product set
gains the 556 files, the frontend receipt is the 556 MeloNX re-run on the
pinned tree, and the engine evidence is the 556 one (its RAM graph proof is
the 553 host's, whose inputs are unchanged). The receipts bound to the
delivered 554 tree are checked there (as_554 in melonxperf556_delivery). On
top, the signed IPA must carry the 556 claims: the audio pacing export in
the engine and the host, the per-second [MeloNX:perf] journal, the
emulation-priority choice and its strings, and the Dart log fixes.
"""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxperf556_delivery as delivery556
import melonxperf556_tree as tree556
d553=delivery556.d553
# Rebind before the 553 validator wires the 549 chain to these values.
for name in ('MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','HOST_SOURCE','HOST_RUN','HOST_ARTIFACT'):
 setattr(d553,name,getattr(delivery556,name))
d553.PRODUCT=d553.PRODUCT|delivery556.MELONX556
d553.validate_melonx_rerun=delivery556.validate_melonx_rerun556
d553.engine_evidence=delivery556.engine_evidence
import validate_melonx_parity553_ipa as parity
from verify_ipa import macho

threading=parity.threading
threading.IDENTITY='MeloNX-perf556-identity.json'
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
 local=delivery556.validate_perf_tests()
 return dict(build=int(delivery556.BUILD),source=delivery556.SOURCE556,hostTree=delivery556.HOST_TREE,
  melonxSource=delivery556.MELONX_SOURCE,melonxRun=delivery556.MELONX_RUN,melonxArtifact=delivery556.MELONX_ARTIFACT[0],
  hostSource=delivery556.HOST_SOURCE,hostRun=delivery556.HOST_RUN,hostArtifact=delivery556.HOST_ARTIFACT[0],
  graphSource=delivery556.HOST_SOURCE553,graphRun=delivery556.HOST_RUN553,
  melonxChanged=sorted(delivery556.MELONX556),dartChanged=sorted(delivery556.DART556),replaced=tree556.REPLACED,
  inputs={p:sha(p) for p in sorted(delivery556.SHIPPED556)},exports=delivery556.EXPORTS556,
  tests={k:v.get('passed') for k,v in local['tests'].items()},
  fullSuite={k:local['fullSuite'][k] for k in ('passed','failed','passed554','failed554')},
  productTrees=tree556.product_trees(),productTrees554=tree556.product_trees_554(),
  measurementOnly=True,stutterFixClaimed=False,physicalDeviceTested=False)

_expected553=threading.expected
def expected():
 return dict(_expected553(),build=int(delivery556.BUILD),perf556=perf_expected())
threading.expected=expected

def embed(app):
 parity.embed(app)

def validate(ipa,build):
 result=parity.validate(ipa,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(z.read(root+threading.IDENTITY))['perf556']
  identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert identity['host']==delivery556.MELONX_SOURCE
  for name in delivery556.EXPORTS556:assert name in identity['exports'],name
  for p in sorted(delivery556.ENGINE556):
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
 return dict(result,perf556=receipt,compiledMeasurementVerified=True,measurementOnly=True,
  stutterFixClaimed=False,physicalDeviceTested=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery556.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
