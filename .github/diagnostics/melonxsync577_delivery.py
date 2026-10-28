"""Private577: the MeloNX engine of cfa5116 (kernel wakeups of condition variables and address arbiters, the GC's memory-load threshold, a 1 GiB code arena for Hogwarts Legacy with its update, a pipeline cache kept per title; FFT boot trace removed; its own engine run from afd0d4b) and the controller relay change of d1f7b8d on the delivered 576 product tree.

577 ships the 576 product (the 575 product with the MeloNX engine 301e0f8,
the StikDebug fallback removal of 504f9c0 and the interface fixes of 48b9865;
RPCS3 Core 575, God of War III without the 30 fps limiter, MeloNX keyboard
and L3/R3) and swaps the MeloNX engine: the 576 engine becomes the one built
and tested from afd0d4b, whose sources change no file compiled into the
application but two native sources compiled into the engine (four engine
adaptations, the trace removed, the adaptation list, the engine workflow's
push paths, the launch preflight's code arena request and its test fixture).
The application also gains d1f7b8d: MeloNXInputRouter takes the pad's
profile-wide handler while a game owns the controller (one Swift file).
The 576 recipe runs unchanged on the delivered 576 tree, which as_576() puts
in place of the pinned 577 one for each inherited check (a scratch index, the
577 files' 576 versions in the working tree, the added adaptations absent,
the deleted trace restored, and BUILD_NUMBER 576, all restored afterwards),
with the 576 engine's downloaded evidence in dist/melonx (old_engine()). The
inherited IPA validators check derived_ipa(): this IPA with the engine payload
that package_runtime produces for the 576 engine on the 576 tree, every other
entry byte for byte; the 576 recipe under them derives its own
575-equivalent in turn. The 577 engine, its run and its receipts are checked
on the pinned 577 tree and on the actual IPA. The RPCS3 Core is the 575 one
in both trees. The source contract is computed once per job and reused on
the same bytes (build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,shutil,sys,tempfile,zipfile
from pathlib import Path
import melonxsync577_tree as tree
import melonxwarm576_delivery as d576
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='577'
HOST_TREE=d576.HOST_TREE
# The RPCS3 Core 575, the MeloNX hosts (558, 562) and every other shipped file are the 576 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'CORE_SOURCE','CORE_RUN','CORE_WORKFLOW','CORE_STEPS','validate_rpc_core_identity','validate_rpc_core_pin',
             'core_receipt','core_run','INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN','CORE563_SOURCE','CORE563_RUN',
             'CORE565_SOURCE','CORE565_RUN','CORE567_SOURCE','CORE567_RUN','CORE569_SOURCE','CORE569_RUN',
             'CORE571_SOURCE','CORE571_RUN','CORE573_SOURCE','CORE573_RUN','MELONX_WORKFLOW',
             'MELONX566_SOURCE','MELONX566_RUN','MELONX566_ARTIFACT','MELONX564_SOURCE','MELONX564_RUN',
             'MELONX564_ARTIFACT','MELONX563_SOURCE','MELONX563_RUN','MELONX563_ARTIFACT',
             'MELONX572_SOURCE','MELONX572_RUN','MELONX572_ARTIFACT','ENGINE_PAYLOAD','engine_entry','sha'):
 globals()[name]=getattr(d576,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565,d566,d567,d572,d573,d575=(d576.previous,
 d576.previous546,d576.d549,d576.d557,d576.d558,d576.d559,d576.d560,d576.d561,d576.d562,d576.d563,d576.d564,
 d576.d565,d576.d566,d576.d567,d576.d572,d576.d573,d576.d575)
# The engine the 576 receipts are bound to.
MELONX576_SOURCE,MELONX576_RUN,MELONX576_ARTIFACT=d576.MELONX_SOURCE,d576.MELONX_RUN,d576.MELONX_ARTIFACT
assert MELONX576_SOURCE==tree.SOURCE576
# Engine built and tested from afd0d4b (cfa5116 and its test fixture), taken by ID and digest.
MELONX_SOURCE=tree.SOURCE577
MELONX_RUN=40610510834
MELONX_ARTIFACT=(12782599009,'475d64c84250bb0e044d652cd49dba445741f4678e250d6aeabc89c46bfc65ea')
# The engine workflow keeps its 572 steps; only its push paths changed.
ENGINE_STEPS577=d576.ENGINE_STEPS576
# 577 adds no export and no journal literal; the 572 ones must remain.
EXPORTS577=d576.EXPORTS576
SYMBOLS577=d576.SYMBOLS576
CORE_TEXT577=d576.CORE_TEXT576
ENGINE577=set(tree.ENGINE577)
SHIPPED577=set(tree.SHIPPED577)
OLD=ROOT/'dist/melonx576engine'
NEW=ROOT/'dist/melonx'
# Python modules of 577 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in list(tree.FIX577)+list(tree.APP577) if p.endswith('.py'))
CHANGED577=list(tree.FIX577)+sorted(tree.APP577)
# What each 577 adaptation must have put into the adapted engine source, and how often.
ADAPTED577={
 'src/Ryujinx.HLE/HOS/Kernel/Threading/KThread.cs':{'public List<KThread> SyncWaitList { get; set; }':1,
  'public void LeaveSyncWaitList()':1},
 'src/Ryujinx.HLE/HOS/Kernel/Threading/KAddressArbiter.cs':{
  'private void InsertWaiter(Dictionary<ulong, List<KThread>> waiters, ulong key, KThread thread)':1,
  'addend = count <= 0 || waitingCount <= count ? -1 : 0;':1,'currentThread.LeaveSyncWaitList();':3},
 'src/Ryujinx.Library/Ryujinx.Library.csproj':{
  '<RuntimeHostConfigurationOption Include="System.GC.HighMemoryPercent" Value="99" />':1,
  '<RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="5" />':1},
 'src/Ryujinx.Cpu/LightningJit/Cache/DualMappedNoWxCache.cs':{
  'ulong size = Math.Max(DefaultCacheSize, DualMappedMemory.RequestedArenaSize);':1,
  'catch (Exception) when (size > DefaultCacheSize)':1,'internal static ulong MappedSize => _sharedCacheAlloc?.Size ?? 0;':1},
 'src/Ryujinx.Cpu/LightningJit/Translator.cs':{'public static ulong RequestedArenaSize { get; set; }':1,
  'public static ulong ArenaSize => DualMappedNoWxCache.MappedSize;':1},
 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs':{'private const long TotalCacheBudget = 512L * 1024 * 1024;':1,
  'string title = VulkanRenderer.PipelineCacheScope?.Invoke();':1,'if (size == state.SavedBytes)':1,
  'state.SavedBytes = written;':1},
 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs':{'public static Func<string> PipelineCacheScope { get; set; }':1},
 'src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs':{
  'SetEnvironmentVariableNoCaching("MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM", "3");':1,
  'SetEnvironmentVariableNoCaching("MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM", "0");':1},
 'src/Ryujinx.Library/Library.cs':{'VulkanRenderer.PipelineCacheScope ??= () => GraphicsConfig.TitleId;':1}}
# The temporary FFT boot trace of 576 (cfa5116 removes it); the other 576
# adaptations (shader-cache warm-ups, attachment-less framebuffers) remain.
TRACE576={name:texts for name,texts in d576.ADAPTED576.items() if name in (
 'src/Ryujinx.Common/Logging/Logger.cs','src/Ryujinx.HLE/HOS/Services/IpcService.cs',
 'src/Ryujinx.Horizon/Sdk/Sf/Cmif/ServiceDispatchTableBase.cs','src/Ryujinx.HLE/Loaders/Processes/ProcessResult.cs',
 'src/Ryujinx.HLE/HOS/Horizon.cs')}
KEPT576={name:texts for name,texts in d576.ADAPTED576.items() if name not in TRACE576}
assert len(TRACE576)==5 and len(KEPT576)==5
# Native sources compiled into the engine and their place in the adapted source.
NATIVE={'native/melonx/EmbeddedLaunchDiagnostics.cs':'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs',
        'native/melonx/EmbeddedLaunchPreflight.cs':'src/Ryujinx.Library/EmbeddedLaunchPreflight.cs',
        'native/melonx/EmbeddedRuntime.cs':'src/Ryujinx.Library/EmbeddedRuntime.cs'}
assert SHIPPED577<=set(NATIVE)

_active=[False]

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in CHANGED577:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_576():
 """The delivered 576 tree in place of the pinned 577 one: a scratch copy of
 the index with the 577 files at their 576 versions (the added adaptations
 absent, the FFT trace back) and this recipe removed, the same 577 files in
 the working tree, their Python modules and build number 576. The RPCS3 Core
 575 and its installed identity are the same in both trees. The 577 bytes,
 modules, the index in use and the environment are restored on exit; a check
 already inside the 576 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_576()
 files={p:s for p,s in versions.items() if p in CHANGED577}
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
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d576.BUILD
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
 # Nothing of the 576 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 576 recipe, run on the delivered 576 tree."""
 with as_576():return function(*args,**kwargs)

_old=[False]
# Receipts this delivery's own steps write into dist/melonx that do not depend
# on the engine: the 576 to 564 recipes found them next to their engine.
CARRIED=d576.CARRIED

@contextlib.contextmanager
def old_engine():
 """The 576 engine's downloaded evidence in dist/melonx, where the 576
 recipe reads it, with the engine-independent receipts of this delivery's
 steps; the 577 engine's is put back on exit. Without a downloaded 576
 engine (before the component download), nothing moves."""
 if _old[0] or not OLD.is_dir():
  yield
  return
 parked=ROOT/'dist/melonx577'
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
def as_576_engine():
 """The delivered 576 tree with its engine evidence: what the 576 recipe saw."""
 with old_engine(),as_576():yield

def validate_interface():
 return inherited(d576.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d576.host_evidence)

def engine_identity():
 identity=json.loads((NEW/'ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE,identity['host']
 return identity

def engine_evidence():
 """The downloaded 577 engine names exactly the pinned engine inputs (the
 four 577 adaptations and the two changed native sources among them, the
 trace adaptation no longer), exports every 572 entry point, compiled every
 adaptation into its adapted source (the 577 ones; the 576 warm-up and
 framebuffer ones; the 566 and 564 decoder, GC and texture pool ones; none of
 the FFT trace), and passed the 572 engine checks again: session ownership,
 display, the simulator runtime, texture pool, journal, and the decoder test
 (upstream vs adapted) with the switch case."""
 identity=engine_identity()
 for name in EXPORTS577:assert name in identity['exports'],name
 kept=(d576.ENGINE576-set(tree.DELETED577))|d572.ENGINE572|d566.ENGINE566|set(d564.ENGINE564)
 assert ENGINE577|kept<=set(identity['adaptations']),sorted((ENGINE577|kept)-set(identity['adaptations']))
 for p,h in identity['adaptations'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 inputs=json.loads((NEW/'embedded-inputs.json').read_bytes())
 for p,h in inputs.items():assert sha(p)==h,p
 for p in sorted(ENGINE577)+['build-utils/melonx/adapt_jit_decoder.py','build-utils/melonx/adapt_texture_pool.py',
                             'build-utils/melonx/adapt_shader_warmup.py','build-utils/melonx/adapt_attachmentless_framebuffer.py']:
  assert p in inputs,p
 for p in tree.DELETED577:assert p not in inputs and p not in identity['adaptations'] and not (ROOT/p).exists(),p
 with zipfile.ZipFile(NEW/'embedded-adapted-source.zip') as z:
  names=set(z.namelist())
  for name,texts in ADAPTED577.items():
   source=z.read(name).decode('utf-8-sig')
   for text,count in texts.items():assert source.count(text)==count,(name,text,source.count(text))
  for name,texts in KEPT576.items():
   source=z.read(name).decode('utf-8-sig')
   for text in texts:assert source.count(text)==1,(name,text)
  for name,texts in TRACE576.items():
   if name in names:
    source=z.read(name).decode('utf-8-sig')
    for text in texts:assert text not in source,(name,text)
  decoder=z.read('src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs').decode('utf-8-sig')
  assert decoder.count('StartsFunction(memoryManager, block.EndAddress)')==1 and 'EndsWithTrap(block)' in decoder
  assert decoder.count('IsSkippedCodeReachable(memoryManager, block.EndAddress, jumpTarget, branchTargets)')==1
  project=z.read('src/Ryujinx.Library/Ryujinx.Library.csproj').decode('utf-8-sig')
  assert 'Value="9"' not in project
  pool=z.read('src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs').decode('utf-8-sig')
  assert pool.count('if (!MemoryManager.ValidateAddress(descriptor.UnpackAddress()))')==1
  for p,name in NATIVE.items():
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
  exports=EXPORTS577,adaptations=len(identity['adaptations']),adapted577=sorted(ADAPTED577),kept576=sorted(KEPT576),
  removedTrace576=sorted(TRACE576),shipped577=sorted(SHIPPED577),sessionCases=session['passedCases'],
  displaySummary=display['summary'].splitlines()[-1],simulatorSessions=smoke['homebrewSimulatorSessions'],
  jitDecoder={k:decoder[k]['switchCase'] for k in ('upstream','adapted')},gcConserveMemory=5,gcHighMemoryPercent=99,
  hogwartsUpdateCodeArenaMiB=1024,pipelineCacheMainBudgetMiB=384,physicalDeviceTested=False,gameTested=False)

def engine_run():
 """The engine run: the exact commit, its own workflow, every 572 engine step passed."""
 state=previous.api(f'actions/runs/{MELONX_RUN}')
 assert state['head_sha']==MELONX_SOURCE and state['path']==MELONX_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS577)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 576 contract, unchanged, on the delivered 576 tree.
 report=inherited(d576.source_contract)
 assert report['productTrees']==tree.product_trees_576(),report['productTrees']
 trees=tree.product_trees()
 # The engine is built by its own run; its native sources and the controller relay change product trees.
 assert {p for p in tree.TREES if trees[p]!=report['productTrees'][p]}=={'native','packages'},trees
 # The pinned index differs from the delivered 576 tree by the 577 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_576()).splitlines())
 expected=set(CHANGED577)|set(tree.RECIPE)
 assert changed==expected,changed^expected
 for p in tree.FIX577:
  if p in tree.DELETED577:assert not (ROOT/p).exists(),p
  else:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p,source in tree.APP577.items():assert (ROOT/p).read_bytes()==at(source,p),p
 # The engine run built exactly these engine inputs.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566|d572.ENGINE572
                 |(d576.ENGINE576-set(tree.DELETED577))|ENGINE577):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 575 and the God of War III profile, unchanged, on the pinned tree.
 d575.native.source_contract()
 for p,h in d575.native.inputs().items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core_receipt()
 for p in d565.tree.FIX565:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build576=report['build'],source576Recipe=report['source'],
  source577=MELONX_SOURCE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  melonx576Source=MELONX576_SOURCE,melonx576Run=MELONX576_RUN,engineCommits577=tree.ENGINE_COMMITS,
  replaced577=tree.REPLACED,added577=tree.ADDED,deleted577=tree.DELETED577,shipped577=sorted(SHIPPED577),
  sourceApp577=tree.SOURCE_APP577,app577=sorted(tree.APP577),controllerRelay577=True,
  changed577=sorted(changed),pinnedFiles=kept,productTrees=trees,productTrees576=report['productTrees'],
  physicalDeviceTested=False,gameTested=False)

def payload_576(scratch):
 """The engine entries package_runtime writes for the 576 engine on the 576
 tree (macOS: install_name_tool, vtool and otool), in a scratch application."""
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import package_runtime as runtime
 saved=runtime.CORE,runtime.FRAMEWORKS
 app=Path(scratch)/'app';app.mkdir()
 try:
  with as_576_engine():
   runtime.CORE=NEW;runtime.FRAMEWORKS=Path(scratch)/'Frameworks'
   runtime.materialize();runtime.embed(app)
   identity=json.loads((app/'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']
   assert identity['host']==MELONX576_SOURCE,identity['host']
 finally:
  runtime.CORE,runtime.FRAMEWORKS=saved
 # The scratch packaging receipt belongs to the 576 artifact; never keep it there.
 (OLD/'packaging-identity.json').unlink(missing_ok=True)
 return app

def derived_ipa(ipa):
 """This IPA with the 576 engine payload of the 576 tree in place of its own:
 the application the 576 recipe validated, but for this build's other files.
 Cached per IPA digest."""
 ipa=Path(ipa);digest=hashlib.sha256(ipa.read_bytes()).hexdigest()
 out=ROOT/'build/derived576'/f'{digest}.ipa'
 if out.is_file():return out
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as scratch:
  app=payload_576(scratch)
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
    target.writestr(zipfile.ZipInfo(root+relative,date_time=(2026,10,28,0,0,0)),payload[relative],zipfile.ZIP_DEFLATED)
 out.with_suffix('.tmp').rename(out)
 return out

def validate_engine_ipa(ipa):
 """The actual IPA carries the 577 engine as package_runtime packaged it and,
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
  for name in SYMBOLS577:assert name in symbols,name
  for text in CORE_TEXT577:assert audio.contains(core,text),text
  for p,h in identity['adaptations'].items():assert sha(p)==h,p
  others=[n for n in real.namelist() if not engine_entry(n,root)]
  assert others==[n for n in old.namelist() if not engine_entry(n,root)]
  for name in others:assert real.read(name)==old.read(name),name
  stale=json.loads(old.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert stale['host']==MELONX576_SOURCE and stale['sha256']!=identity['sha256']
 return dict(engineSource=MELONX_SOURCE,engineRun=MELONX_RUN,coreSHA256=identity['sha256'],
  packagedCoreFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],engine576Source=MELONX576_SOURCE,
  engine576SHA256=stale['sha256'],otherEntriesEqualTo576Equivalent=len(others),symbols=SYMBOLS577)

def retain_checks():
 """The 576 receipts stay bound to the delivered 576 tree (and its 575 to 554 views); the 577 engine run to the pinned tree."""
 inherited(d576.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'melonx-sync577-engine-run.json').write_text(json.dumps(engine_run(),indent=2)+'\n')
 print('Bound the 576 receipts to the delivered 576 tree and the 577 engine run to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation577.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 576 binding on the delivered 576 tree (its own views in turn), then the pinned tree.
  views=[d576.inherited,d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.inherited,d565.inherited,
         d564.inherited,d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,d558.inherited,
         d557.inherited]
  for depth in (15,13,12,11,10,9,8,7,6,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX576_ARTIFACT,'dist/melonx576engine'),
                       d549.download(MELONX572_ARTIFACT,'dist/melonx572engine'),d549.download(MELONX566_ARTIFACT,'dist/melonx566engine'),
                       d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),d549.download(MELONX563_ARTIFACT,'dist/melonx563'),
                       d549.download(HOST_ARTIFACT,'dist/melonx-host'),d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),
                       d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558, 564, 566, 572 and 576 engines and the 562 host on the delivered 576 tree, as 576 bound them; then the 577 engine.
  with old_engine():
   with d576.old_engine():
    with d572.old_engine():
     with d566.old_engine():
      with d564.old_engine():
       report['engine563Evidence']=inherited(d576.inherited,d575.inherited,d573.inherited,d572.inherited,d567.inherited,
                                             d566.inherited,d565.inherited,d564.inherited,d563.inherited,d562.inherited,
                                             d558.engine_evidence)
      report['engine564Evidence']=inherited(d576.inherited,d575.inherited,d573.inherited,d572.inherited,d567.inherited,
                                            d566.inherited,d565.inherited,d564.engine_evidence)
     report['engine566Evidence']=inherited(d576.inherited,d575.inherited,d573.inherited,d572.inherited,d567.inherited,
                                           d566.engine_evidence)
    report['engine572Evidence']=inherited(d576.inherited,d575.inherited,d573.inherited,d572.engine_evidence)
   report['engine576Evidence']=inherited(d576.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=engine_run()
  report['engine576']=d576.engine_run()
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
