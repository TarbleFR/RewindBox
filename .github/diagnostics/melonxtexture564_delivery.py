"""Private564: the MeloNX engine of 876a087 (texture pool, bounded engine journal, crash record; its own engine run) on the delivered 563 product tree.

564 ships the 563 product (the 562 product with the RPCS3 Core 563) and swaps
only the MeloNX engine: the 558 engine (8f83748) becomes the one built and
tested from 876a087. Its sources change two native files compiled into the
engine (never into the application) and the adaptation registration. The 563
recipe therefore runs unchanged on the delivered 563 tree, which as_563()
puts in place of the pinned 564 one for each inherited check (a scratch
index, the 564 files' 563 versions in the working tree and BUILD_NUMBER 563,
all restored afterwards), with the 558 engine's downloaded evidence in
dist/melonx (old_engine()). The inherited IPA validators that read the engine
check derived_ipa(): this IPA with the engine payload that package_runtime
produces for the 558 engine on the 563 tree, every other entry byte for byte.
The 564 engine, its run and its receipts are checked on the pinned 564 tree
and on the actual IPA.
"""
import argparse,contextlib,hashlib,json,os,shutil,sys,tempfile,zipfile
from pathlib import Path
import melonxtexture564_tree as tree
import rpcs3cell563_delivery as d563
ROOT=Path(__file__).resolve().parents[2]
BUILD='564'
HOST_TREE=d563.HOST_TREE
# The MeloNX hosts (558, 562), the RPCS3 Core 563 and every other shipped file are the 563 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'CORE_SOURCE','CORE_RUN','CORE_WORKFLOW','CORE_STEPS','validate_rpc_core_identity','validate_rpc_core_pin',
             'core_receipt','core_run','INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN'):
 globals()[name]=getattr(d563,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562=(d563.previous,d563.previous546,d563.d549,d563.d557,
 d563.d558,d563.d559,d563.d560,d563.d561,d563.d562)
# The engine every earlier receipt is bound to (558, carried by 559 to 563).
MELONX563_SOURCE,MELONX563_RUN,MELONX563_ARTIFACT=d563.MELONX_SOURCE,d563.MELONX_RUN,d563.MELONX_ARTIFACT
# Engine built and tested from 876a087, taken by ID and digest.
MELONX_SOURCE=tree.SOURCE564
MELONX_RUN=40502672385
MELONX_ARTIFACT=(12734162101,'e4d30dab24a83583a08da93449b35e184d9e1a11fa7aa2171ba6c3516c62bd79')
MELONX_WORKFLOW='.github/workflows/melonx-core.yml'
TEXTURE_STEP='Execute compiled texture pool lookups of out-of-space descriptors through the engine journal'
JOURNAL_STEP="Execute the engine journal's repeat bound and unhandled-exception record (JIT and NativeAOT)"
ENGINE_STEPS564=ENGINE_STEPS+[TEXTURE_STEP,JOURNAL_STEP]
# The engine identity's export list (the 558 one and the callback registry the
# 562 host binds) and the symbols the packaged engine must define.
EXPORTS564=d558.EXPORTS558+['RegisterCallback']
SYMBOLS564=['_'+name for name in EXPORTS564]+['_InvokeCallback']
# Engine literals the 564 sources add (NativeAOT keeps them as UTF-16 text).
CORE_TEXT564=['unhandledException','Unknown exception object.',' (repeated ',' times)']
ENGINE564=set(tree.ENGINE564)
SHIPPED564=set(tree.SHIPPED564)
OLD=ROOT/'dist/melonx563'
NEW=ROOT/'dist/melonx'
# Entries of the application that package_runtime writes from the engine
# artifact; every other entry is independent of the engine.
ENGINE_PAYLOAD=('MeloNX-native-identity.json','Frameworks/MeloNXCore.framework/MeloNXCore',
                'Legal/MeloNX/Engine-LICENSE.txt','Legal/MeloNX/ManagedDependencies/')

_active=[False]

@contextlib.contextmanager
def as_563():
 """The delivered 563 tree in place of the pinned 564 one: a scratch copy of
 the index with the 564 files at their 563 versions and this recipe removed,
 the same 564 files in the working tree, and build number 563. The 564
 bytes, the index in use and the environment are restored on exit; a check
 already inside the 563 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_563()
 files={p:s for p,s in versions.items() if p in tree.FIX564}
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
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d563.BUILD
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
 # Nothing of the 563 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 563 recipe, run on the delivered 563 tree."""
 with as_563():return function(*args,**kwargs)

_old=[False]

@contextlib.contextmanager
def old_engine():
 """The 558 engine's downloaded evidence in dist/melonx, where the earlier
 recipes read it; the 564 engine's is put back on exit. Without a downloaded
 558 engine (before the component download), nothing moves."""
 if _old[0] or not OLD.is_dir():
  yield
  return
 parked=ROOT/'dist/melonx564'
 assert not parked.exists(),parked
 NEW.rename(parked);OLD.rename(NEW)
 _old[0]=True
 try:yield
 finally:
  _old[0]=False
  NEW.rename(OLD);parked.rename(NEW)
 assert json.loads((NEW/'ios-arm64/identity.json').read_bytes())['host']==MELONX_SOURCE

@contextlib.contextmanager
def as_563_engine():
 """The delivered 563 tree with its engine evidence: what the 563 recipe saw."""
 with old_engine(),as_563():yield

@contextlib.contextmanager
def as_558():
 """The delivered 558 tree, through the 563 view (for the validators of 558 receipts)."""
 with as_563_engine(),d563.as_558():yield

def validate_interface():
 return inherited(d563.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d563.host_evidence)

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def engine_identity():
 identity=json.loads((NEW/'ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE,identity['host']
 return identity

def engine_evidence():
 """The downloaded 564 engine names exactly the pinned engine inputs, exports
 every 558 entry point and the callback registry, passed the 558 engine checks
 again (session ownership, display, simulator runtime) and the 564 ones
 (compiled texture pool control vs fixed with the journal wired in; journal
 repeat bound and crash record under JIT and NativeAOT)."""
 identity=engine_identity()
 for name in EXPORTS564:assert name in identity['exports'],name
 assert set(ENGINE564)<=set(identity['adaptations'])
 for p,h in identity['adaptations'].items():
  assert sha(p)==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 inputs=json.loads((NEW/'embedded-inputs.json').read_bytes())
 for p,h in inputs.items():assert sha(p)==h,p
 assert 'build-utils/melonx/adapt_texture_pool.py' in inputs
 with zipfile.ZipFile(NEW/'embedded-adapted-source.zip') as z:
  pool=z.read('src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs').decode('utf-8-sig')
  assert pool.count('if (!MemoryManager.ValidateAddress(descriptor.UnpackAddress()))')==1
  memory=z.read('src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs').decode('utf-8-sig')
  assert 'internal static bool ValidateAddress(ulong va)' in memory
  for p in SHIPPED564:
   name={'native/melonx/EmbeddedLaunchDiagnostics.cs':'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs',
         'native/melonx/EmbeddedRuntime.cs':'src/Ryujinx.Library/EmbeddedRuntime.cs'}[p]
   assert z.read(name)==(ROOT/p).read_bytes(),p
 texture=json.loads((NEW/'texture-pool-checks.json').read_bytes())
 assert texture['result']=='passed' and not texture['failures'] and texture['physicalDeviceTested'] is False
 assert texture['control']['outOfSpaceGarbage']['journalLines']==texture['control']['outOfSpaceGarbage']['lookups']>0
 assert texture['fixed']['outOfSpaceGarbage']['journalLines']==0
 journal=json.loads((NEW/'engine-journal-checks.json').read_bytes())
 assert journal['result']=='passed' and not journal['failures'] and journal['nativeAot'] is True
 assert journal['new']['crash'] and journal['new']['aotCrash'] and journal['old']['crashRecords']==0
 for receipt in (texture,journal):
  for p,h in receipt['inputs'].items():assert sha(p)==h,p
 session=json.loads((NEW/'session-checks.json').read_bytes())
 assert session['passedCases']==25
 display=json.loads((NEW/'display-checks.json').read_bytes())
 assert display['result']=='passed' and 'PASS 69 graphics, FPS snapshot' in display['summary']
 smoke=json.loads((NEW/'runtime-smoke/actual-runtime.json').read_bytes())
 assert smoke['result']=='passed' and smoke['homebrewSimulatorSessions']==2
 assert smoke['performanceSnapshotStaleAndEndedRefused'] and smoke['livePerformanceSnapshotSessions']>=1
 for receipt in (session,display,smoke):
  for p,h in receipt.get('inputs',{}).items():assert sha(p)==h,p
 return dict(source=MELONX_SOURCE,run=MELONX_RUN,artifact=MELONX_ARTIFACT[0],coreSHA256=identity['sha256'],
  exports=EXPORTS564,adaptations=len(identity['adaptations']),sessionCases=session['passedCases'],
  displaySummary=display['summary'].splitlines()[-1],simulatorSessions=smoke['homebrewSimulatorSessions'],
  texturePool={k:texture[k]['outOfSpaceGarbage'] for k in ('control','fixed')},
  texturePoolUnmapped={k:texture[k]['unmappedGarbage'] for k in ('control','fixed')},
  engineJournal={'old':journal['old'],'new':{k:journal['new'][k] for k in ('textureLines','concurrentLines')},'nativeAotCrashRecord':True},
  physicalDeviceTested=False,gameTested=False)

def engine_run():
 """The engine run: the exact commit, its own workflow, every 558 engine step and the 564 ones passed."""
 state=previous.api(f'actions/runs/{MELONX_RUN}')
 assert state['head_sha']==MELONX_SOURCE and state['path']==MELONX_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS564)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 563 contract, unchanged, on the delivered 563 tree.
 report=inherited(d563.source_contract)
 assert report['productTrees']==tree.product_trees_563(),report['productTrees']
 trees=tree.product_trees()
 assert {p for p in tree.TREES if trees[p]!=report['productTrees'][p]}=={'native'},trees
 # The pinned index differs from the delivered 563 tree by the 564 files and this recipe only.
 versions=tree.at_563()
 changed=set(command('git','diff','--cached','--name-only',tree.tree_563()).splitlines())
 expected={p for p in set(tree.FIX564)|set(tree.RECIPE) if versions[p]!=head}
 assert changed==expected,changed^expected
 for p in tree.FIX564:
  if tree.source_of(p):assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The engine run built exactly these engine inputs.
 for p in sorted(set(d558.ENGINE_INPUTS)|ENGINE564):assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 563, unchanged, on the pinned tree.
 d563.native.source_contract()
 for p,h in d563.native.inputs().items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build563=report['build'],source563Recipe=report['source'],
  source564=MELONX_SOURCE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  melonx563Source=MELONX563_SOURCE,melonx563Run=MELONX563_RUN,replaced564=tree.REPLACED,changed564=sorted(changed),
  shipped564=sorted(SHIPPED564),pinnedFiles=kept,productTrees=trees,productTrees563=report['productTrees'],
  physicalDeviceTested=False,gameTested=False)

def payload_563(scratch):
 """The engine entries package_runtime writes for the 558 engine on the 563
 tree (macOS: install_name_tool, vtool and otool), in a scratch application."""
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import package_runtime as runtime
 saved=runtime.CORE,runtime.FRAMEWORKS
 app=Path(scratch)/'app';app.mkdir()
 try:
  with as_563_engine():
   runtime.CORE=NEW;runtime.FRAMEWORKS=Path(scratch)/'Frameworks'
   runtime.materialize();runtime.embed(app)
   identity=json.loads((app/'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']
   assert identity['host']==MELONX563_SOURCE,identity['host']
 finally:
  runtime.CORE,runtime.FRAMEWORKS=saved
 # The scratch packaging receipt belongs to the 558 artifact; never keep it there.
 (OLD/'packaging-identity.json').unlink(missing_ok=True)
 return app

def engine_entry(name,root):
 relative=name[len(root):]
 return name.startswith(root) and any(relative==p or (p.endswith('/') and relative.startswith(p)) for p in ENGINE_PAYLOAD)

def derived_ipa(ipa):
 """This IPA with the 558 engine payload of the 563 tree in place of its own:
 the application the 563 recipe validated, but for this build's other files.
 Cached per IPA digest."""
 ipa=Path(ipa);digest=hashlib.sha256(ipa.read_bytes()).hexdigest()
 out=ROOT/'build/derived563'/f'{digest}.ipa'
 if out.is_file():return out
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as scratch:
  app=payload_563(scratch)
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
 """The actual IPA carries the 564 engine as package_runtime packaged it and,
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
  for name in SYMBOLS564:assert name in symbols,name
  for text in CORE_TEXT564:assert audio.contains(core,text),text
  for p,h in identity['adaptations'].items():assert sha(p)==h,p
  others=[n for n in real.namelist() if not engine_entry(n,root)]
  assert others==[n for n in old.namelist() if not engine_entry(n,root)]
  for name in others:assert real.read(name)==old.read(name),name
  stale=json.loads(old.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert stale['host']==MELONX563_SOURCE and stale['sha256']!=identity['sha256']
 return dict(engineSource=MELONX_SOURCE,engineRun=MELONX_RUN,coreSHA256=identity['sha256'],
  packagedCoreFingerprint=receipt['compiledPayloadFingerprints']['MeloNXCore'],engine563Source=MELONX563_SOURCE,
  engine563SHA256=stale['sha256'],otherEntriesEqualTo563Equivalent=len(others),symbols=SYMBOLS564,coreText=CORE_TEXT564)

def retain_checks():
 """The 563 receipts stay bound to the delivered 563 tree (and its 562 to 554 views); the 564 engine run to the pinned tree."""
 inherited(d563.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'melonx-texture564-engine-run.json').write_text(json.dumps(engine_run(),indent=2)+'\n')
 print('Bound the 563 receipts to the delivered 563 tree and the 564 engine run to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation564.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 563 binding on the delivered 563 tree (its own views in turn), then the pinned tree.
  inherited(d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,d558.inherited,d557.inherited,previous546.logger_proofs)
  inherited(d563.inherited,d562.inherited,d561.inherited,d560.inherited,previous546.logger_proofs)
  inherited(d563.inherited,d562.inherited,d561.inherited,previous546.logger_proofs)
  inherited(d563.inherited,d562.inherited,previous546.logger_proofs)
  inherited(d563.inherited,previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX563_ARTIFACT,'dist/melonx563'),
                       d549.download(HOST_ARTIFACT,'dist/melonx-host'),d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),
                       d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558 engine and 562 host evidence on the delivered 563 tree, as 563 bound them; then the 564 engine.
  with old_engine():report['engine563Evidence']=inherited(d563.inherited,d562.inherited,d558.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=engine_run()
  report['engine563']=previous.completed(MELONX563_RUN,MELONX563_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
  report['host562']=host_run()
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
