#!/usr/bin/env python3
"""Bind the Cheats & Enhancements page and catalogues (b451b10 to d0f27cc), the 28 October cheat withdrawal and the origin publication (v2) of the cheat index to private IPA586.

The receipt names every shipped file of the change with its digest (the
catalogue shards and cheat packs, downloaded on demand and never bundled, by
one digest each), its commits, the bundled cheat index (the origin
publication v2), the hosted index it republishes and the withdrawal receipt
that index matches. On the signed IPA: the bundled enhancements index and
the cheat index are the pinned bytes, the cheat index is the v2 index of
VALIDATION.json with the games and chunks of the withdrawal's index, the
compiled Dart holds the page's strings, catalogue constants and the origin
download channel, the cheat catalogue framework holds the withheld sources
and programs it refuses from old caches and the v2 index URL, the packaged
notice is NOTICE.md, and no shard or pack is bundled. No game or iPhone
runs here; no cheat is applied and no origin file is downloaded.
"""
import argparse,gzip,hashlib,json,plistlib,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import rewind586_fast  # noqa: F401  (batched existence checks for the 586 recipe modules)
import rewind586_delivery as delivery
import rewind586_tree as tree

IDENTITY='RewindBox-enhancements586-identity.json'
INDEX='assets/data/enhancements_index.json.gz'
CHEATS='packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'
# The origin publication the app bundles, and the hosted index (v1) it republishes for older builds.
ORIGIN='native/cheats/catalogue/v2/manifest.json.gz'
ORIGIN_VALIDATION='native/cheats/catalogue/v2/VALIDATION.json'
HOSTED='native/cheats/catalogue/manifest.json.gz'
WITHDRAWAL='docs/evidence/source-rights-withdrawal-fps478.json'
# Downloaded on demand from the Claude branch (SHA-256 checked), never bundled.
ON_DEMAND=('native/enhancements/catalogue/shards/','native/cheats/catalogue/packs/','native/cheats/catalogue/v2/packs/')
# Strings of the page (English, German), constants of the catalogue service and the RPCS3 adapter, and
# the channel method and error code of the origin downloads (68e28dd).
DART_MARKERS=['Cheats & Enhancements catalogue','Katalog Cheats & Verbesserungen','rewindbox-enhancements',
              INDEX,'origin_integrity','resolveOriginPack','origin_failed']
# Sources and programs the cheat catalogue refuses from an old cached index (3192f0f); the origin
# channel and the v2 index URL (68e28dd).
NATIVE_MARKERS=['pcsx2_fps478','gabominated_fps478','nethersx2_fps478','nds_fps478','illusion_fps478',
                '27f742c00526dffcd10f3d2b5593ee1a','8652b210de7d0220d9f877e7600bfb8a','dbe94750f58a5e0aebc9010c67f55540',
                'resolveOriginPack',ORIGIN]

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def contains(data,text):
 # Dart stores Latin-1 constants one byte per character, others as UTF-16.
 return any(form in data for form in (text.encode('utf-8'),text.encode('utf-16le')))

def expected():
 shipped=sorted(p for p in tree.APP586 if p not in tree.DELETED586 and not p.startswith(ON_DEMAND))
 on_demand={}
 for prefix in ON_DEMAND:
  files=sorted(p for p in tree.APP586 if p.startswith(prefix) and p not in tree.DELETED586)
  on_demand[prefix]=dict(files=len(files),sha256=hashlib.sha256(''.join(f'{p} {sha(p)}\n' for p in files).encode()).hexdigest())
 withdrawal=json.loads((ROOT/WITHDRAWAL).read_bytes())
 origin=json.loads((ROOT/ORIGIN_VALIDATION).read_bytes())
 manifest=json.loads(gzip.decompress((ROOT/CHEATS).read_bytes()))
 hosted=json.loads(gzip.decompress((ROOT/HOSTED).read_bytes()))
 assert sha(CHEATS)==sha(ORIGIN)==origin['manifest_sha256'] and (ROOT/CHEATS).stat().st_size==origin['manifest_bytes']
 assert sha(HOSTED)==withdrawal['manifestSHA256']
 # Same games and chunk digests as the hosted index: installed chunks stay installed.
 strip=lambda game:{k:v for k,v in game.items() if k!='pack_id'}
 assert [strip(g) for g in manifest['games']]==[strip(g) for g in hosted['games']]
 assert manifest['sources']==hosted['sources'] and manifest['totals']['programs']==hosted['totals']['programs']
 assert (len(manifest['games']),len(manifest['packs']),manifest['totals']['programs'])==(
  withdrawal['totals']['games'],withdrawal['preservedPacks']+len(withdrawal['replacedPacks']),withdrawal['totals']['programs'])
 assert sha(INDEX)==sha('native/enhancements/catalogue/index.json.gz')
 return dict(build=int(delivery.BUILD),appCommits=tree.APP_COMMITS,validatorCommit=tree.VALIDATOR586,
  files={p:sha(p) for p in shipped},onDemand=on_demand,removed=tree.DELETED586,shippedTrees=tree.SHIPPED,
  enhancementsIndexSHA256=sha(INDEX),cheatIndexSHA256=sha(CHEATS),hostedCheatIndexSHA256=sha(HOSTED),
  originPublication=origin,withdrawalReceiptSHA256=sha(WITHDRAWAL),
  cheatIndex=dict(games=len(manifest['games']),packs=len(manifest['packs']),programs=manifest['totals']['programs']),
  withheldPrograms=withdrawal['removedPrograms'],dartMarkers=DART_MARKERS,nativeMarkers=NATIVE_MARKERS,
  physicalDeviceTested=False,cheatApplied=False,originDownloaded=False)

def embed(app):
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 with zipfile.ZipFile(ipa) as z:
  names=z.namelist()
  root=next(n[:-10] for n in names if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  info=plistlib.loads(z.read(root+'Info.plist'))
  assert str(info['CFBundleVersion'])==str(build),info['CFBundleVersion']
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  assert z.read(root+'Frameworks/App.framework/flutter_assets/'+INDEX)==(ROOT/INDEX).read_bytes()
  cheats=[n for n in names if n.startswith(root) and n.endswith('/NeoCheatCatalog.bundle/manifest.json.gz')]
  assert len(cheats)==1 and z.read(cheats[0])==(ROOT/CHEATS).read_bytes(),cheats
  assert hashlib.sha256(z.read(cheats[0])).hexdigest()==receipt['cheatIndexSHA256']
  dart=z.read(root+'Frameworks/App.framework/App')
  for text in DART_MARKERS:assert contains(dart,text),text
  catalog=z.read(root+'Frameworks/neo_cheat_catalog.framework/neo_cheat_catalog')
  for text in NATIVE_MARKERS:assert text.encode() in catalog,text
  assert z.read(root+'Legal/NeoStation-NOTICE.md')==(ROOT/'NOTICE.md').read_bytes()
  bundled=[n for n in names if '/enhancements/catalogue/shards/' in n or '/cheats/catalogue/packs/' in n
           or '/cheats/catalogue/v2/packs/' in n]
  assert not bundled,bundled[:5]
 return dict(result='passed',build=build,ipaSHA256=hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),identity=receipt,
  compiledDartMarkers=DART_MARKERS,compiledNativeMarkers=NATIVE_MARKERS,physicalDeviceTested=False,cheatApplied=False,
  originDownloaded=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
