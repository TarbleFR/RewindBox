"""Private586: the MeloNX engine of 75a13f7 (with 6314127, d8cd5f6, ac16f1c and 6edcd57: the GPU thread no longer allocates an array per copy, large MemoryOwner arrays wait as spares outside the upstream pool, GPFIFO words come from the runtime's shared pool; JIT units laid out off word alignment ignore the entry stops and the jump look-ahead; the render thread blocks instead of spinning while a new program compiles, and depth-only passes hit their warm-up; a queued texture write-back skips guest memory unmapped since; bindless handles read through SHFL bind; its own engine run), the Cheats & Enhancements page and catalogues (b451b10 to d0f27cc) and the RPCS3 Core 587 (a8a7ce1, its own Core run) on the delivered 585 product tree.

586 ships the 585 product (the 583 product with the RPCS3 Core 585: the 582
product with the RPCS3 Core 583; the 581 product with the MeloNX engine of
e55ca25 and the Switch discovery fix of 32a0da6/63fdb7e) and changes three
things. The MeloNX engine: the 582 engine becomes the one built and tested
from 75a13f7, whose sources change no file compiled into the application.
The RPCS3 Core: the 585 Core becomes the 587 one (MoltenVK asynchronous
submits with an encode barrier, the MetalFX handoff ordered, a boot
canary), with the profile of 147af30 (God of War III asynchronous submits
Automatic, Black Ops II relaxed SPU reservations), bound through
rpcs3cell587_delivery_core. The application: the Cheats & Enhancements
page, its service, adapters and strings (Dart), the bundled enhancements
index, the catalogues (the unified cheat index after the 28 October
withdrawal of the unlicensed 60 FPS programs) and the cheat catalogue's
refusal of withheld programs (Objective-C), with their notices.
The 585 recipe runs unchanged on the delivered 585 tree, which as_585() puts
in place of the pinned 586 one for each inherited check (a scratch index,
the 586 files' 585 versions in the working tree, the added files and the
Core 587 documentation absent, the installed 587 Core identity set aside,
and BUILD_NUMBER 585, all restored afterwards), with the 582 engine's
downloaded evidence in dist/melonx (old_engine()). The inherited IPA
validators check derived_ipa(): this IPA with the engine payload that
package_runtime produces for the 582 engine on the 585 tree, every other
entry byte for byte. The 586 engine, its run and its receipts, the Core 587
and its receipt, and the Cheats & Enhancements files are checked on the
pinned 586 tree and on the actual IPA. The source contract is computed once
per job and reused on the same bytes (build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,shutil,sys,tempfile,zipfile
from pathlib import Path
import rewind586_tree as tree
import rpcs3cell585_delivery as d585
import rpcs3cell587_delivery_core as core587
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='586'
HOST_TREE=d585.HOST_TREE
# The MeloNX hosts (558, 562) and every shipped file but the 586 ones are the 585 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN','CORE563_SOURCE','CORE563_RUN',
             'CORE565_SOURCE','CORE565_RUN','CORE567_SOURCE','CORE567_RUN','CORE569_SOURCE','CORE569_RUN',
             'CORE571_SOURCE','CORE571_RUN','CORE573_SOURCE','CORE573_RUN','CORE575_SOURCE','CORE575_RUN',
             'CORE579_SOURCE','CORE579_RUN','CORE581_SOURCE','CORE581_RUN','CORE583_SOURCE','CORE583_RUN',
             'MELONX_WORKFLOW','MELONX577_SOURCE','MELONX577_RUN','MELONX577_ARTIFACT','MELONX576_SOURCE',
             'MELONX576_RUN','MELONX576_ARTIFACT','MELONX572_SOURCE','MELONX572_RUN','MELONX572_ARTIFACT',
             'MELONX566_SOURCE','MELONX566_RUN','MELONX566_ARTIFACT','MELONX564_SOURCE','MELONX564_RUN',
             'MELONX564_ARTIFACT','MELONX563_SOURCE','MELONX563_RUN','MELONX563_ARTIFACT','ENGINE577','ENGINE582',
             'ENGINE_PAYLOAD','engine_entry','sha'):
 globals()[name]=getattr(d585,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565,d566,d567,d572,d573,d575,d576,d577,d579=(
 d585.previous,d585.previous546,d585.d549,d585.d557,d585.d558,d585.d559,d585.d560,d585.d561,d585.d562,d585.d563,
 d585.d564,d585.d565,d585.d566,d585.d567,d585.d572,d585.d573,d585.d575,d585.d576,d585.d577,d585.d579)
d581,d582,d583=d585.d581,d585.d582,d585.d583
# The RPCS3 Core 587 (a8a7ce1, its own Core run) in place of the Core 585 the 585 receipts are bound to.
CORE585_SOURCE,CORE585_RUN=d585.CORE_SOURCE,d585.CORE_RUN
for name in ('CORE_SOURCE','CORE_RUN','CORE_WORKFLOW','CORE_STEPS','validate_rpc_core_identity','validate_rpc_core_pin',
             'core_receipt','core_run','CORE587_MARKERS'):
 globals()[name]=getattr(core587,name)
native=core587.native
assert CORE_SOURCE==tree.SOURCE587 and CORE585_SOURCE==tree.SOURCE585 and core587.CORE585_SOURCE==CORE585_SOURCE
assert core587.CELL587==tree.CELL587 and core587.PROFILE587==sorted(tree.PROFILE587)
assert set(tree.PROFILE587.values())=={core587.PROFILE_SOURCE}
# The engine the 585, 583 and 582 receipts are bound to.
MELONX582_SOURCE,MELONX582_RUN,MELONX582_ARTIFACT=d585.MELONX_SOURCE,d585.MELONX_RUN,d585.MELONX_ARTIFACT
assert MELONX582_SOURCE==d582.MELONX_SOURCE==tree.SOURCE582
# Engine built and tested from 75a13f7 (6314127, d8cd5f6, ac16f1c, 6edcd57 and 75a13f7), taken by ID and digest.
MELONX_SOURCE=tree.SOURCE586
MELONX_RUN=40734346962
MELONX_ARTIFACT=(12838535262,'ad2905b87263933e25d5bdea39d1b467dfaf462dd3df7b66934e38b04501c6dd')
# The engine workflow is the one of 577, unchanged: the same steps.
ENGINE_STEPS586=d582.ENGINE_STEPS582
# 586 adds no export and no journal literal; the 572 ones must remain.
EXPORTS586=d582.EXPORTS582
SYMBOLS586=d582.SYMBOLS582
CORE_TEXT586=d582.CORE_TEXT582
ENGINE586=set(tree.ENGINE586)
OLD=ROOT/'dist/melonx582engine'
NEW=ROOT/'dist/melonx'
# Python modules of 586 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in tree.CHANGED if p.endswith('.py'))
assert 'rpcs3cell587_core' in MODULES
CHANGED586=list(tree.CHANGED)
DECODER=d582.DECODER
# What the 586 adaptations must have put into the adapted engine source, and how often.
ADAPTED586={
 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs':{'private byte[] _destinationScratch;':1,
  'private Span<byte> DestinationScratch(int size)':1,'Span<byte> dstSpan = DestinationScratch(dstSize);':1,
  'memoryManager.GetSpan(dstGpuVa + (ulong)dstBaseOffset, dstSize).CopyTo(dstSpan);':1,
  'memoryManager.GetSpan(dstGpuVa + (ulong)dstBaseOffset, dstSize).ToArray();':0},
 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs':{
  'System.Buffers.ArrayPool<int>.Shared;':1,'ArrayPool<int>.Create(':0,'Words = _wordPool.Rent(words.Length);':1,
  'new ReadOnlySpan<int>(Words, 0, (int)EntryCount)':1,'_wordPool.Return(entry.Words);':1,
  'GetWords(memoryManager, true).ToArray();':0},
 'src/Ryujinx.Common/Memory/MemoryOwner.cs':{'private const long MinSpareBytes = 85000;':1,
  'private const long MaxSpareBytes = 64L * 1024 * 1024;':1,'private const int SpareIdleMilliseconds = 3000;':1,
  'KeepSpareLocked(holder);':1,'DropSparesLocked(h.Array!.Length);':1,'_pool[index] = spare;':1,
  '(_spareTimer ??= new Timer(ReleaseIdleSpares)).Change(SpareIdleMilliseconds, Timeout.Infinite);':1,
  '_pool.Remove(':0,'MaxPooledBytes':0,'OldestLocked':0},
 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs':{
  'private const int SpanPoolBytes = 32 * 1024 * 1024;':1,'private const int SpanPoolBytes = 8 * 1024 * 1024;':0},
 'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ProgramQueue.cs':{
  'private static bool WaitForLink(IProgram program)':1,'if (WaitForLink(program.Base))':1,
  'return program.CheckProgramLink(true) != ProgramLinkStatus.Incomplete;':1},
 'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs':{
  'pipeline.Internal.LogicOpsAllowed = maxColorAttachmentIndex < 0 || !allFormatsFloatOrSrgb;':1,
  'pipeline.Internal.LogicOpsAllowed = attachmentCount == 0 || !allFormatsFloatOrSrgb;':0},
 DECODER:{'if ((end & 3UL) != 0 || !code.IsMapped(end))':1,'|| (_unitAddress & 3UL) != 0)':1,
  '// hardware) ignores them.':1},
 'src/Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessToArray.cs':{'Operation handleShuffle = null;':1,
  'indexMin = shuffledIndex;':1,'Operand bindlessHandle = Utils.FindLastOperation(texOp.GetSource(0), block);':0},
 'src/Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs':{
  'private static string DescribeHandle(Operand operand, int depth)':1,
  '// A handle read from another quad lane (SHFL in a manual textureGrad) comes from the':1,
  'if (bindlessHandle.AsgOp is Operation shuffleOp && shuffleOp.Inst == Instruction.Shuffle)':2},
 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs':{
  'private const uint CodeGenVersion = 7353 + 0x5242_0001;':1},
 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs':{'private bool SlicesMapped(int sliceStart, int sliceEnd)':1,
  'if (isGpuThread && !SlicesMapped(handle.BaseSlice, handle.BaseSlice + handle.SliceCount))':1,
  'Texture flush skipped: its guest memory was unmapped before the queued write-back.':1,
  'if (!_physicalMemory.IsMapped(page))':1}}
# The 582 entry-stop markers, but for the 572 look-ahead's unmapped check, which 586 widens.
MARKERS582={name:{text:count for text,count in texts.items() if text!='if (!code.IsMapped(end))'}
            for name,texts in d582.ADAPTED582.items()}
# A page that ends with a call, read as zeros past it (HostTracked on iOS): upstream decodes 10,000
# instructions into it, the adapted unit ends before it.
SILENT586=('silentUnmappedAfterCall',10000,1024)
# Units laid out 1-3 bytes off word alignment next to an unmapped page: decoded and compiled as upstream
# (a jump look-ahead case: 3 instructions, compile rejected by the table; an entry-stop case: 4 compiled).
MISALIGNED586={f'misalignedJump{shift}':{'decoded':3,'truncated':False,'compileThrows':'ArgumentException'}
               for shift in (1,2,3)}
MISALIGNED586.update({f'misalignedEntry{shift}':{'decoded':4,'truncated':False,'guestInstructions':4} for shift in (1,2,3)})

_active=[False]
# The 585 version of each 586 file (None when absent): fixed for the job, read once.
_bytes585={}

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in CHANGED586:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

def _version585(p,source):
 # The 585 tree carries no Core 587 documentation.
 if p in tree.CORE_DOCS587:return None
 if p not in _bytes585:_bytes585[p]=None if source is None else at(source,p)
 return _bytes585[p]

@contextlib.contextmanager
def as_585():
 """The delivered 585 tree in place of the pinned 586 one: a scratch copy of
 the index with the 586 files at their 585 versions (the added files and
 the Core 587 documentation absent) and this recipe removed, the same files
 in the working tree, their Python modules and build number 585. The
 installed 587 Core identity is set aside: the 585 recipe checks an
 installed identity against the 585 Core when one is present, and this one
 checks it against 587. The 586 bytes, file modes, modules, the identity,
 the index in use and the environment are restored on exit; a check already
 inside the 585 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_585()
 files={p:s for p,s in versions.items() if p in CHANGED586 or p in tree.CORE_DOCS587}
 saved={p:(ROOT/p).read_bytes() if (ROOT/p).is_file() else None for p in files}
 modes={p:(ROOT/p).stat().st_mode for p in files if (ROOT/p).is_file()}
 modules={name:sys.modules[name] for name in MODULES if name in sys.modules}
 installed=INSTALLED.read_bytes() if INSTALLED.is_file() else None
 env={k:os.environ.get(k) for k in ('GIT_INDEX_FILE','BUILD_NUMBER')}
 with tempfile.TemporaryDirectory() as scratch:
  index=os.path.join(scratch,'index')
  tree.index_with(versions,index)
  try:
   for p,source in files.items():
    target=ROOT/p;data=_version585(p,source)
    if data is None:target.unlink(missing_ok=True)
    else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
   _forget(MODULES)
   INSTALLED.unlink(missing_ok=True)
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d585.BUILD
   _active[0]=True
   yield
  finally:
   _active[0]=False
   for k,v in env.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
   for p,data in saved.items():
    if data is None:(ROOT/p).unlink(missing_ok=True)
    else:(ROOT/p).parent.mkdir(parents=True,exist_ok=True);(ROOT/p).write_bytes(data);os.chmod(ROOT/p,modes[p])
   _forget(MODULES)
   sys.modules.update(modules)
   if installed is not None:INSTALLED.write_bytes(installed)
 # Nothing of the 585 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
  assert data is None or (ROOT/p).stat().st_mode==modes[p],p
 assert (INSTALLED.read_bytes() if INSTALLED.is_file() else None)==installed
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 585 recipe, run on the delivered 585 tree."""
 with as_585():return function(*args,**kwargs)

_old=[False]
# Receipts this delivery's own steps write into dist/melonx that do not depend
# on the engine: the 585 to 564 recipes found them next to their engine.
CARRIED=d582.CARRIED

@contextlib.contextmanager
def old_engine():
 """The 582 engine's downloaded evidence in dist/melonx, where the 585
 recipe reads it, with the engine-independent receipts of this delivery's
 steps; the 586 engine's is put back on exit. Without a downloaded 582
 engine (before the component download), nothing moves."""
 if _old[0] or not OLD.is_dir():
  yield
  return
 parked=ROOT/'dist/melonx586'
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
def as_585_engine():
 """The delivered 585 tree with its engine evidence: what the 585 recipe saw."""
 with old_engine(),as_585():yield

def validate_interface():
 return inherited(d585.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d585.host_evidence)

def engine_identity():
 identity=json.loads((NEW/'ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE,identity['host']
 return identity

def engine_evidence():
 """The downloaded 586 engine names exactly the pinned engine inputs (the
 allocation and shader-wait adaptations among them), exports every 572 entry
 point, compiled every adaptation into its adapted source (the 586
 allocation changes, blocking program wait, depth-only warm-up key and
 misaligned-unit guards; the 582 entry stops and page reader; the 577, 576,
 566 and 564 ones; none of the FFT trace), and passed the 572 engine checks
 again: session ownership, display, the simulator runtime, texture pool,
 journal, and the decoder test (upstream vs adapted) with the switch case,
 the 582 cases, the unmapped page read as zeros and the misaligned units."""
 identity=engine_identity()
 for name in EXPORTS586:assert name in identity['exports'],name
 kept=ENGINE582|ENGINE577|(d576.ENGINE576-set(d577.tree.DELETED577))|d572.ENGINE572|d566.ENGINE566|set(d564.ENGINE564)
 assert ENGINE586|kept<=set(identity['adaptations']),sorted((ENGINE586|kept)-set(identity['adaptations']))
 for p,h in identity['adaptations'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 inputs=json.loads((NEW/'embedded-inputs.json').read_bytes())
 for p,h in inputs.items():assert sha(p)==h,p
 for p in sorted(ENGINE586|ENGINE577)+['build-utils/melonx/adapt_texture_pool.py','build-utils/melonx/adapt_shader_warmup.py',
                                        'build-utils/melonx/adapt_attachmentless_framebuffer.py']:
  assert p in inputs,p
 for p in d577.tree.DELETED577:assert p not in inputs and p not in identity['adaptations'] and not (ROOT/p).exists(),p
 with zipfile.ZipFile(NEW/'embedded-adapted-source.zip') as z:
  names=set(z.namelist())
  for adapted in (ADAPTED586,MARKERS582,d577.ADAPTED577):
   for name,texts in adapted.items():
    source=z.read(name).decode('utf-8-sig')
    for text,count in texts.items():assert source.count(text)==count,(name,text,source.count(text))
  for name,texts in d577.KEPT576.items():
   source=z.read(name).decode('utf-8-sig')
   for text in texts:assert source.count(text)==1,(name,text)
  for name,texts in d577.TRACE576.items():
   if name in names:
    source=z.read(name).decode('utf-8-sig')
    for text in texts:assert text not in source,(name,text)
  decoder=z.read(DECODER).decode('utf-8-sig')
  assert decoder.count('StartsFunction(memoryManager, block.EndAddress)')==1 and 'EndsWithTrap(block)' in decoder
  assert decoder.count('IsSkippedCodeReachable(memoryManager, block.EndAddress, jumpTarget, branchTargets)')==1
  project=z.read('src/Ryujinx.Library/Ryujinx.Library.csproj').decode('utf-8-sig')
  assert 'Value="9"' not in project
  pool=z.read('src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs').decode('utf-8-sig')
  assert pool.count('if (!MemoryManager.ValidateAddress(descriptor.UnpackAddress()))')==1
  for p,name in d577.NATIVE.items():
   assert z.read(name)==(ROOT/p).read_bytes(),p
 decoder=json.loads((NEW/'jit-decoder-checks.json').read_bytes())
 assert decoder['result']=='passed' and not decoder['failures'] and decoder['executed'] is False
 upstream,adapted=decoder['upstream'],decoder['adapted']
 assert upstream['switchCase']['guestInstructions']==82 and adapted['switchCase']['guestInstructions']==6
 for case in ('rotatedLoop','shortSkip','enteredSkip'):
  assert adapted[case]['guestInstructions']==upstream[case]['guestInstructions'],case
 for case,(before,after) in d582.STOPPED582.items():
  assert upstream[case]['guestInstructions']==before and not upstream[case]['truncated'],case
  assert adapted[case]['guestInstructions']==after and adapted[case]['truncated'],case
 for case,(before,after) in d582.LAYOUT582.items():
  assert upstream[case]['functions']==adapted[case]['functions']==300,case
  assert upstream[case]['guestInstructions']==before and adapted[case]['guestInstructions']==after,case
 for case in d582.KEPT582:
  assert adapted[case]['guestInstructions']==upstream[case]['guestInstructions'] and not adapted[case]['truncated'],case
 assert upstream['unmappedAfterCall']=={'throws':True}
 assert adapted['unmappedAfterCall']['guestInstructions']==1024 and adapted['unmappedAfterCall']['truncated']
 case,before,after=SILENT586
 assert upstream[case]['guestInstructions']==before and upstream[case]['truncated'],case
 assert adapted[case]['guestInstructions']==after and adapted[case]['truncated'] and adapted[case]['emptyLastBlock'],case
 for case,outcome in MISALIGNED586.items():
  assert upstream[case]==adapted[case]==outcome,(case,upstream[case],adapted[case])
 texture=json.loads((NEW/'texture-pool-checks.json').read_bytes())
 assert texture['result']=='passed' and not texture['failures']
 journal=json.loads((NEW/'engine-journal-checks.json').read_bytes())
 assert journal['result']=='passed' and not journal['failures'] and journal['nativeAot'] is True
 for receipt in (decoder,texture,journal):
  for p,h in receipt['inputs'].items():assert sha(p)==h,p
 for p in ('build-utils/melonx/adapt_jit_decoder.py','test/melonx_jit_decoder/Program.cs','test/melonx_jit_decoder_test.py'):
  assert p in decoder['inputs'],p
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
  exports=EXPORTS586,adaptations=len(identity['adaptations']),adapted586=sorted(ADAPTED586),
  adapted582=sorted(MARKERS582),adapted577=sorted(d577.ADAPTED577),kept576=sorted(d577.KEPT576),
  removedTrace576=sorted(d577.TRACE576),sessionCases=session['passedCases'],
  displaySummary=display['summary'].splitlines()[-1],simulatorSessions=smoke['homebrewSimulatorSessions'],
  jitDecoder={k:{c:decoder[k][c] for c in ['switchCase',*d582.STOPPED582,*d582.LAYOUT582,*d582.KEPT582,
                                           'unmappedAfterCall',SILENT586[0],*MISALIGNED586]} for k in ('upstream','adapted')},
  memoryOwnerSpares=dict(minBytes=85000,maxMiB=64,releasedAfterSeconds=3),gpfifoWordPool='ArrayPool<int>.Shared',
  dmaScratchMaxMiB=16,renderSpanRingMiB=32,blockingProgramWait=True,depthOnlyWarmUpKey=True,deferredFlushGuard=True,bindlessThroughShuffle=True,
  physicalDeviceTested=False,gameTested=False)

def engine_run():
 """The engine run: the exact commit, its own workflow, every engine step passed."""
 state=previous.api(f'actions/runs/{MELONX_RUN}')
 assert state['head_sha']==MELONX_SOURCE and state['path']==MELONX_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS586)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 585 contract, unchanged, on the delivered 585 tree.
 report=inherited(d585.source_contract)
 assert report['productTrees']==tree.product_trees_585(),report['productTrees']
 trees=tree.product_trees()
 # The engine is built by its own run; the Cheats & Enhancements work changes these product trees.
 assert sorted(p for p in tree.TREES if trees[p]!=report['productTrees'][p])==tree.SHIPPED,trees
 # The pinned index differs from the delivered 585 tree by the 586 files, the Core 587 documentation
 # and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_585()).splitlines())
 expected=set(CHANGED586)|set(tree.RECIPE)|set(tree.CORE_DOCS587)
 assert changed==expected,changed^expected
 for p in tree.FIX586:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p,source in tree.APP586.items():
  if p in tree.DELETED586:assert not (ROOT/p).exists(),p
  else:assert (ROOT/p).read_bytes()==at(source,p),p
 for p in tree.CORE587:assert (ROOT/p).read_bytes()==at(CORE_SOURCE,p),p
 # The engine run built exactly these engine inputs.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566|d572.ENGINE572
                 |(d576.ENGINE576-set(d577.tree.DELETED577))|ENGINE577|ENGINE582|ENGINE586):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 587 contract and its inputs, on the pinned tree.
 native.source_contract()
 inputs=native.inputs()
 for p,h in inputs.items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core=core_receipt()
 # The Switch discovery fix, the controller relay and the 565 files, unchanged, on the pinned tree.
 for p,source in d582.tree.APP582.items():assert (ROOT/p).read_bytes()==at(source,p),p
 for p,source in d577.tree.APP577.items():assert (ROOT/p).read_bytes()==at(source,p),p
 # The 565 game profiles, but for the two files of the 587 profile commit (checked with the 586 files).
 for p in d565.tree.FIX565:
  if p not in tree.PROFILE587:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build585=report['build'],source585Recipe=report['source'],
  source586=MELONX_SOURCE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  melonx582Source=MELONX582_SOURCE,melonx582Run=MELONX582_RUN,engineCommits586=tree.ENGINE_COMMITS,
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,rpcCore585Source=CORE585_SOURCE,rpcCore585Run=CORE585_RUN,
  coreInputs=len(inputs),coreOptimizations=core['optimizations'],coreSHA256=core['coreSHA256'],
  replacedCore587=tree.REPLACED_CORE,profileSource587=tree.PROFILE_SOURCE,
  appCommits586=tree.APP_COMMITS,validator586=tree.VALIDATOR586,app586=len(tree.APP586),
  deleted586=tree.DELETED586,shippedTrees586=tree.SHIPPED,replaced586=len(tree.REPLACED),added586=len(tree.ADDED),
  changed586=len(changed),pinnedFiles=kept,productTrees=trees,productTrees585=report['productTrees'],
  physicalDeviceTested=False,gameTested=False)

def payload_585(scratch):
 """The engine entries package_runtime writes for the 582 engine on the 585
 tree (macOS: install_name_tool, vtool and otool), in a scratch application."""
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import package_runtime as runtime
 saved=runtime.CORE,runtime.FRAMEWORKS
 app=Path(scratch)/'app';app.mkdir()
 try:
  with as_585_engine():
   runtime.CORE=NEW;runtime.FRAMEWORKS=Path(scratch)/'Frameworks'
   runtime.materialize();runtime.embed(app)
   identity=json.loads((app/'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']
   assert identity['host']==MELONX582_SOURCE,identity['host']
 finally:
  runtime.CORE,runtime.FRAMEWORKS=saved
 # The scratch packaging receipt belongs to the 582 artifact; never keep it there.
 (OLD/'packaging-identity.json').unlink(missing_ok=True)
 return app

def derived_ipa(ipa):
 """This IPA with the 582 engine payload of the 585 tree in place of its own:
 the application the 585 recipe validated, but for this build's other files.
 Cached per IPA digest."""
 ipa=Path(ipa);digest=hashlib.sha256(ipa.read_bytes()).hexdigest()
 out=ROOT/'build/derived585'/f'{digest}.ipa'
 if out.is_file():return out
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as scratch:
  app=payload_585(scratch)
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
 """The actual IPA carries the 586 engine as package_runtime packaged it and,
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
  for name in SYMBOLS586:assert name in symbols,name
  for text in CORE_TEXT586:assert audio.contains(core,text),text
  for p,h in identity['adaptations'].items():assert sha(p)==h,p
  others=[n for n in real.namelist() if not engine_entry(n,root)]
  assert others==[n for n in old.namelist() if not engine_entry(n,root)]
  for name in others:assert real.read(name)==old.read(name),name
  stale=json.loads(old.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert stale['host']==MELONX582_SOURCE and stale['sha256']!=identity['sha256']
 return dict(engineSource=MELONX_SOURCE,engineRun=MELONX_RUN,coreSHA256=identity['sha256'],
  packagedCoreFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],engine582Source=MELONX582_SOURCE,
  engine582SHA256=stale['sha256'],otherEntriesEqualTo585Equivalent=len(others),symbols=SYMBOLS586)

def retain_checks():
 """The 585 receipts stay bound to the delivered 585 tree (and its 583 to 554 views); the 586 engine run and the 587 Core receipt to the pinned tree."""
 inherited(d585.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'rewind586-engine-run.json').write_text(json.dumps(engine_run(),indent=2)+'\n')
 (out/'rpcs3-cell587-core.json').write_text(json.dumps(dict(core_receipt(),run=core_run()),indent=2)+'\n')
 print('Bound the 585 receipts to the delivered 585 tree, the 586 engine run and the 587 Core receipt to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation586.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 585 binding on the delivered 585 tree (its own views in turn), then the pinned tree.
  views=[d585.inherited,d583.inherited,d582.inherited,d581.inherited,d579.inherited,d577.inherited,d576.inherited,
         d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.inherited,d565.inherited,d564.inherited,
         d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,d558.inherited,d557.inherited]
  for depth in (21,19,18,17,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX582_ARTIFACT,'dist/melonx582engine'),
                       d549.download(MELONX577_ARTIFACT,'dist/melonx577engine'),d549.download(MELONX576_ARTIFACT,'dist/melonx576engine'),
                       d549.download(MELONX572_ARTIFACT,'dist/melonx572engine'),d549.download(MELONX566_ARTIFACT,'dist/melonx566engine'),
                       d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),d549.download(MELONX563_ARTIFACT,'dist/melonx563'),
                       d549.download(HOST_ARTIFACT,'dist/melonx-host'),d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),
                       d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558 to 582 engines on their delivered trees, as 585 bound them, then the 586 engine on the
  # pinned tree; the 562 host on the delivered 562 tree.
  with old_engine():
   with d582.old_engine():
    with d577.old_engine():
     with d576.old_engine():
      with d572.old_engine():
       with d566.old_engine():
        with d564.old_engine():
         report['engine563Evidence']=inherited(d585.inherited,d583.inherited,d582.inherited,d581.inherited,d579.inherited,
                                               d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,
                                               d567.inherited,d566.inherited,d565.inherited,d564.inherited,d563.inherited,
                                               d562.inherited,d558.engine_evidence)
        report['engine564Evidence']=inherited(d585.inherited,d583.inherited,d582.inherited,d581.inherited,d579.inherited,
                                              d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,
                                              d567.inherited,d566.inherited,d565.inherited,d564.engine_evidence)
       report['engine566Evidence']=inherited(d585.inherited,d583.inherited,d582.inherited,d581.inherited,d579.inherited,
                                             d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,
                                             d567.inherited,d566.engine_evidence)
      report['engine572Evidence']=inherited(d585.inherited,d583.inherited,d582.inherited,d581.inherited,d579.inherited,
                                            d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.engine_evidence)
     report['engine576Evidence']=inherited(d585.inherited,d583.inherited,d582.inherited,d581.inherited,d579.inherited,
                                           d577.inherited,d576.engine_evidence)
    report['engine577Evidence']=inherited(d585.inherited,d583.inherited,d582.inherited,d581.inherited,d579.inherited,
                                          d577.engine_evidence)
   report['engine582Evidence']=inherited(d585.inherited,d583.inherited,d582.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=engine_run()
  report['engine582']=d582.engine_run()
  report['engine577']=d577.engine_run()
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
