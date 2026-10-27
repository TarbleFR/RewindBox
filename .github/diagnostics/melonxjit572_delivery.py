"""Private572: the MeloNX engine of 8cc2348 (a JIT unit ends at a jump past the other cases of a switch; its own engine run) on the delivered 567 product tree.

572 ships the 567 product (the 566 product with the RPCS3 Core 567; MeloNX
engine 86c2b4d, God of War III without the 30 fps limiter, MeloNX keyboard
and L3/R3) and swaps only the MeloNX engine: the 566 engine becomes the one
built and tested from 8cc2348. Its sources change no file compiled into the
application: the decoder adaptation, the decoder test and the simulator smoke.
The 567 recipe therefore runs unchanged on the delivered 567 tree, which
as_567() puts in place of the pinned 572 one for each inherited check (a
scratch index, the 572 files' 567 versions in the working tree and
BUILD_NUMBER 567, all restored afterwards), with the 566 engine's downloaded
evidence in dist/melonx (old_engine()). The inherited IPA validators check
derived_ipa(): this IPA with the engine payload that package_runtime produces
for the 566 engine on the 567 tree, every other entry byte for byte; the 566
recipe under them derives its own 565-equivalent in turn. The 572 engine, its
run and its receipts are checked on the pinned 572 tree and on the actual
IPA. The source contract is computed once per job and reused on the same
bytes (build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,shutil,sys,tempfile,zipfile
from pathlib import Path
import melonxjit572_tree as tree
import rpcs3cell567_delivery as d567
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='572'
HOST_TREE=d567.HOST_TREE
d566=d567.d566
# The RPCS3 Core 567, the MeloNX hosts (558, 562) and every shipped file are the 567 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'CORE_SOURCE','CORE_RUN','CORE_WORKFLOW','CORE_STEPS','validate_rpc_core_identity','validate_rpc_core_pin',
             'core_receipt','core_run','INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN','CORE563_SOURCE','CORE563_RUN',
             'CORE565_SOURCE','CORE565_RUN','MELONX_WORKFLOW','MELONX563_SOURCE','MELONX563_RUN','MELONX563_ARTIFACT',
             'MELONX564_SOURCE','MELONX564_RUN','MELONX564_ARTIFACT'):
 globals()[name]=getattr(d567,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565=(d567.previous,d567.previous546,d567.d549,
 d567.d557,d567.d558,d567.d559,d567.d560,d567.d561,d567.d562,d567.d563,d567.d564,d567.d565)
for name in ('ENGINE_PAYLOAD','engine_entry','sha'):
 globals()[name]=getattr(d566,name)
# The engine the 567 and 566 receipts are bound to.
MELONX566_SOURCE,MELONX566_RUN,MELONX566_ARTIFACT=d567.MELONX_SOURCE,d567.MELONX_RUN,d567.MELONX_ARTIFACT
assert MELONX566_SOURCE==d566.MELONX_SOURCE==tree.SOURCE566
# Engine built and tested from 8cc2348, taken by ID and digest.
MELONX_SOURCE=tree.SOURCE572
MELONX_RUN=40570622034
MELONX_ARTIFACT=(12766340886,'612754d62f2ba01c2eab7f70e4072c8b85c6dd68ecc25551a66323243fb0996e')
# The engine workflow keeps its 566 steps; the decoder step now also runs the switch case.
ENGINE_STEPS572=d566.ENGINE_STEPS566
# 572 adds no export and no engine literal; the 566 ones must remain.
EXPORTS572=d566.EXPORTS566
SYMBOLS572=d566.SYMBOLS566
CORE_TEXT572=d566.CORE_TEXT566
ENGINE572=set(tree.ENGINE572)
OLD=ROOT/'dist/melonx566engine'
NEW=ROOT/'dist/melonx'
# Python modules of 572 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in tree.FIX572 if p.endswith('.py'))

_active=[False]

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in tree.FIX572:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_567():
 """The delivered 567 tree in place of the pinned 572 one: a scratch copy of
 the index with the 572 files at their 567 versions and this recipe removed,
 the same 572 files in the working tree, their Python modules and build
 number 567. The RPCS3 Core 567 and its installed identity are the same in
 both trees. The 572 bytes, modules, the index in use and the environment are
 restored on exit; a check already inside the 567 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_567()
 files={p:s for p,s in versions.items() if p in tree.FIX572}
 saved={p:(ROOT/p).read_bytes() if (ROOT/p).is_file() else None for p in files}
 modules={name:sys.modules[name] for name in MODULES if name in sys.modules}
 env={k:os.environ.get(k) for k in ('GIT_INDEX_FILE','BUILD_NUMBER')}
 with tempfile.TemporaryDirectory() as scratch:
  index=os.path.join(scratch,'index')
  tree.index_with(versions,index)
  try:
   for p,source in files.items():
    target=ROOT/p
    if source is None:target.unlink(missing_ok=True)
    else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(at(source,p))
   _forget(MODULES)
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d567.BUILD
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
   _forget(MODULES)
   sys.modules.update(modules)
 # Nothing of the 567 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 567 recipe, run on the delivered 567 tree."""
 with as_567():return function(*args,**kwargs)

_old=[False]
# Receipts this delivery's own steps write into dist/melonx that do not depend
# on the engine: the 567, 566 and 564 recipes found them next to their engine.
CARRIED=d566.CARRIED

@contextlib.contextmanager
def old_engine():
 """The 566 engine's downloaded evidence in dist/melonx, where the 567 and 566
 recipes read it, with the engine-independent receipts of this delivery's
 steps; the 572 engine's is put back on exit. Without a downloaded 566 engine
 (before the component download), nothing moves."""
 if _old[0] or not OLD.is_dir():
  yield
  return
 parked=ROOT/'dist/melonx572'
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
def as_567_engine():
 """The delivered 567 tree with its engine evidence: what the 567 recipe saw."""
 with old_engine(),as_567():yield

def validate_interface():
 return inherited(d567.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d567.host_evidence)

def engine_identity():
 identity=json.loads((NEW/'ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE,identity['host']
 return identity

def engine_evidence():
 """The downloaded 572 engine names exactly the pinned engine inputs, exports
 every 566 entry point, compiled the adapted decoder (the 566 unit ends and
 the switch-case one) and GC setting, and passed the 566 engine checks again:
 session ownership, display, the simulator runtime whose homebrew now also
 jumps past undefined words, texture pool, journal, and the decoder test
 (upstream vs adapted) with the switch case."""
 identity=engine_identity()
 for name in EXPORTS572:assert name in identity['exports'],name
 assert ENGINE572|d566.ENGINE566|set(d564.ENGINE564)<=set(identity['adaptations'])
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
  assert decoder.count('IsSkippedCodeReachable(memoryManager, block.EndAddress, jumpTarget, branchTargets)')==1
  assert 'jumpTarget >= block.EndAddress + 256UL' in decoder
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
 assert decoder['upstream']['switchCase']['guestInstructions']==82 and decoder['adapted']['switchCase']['guestInstructions']==6
 for case in ('rotatedLoop','shortSkip','enteredSkip'):
  assert decoder['adapted'][case]['guestInstructions']==decoder['upstream'][case]['guestInstructions'],case
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
  exports=EXPORTS572,adaptations=len(identity['adaptations']),sessionCases=session['passedCases'],
  displaySummary=display['summary'].splitlines()[-1],simulatorSessions=smoke['homebrewSimulatorSessions'],
  jitDecoder={k:{case:decoder[k][case] for case in ('layout','switchCase')} for k in ('upstream','adapted')},
  gcConserveMemory=5,physicalDeviceTested=False,gameTested=False)

def engine_run():
 """The engine run: the exact commit, its own workflow, every 566 engine step passed."""
 state=previous.api(f'actions/runs/{MELONX_RUN}')
 assert state['head_sha']==MELONX_SOURCE and state['path']==MELONX_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS572)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 567 contract, unchanged, on the delivered 567 tree.
 report=inherited(d567.source_contract)
 assert report['productTrees']==tree.product_trees_567(),report['productTrees']
 trees=tree.product_trees()
 # No product tree changes: only the engine, built by its own run, does.
 assert trees==report['productTrees'],trees
 # The pinned index differs from the delivered 567 tree by the 572 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_567()).splitlines())
 expected=set(tree.FIX572)|set(tree.RECIPE)
 assert changed==expected,changed^expected
 for p in tree.FIX572:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The engine run built exactly these engine inputs.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566|ENGINE572):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 567 and the God of War III profile, unchanged, on the pinned tree.
 d567.native.source_contract()
 for p,h in d567.native.inputs().items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 for p in d565.tree.FIX565:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build567=report['build'],source567Recipe=report['source'],
  source572=MELONX_SOURCE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  melonx566Source=MELONX566_SOURCE,melonx566Run=MELONX566_RUN,replaced572=tree.REPLACED,changed572=sorted(changed),
  pinnedFiles=kept,productTrees=trees,productTrees567=report['productTrees'],
  physicalDeviceTested=False,gameTested=False)

def payload_567(scratch):
 """The engine entries package_runtime writes for the 566 engine on the 567
 tree (macOS: install_name_tool, vtool and otool), in a scratch application."""
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import package_runtime as runtime
 saved=runtime.CORE,runtime.FRAMEWORKS
 app=Path(scratch)/'app';app.mkdir()
 try:
  with as_567_engine():
   runtime.CORE=NEW;runtime.FRAMEWORKS=Path(scratch)/'Frameworks'
   runtime.materialize();runtime.embed(app)
   identity=json.loads((app/'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']
   assert identity['host']==MELONX566_SOURCE,identity['host']
 finally:
  runtime.CORE,runtime.FRAMEWORKS=saved
 # The scratch packaging receipt belongs to the 566 artifact; never keep it there.
 (OLD/'packaging-identity.json').unlink(missing_ok=True)
 return app

def derived_ipa(ipa):
 """This IPA with the 566 engine payload of the 567 tree in place of its own:
 the application the 567 recipe validated, but for this build's other files.
 Cached per IPA digest."""
 ipa=Path(ipa);digest=hashlib.sha256(ipa.read_bytes()).hexdigest()
 out=ROOT/'build/derived567'/f'{digest}.ipa'
 if out.is_file():return out
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as scratch:
  app=payload_567(scratch)
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
 """The actual IPA carries the 572 engine as package_runtime packaged it and,
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
  for name in SYMBOLS572:assert name in symbols,name
  for text in CORE_TEXT572:assert audio.contains(core,text),text
  for p,h in identity['adaptations'].items():assert sha(p)==h,p
  others=[n for n in real.namelist() if not engine_entry(n,root)]
  assert others==[n for n in old.namelist() if not engine_entry(n,root)]
  for name in others:assert real.read(name)==old.read(name),name
  stale=json.loads(old.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert stale['host']==MELONX566_SOURCE and stale['sha256']!=identity['sha256']
 return dict(engineSource=MELONX_SOURCE,engineRun=MELONX_RUN,coreSHA256=identity['sha256'],
  packagedCoreFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],engine566Source=MELONX566_SOURCE,
  engine566SHA256=stale['sha256'],otherEntriesEqualTo567Equivalent=len(others),symbols=SYMBOLS572)

def retain_checks():
 """The 567 receipts stay bound to the delivered 567 tree (and its 566 to 554 views); the 572 engine run to the pinned tree."""
 inherited(d567.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'melonx-jit572-engine-run.json').write_text(json.dumps(engine_run(),indent=2)+'\n')
 print('Bound the 567 receipts to the delivered 567 tree and the 572 engine run to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation572.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 567 binding on the delivered 567 tree (its own views in turn), then the pinned tree.
  views=[d567.inherited,d566.inherited,d565.inherited,d564.inherited,d563.inherited,d562.inherited,d561.inherited,
         d560.inherited,d559.inherited,d558.inherited,d557.inherited]
  for depth in (11,9,8,7,6,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX566_ARTIFACT,'dist/melonx566engine'),
                       d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),d549.download(MELONX563_ARTIFACT,'dist/melonx563'),
                       d549.download(HOST_ARTIFACT,'dist/melonx-host'),d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),
                       d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558, 564 and 566 engines and the 562 host on the delivered 567 tree, as 567 bound them; then the 572 engine.
  with old_engine():
   with d566.old_engine():
    with d564.old_engine():
     report['engine563Evidence']=inherited(d567.inherited,d566.inherited,d565.inherited,d564.inherited,d563.inherited,
                                           d562.inherited,d558.engine_evidence)
    report['engine564Evidence']=inherited(d567.inherited,d566.inherited,d565.inherited,d564.engine_evidence)
   report['engine566Evidence']=inherited(d567.inherited,d566.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=engine_run()
  report['engine566']=d566.engine_run()
  report['engine564']=d564.engine_run()
  report['engine563']=previous.completed(MELONX563_RUN,MELONX563_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
  report['host562']=host_run()
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
