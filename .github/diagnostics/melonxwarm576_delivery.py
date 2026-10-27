"""Private576: the MeloNX engine of 301e0f8 (shader-cache warm-ups off the game's start, attachment-less framebuffers sized to the viewports, temporary FFT boot trace; its own engine run) and the StikDebug fallback removal of 504f9c0 on the delivered 575 product tree.

576 ships the 575 product (the 573 product with the RPCS3 Core 575; MeloNX
engine 8cc2348, God of War III without the 30 fps limiter, MeloNX keyboard
and L3/R3) and swaps only the MeloNX engine: the 572 engine becomes the one
built and tested from 301e0f8, whose sources change no file compiled into
the application (three engine adaptations, the adaptation list and the
engine workflow's push paths). The application also loses the StikDebug JIT
fallback (504f9c0: MeloNX always uses the integrated helper; three product
files in lib and packages, two Dart files deleted, their tests). The 575
recipe runs unchanged on the delivered 575 tree, which as_575() puts in
place of the pinned 576 one for each inherited check (a scratch index, the
576 files' 575 versions in the working tree, the deleted files restored, and
BUILD_NUMBER 575, all restored afterwards), with the 572
engine's downloaded evidence in dist/melonx (old_engine()). The inherited
IPA validators check derived_ipa(): this IPA with the engine payload that
package_runtime produces for the 572 engine on the 575 tree, every other
entry byte for byte; the 572 recipe under them derives its own
567-equivalent in turn. The 576 engine, its run and its receipts are checked
on the pinned 576 tree and on the actual IPA. The RPCS3 Core is the 575 one
in both trees. The source contract is computed once per job and reused on
the same bytes (build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,shutil,sys,tempfile,zipfile
from pathlib import Path
import melonxwarm576_tree as tree
import rpcs3cell575_delivery as d575
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='576'
HOST_TREE=d575.HOST_TREE
# The RPCS3 Core 575, the MeloNX hosts (558, 562) and every shipped file are the 575 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'CORE_SOURCE','CORE_RUN','CORE_WORKFLOW','CORE_STEPS','validate_rpc_core_identity','validate_rpc_core_pin',
             'core_receipt','core_run','INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN','CORE563_SOURCE','CORE563_RUN',
             'CORE565_SOURCE','CORE565_RUN','CORE567_SOURCE','CORE567_RUN','CORE569_SOURCE','CORE569_RUN',
             'CORE571_SOURCE','CORE571_RUN','CORE573_SOURCE','CORE573_RUN','MELONX_WORKFLOW',
             'MELONX566_SOURCE','MELONX566_RUN','MELONX566_ARTIFACT','MELONX564_SOURCE','MELONX564_RUN',
             'MELONX564_ARTIFACT','MELONX563_SOURCE','MELONX563_RUN','MELONX563_ARTIFACT'):
 globals()[name]=getattr(d575,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565,d566,d567,d572,d573=(d575.previous,
 d575.previous546,d575.d549,d575.d557,d575.d558,d575.d559,d575.d560,d575.d561,d575.d562,d575.d563,d575.d564,
 d575.d565,d575.d566,d575.d567,d575.d572,d575.d573)
for name in ('ENGINE_PAYLOAD','engine_entry','sha'):
 globals()[name]=getattr(d566,name)
# The engine the 575, 573 and 572 receipts are bound to.
MELONX572_SOURCE,MELONX572_RUN,MELONX572_ARTIFACT=d575.MELONX_SOURCE,d575.MELONX_RUN,d575.MELONX_ARTIFACT
assert MELONX572_SOURCE==d572.MELONX_SOURCE==tree.SOURCE572
# Engine built and tested from 301e0f8, taken by ID and digest.
MELONX_SOURCE=tree.SOURCE576
MELONX_RUN=40591863306
MELONX_ARTIFACT=(12774198978,'f5502a45adae30ea6d20a92c282d0139f61fe37d779b04b26840530d91157354')
# The engine workflow keeps its 572 steps; only its push paths changed.
ENGINE_STEPS576=d572.ENGINE_STEPS572
# 576 adds no export and no engine literal; the 572 ones must remain.
EXPORTS576=d572.EXPORTS572
SYMBOLS576=d572.SYMBOLS572
CORE_TEXT576=d572.CORE_TEXT572
ENGINE576=set(tree.ENGINE576)
OLD=ROOT/'dist/melonx572engine'
NEW=ROOT/'dist/melonx'
# Python modules of 576 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in list(tree.FIX576)+list(tree.APP576) if p.endswith('.py'))
CHANGED576=list(tree.FIX576)+sorted(tree.APP576)
# What each adaptation must have put into the adapted engine source.
ADAPTED576={
 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs':['_detachedWarmUp = fromCache && warmUpInitialPipeline;',
  'if (_detachedWarmUp)','!_gd.BackgroundCompilationScheduler.TryCancelPipelineCompile(Volatile.Read(ref _initialPipelineCompileTask)))',
  'return; // Cancelled by Dispose or by the closing renderer.'],
 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs':['public bool TryCancelPipelineCompile(Task task)',
  'public bool TryCancel(Task task)'],
 'src/Ryujinx.Graphics.Vulkan/FramebufferParams.cs':['public bool GrowWithoutAttachments(uint width, uint height)'],
 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs':['private bool FitAttachmentlessFramebuffer()',
  'FramebufferParams = FramebufferParams?.Update(colors, depthStencil) ?? new FramebufferParams(Device, colors, depthStencil);\n            FitAttachmentlessFramebuffer();'],
 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs':['internal uint MaxFramebufferWidth =>'],
 'src/Ryujinx.Common/Logging/Logger.cs':['public static int ServiceCallTraceBudget;'],
 'src/Ryujinx.HLE/HOS/Services/IpcService.cs':['Logger.TraceServiceCall($"{GetType().Name}: {name}");'],
 'src/Ryujinx.Horizon/Sdk/Sf/Cmif/ServiceDispatchTableBase.cs':['Logger.TraceServiceCall($"{objectName}.{commandHandler.MethodName}");'],
 'src/Ryujinx.HLE/Loaders/Processes/ProcessResult.cs':['ProgramId == 0x010038B015560000UL ? 300 : 0'],
 'src/Ryujinx.HLE/HOS/Horizon.cs':['traced.Debugger.GetMinidump()']}

_active=[False]

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in CHANGED576:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_575():
 """The delivered 575 tree in place of the pinned 576 one: a scratch copy of
 the index with the 576 files at their 575 versions (the added adaptations
 absent) and this recipe removed, the same 576 files in the working tree,
 their Python modules and build number 575. The RPCS3 Core 575 and its
 installed identity are the same in both trees. The 576 bytes, modules, the
 index in use and the environment are restored on exit; a check already
 inside the 575 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_575()
 files={p:s for p,s in versions.items() if p in CHANGED576}
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
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d575.BUILD
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
 # Nothing of the 575 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 575 recipe, run on the delivered 575 tree."""
 with as_575():return function(*args,**kwargs)

_old=[False]
# Receipts this delivery's own steps write into dist/melonx that do not depend
# on the engine: the 575 to 564 recipes found them next to their engine.
CARRIED=d566.CARRIED

@contextlib.contextmanager
def old_engine():
 """The 572 engine's downloaded evidence in dist/melonx, where the 575, 573
 and 572 recipes read it, with the engine-independent receipts of this
 delivery's steps; the 576 engine's is put back on exit. Without a
 downloaded 572 engine (before the component download), nothing moves."""
 if _old[0] or not OLD.is_dir():
  yield
  return
 parked=ROOT/'dist/melonx576'
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
def as_575_engine():
 """The delivered 575 tree with its engine evidence: what the 575 recipe saw."""
 with old_engine(),as_575():yield

def validate_interface():
 return inherited(d575.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d575.host_evidence)

def engine_identity():
 identity=json.loads((NEW/'ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE,identity['host']
 return identity

def engine_evidence():
 """The downloaded 576 engine names exactly the pinned engine inputs (the
 three 576 adaptations among them), exports every 572 entry point, compiled
 every adaptation into its adapted source (the 576 ones and the 572, 566 and
 564 decoder, GC and texture pool ones), and passed the 572 engine checks
 again: session ownership, display, the simulator runtime, texture pool,
 journal, and the decoder test (upstream vs adapted) with the switch case."""
 identity=engine_identity()
 for name in EXPORTS576:assert name in identity['exports'],name
 assert ENGINE576|d572.ENGINE572|d566.ENGINE566|set(d564.ENGINE564)<=set(identity['adaptations'])
 for p,h in identity['adaptations'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 inputs=json.loads((NEW/'embedded-inputs.json').read_bytes())
 for p,h in inputs.items():assert sha(p)==h,p
 for p in sorted(ENGINE576)+['build-utils/melonx/adapt_jit_decoder.py','build-utils/melonx/adapt_gc.py',
                             'build-utils/melonx/adapt_texture_pool.py']:
  assert p in inputs,p
 with zipfile.ZipFile(NEW/'embedded-adapted-source.zip') as z:
  for name,texts in ADAPTED576.items():
   source=z.read(name).decode('utf-8-sig')
   for text in texts:assert source.count(text)==1,(name,text)
  decoder=z.read('src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs').decode('utf-8-sig')
  assert decoder.count('StartsFunction(memoryManager, block.EndAddress)')==1 and 'EndsWithTrap(block)' in decoder
  assert decoder.count('IsSkippedCodeReachable(memoryManager, block.EndAddress, jumpTarget, branchTargets)')==1
  project=z.read('src/Ryujinx.Library/Ryujinx.Library.csproj').decode('utf-8-sig')
  assert '"System.GC.ConserveMemory" Value="5"' in project and 'Value="9"' not in project
  pool=z.read('src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs').decode('utf-8-sig')
  assert pool.count('if (!MemoryManager.ValidateAddress(descriptor.UnpackAddress()))')==1
  for p,name in (('native/melonx/EmbeddedLaunchDiagnostics.cs','src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs'),
                 ('native/melonx/EmbeddedRuntime.cs','src/Ryujinx.Library/EmbeddedRuntime.cs')):
   assert z.read(name)==(ROOT/p).read_bytes(),p
 decoder=json.loads((NEW/'jit-decoder-checks.json').read_bytes())
 assert decoder['result']=='passed' and not decoder['failures'] and decoder['executed'] is False
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
  exports=EXPORTS576,adaptations=len(identity['adaptations']),adapted576=sorted(ADAPTED576),
  sessionCases=session['passedCases'],displaySummary=display['summary'].splitlines()[-1],
  simulatorSessions=smoke['homebrewSimulatorSessions'],
  jitDecoder={k:decoder[k]['switchCase'] for k in ('upstream','adapted')},gcConserveMemory=5,
  temporaryBootTrace='010038b015560000',physicalDeviceTested=False,gameTested=False)

def engine_run():
 """The engine run: the exact commit, its own workflow, every 572 engine step passed."""
 state=previous.api(f'actions/runs/{MELONX_RUN}')
 assert state['head_sha']==MELONX_SOURCE and state['path']==MELONX_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS576)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 575 contract, unchanged, on the delivered 575 tree.
 report=inherited(d575.source_contract)
 assert report['productTrees']==tree.product_trees_575(),report['productTrees']
 trees=tree.product_trees()
 # The engine is built by its own run; only the StikDebug removal changes product trees (lib, packages).
 assert {p for p in tree.TREES if trees[p]!=report['productTrees'][p]}=={'lib','packages'},trees
 # The pinned index differs from the delivered 575 tree by the 576 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_575()).splitlines())
 expected=set(CHANGED576)|set(tree.RECIPE)
 assert changed==expected,changed^expected
 for p in tree.FIX576:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p,source in tree.APP576.items():
  if p in tree.DELETED576:assert not (ROOT/p).exists(),p
  else:assert (ROOT/p).read_bytes()==at(source,p),p
 # The engine run built exactly these engine inputs.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566|d572.ENGINE572|ENGINE576):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 575 and the God of War III profile, unchanged, on the pinned tree.
 d575.native.source_contract()
 for p,h in d575.native.inputs().items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core_receipt()
 for p in d565.tree.FIX565:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build575=report['build'],source575Recipe=report['source'],
  source576=MELONX_SOURCE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  melonx572Source=MELONX572_SOURCE,melonx572Run=MELONX572_RUN,replaced576=tree.REPLACED,added576=tree.ADDED,
  sourceApp576=tree.SOURCE_APP576,app576=sorted(tree.APP576),deleted576=tree.DELETED576,stikDebugFallbackRemoved=True,
  changed576=sorted(changed),pinnedFiles=kept,productTrees=trees,productTrees575=report['productTrees'],
  physicalDeviceTested=False,gameTested=False)

def payload_575(scratch):
 """The engine entries package_runtime writes for the 572 engine on the 575
 tree (macOS: install_name_tool, vtool and otool), in a scratch application."""
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import package_runtime as runtime
 saved=runtime.CORE,runtime.FRAMEWORKS
 app=Path(scratch)/'app';app.mkdir()
 try:
  with as_575_engine():
   runtime.CORE=NEW;runtime.FRAMEWORKS=Path(scratch)/'Frameworks'
   runtime.materialize();runtime.embed(app)
   identity=json.loads((app/'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']
   assert identity['host']==MELONX572_SOURCE,identity['host']
 finally:
  runtime.CORE,runtime.FRAMEWORKS=saved
 # The scratch packaging receipt belongs to the 572 artifact; never keep it there.
 (OLD/'packaging-identity.json').unlink(missing_ok=True)
 return app

def derived_ipa(ipa):
 """This IPA with the 572 engine payload of the 575 tree in place of its own:
 the application the 575 recipe validated, but for this build's other files.
 Cached per IPA digest."""
 ipa=Path(ipa);digest=hashlib.sha256(ipa.read_bytes()).hexdigest()
 out=ROOT/'build/derived575'/f'{digest}.ipa'
 if out.is_file():return out
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as scratch:
  app=payload_575(scratch)
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
 """The actual IPA carries the 576 engine as package_runtime packaged it and,
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
  for name in SYMBOLS576:assert name in symbols,name
  for text in CORE_TEXT576:assert audio.contains(core,text),text
  for p,h in identity['adaptations'].items():assert sha(p)==h,p
  others=[n for n in real.namelist() if not engine_entry(n,root)]
  assert others==[n for n in old.namelist() if not engine_entry(n,root)]
  for name in others:assert real.read(name)==old.read(name),name
  stale=json.loads(old.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert stale['host']==MELONX572_SOURCE and stale['sha256']!=identity['sha256']
 return dict(engineSource=MELONX_SOURCE,engineRun=MELONX_RUN,coreSHA256=identity['sha256'],
  packagedCoreFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],engine572Source=MELONX572_SOURCE,
  engine572SHA256=stale['sha256'],otherEntriesEqualTo575Equivalent=len(others),symbols=SYMBOLS576)

def retain_checks():
 """The 575 receipts stay bound to the delivered 575 tree (and its 573 to 554 views); the 576 engine run to the pinned tree."""
 inherited(d575.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'melonx-warm576-engine-run.json').write_text(json.dumps(engine_run(),indent=2)+'\n')
 print('Bound the 575 receipts to the delivered 575 tree and the 576 engine run to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation576.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 575 binding on the delivered 575 tree (its own views in turn), then the pinned tree.
  views=[d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.inherited,d565.inherited,d564.inherited,
         d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,d558.inherited,d557.inherited]
  for depth in (14,12,11,10,9,8,7,6,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX572_ARTIFACT,'dist/melonx572engine'),
                       d549.download(MELONX566_ARTIFACT,'dist/melonx566engine'),d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),
                       d549.download(MELONX563_ARTIFACT,'dist/melonx563'),d549.download(HOST_ARTIFACT,'dist/melonx-host'),
                       d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558, 564, 566 and 572 engines and the 562 host on the delivered 575 tree, as 575 bound them; then the 576 engine.
  with old_engine():
   with d572.old_engine():
    with d566.old_engine():
     with d564.old_engine():
      report['engine563Evidence']=inherited(d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.inherited,
                                            d565.inherited,d564.inherited,d563.inherited,d562.inherited,d558.engine_evidence)
     report['engine564Evidence']=inherited(d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.inherited,
                                           d565.inherited,d564.engine_evidence)
    report['engine566Evidence']=inherited(d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.engine_evidence)
   report['engine572Evidence']=inherited(d575.inherited,d573.inherited,d572.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=engine_run()
  report['engine572']=d572.engine_run()
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
