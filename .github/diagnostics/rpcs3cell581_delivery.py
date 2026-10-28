"""Private581: the RPCS3 Core 581 (0395645, its own Core run) on the delivered 579 product tree.

581 ships the 579 product (the 577 product: the 576 product with the
MeloNX engine of cfa5116/afd0d4b and the controller relay of d1f7b8d;
StikDebug fallback removal, interface fixes of 48b9865, God of War III
without the 30 fps limiter, MeloNX keyboard and L3/R3) and swaps only the
RPCS3 Core: the 579 Core (1f82f9d) becomes the 581 one, built and tested
from 0395645 (the texture pre-validation by a worker thread). The Core
recipe files the 579 tree pins at 1f82f9d (canonical delta, manifest, build
script, Core pin test, Core workflow) change with it, so the 579 recipe runs
unchanged on the delivered 579 tree, which as_579() puts in place of the
pinned 581 one for the duration of each inherited check (a scratch index,
the 581 files' 579 versions in the working tree and their Python modules,
and BUILD_NUMBER 579, all restored afterwards); the 579 recipe puts the 577
tree back for its own inherited checks in turn. The MeloNX engine, its
downloaded evidence and every shipped file are the 579 (577) ones. The 581
Core identity and its receipt are checked on the pinned 581 tree. The source
contract is computed once per job and reused on the same bytes
(build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,sys,tempfile
from pathlib import Path
import rpcs3cell581_tree as tree
import rpcs3cell581_core as native
import rpcs3cell579_delivery as d579
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='581'
HOST_TREE=d579.HOST_TREE
# The MeloNX engine (577), the MeloNX hosts (558, 562) and every shipped file are the 579 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','MELONX_WORKFLOW','MELONX576_SOURCE','MELONX576_RUN',
             'MELONX576_ARTIFACT','MELONX572_SOURCE','MELONX572_RUN','MELONX572_ARTIFACT','MELONX566_SOURCE',
             'MELONX566_RUN','MELONX566_ARTIFACT','MELONX564_SOURCE','MELONX564_RUN','MELONX564_ARTIFACT',
             'MELONX563_SOURCE','MELONX563_RUN','MELONX563_ARTIFACT','ENGINE_STEPS577','EXPORTS577','SYMBOLS577',
             'CORE_TEXT577','ENGINE577','SHIPPED577','ENGINE_PAYLOAD','engine_entry','INSTALLED',
             'CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN','CORE560_SOURCE','CORE560_RUN',
             'CORE561_SOURCE','CORE561_RUN','CORE563_SOURCE','CORE563_RUN','CORE565_SOURCE','CORE565_RUN',
             'CORE567_SOURCE','CORE567_RUN','CORE569_SOURCE','CORE569_RUN','CORE571_SOURCE','CORE571_RUN',
             'CORE573_SOURCE','CORE573_RUN','CORE575_SOURCE','CORE575_RUN'):
 globals()[name]=getattr(d579,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565,d566,d567,d572,d573,d575,d576,d577=(d579.previous,
 d579.previous546,d579.d549,d579.d557,d579.d558,d579.d559,d579.d560,d579.d561,d579.d562,d579.d563,d579.d564,
 d579.d565,d579.d566,d579.d567,d579.d572,d579.d573,d579.d575,d579.d576,d579.d577)
# The Core the 579 receipts are bound to.
CORE579_SOURCE,CORE579_RUN=d579.CORE_SOURCE,d579.CORE_RUN
CORE_SOURCE=tree.SOURCE581
CORE_RUN=40631132527
CORE_WORKFLOW='.github/workflows/rpcs3-cell581-core.yml'
CORE_STEPS=['Authenticate the 579 Core and execute every 581 native case on ARM64',
            'Compile actual iPhone Core from the verified source',
            'Verify actual Core, exact exports, passive loading and 581 identity',
            'Upload source-built581 Core']
HOST_EVIDENCE='docs/evidence/rpcs3-cell581-host-linux.json'
MAC_EVIDENCE='docs/evidence/rpcs3-cell581-macos.json'
# Each earlier Core of the 575 swap, the 575 and the 579 Core, with its own run and Mac evidence.
EARLIER=dict(d579.EARLIER)
EARLIER[579]=(CORE579_SOURCE,CORE579_RUN,d579.MAC_EVIDENCE)
assert CORE579_SOURCE==tree.SOURCE579 and CORE575_SOURCE==tree.SOURCE575 and CORE573_SOURCE==tree.SOURCE573
assert CORE571_SOURCE==tree.SOURCE571 and CORE569_SOURCE==tree.SOURCE569 and CORE567_SOURCE==tree.SOURCE567
assert MELONX_SOURCE==tree.SOURCE577
# Python modules of 581 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in tree.CELL581 if p.endswith('.py'))

_active=[False]

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in tree.CELL581:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_579():
 """The delivered 579 tree in place of the pinned 581 one: a scratch copy of
 the index with the 581 files at their 579 versions and this recipe removed,
 the same 581 files in the working tree, their Python modules and build
 number 579. The installed 581 Core identity is set aside: the 579 recipe
 checks an installed identity against the 579 Core when one is present, and
 this one checks it against 581. The 581 bytes, modules, the identity, the
 index in use and the environment are restored on exit; a check already
 inside the 579 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_579()
 files={p:s for p,s in versions.items() if p in tree.CELL581}
 saved={p:(ROOT/p).read_bytes() if (ROOT/p).is_file() else None for p in files}
 modules={name:sys.modules[name] for name in MODULES if name in sys.modules}
 installed=INSTALLED.read_bytes() if INSTALLED.is_file() else None
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
   INSTALLED.unlink(missing_ok=True)
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d579.BUILD
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
   if installed is not None:INSTALLED.write_bytes(installed)
 # Nothing of the 579 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert (INSTALLED.read_bytes() if INSTALLED.is_file() else None)==installed
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 579 recipe, run on the delivered 579 tree."""
 with as_579():return function(*args,**kwargs)

def validate_interface():
 return inherited(d579.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d579.host_evidence)

def validate_rpc_core_identity(identity):
 """The 581 Core identity, bound to its own commit: the canonical delta,
 every Core source and every recorded input equal the 0395645 blobs and
 this checkout."""
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 manifest=native.manifest()
 assert identity['source_patch_sha256']==manifest['patch_sha256']
 assert identity['native_source_sha256']==manifest['files_sha256']
 assert identity['core_input_sha256']==native.pin_module().core_input_hashes()
 # The identity names this Core's inputs, not an earlier Core's.
 assert not {'cell551_input_sha256','cell555_input_sha256','cell559_input_sha256','cell560_input_sha256',
             'cell561_input_sha256','cell563_input_sha256','cell565_input_sha256','cell567_input_sha256',
             'cell569_input_sha256','cell571_input_sha256','cell573_input_sha256','cell575_input_sha256',
             'cell579_input_sha256'}&set(identity),set(identity)
 recorded=identity['cell581_input_sha256'];current=native.inputs()
 assert set(recorded)==set(current),set(recorded)^set(current)
 for p,h in recorded.items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
  assert current[p]==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 assert paths and set(paths)<=set(native.inputs()),set(paths)-set(native.inputs())
 for p in paths:assert at(source,p)==(ROOT/p).read_bytes(),p

def core_receipt():
 """The 581 Core: its host evidence names the canonical delta and fixture of
 this checkout, its Mac evidence the Core the run built from them; the 569 to
 579 Cores under it each passed their own Core run."""
 local=json.loads((ROOT/HOST_EVIDENCE).read_bytes())
 mac=json.loads((ROOT/MAC_EVIDENCE).read_bytes())
 manifest=native.manifest();record=manifest['cell581']
 assert local['build']==581 and local['passed'] and local['result']=='passed'
 assert local['physicalDeviceTested'] is False and local['gameplayMeasured'] is False
 assert local['sourceContract']['baseline']==record['baseline']
 assert local['sourceContract']['fixtureSHA256']==record['fixture_sha256']==sha(native.FIXTURE)
 assert local['sourceContract']['sourceSHA256']==record['after_sha256']
 prehash=local['texturePrehash']
 for mode in ('plain','asanUbsan','tsan'):
  case=prehash[mode]
  assert case['passed'] and case['disabledIdenticalTo579'] and case['rangeLockReleased'] and case['noRestartAfterStop'],mode
  assert case['steady']['staleAccepted']==case['tightLoop']['staleAccepted']==case['scopedRsxWrites']['staleAccepted']==0,mode
  assert case['steady']['hits']>0 and case['steady']['changesSeen']>0,mode
 assert prehash['mutations']['no_epoch_check']['rejected'] and prehash['mutations']['no_bypass']['rejected']
 assert local['codegenIdentity']['unchangedFrom579'] and not local['codegenIdentity']['coldCompileRequiredByThisChange']
 assert mac['build']==581 and mac['result']=='passed' and mac['source']==CORE_SOURCE and mac['run']==CORE_RUN
 assert mac['physicalDeviceTested'] is False and mac['gameplayMeasured'] is False
 assert mac['core']['sourcePatchSHA256']==manifest['patch_sha256']==sha('build-utils/rpcs3/embedded-core.patch')
 earlier={}
 for build,(source,run,path) in EARLIER.items():
  evidence=json.loads((ROOT/path).read_bytes())
  assert evidence['build']==build and evidence['result']=='passed' and evidence['source']==source and evidence['run']==run,build
  assert evidence['physicalDeviceTested'] is False and manifest['cell%d'%build]['device_tested'] is False,build
  earlier[build]=dict(source=source,run=run,coreSHA256=evidence['core']['sha256'])
 assert record['device_tested'] is False and record['game_performance_measured'] is False
 assert record['codegen']==manifest['cell579']['codegen']==manifest['cell567']['codegen']
 return dict(coreSource=CORE_SOURCE,coreRun=CORE_RUN,core579Source=CORE579_SOURCE,core579Run=CORE579_RUN,
  core575Source=CORE575_SOURCE,core575Run=CORE575_RUN,
  core573Source=CORE573_SOURCE,core573Run=CORE573_RUN,
  core571Source=CORE571_SOURCE,core571Run=CORE571_RUN,core569Source=CORE569_SOURCE,core569Run=CORE569_RUN,
  core567Source=CORE567_SOURCE,core567Run=CORE567_RUN,core565Source=CORE565_SOURCE,core565Run=CORE565_RUN,
  core563Source=CORE563_SOURCE,core563Run=CORE563_RUN,core561Source=CORE561_SOURCE,core561Run=CORE561_RUN,
  core560Source=CORE560_SOURCE,core560Run=CORE560_RUN,core559Source=CORE559_SOURCE,core559Run=CORE559_RUN,
  core551Source=CORE551_SOURCE,core551Run=CORE551_RUN,
  sourcePatchSHA256=manifest['patch_sha256'],fixtureSHA256=record['fixture_sha256'],codegen=record['codegen'],
  optimizations={k:v for cell in ('cell567','cell569','cell571','cell573','cell575','cell579','cell581') for k,v in manifest[cell]['optimizations'].items()},
  qosKeep=manifest['cell569']['qos_keep'],textureResidency=manifest['cell573']['texture_residency'],
  scopedTextureRevalidation=manifest['cell573']['scoped_texture_revalidation'],
  passiveLockFairness=manifest['cell571']['passive_lock_fairness'],titleLevers=manifest['cell575']['title_levers'],
  changes579=manifest['cell579']['changes'],changes581=record['changes'],earlierCores=earlier,coreSHA256=mac['core']['sha256'],inputs=native.inputs(),
  hostEvidence=local,macEvidence=mac,physicalDeviceTested=False,fpsGainMeasured=False)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 579 contract, unchanged, on the delivered 579 tree.
 report=inherited(d579.source_contract)
 assert report['productTrees']==tree.product_trees_579(),report['productTrees']
 trees=tree.product_trees()
 # No product tree changes: only the Core, built by its own run, does.
 assert trees==report['productTrees'],trees
 # The pinned index differs from the delivered 579 tree by the 581 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_579()).splitlines())
 allowed=set(tree.CELL581)|set(tree.RECIPE)
 assert changed<=allowed,changed-allowed
 assert {p for p in tree.CELL581 if not p.startswith('docs/')}<=changed
 for p in tree.CELL581:
  if tree.source_of(p):assert (ROOT/p).read_bytes()==at(CORE_SOURCE,p),p
 # The MeloNX engine inputs, the controller relay and the God of War III profile, unchanged, on the pinned tree.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566|d572.ENGINE572
                 |(d576.ENGINE576-set(tree.previous.previous.DELETED577))|ENGINE577):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p,source in tree.previous.previous.APP577.items():assert (ROOT/p).read_bytes()==at(source,p),p
 for p in d565.tree.FIX565:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 # The 581 Core contract and its inputs, on the pinned tree.
 native.source_contract()
 inputs=native.inputs()
 for p,h in inputs.items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core=core_receipt()
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build579=report['build'],source579Recipe=report['source'],
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,rpcCore579Source=CORE579_SOURCE,rpcCore579Run=CORE579_RUN,
  rpcCore575Source=CORE575_SOURCE,rpcCore575Run=CORE575_RUN,
  rpcCore573Source=CORE573_SOURCE,rpcCore573Run=CORE573_RUN,rpcCore571Source=CORE571_SOURCE,rpcCore571Run=CORE571_RUN,
  rpcCore569Source=CORE569_SOURCE,rpcCore569Run=CORE569_RUN,rpcCore567Source=CORE567_SOURCE,rpcCore567Run=CORE567_RUN,
  rpcCore565Source=CORE565_SOURCE,rpcCore565Run=CORE565_RUN,rpcCore563Source=CORE563_SOURCE,rpcCore563Run=CORE563_RUN,
  rpcCore561Source=CORE561_SOURCE,rpcCore561Run=CORE561_RUN,rpcCore560Source=CORE560_SOURCE,rpcCore560Run=CORE560_RUN,
  rpcCore559Source=CORE559_SOURCE,rpcCore559Run=CORE559_RUN,rpcCore551Source=CORE551_SOURCE,rpcCore551Run=CORE551_RUN,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,replaced581=tree.REPLACED,changed581=sorted(changed),
  pinnedFiles=kept,productTrees=trees,productTrees579=report['productTrees'],coreInputs=len(inputs),
  optimizations=core['optimizations'],coreSHA256=core['coreSHA256'],physicalDeviceTested=False,fpsGainMeasured=False)

def core_run():
 """The Core run: the exact commit, its own workflow, each Core step passed."""
 state=previous.api(f'actions/runs/{CORE_RUN}')
 assert state['head_sha']==CORE_SOURCE and state['path']==CORE_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(CORE_RUN,CORE_SOURCE,CORE_STEPS)

def retain_checks():
 """The 579 receipts stay bound to the delivered 579 tree (and its 577 to 554 views); the 581 Core receipt to the pinned tree."""
 inherited(d579.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'rpcs3-cell581-core.json').write_text(json.dumps(dict(core_receipt(),run=core_run()),indent=2)+'\n')
 print('Bound the 579 receipts to the delivered 579 tree and the 581 Core receipt to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation581.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 579 binding on the delivered 579 tree (its own views in turn), then the pinned tree.
  views=[d579.inherited,d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.inherited,
         d565.inherited,d564.inherited,d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,
         d558.inherited,d557.inherited]
  for depth in (17,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX576_ARTIFACT,'dist/melonx576engine'),
                       d549.download(MELONX572_ARTIFACT,'dist/melonx572engine'),d549.download(MELONX566_ARTIFACT,'dist/melonx566engine'),
                       d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),d549.download(MELONX563_ARTIFACT,'dist/melonx563'),
                       d549.download(HOST_ARTIFACT,'dist/melonx-host'),d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),
                       d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558, 564, 566, 572 and 576 engines on the delivered 576 tree, as 577 and 579 bound them, then the 577
  # engine on the delivered 577 tree, and the 562 host on the delivered 562 tree.
  with d577.old_engine():
   with d576.old_engine():
    with d572.old_engine():
     with d566.old_engine():
      with d564.old_engine():
       report['engine563Evidence']=inherited(d579.inherited,d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,
                                             d567.inherited,d566.inherited,d565.inherited,d564.inherited,d563.inherited,
                                             d562.inherited,d558.engine_evidence)
      report['engine564Evidence']=inherited(d579.inherited,d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,
                                            d567.inherited,d566.inherited,d565.inherited,d564.engine_evidence)
     report['engine566Evidence']=inherited(d579.inherited,d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.inherited,
                                           d567.inherited,d566.engine_evidence)
    report['engine572Evidence']=inherited(d579.inherited,d577.inherited,d576.inherited,d575.inherited,d573.inherited,d572.engine_evidence)
   report['engine576Evidence']=inherited(d579.inherited,d577.inherited,d576.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=inherited(d579.inherited,d577.engine_evidence)
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=d577.engine_run()
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
