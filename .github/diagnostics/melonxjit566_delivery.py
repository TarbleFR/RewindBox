"""Private566: the MeloNX engine of 86c2b4d (JIT translation units, GC gen2 budget; its own engine run) on the delivered 564 product tree.

566 ships the 564 product (the 563 product with the MeloNX engine of 876a087)
and swaps only the MeloNX engine again: the 564 engine becomes the one built
and tested from 86c2b4d. Its sources change no file compiled into the
application: two engine adaptations, their registration, the engine tests and
workflow. The 564 recipe therefore runs unchanged on the delivered 564 tree,
which as_564() puts in place of the pinned 566 one for each inherited check (a
scratch index, the 566 files' 564 versions in the working tree and
BUILD_NUMBER 564, all restored afterwards), with the 564 engine's downloaded
evidence in dist/melonx (old_engine()). The inherited IPA validators that read
the engine check derived_ipa(): this IPA with the engine payload that
package_runtime produces for the 564 engine on the 564 tree, every other entry
byte for byte. The 564 recipe derives its own 563-equivalent from that one in
turn. The 566 engine, its run and its receipts are checked on the pinned 566
tree and on the actual IPA.
"""
import argparse,contextlib,hashlib,json,os,shutil,sys,tempfile,zipfile
from pathlib import Path
import melonxjit566_tree as tree
import melonxtexture564_delivery as d564
ROOT=Path(__file__).resolve().parents[2]
BUILD='566'
HOST_TREE=d564.HOST_TREE
# The MeloNX hosts (558, 562), the RPCS3 Core 563 and every other shipped file are the 564 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'CORE_SOURCE','CORE_RUN','CORE_WORKFLOW','CORE_STEPS','validate_rpc_core_identity','validate_rpc_core_pin',
             'core_receipt','core_run','INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN','MELONX_WORKFLOW','ENGINE_PAYLOAD',
             'EXPORTS564','SYMBOLS564','CORE_TEXT564','engine_entry','sha'):
 globals()[name]=getattr(d564,name)
d563=d564.d563
previous,previous546,d549,d557,d558,d559,d560,d561,d562=(d564.previous,d564.previous546,d564.d549,d564.d557,
 d564.d558,d564.d559,d564.d560,d564.d561,d564.d562)
# The engine the 564 receipts are bound to, and the 558 engine under it.
MELONX564_SOURCE,MELONX564_RUN,MELONX564_ARTIFACT=d564.MELONX_SOURCE,d564.MELONX_RUN,d564.MELONX_ARTIFACT
MELONX563_SOURCE,MELONX563_RUN,MELONX563_ARTIFACT=d564.MELONX563_SOURCE,d564.MELONX563_RUN,d564.MELONX563_ARTIFACT
# Engine built and tested from 86c2b4d, taken by ID and digest.
MELONX_SOURCE=tree.SOURCE566
MELONX_RUN=40535449055
MELONX_ARTIFACT=(12749113131,'f5d48a296e87419c46d4313d04e42e7de53f900f56f2b05643b38ad226019377')
DECODER_STEP='Compile guest code with the real LightningJit decoder (units end at traps and at the next function)'
ENGINE_STEPS566=d564.ENGINE_STEPS564+[DECODER_STEP]
# 566 adds no export and no engine literal; the 564 ones must remain.
EXPORTS566=EXPORTS564
SYMBOLS566=SYMBOLS564
CORE_TEXT566=CORE_TEXT564
ENGINE566=set(tree.ENGINE566)
OLD=ROOT/'dist/melonx564engine'
NEW=ROOT/'dist/melonx'

_active=[False]

@contextlib.contextmanager
def as_564():
 """The delivered 564 tree in place of the pinned 566 one: a scratch copy of
 the index with the 566 files at their 564 versions and this recipe removed,
 the same 566 files in the working tree, and build number 564. The 566
 bytes, the index in use and the environment are restored on exit; a check
 already inside the 564 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_564()
 files={p:s for p,s in versions.items() if p in tree.FIX566}
 saved={p:(ROOT/p).read_bytes() if (ROOT/p).is_file() else None for p in files}
 env={k:os.environ.get(k) for k in ('GIT_INDEX_FILE','BUILD_NUMBER')}
 with tempfile.TemporaryDirectory() as scratch:
  index=os.path.join(scratch,'index')
  tree.index_with(versions,index)
  try:
   for p,source in files.items():
    target=ROOT/p
    if source is None:target.unlink(missing_ok=True)
    else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(at(source,p))
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d564.BUILD
   _active[0]=True
   yield
  finally:
   _active[0]=False
   for k,v in env.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
   for p,data in saved.items():
    if data is None:(ROOT/p).unlink(missing_ok=True)
    else:(ROOT/p).parent.mkdir(parents=True,exist_ok=True);(ROOT/p).write_bytes(data)
 # Nothing of the 564 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 564 recipe, run on the delivered 564 tree."""
 with as_564():return function(*args,**kwargs)

_old=[False]
# Receipts this delivery's own steps write into dist/melonx that do not depend
# on the engine: the 564 recipe found them next to its engine (and carries
# them to the 558 engine in its own view).
CARRIED=d564.CARRIED

@contextlib.contextmanager
def old_engine():
 """The 564 engine's downloaded evidence in dist/melonx, where the 564 recipe
 reads it, with the engine-independent receipts of this delivery's steps; the
 566 engine's is put back on exit. Without a downloaded 564 engine (before the
 component download), nothing moves."""
 if _old[0] or not OLD.is_dir():
  yield
  return
 parked=ROOT/'dist/melonx566'
 assert not parked.exists(),parked
 carried=[name for name in CARRIED if (NEW/name).is_file()]
 assert not any((OLD/name).exists() for name in carried),carried
 NEW.rename(parked);OLD.rename(NEW)
 for name in carried:shutil.copy2(parked/name,NEW/name)
 _old[0]=True
 try:yield
 finally:
  _old[0]=False
  for name in carried:(NEW/name).unlink(missing_ok=True)
  NEW.rename(OLD);parked.rename(NEW)
 assert json.loads((NEW/'ios-arm64/identity.json').read_bytes())['host']==MELONX_SOURCE

@contextlib.contextmanager
def as_564_engine():
 """The delivered 564 tree with its engine evidence: what the 564 recipe saw."""
 with old_engine(),as_564():yield

@contextlib.contextmanager
def as_563():
 """The delivered 563 tree, through the 564 view (for the validators of 563 receipts)."""
 with as_564_engine(),d564.as_563():yield

@contextlib.contextmanager
def as_563_engine():
 """The delivered 563 tree with the 558 engine's evidence, through the 564 view."""
 with as_564_engine(),d564.as_563_engine():yield

def validate_interface():
 return inherited(d564.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d564.host_evidence)

def engine_identity():
 identity=json.loads((NEW/'ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE,identity['host']
 return identity

def engine_evidence():
 """The downloaded 566 engine names exactly the pinned engine inputs, exports
 every 564 entry point, compiled the adapted decoder and GC setting, and passed
 the 564 engine checks again (session ownership, display, the simulator runtime
 whose homebrew now executes the new unit ends, texture pool, journal) and the
 566 one (decoder and compiler, upstream vs adapted)."""
 identity=engine_identity()
 for name in EXPORTS566:assert name in identity['exports'],name
 assert ENGINE566|set(d564.ENGINE564)<=set(identity['adaptations'])
 for p,h in identity['adaptations'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 inputs=json.loads((NEW/'embedded-inputs.json').read_bytes())
 for p,h in inputs.items():assert sha(p)==h,p
 for p in ('build-utils/melonx/adapt_jit_decoder.py','build-utils/melonx/adapt_gc.py','build-utils/melonx/adapt_texture_pool.py'):
  assert p in inputs,p
 with zipfile.ZipFile(NEW/'embedded-adapted-source.zip') as z:
  decoder=z.read('src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs').decode('utf-8-sig')
  assert decoder.count('StartsFunction(memoryManager, block.EndAddress)')==1 and 'EndsWithTrap(block)' in decoder
  project=z.read('src/Ryujinx.Library/Ryujinx.Library.csproj').decode('utf-8-sig')
  assert '"System.GC.ConserveMemory" Value="5"' in project and 'Value="9"' not in project
  pool=z.read('src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs').decode('utf-8-sig')
  assert pool.count('if (!MemoryManager.ValidateAddress(descriptor.UnpackAddress()))')==1
  for p,name in (('native/melonx/EmbeddedLaunchDiagnostics.cs','src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs'),
                 ('native/melonx/EmbeddedRuntime.cs','src/Ryujinx.Library/EmbeddedRuntime.cs')):
   assert z.read(name)==(ROOT/p).read_bytes(),p
 decoder=json.loads((NEW/'jit-decoder-checks.json').read_bytes())
 assert decoder['result']=='passed' and not decoder['failures'] and decoder['executed'] is False
 assert decoder['adapted']['layout']['guestInstructions']==300*12+1
 assert decoder['upstream']['layout']['hostBytes']>20*decoder['adapted']['layout']['hostBytes']
 texture=json.loads((NEW/'texture-pool-checks.json').read_bytes())
 assert texture['result']=='passed' and not texture['failures']
 journal=json.loads((NEW/'engine-journal-checks.json').read_bytes())
 assert journal['result']=='passed' and not journal['failures'] and journal['nativeAot'] is True
 for receipt in (decoder,texture,journal):
  for p,h in receipt['inputs'].items():assert sha(p)==h,p
 session=json.loads((NEW/'session-checks.json').read_bytes())
 assert session['passedCases']==25
 display=json.loads((NEW/'display-checks.json').read_bytes())
 assert display['result']=='passed' and 'PASS 69 graphics, FPS snapshot' in display['summary']
 smoke=json.loads((NEW/'runtime-smoke/actual-runtime.json').read_bytes())
 assert smoke['result']=='passed' and smoke['homebrewSimulatorSessions']==2 and smoke['originalHomebrewGuestSvcConfirmed']
 assert smoke['performanceSnapshotStaleAndEndedRefused'] and smoke['livePerformanceSnapshotSessions']>=1
 for receipt in (session,display,smoke):
  for p,h in receipt.get('inputs',{}).items():assert sha(p)==h,p
 return dict(source=MELONX_SOURCE,run=MELONX_RUN,artifact=MELONX_ARTIFACT[0],coreSHA256=identity['sha256'],
  exports=EXPORTS566,adaptations=len(identity['adaptations']),sessionCases=session['passedCases'],
  displaySummary=display['summary'].splitlines()[-1],simulatorSessions=smoke['homebrewSimulatorSessions'],
  jitDecoder={k:decoder[k]['layout'] for k in ('upstream','adapted')},gcConserveMemory=5,
  physicalDeviceTested=False,gameTested=False)

def engine_run():
 """The engine run: the exact commit, its own workflow, every 564 engine step and the 566 one passed."""
 state=previous.api(f'actions/runs/{MELONX_RUN}')
 assert state['head_sha']==MELONX_SOURCE and state['path']==MELONX_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS566)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 564 contract, unchanged, on the delivered 564 tree.
 report=inherited(d564.source_contract)
 assert report['productTrees']==tree.product_trees_564(),report['productTrees']
 trees=tree.product_trees()
 # No product tree changes: only the engine, built by its own run, does.
 assert trees==report['productTrees'],trees
 # The pinned index differs from the delivered 564 tree by the 566 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_564()).splitlines())
 expected=set(tree.FIX566)|{p for p in tree.RECIPE if (ROOT/p).is_file()}
 assert changed==expected,changed^expected
 for p in tree.FIX566:
  if tree.source_of(p):assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The engine run built exactly these engine inputs.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|ENGINE566):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 563, unchanged, on the pinned tree.
 d563.native.source_contract()
 for p,h in d563.native.inputs().items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build564=report['build'],source564Recipe=report['source'],
  source566=MELONX_SOURCE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  melonx564Source=MELONX564_SOURCE,melonx564Run=MELONX564_RUN,replaced566=tree.REPLACED,changed566=sorted(changed),
  pinnedFiles=kept,productTrees=trees,productTrees564=report['productTrees'],
  physicalDeviceTested=False,gameTested=False)

def payload_564(scratch):
 """The engine entries package_runtime writes for the 564 engine on the 564
 tree (macOS: install_name_tool, vtool and otool), in a scratch application."""
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import package_runtime as runtime
 saved=runtime.CORE,runtime.FRAMEWORKS
 app=Path(scratch)/'app';app.mkdir()
 try:
  with as_564_engine():
   runtime.CORE=NEW;runtime.FRAMEWORKS=Path(scratch)/'Frameworks'
   runtime.materialize();runtime.embed(app)
   identity=json.loads((app/'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']
   assert identity['host']==MELONX564_SOURCE,identity['host']
 finally:
  runtime.CORE,runtime.FRAMEWORKS=saved
 # The scratch packaging receipt belongs to the 564 artifact; never keep it there.
 (OLD/'packaging-identity.json').unlink(missing_ok=True)
 return app

def derived_ipa(ipa):
 """This IPA with the 564 engine payload of the 564 tree in place of its own:
 the application the 564 recipe validated, but for this build's other files.
 Cached per IPA digest."""
 ipa=Path(ipa);digest=hashlib.sha256(ipa.read_bytes()).hexdigest()
 out=ROOT/'build/derived564'/f'{digest}.ipa'
 if out.is_file():return out
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as scratch:
  app=payload_564(scratch)
  payload={str(p.relative_to(app)).replace(os.sep,'/'):p.read_bytes() for p in app.rglob('*') if p.is_file()}
  payload={k:v for k,v in payload.items() if any(k==e or (e.endswith('/') and k.startswith(e)) for e in ENGINE_PAYLOAD)}
  assert set(ENGINE_PAYLOAD[:3])<=set(payload),sorted(payload)
  with zipfile.ZipFile(ipa) as source,zipfile.ZipFile(out.with_suffix('.tmp'),'w') as target:
   roots={n.split('/')[1] for n in source.namelist() if n.startswith('Payload/') and n.split('/')[1].endswith('.app')}
   assert len(roots)==1;root='Payload/'+roots.pop()+'/'
   replaced=set()
   for info in source.infolist():
    if engine_entry(info.filename,root):
     relative=info.filename[len(root):]
     if relative in payload:target.writestr(info,payload[relative]);replaced.add(relative)
     continue
    target.writestr(info,source.read(info))
   for relative in sorted(set(payload)-replaced):
    target.writestr(zipfile.ZipInfo(root+relative,date_time=(2026,10,27,0,0,0)),payload[relative],zipfile.ZIP_DEFLATED)
 out.with_suffix('.tmp').rename(out)
 return out

def validate_engine_ipa(ipa):
 """The actual IPA carries the 566 engine as package_runtime packaged it and,
 apart from the engine entries, the same bytes as derived_ipa()."""
 sys.path.insert(0,str(ROOT/'build-utils'))
 sys.path.insert(0,str(ROOT/'packages/dolphin_internal_bridge/ci'))
 from delivery_benchmark import payload_fingerprint
 from verify_ipa import macho
 import validate_melonx_audio537_ipa as audio
 derived=derived_ipa(ipa)
 identity=engine_identity()
 with zipfile.ZipFile(ipa) as real,zipfile.ZipFile(derived) as old:
  root=next(n[:-10] for n in real.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(real.read(root+'MeloNX-native-identity.json'))
  assert receipt['sourceCoreIdentity']==identity
  core=real.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  assert payload_fingerprint(core)==receipt['compiledPayloadFingerprints']['MeloNXCore']
  symbols=set(macho(core)['definedSymbols'])
  for name in SYMBOLS566:assert name in symbols,name
  for text in CORE_TEXT566:assert audio.contains(core,text),text
  for p,h in identity['adaptations'].items():assert sha(p)==h,p
  others=[n for n in real.namelist() if not engine_entry(n,root)]
  assert others==[n for n in old.namelist() if not engine_entry(n,root)]
  for name in others:assert real.read(name)==old.read(name),name
  stale=json.loads(old.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert stale['host']==MELONX564_SOURCE and stale['sha256']!=identity['sha256']
 return dict(engineSource=MELONX_SOURCE,engineRun=MELONX_RUN,coreSHA256=identity['sha256'],
  packagedCoreFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],engine564Source=MELONX564_SOURCE,
  engine564SHA256=stale['sha256'],otherEntriesEqualTo564Equivalent=len(others),symbols=SYMBOLS566)

def retain_checks():
 """The 564 receipts stay bound to the delivered 564 tree (and its 563 to 554 views); the 566 engine run to the pinned tree."""
 inherited(d564.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'melonx-jit566-engine-run.json').write_text(json.dumps(engine_run(),indent=2)+'\n')
 print('Bound the 564 receipts to the delivered 564 tree and the 566 engine run to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation566.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 564 binding on the delivered 564 tree (its own views in turn), then the pinned tree.
  views=[d564.inherited,d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,d558.inherited,d557.inherited]
  for depth in (8,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),
                       d549.download(MELONX563_ARTIFACT,'dist/melonx563'),d549.download(HOST_ARTIFACT,'dist/melonx-host'),
                       d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558 and 564 engines and the 562 host on the delivered 564 tree, as 564 bound them; then the 566 engine.
  with old_engine():
   with d564.old_engine():report['engine563Evidence']=inherited(d564.inherited,d563.inherited,d562.inherited,d558.engine_evidence)
   report['engine564Evidence']=inherited(d564.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=engine_run()
  report['engine564']=d564.engine_run()
  report['engine563']=previous.completed(MELONX563_RUN,MELONX563_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
  report['host562']=host_run()
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
