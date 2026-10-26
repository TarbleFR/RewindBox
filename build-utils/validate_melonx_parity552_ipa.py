#!/usr/bin/env python3
"""Bind the MeloNX standalone parity (62626c0), its engine and host to private IPA552.

The 549 threading validator chain (544 close, 540 pipeline, 539 journal, 537
audio, 533 memory, 518 presentation) runs against the 552 engine and host
with three changes: its frontend receipt is the 552 re-run, its MeloNX
product set includes the 552 files, and its journal check accepts the one
added engine-options record. On top, the signed IPA must carry the 552
claims: the two new exports, the standalone MoltenVK framework (the pinned
upstream bytes, renamed only), Game Mode keys, the stderr journal, the
MoltenVK choice and its menu strings.
"""
import argparse,hashlib,json,plistlib,struct,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics','build-utils','build-utils/melonx','packages/dolphin_internal_bridge/ci'):
 sys.path.insert(0,str(ROOT/path))
import melonxparity552_delivery as delivery552
import melonxthreading549_delivery as delivery549
# Rebind before the 549 validator wires its reused validators to these values.
for name in ('MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','HOST_SOURCE','HOST_RUN','HOST_ARTIFACT'):
 setattr(delivery549,name,getattr(delivery552,name))
delivery549.PRODUCT549=delivery552.PRODUCT
delivery549.validate_local_imports=delivery552.validate_melonx_rerun
delivery549.engine_evidence=delivery552.engine_evidence
import validate_melonx_threading549_ipa as threading
import package_standalone_moltenvk as standalone
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho

threading.IDENTITY='MeloNX-parity552-identity.json'
at=delivery552.at
audio=threading.audio
SESSION=threading.journal.SESSION
# The one record 552 adds to the 549 session file, after the applied graphics.
ENGINE_OPTIONS=b'''                // Every other option the engine consumes, so a session can be
                // compared field by field with the standalone app's config.
                EmbeddedLaunchDiagnostics.Record("configuration", "engine", detail:
                    FormattableString.Invariant($"Engine options: ptc={!options.DisablePTC}; macroHle={!options.DisableMacroHLE}; docked={!options.DisableDockedMode}; memoryManager={options.MemoryManagerMode}; aspect={options.AspectRatio}; anisotropy={options.MaxAnisotropy}; antiAliasing={options.AntiAliasing}; scaling={options.ScalingFilter}/{options.ScalingFilterLevel}; language={options.SystemLanguage}; region={options.SystemRegion}; ignoreMissingServices={options.IgnoreMissingServices}; customVsync={options.CustomVSyncInterval}; moltenVk={EmbeddedNativeLibraries.MoltenVk}"));
'''
APPLIED=b'threading={options.BackendThreading}"));\n'
GAME_MODE={'LSSupportsGameMode':True,'GCSupportsGameMode':True,'LSApplicationCategoryType':'public.app-category.games'}
EXPORTS=['_neostation_melonx_select_moltenvk','_neostation_melonx_set_present_target_fps','_neostation_melonx_performance_snapshot']
# Host literals longer than Swift's 15-byte inline strings, so stored as bytes.
HOST_MARKERS=[b'neostation_melonx_select_moltenvk',b'neostation_melonx_set_present_target_fps',b'RewindBoxMeloNXMoltenVK',
 b'MeloNXMoltenVKStandalone',b'[MeloNX:stderr] ',b'RewindBox.MeloNX.Stderr',b'moltenVkPreference',
 b'Restart RewindBox to use this MoltenVK.',b'Version de MoltenVK',b'MeloNX app (1.4.0)']
CORE_TEXT=['Engine options: ptc=','MeloNXMoltenVKStandalone','moltenVkFixed']
STANDALONE=f'Frameworks/{standalone.NAME}.framework/{standalone.NAME}'
STANDALONE_IDENTITY='MeloNX-standalone-moltenvk-identity.json'

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def journal_expected():
 """539 journal proof with the 552 engine: the 549 session file plus the engine-options record."""
 receipt=json.loads((ROOT/'docs/evidence/melonx-effective-graphics-journal.json').read_bytes())
 assert receipt['result']=='passed' and receipt['summary'].startswith('PASS 26 ')
 assert not receipt['gpuRenderingTested'] and not receipt['deviceTested']
 for p,h in receipt['inputs'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(delivery552.MELONX_SOURCE,p),p
 old=at(threading.PREVIOUS_ENGINE,SESSION)
 assert old.count(threading.THREADING_OFF)==1 and old.count(APPLIED)==1
 expected549=old.replace(threading.THREADING_OFF,threading.THREADING_ON,1)
 assert expected549==at(delivery552.tree.previous.previous.SOURCE549,SESSION)
 assert expected549.replace(APPLIED,APPLIED+ENGINE_OPTIONS,1)==(ROOT/SESSION).read_bytes()
 return dict(coreSource=delivery552.MELONX_SOURCE,coreRun=delivery552.MELONX_RUN,regression=receipt,engineOptionsRecord=True,
  physicalDeviceTested=False,graphicsImprovementClaimed=False)

threading.journal_expected=journal_expected
threading.journal.expected=journal_expected

def sections(data):
 """Code and data section digests of a thin arm64 image (no load commands)."""
 ncmds=struct.unpack_from('<I',data,16)[0];cursor=32;found={}
 for _ in range(ncmds):
  command,size=struct.unpack_from('<II',data,cursor)
  if command==0x19:
   for index in range(struct.unpack_from('<I',data,cursor+64)[0]):
    pos=cursor+72+80*index
    section,segment=struct.unpack_from('<16s16s',data,pos)
    length=struct.unpack_from('<Q',data,pos+40)[0];offset=struct.unpack_from('<I',data,pos+48)[0]
    if offset and length:found[(segment+section).hex()]=hashlib.sha256(data[offset:offset+length]).hexdigest()
  cursor+=size
 return found

def parity_expected():
 """The standalone MoltenVK as packaged: pinned upstream bytes, only the install name changed."""
 receipt=json.loads(standalone.RECEIPT.read_bytes())
 pin=json.loads((ROOT/'build-utils/melonx/source.json').read_bytes())
 assert receipt['sourceSha256']==standalone.PINNED_SHA256 and receipt['revision']==pin['revision']
 assert receipt['repository']==pin['repository'] and receipt['path']==standalone.SOURCE_PATH and receipt['sourceBuilt'] is False
 source=(ROOT/'.native-sources/MeloNX'/standalone.SOURCE_PATH).read_bytes()
 assert hashlib.sha256(source).hexdigest()==standalone.PINNED_SHA256
 packaged=(standalone.FRAMEWORKS/f'{standalone.NAME}.framework'/standalone.NAME).read_bytes()
 assert hashlib.sha256(packaged).hexdigest()==receipt['packagedSha256']
 assert sections(packaged)==sections(source) and sections(source)
 image=macho(packaged);origin=macho(source)
 assert image['id']==receipt['installName']==f'@rpath/{standalone.NAME}.framework/{standalone.NAME}'
 assert origin['id']=='@rpath/libMoltenVK.dylib' and image['dependencies']==origin['dependencies']
 assert image['definedSymbols']==origin['definedSymbols'] and image['platform']==2
 assert all(d['path'].startswith(('/usr/lib/','/System/Library/Frameworks/')) for d in image['dependencies'])
 return dict(standaloneMoltenVk=dict(repository=receipt['repository'],revision=receipt['revision'],path=receipt['path'],
   sourceSha256=receipt['sourceSha256'],packagedSha256=receipt['packagedSha256'],installName=receipt['installName'],
   payloadFingerprint=payload_fingerprint(packaged),sectionsMatchingSource=len(sections(source)),
   sourceBuilt=False,exception='maintainer-approved Persona flicker A/B'),
  defaultMoltenVk='standalone',gameMode=GAME_MODE,exports=EXPORTS,stderrJournal='[MeloNX:stderr] lines in app.log during a session',
  standaloneMoltenVkDeviceTested=False,flickerFixClaimed=False)

_expected549=threading.expected
def expected():
 return dict(_expected549(),build=int(delivery552.BUILD),parity552=parity_expected())
threading.expected=expected

def embed(app):
 threading.embed(app)

def validate(ipa,build):
 result=threading.validate(ipa,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(z.read(root+threading.IDENTITY))['parity552']
  info=plistlib.loads(z.read(root+'Info.plist'))
  for key,value in GAME_MODE.items():assert info.get(key)==value,key
  identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  for name in EXPORTS:assert name.removeprefix('_') in identity['exports'],name
  for p in sorted(delivery552.PRODUCT552):
   if p.startswith('native/'):assert identity['adaptations'][p]==sha(p),p
  core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  symbols=set(macho(core)['definedSymbols'])
  for name in EXPORTS:assert name in symbols,name
  for text in CORE_TEXT:assert audio.contains(core,text),text
  host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  for marker in HOST_MARKERS:assert marker in host,marker
  shipped=z.read(root+STANDALONE)
  image=macho(shipped)
  assert image['id']==receipt['standaloneMoltenVk']['installName'] and image['platform']==2
  assert payload_fingerprint(shipped)==receipt['standaloneMoltenVk']['payloadFingerprint']
  source=(ROOT/'.native-sources/MeloNX'/standalone.SOURCE_PATH).read_bytes()
  assert hashlib.sha256(source).hexdigest()==standalone.PINNED_SHA256 and sections(shipped)==sections(source)
  packaged=json.loads(z.read(root+STANDALONE_IDENTITY))
  assert packaged['sourceSha256']==standalone.PINNED_SHA256 and packaged['packagedSha256']==receipt['standaloneMoltenVk']['packagedSha256']
  license=z.read(root+standalone.LEGAL+'/LICENSE.txt')
  assert hashlib.sha256(license).hexdigest()==packaged['license']['sha256'] and b'Apache License' in license
  notice=z.read(root+standalone.LEGAL+'/NOTICE.txt').decode()
  assert standalone.PINNED_SHA256 in notice and 'Apache License, Version 2.0' in notice
  # The source-built six-framework receipt is unchanged; the standalone one stands apart.
  assert standalone.NAME not in json.loads(z.read(root+'MeloNX-native-identity.json'))['frameworks']
  assert z.read(root+'Frameworks/MeloNXMoltenVK.framework/MeloNXMoltenVK')
 return dict(result,parity552=receipt,compiledParityVerified=True,standaloneMoltenVkShipped=True,
  standaloneMoltenVkDeviceTested=False,flickerFixClaimed=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=int(delivery552.BUILD));p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
