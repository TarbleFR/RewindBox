"""Private582: the MeloNX engine of e55ca25 (LightningJit translation units end where another translation already starts, keeping a loop or a short skip around it; guest code read a page at a time; a unit ends before an unmapped page; its own engine run) and the Switch discovery fix of 32a0da6/63fdb7e on the delivered 581 product tree.

582 ships the 581 product (the 579 product with the RPCS3 Core 581: the
577 product with the MeloNX engine of cfa5116/afd0d4b and the controller
relay of d1f7b8d; StikDebug fallback removal, interface fixes of 48b9865,
God of War III without the 30 fps limiter, MeloNX keyboard and L3/R3) and
swaps the MeloNX engine: the 577 engine becomes the one built and tested
from e55ca25, whose sources change no file compiled into the application
(the JIT decoder adaptation, its probe and its test). The application also
gains the Switch discovery fix of 32a0da6/63fdb7e: the MeloNX bridge hashes
a game file with CryptoKit off the main thread and stops at a launch, the
scanner no longer hashes on the root isolate or while a game starts or
runs, and an index entry follows its file into a new app container (two
Dart files, one Swift file, one new test). The 581 recipe runs unchanged on
the delivered 581 tree, which as_581() puts in place of the pinned 582 one
for each inherited check (a scratch index, the 582 files' 581 versions in
the working tree, the added test absent, and BUILD_NUMBER 581, all restored
afterwards), with the 577 engine's downloaded evidence in dist/melonx
(old_engine()). The inherited IPA validators check derived_ipa(): this IPA
with the engine payload that package_runtime produces for the 577 engine on
the 581 tree, every other entry byte for byte; the 577 recipe under them
derives its own 576-equivalent in turn. The 582 engine, its run and its
receipts are checked on the pinned 582 tree and on the actual IPA. The
RPCS3 Core is the 581 one in both trees. The source contract is computed
once per job and reused on the same bytes (build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,shutil,sys,tempfile,zipfile
from pathlib import Path
import melonxentry582_tree as tree
import rpcs3cell581_delivery as d581
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='582'
HOST_TREE=d581.HOST_TREE
# The RPCS3 Core 581, the MeloNX hosts (558, 562) and every other shipped file are the 581 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'CORE_SOURCE','CORE_RUN','CORE_WORKFLOW','CORE_STEPS','validate_rpc_core_identity','validate_rpc_core_pin',
             'core_receipt','core_run','INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN','CORE563_SOURCE','CORE563_RUN',
             'CORE565_SOURCE','CORE565_RUN','CORE567_SOURCE','CORE567_RUN','CORE569_SOURCE','CORE569_RUN',
             'CORE571_SOURCE','CORE571_RUN','CORE573_SOURCE','CORE573_RUN','CORE575_SOURCE','CORE575_RUN',
             'CORE579_SOURCE','CORE579_RUN','MELONX_WORKFLOW','MELONX576_SOURCE','MELONX576_RUN','MELONX576_ARTIFACT',
             'MELONX572_SOURCE','MELONX572_RUN','MELONX572_ARTIFACT','MELONX566_SOURCE','MELONX566_RUN',
             'MELONX566_ARTIFACT','MELONX564_SOURCE','MELONX564_RUN','MELONX564_ARTIFACT','MELONX563_SOURCE',
             'MELONX563_RUN','MELONX563_ARTIFACT','ENGINE577','ENGINE_PAYLOAD','engine_entry','sha'):
 globals()[name]=getattr(d581,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565,d566,d567,d572,d573,d575,d576,d577,d579=(d581.previous,
 d581.previous546,d581.d549,d581.d557,d581.d558,d581.d559,d581.d560,d581.d561,d581.d562,d581.d563,d581.d564,
 d581.d565,d581.d566,d581.d567,d581.d572,d581.d573,d581.d575,d581.d576,d581.d577,d581.d579)
# The engine the 581, 579 and 577 receipts are bound to.
MELONX577_SOURCE,MELONX577_RUN,MELONX577_ARTIFACT=d581.MELONX_SOURCE,d581.MELONX_RUN,d581.MELONX_ARTIFACT
assert MELONX577_SOURCE==d577.MELONX_SOURCE==tree.SOURCE577
# Engine built and tested from e55ca25 (6d8929d, e72895b and e55ca25), taken by ID and digest.
MELONX_SOURCE=tree.SOURCE582
MELONX_RUN=40665520797
MELONX_ARTIFACT=(12806293726,'f684cfecda061e100122dd548dcc8222ee85b96eda55cad620cf578290b03579')
# The engine workflow is the one of 577, unchanged: the same steps.
ENGINE_STEPS582=d581.ENGINE_STEPS577
# 582 adds no export and no journal literal; the 572 ones must remain.
EXPORTS582=d581.EXPORTS577
SYMBOLS582=d581.SYMBOLS577
CORE_TEXT582=d581.CORE_TEXT577
ENGINE582=set(tree.ENGINE582)
OLD=ROOT/'dist/melonx577engine'
NEW=ROOT/'dist/melonx'
# Python modules of 582 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in tree.CHANGED if p.endswith('.py'))
CHANGED582=list(tree.CHANGED)
DECODER='src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs'
# What the 582 decoder adaptation must have put into the adapted engine source, and how often.
ADAPTED582={
 DECODER:{'private sealed class CodeReader':1,'private struct EntryStop':1,
  'CodeReader code = CodeReader.For(memoryManager);':1,'CodeReader code = CodeReader.Active(memoryManager);':2,
  'if (code.EndsBefore(address))':2,'EntryStop entryStop = new(TranslatedEntries.Current, address);':1,
  'if (entryStop.StopsAt(code, address))':1,'entryStop.Continue(block);':1,'if (!code.IsMapped(end))':1,
  'catch (Ryujinx.Memory.InvalidMemoryRegionException)':1,'private const int LoopScanInstructions = 1024;':1,
  'private const ulong ShortSkipBytes = 256;':1},
 'src/Ryujinx.Cpu/LightningJit/Translator.cs':{'sealed class TranslatedEntries':1,
  'internal static TranslatedEntries Current':1,'private readonly TranslatedEntries _entries = new();':1,
  '_entries.Add(':1,'_entries.Remove(':1,'TranslatedEntries.Current = _entries;':1,
  'TranslatedEntries.Current = null;':1}}
# Decoder probe cases (guest instructions, upstream then adapted): the unit ends at an entry another
# translation already starts; the units of a 300-function layout hold 3,601 guest instructions, not 542,100.
STOPPED582={'knownRunOn':(41,20),'knownBlockStart':(12,2),'knownAfterLoop':(11,5),'farLoop':(1203,100)}
LAYOUT582={'layout':(542100,3601),'framelessLayout':(542100,3601)}
# Cases the adapted unit keeps whole: a loop or a switch around the entry, a short skip, the unit's own
# entry, a continuation inside a loop, and a long jump to an unmapped page (decoded as upstream).
KEPT582=('knownInLoop','ownEntry','knownSwitchCases','knownSkippedThen','continuationInLoop','unmappedLongJump')

_active=[False]

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in CHANGED582:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_581():
 """The delivered 581 tree in place of the pinned 582 one: a scratch copy of
 the index with the 582 files at their 581 versions (the added test absent)
 and this recipe removed, the same 582 files in the working tree, their
 Python modules and build number 581. The RPCS3 Core 581 and its installed
 identity are the same in both trees. The 582 bytes, modules, the index in
 use and the environment are restored on exit; a check already inside the
 581 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_581()
 files={p:s for p,s in versions.items() if p in CHANGED582}
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
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d581.BUILD
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
 # Nothing of the 581 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 581 recipe, run on the delivered 581 tree."""
 with as_581():return function(*args,**kwargs)

_old=[False]
# Receipts this delivery's own steps write into dist/melonx that do not depend
# on the engine: the 581 to 564 recipes found them next to their engine.
CARRIED=d577.CARRIED

@contextlib.contextmanager
def old_engine():
 """The 577 engine's downloaded evidence in dist/melonx, where the 581
 recipe reads it, with the engine-independent receipts of this delivery's
 steps; the 582 engine's is put back on exit. Without a downloaded 577
 engine (before the component download), nothing moves."""
 if _old[0] or not OLD.is_dir():
  yield
  return
 parked=ROOT/'dist/melonx582'
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
def as_581_engine():
 """The delivered 581 tree with its engine evidence: what the 581 recipe saw."""
 with old_engine(),as_581():yield

def validate_interface():
 return inherited(d581.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d581.host_evidence)

def engine_identity():
 identity=json.loads((NEW/'ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE,identity['host']
 return identity

def engine_evidence():
 """The downloaded 582 engine names exactly the pinned engine inputs (the
 582 decoder adaptation among them), exports every 572 entry point, compiled
 every adaptation into its adapted source (the 582 entry stops and page
 reader; the 577 kernel, GC, code arena and pipeline cache ones; the 576
 warm-up and framebuffer ones; the 566 and 564 decoder, GC and texture pool
 ones; none of the FFT trace), and passed the 572 engine checks again:
 session ownership, display, the simulator runtime, texture pool, journal,
 and the decoder test (upstream vs adapted) with the switch case and the
 582 cases."""
 identity=engine_identity()
 for name in EXPORTS582:assert name in identity['exports'],name
 kept=ENGINE577|(d576.ENGINE576-set(d577.tree.DELETED577))|d572.ENGINE572|d566.ENGINE566|set(d564.ENGINE564)
 assert ENGINE582|kept<=set(identity['adaptations']),sorted((ENGINE582|kept)-set(identity['adaptations']))
 for p,h in identity['adaptations'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 inputs=json.loads((NEW/'embedded-inputs.json').read_bytes())
 for p,h in inputs.items():assert sha(p)==h,p
 for p in sorted(ENGINE582|ENGINE577)+['build-utils/melonx/adapt_texture_pool.py','build-utils/melonx/adapt_shader_warmup.py',
                                        'build-utils/melonx/adapt_attachmentless_framebuffer.py']:
  assert p in inputs,p
 for p in d577.tree.DELETED577:assert p not in inputs and p not in identity['adaptations'] and not (ROOT/p).exists(),p
 with zipfile.ZipFile(NEW/'embedded-adapted-source.zip') as z:
  names=set(z.namelist())
  for adapted in (ADAPTED582,d577.ADAPTED577):
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
 for case,(before,after) in STOPPED582.items():
  assert upstream[case]['guestInstructions']==before and not upstream[case]['truncated'],case
  assert adapted[case]['guestInstructions']==after and adapted[case]['truncated'],case
 for case,(before,after) in LAYOUT582.items():
  assert upstream[case]['functions']==adapted[case]['functions']==300,case
  assert upstream[case]['guestInstructions']==before and adapted[case]['guestInstructions']==after,case
 for case in KEPT582:
  assert adapted[case]['guestInstructions']==upstream[case]['guestInstructions'] and not adapted[case]['truncated'],case
 # A call at the end of the last mapped page: upstream throws, the adapted unit ends before the page.
 assert upstream['unmappedAfterCall']=={'throws':True}
 assert adapted['unmappedAfterCall']['guestInstructions']==1024 and adapted['unmappedAfterCall']['truncated']
 texture=json.loads((NEW/'texture-pool-checks.json').read_bytes())
 assert texture['result']=='passed' and not texture['failures']
 journal=json.loads((NEW/'engine-journal-checks.json').read_bytes())
 assert journal['result']=='passed' and not journal['failures'] and journal['nativeAot'] is True
 for receipt in (decoder,texture,journal):
  for p,h in receipt['inputs'].items():assert sha(p)==h,p
 for p in tree.FIX582:assert p in decoder['inputs'],p
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
  exports=EXPORTS582,adaptations=len(identity['adaptations']),adapted582=sorted(ADAPTED582),
  adapted577=sorted(d577.ADAPTED577),kept576=sorted(d577.KEPT576),removedTrace576=sorted(d577.TRACE576),
  sessionCases=session['passedCases'],displaySummary=display['summary'].splitlines()[-1],
  simulatorSessions=smoke['homebrewSimulatorSessions'],
  jitDecoder={k:{case:decoder[k][case] for case in ['switchCase',*STOPPED582,*LAYOUT582,*KEPT582,'unmappedAfterCall']}
              for k in ('upstream','adapted')},
  gcConserveMemory=5,gcHighMemoryPercent=99,hogwartsUpdateCodeArenaMiB=1024,pipelineCacheMainBudgetMiB=384,
  physicalDeviceTested=False,gameTested=False)

def engine_run():
 """The engine run: the exact commit, its own workflow, every engine step passed."""
 state=previous.api(f'actions/runs/{MELONX_RUN}')
 assert state['head_sha']==MELONX_SOURCE and state['path']==MELONX_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS582)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 581 contract, unchanged, on the delivered 581 tree.
 report=inherited(d581.source_contract)
 assert report['productTrees']==tree.product_trees_581(),report['productTrees']
 trees=tree.product_trees()
 # The engine is built by its own run; the Switch discovery fix (Dart, Swift) changes product trees.
 assert {p for p in tree.TREES if trees[p]!=report['productTrees'][p]}=={'lib','packages'},trees
 # The pinned index differs from the delivered 581 tree by the 582 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_581()).splitlines())
 expected=set(CHANGED582)|set(tree.RECIPE)
 assert changed==expected,changed^expected
 for p in tree.FIX582:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p,source in tree.APP582.items():assert (ROOT/p).read_bytes()==at(source,p),p
 # The engine run built exactly these engine inputs.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566|d572.ENGINE572
                 |(d576.ENGINE576-set(d577.tree.DELETED577))|ENGINE577|ENGINE582):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 581, the controller relay and the God of War III profile, unchanged, on the pinned tree.
 d581.native.source_contract()
 for p,h in d581.native.inputs().items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core_receipt()
 for p,source in d577.tree.APP577.items():assert (ROOT/p).read_bytes()==at(source,p),p
 for p in d565.tree.FIX565:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build581=report['build'],source581Recipe=report['source'],
  source582=MELONX_SOURCE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  melonx577Source=MELONX577_SOURCE,melonx577Run=MELONX577_RUN,engineCommits582=tree.ENGINE_COMMITS,
  replaced582=tree.REPLACED,added582=tree.ADDED,sourceApp582=tree.SOURCE_APP582,appCommits582=tree.APP_COMMITS,
  app582=sorted(tree.APP582),switchDiscovery582=True,changed582=sorted(changed),pinnedFiles=kept,
  productTrees=trees,productTrees581=report['productTrees'],physicalDeviceTested=False,gameTested=False)

def payload_581(scratch):
 """The engine entries package_runtime writes for the 577 engine on the 581
 tree (macOS: install_name_tool, vtool and otool), in a scratch application."""
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import package_runtime as runtime
 saved=runtime.CORE,runtime.FRAMEWORKS
 app=Path(scratch)/'app';app.mkdir()
 try:
  with as_581_engine():
   runtime.CORE=NEW;runtime.FRAMEWORKS=Path(scratch)/'Frameworks'
   runtime.materialize();runtime.embed(app)
   identity=json.loads((app/'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']
   assert identity['host']==MELONX577_SOURCE,identity['host']
 finally:
  runtime.CORE,runtime.FRAMEWORKS=saved
 # The scratch packaging receipt belongs to the 577 artifact; never keep it there.
 (OLD/'packaging-identity.json').unlink(missing_ok=True)
 return app

def derived_ipa(ipa):
 """This IPA with the 577 engine payload of the 581 tree in place of its own:
 the application the 581 recipe validated, but for this build's other files.
 Cached per IPA digest."""
 ipa=Path(ipa);digest=hashlib.sha256(ipa.read_bytes()).hexdigest()
 out=ROOT/'build/derived581'/f'{digest}.ipa'
 if out.is_file():return out
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as scratch:
  app=payload_581(scratch)
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
 """The actual IPA carries the 582 engine as package_runtime packaged it and,
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
  for name in SYMBOLS582:assert name in symbols,name
  for text in CORE_TEXT582:assert audio.contains(core,text),text
  for p,h in identity['adaptations'].items():assert sha(p)==h,p
  others=[n for n in real.namelist() if not engine_entry(n,root)]
  assert others==[n for n in old.namelist() if not engine_entry(n,root)]
  for name in others:assert real.read(name)==old.read(name),name
  stale=json.loads(old.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert stale['host']==MELONX577_SOURCE and stale['sha256']!=identity['sha256']
 return dict(engineSource=MELONX_SOURCE,engineRun=MELONX_RUN,coreSHA256=identity['sha256'],
  packagedCoreFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],engine577Source=MELONX577_SOURCE,
  engine577SHA256=stale['sha256'],otherEntriesEqualTo581Equivalent=len(others),symbols=SYMBOLS582)

def retain_checks():
 """The 581 receipts stay bound to the delivered 581 tree (and its 579 to 554 views); the 582 engine run to the pinned tree."""
 inherited(d581.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'melonx-entry582-engine-run.json').write_text(json.dumps(engine_run(),indent=2)+'\n')
 print('Bound the 581 receipts to the delivered 581 tree and the 582 engine run to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation582.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 581 binding on the delivered 581 tree (its own views in turn), then the pinned tree.
  views=[d581.inherited,d579.inherited,d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,
         d567.inherited,d566.inherited,d565.inherited,d564.inherited,d563.inherited,d562.inherited,d561.inherited,
         d560.inherited,d559.inherited,d558.inherited,d557.inherited]
  for depth in (18,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX577_ARTIFACT,'dist/melonx577engine'),
                       d549.download(MELONX576_ARTIFACT,'dist/melonx576engine'),d549.download(MELONX572_ARTIFACT,'dist/melonx572engine'),
                       d549.download(MELONX566_ARTIFACT,'dist/melonx566engine'),d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),
                       d549.download(MELONX563_ARTIFACT,'dist/melonx563'),d549.download(HOST_ARTIFACT,'dist/melonx-host'),
                       d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558 to 577 engines on their delivered trees, as 581 bound them, then the 582 engine on the
  # pinned tree; the 562 host on the delivered 562 tree.
  with old_engine():
   with d577.old_engine():
    with d576.old_engine():
     with d572.old_engine():
      with d566.old_engine():
       with d564.old_engine():
        report['engine563Evidence']=inherited(d581.inherited,d579.inherited,d577.inherited,d576.inherited,d575.inherited,
                                              d573.inherited,d572.inherited,d567.inherited,d566.inherited,d565.inherited,
                                              d564.inherited,d563.inherited,d562.inherited,d558.engine_evidence)
       report['engine564Evidence']=inherited(d581.inherited,d579.inherited,d577.inherited,d576.inherited,d575.inherited,
                                             d573.inherited,d572.inherited,d567.inherited,d566.inherited,d565.inherited,
                                             d564.engine_evidence)
      report['engine566Evidence']=inherited(d581.inherited,d579.inherited,d577.inherited,d576.inherited,d575.inherited,
                                            d573.inherited,d572.inherited,d567.inherited,d566.engine_evidence)
     report['engine572Evidence']=inherited(d581.inherited,d579.inherited,d577.inherited,d576.inherited,d575.inherited,
                                           d573.inherited,d572.engine_evidence)
    report['engine576Evidence']=inherited(d581.inherited,d579.inherited,d577.inherited,d576.engine_evidence)
   report['engine577Evidence']=inherited(d581.inherited,d579.inherited,d577.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=engine_run()
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
