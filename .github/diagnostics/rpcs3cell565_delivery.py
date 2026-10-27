"""Private565: the RPCS3 Core 565 (07e416c, its own Core run) and the God of War III profile without the 30 fps limiter (c5ba917) on the delivered 564 product tree.

565 ships the 564 product (the 563 product with the MeloNX engine of
876a087) with one profile change (God of War III: frame limit Auto instead
of 30, c5ba917) and swaps the RPCS3 Core: the 563 Core (dd65e86)
becomes the 565 one, built and tested from 07e416c (the early submission kept
on for DBZ, the no-op PUTLLC that keeps reservations, the RSX idle park). The
Core recipe files the 564 tree pins at dd65e86 (canonical delta, manifest,
build script, Core pin test, Core workflow) change with it, so the 564 recipe
runs unchanged on the delivered 564 tree, which as_564() puts in place of the
pinned 565 one for the duration of each inherited check (a scratch index, the
565 files' 564 versions, the profile's included, in the working tree and their Python modules, and
BUILD_NUMBER 564, all restored afterwards); the 564 recipe puts the 563 tree
back for its own inherited checks in turn. The 565 Core identity and its
receipt are checked on the pinned 565 tree. The source contract is computed
once per job and reused on the same bytes (build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,sys,tempfile
from pathlib import Path
import rpcs3cell565_tree as tree
import rpcs3cell565_core as native
import melonxtexture564_delivery as d564
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='565'
HOST_TREE=d564.HOST_TREE
# The MeloNX engine (564), the MeloNX hosts (558, 562) and every shipped file are the 564 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','MELONX_WORKFLOW','ENGINE_STEPS564',
             'MELONX563_SOURCE','MELONX563_RUN','MELONX563_ARTIFACT','INSTALLED','CORE551_SOURCE','CORE551_RUN',
             'CORE559_SOURCE','CORE559_RUN','CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN'):
 globals()[name]=getattr(d564,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563=(d564.previous,d564.previous546,d564.d549,d564.d557,
 d564.d558,d564.d559,d564.d560,d564.d561,d564.d562,d564.d563)
CORE563_SOURCE,CORE563_RUN=d564.CORE_SOURCE,d564.CORE_RUN
CORE_SOURCE=tree.SOURCE565
CORE_RUN=40533429692
CORE_WORKFLOW='.github/workflows/rpcs3-cell565-core.yml'
CORE_STEPS=['Authenticate the 563 Core and execute every 565 native case on ARM64',
            'Compile actual iPhone Core from the verified source',
            'Verify actual Core, exact exports, passive loading and 565 identity',
            'Upload source-built565 Core']
HOST_EVIDENCE='docs/evidence/rpcs3-cell565-host-linux.json'
assert CORE563_SOURCE==tree.SOURCE563 and CORE561_SOURCE==tree.SOURCE561 and CORE560_SOURCE==tree.SOURCE560
# Python modules of 565 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in tree.CELL565 if p.endswith('.py'))

_active=[False]

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in tree.CELL565:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_564():
 """The delivered 564 tree in place of the pinned 565 one: a scratch copy of
 the index with the 565 files at their 564 versions and this recipe removed,
 the same 565 files in the working tree, their Python modules and build
 number 564. The installed 565 Core identity is set aside: the 564 recipe
 checks an installed identity against the 563 Core when one is present, and
 this one checks it against 565. The 565 bytes, modules, the identity, the
 index in use and the environment are restored on exit; a check already
 inside the 564 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_564()
 files={p:s for p,s in versions.items() if p in tree.CELL565 or p in tree.FIX565}
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
   _forget(MODULES)
   sys.modules.update(modules)
   if installed is not None:INSTALLED.write_bytes(installed)
 # Nothing of the 564 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert (INSTALLED.read_bytes() if INSTALLED.is_file() else None)==installed
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 564 recipe, run on the delivered 564 tree."""
 with as_564():return function(*args,**kwargs)

@contextlib.contextmanager
def as_558():
 """The delivered 558 tree, through the 564 view (for the validators of 558 receipts)."""
 with as_564(),d564.as_558():yield

def validate_interface():
 return inherited(d564.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d564.host_evidence)

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def validate_rpc_core_identity(identity):
 """The 565 Core identity, bound to its own commit: the canonical delta,
 every Core source and every recorded input equal the 07e416c blobs and
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
             'cell561_input_sha256','cell563_input_sha256'}&set(identity),set(identity)
 recorded=identity['cell565_input_sha256'];current=native.inputs()
 assert set(recorded)==set(current),set(recorded)^set(current)
 for p,h in recorded.items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
  assert current[p]==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 assert paths and set(paths)<=set(native.inputs()),set(paths)-set(native.inputs())
 for p in paths:assert at(source,p)==(ROOT/p).read_bytes(),p

def core_receipt():
 """The 565 Core: its host and ARM64 evidence names the canonical delta and
 fixture of this checkout; the Core run built and tested them."""
 local=json.loads((ROOT/HOST_EVIDENCE).read_bytes())
 manifest=native.manifest();record=manifest['cell565']
 assert local['build']==565 and local['result']=='passed'
 assert local['physicalDeviceTested'] is False and local['gameplayMeasured'] is False
 assert local['sourcePatchSHA256']==manifest['patch_sha256']==sha('build-utils/rpcs3/embedded-core.patch')
 assert local['fixtureSHA256']==record['fixture_sha256']==sha(native.FIXTURE)
 assert local['hostTest']['report']['passed'] and local['materializedSourceTest']['passed']
 assert local['arm64Correctness']['contention']['keep']['workerFailures']==0
 assert not local['mutationChecks']['notDetected']
 assert record['device_tested'] is False and record['game_performance_measured'] is False
 assert record['codegen']==manifest['cell563']['codegen']==manifest['cell561']['codegen']
 return dict(coreSource=CORE_SOURCE,coreRun=CORE_RUN,core563Source=CORE563_SOURCE,core563Run=CORE563_RUN,
  core561Source=CORE561_SOURCE,core561Run=CORE561_RUN,core560Source=CORE560_SOURCE,core560Run=CORE560_RUN,
  core559Source=CORE559_SOURCE,core559Run=CORE559_RUN,core551Source=CORE551_SOURCE,core551Run=CORE551_RUN,
  sourcePatchSHA256=manifest['patch_sha256'],fixtureSHA256=record['fixture_sha256'],codegen=record['codegen'],
  optimizations=record['optimizations'],earlySubmit=record['early_submit'],noopPutllc=record['noop_putllc'],
  rsxIdlePark=record['rsx_idle_park'],inputs=native.inputs(),hostEvidence=local,physicalDeviceTested=False,
  fpsGainMeasured=False)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 564 contract, unchanged, on the delivered 564 tree.
 report=inherited(d564.source_contract)
 trees=tree.product_trees()
 assert report['productTrees']==tree.product_trees_564(),report['productTrees']
 # Only the lib tree changes, by the God of War III profile.
 assert {p for p in tree.TREES if trees[p]!=report['productTrees'][p]}=={'lib'},trees
 # The pinned index differs from the delivered 564 tree by the 565 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_564()).splitlines())
 allowed=set(tree.CELL565)|set(tree.FIX565)|set(tree.RECIPE)
 assert changed<=allowed,changed-allowed
 assert {p for p in tree.CELL565 if not p.startswith('docs/')}|set(tree.FIX565)<=changed
 for p in tree.CELL565:
  if tree.source_of(p):assert (ROOT/p).read_bytes()==at(CORE_SOURCE,p),p
 for p in tree.FIX565:assert (ROOT/p).read_bytes()==at(tree.SOURCE565APP,p),p
 profile=(ROOT/'lib/services/rpcs3_game_profile_service.dart').read_text()
 assert "'gpu.frame_limit': 'Auto'," in profile and "'gpu.frame_limit': '30'" not in profile
 # The 565 Core contract and its inputs, on the pinned tree.
 native.source_contract()
 inputs=native.inputs()
 for p,h in inputs.items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core=core_receipt()
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build564=report['build'],source564Recipe=report['source'],
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,rpcCore563Source=CORE563_SOURCE,rpcCore563Run=CORE563_RUN,
  rpcCore561Source=CORE561_SOURCE,rpcCore561Run=CORE561_RUN,rpcCore560Source=CORE560_SOURCE,rpcCore560Run=CORE560_RUN,
  rpcCore559Source=CORE559_SOURCE,rpcCore559Run=CORE559_RUN,rpcCore551Source=CORE551_SOURCE,rpcCore551Run=CORE551_RUN,
  replaced565=tree.REPLACED,changed565=sorted(changed),source565App=tree.SOURCE565APP,fix565=tree.FIX565,
  gow3FrameLimit='Auto (60 Hz vblank), was 30',pinnedFiles=kept,productTrees=trees,
  productTrees564=report['productTrees'],coreInputs=len(inputs),optimizations=core['optimizations'],
  physicalDeviceTested=False,fpsGainMeasured=False)

def core_run():
 """The Core run: the exact commit, its own workflow, each Core step passed."""
 state=previous.api(f'actions/runs/{CORE_RUN}')
 assert state['head_sha']==CORE_SOURCE and state['path']==CORE_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(CORE_RUN,CORE_SOURCE,CORE_STEPS)

def retain_checks():
 """The 564 receipts stay bound to the delivered 564 tree (and its 563 to 554 views); the 565 Core receipt to the pinned tree."""
 inherited(d564.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'rpcs3-cell565-core.json').write_text(json.dumps(dict(core_receipt(),run=core_run()),indent=2)+'\n')
 print('Bound the 564 receipts to the delivered 564 tree and the 565 Core receipt to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation565.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 564 binding on the delivered 564 tree (its own views in turn), then the pinned tree.
  inherited(d564.inherited,d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,d558.inherited,d557.inherited,previous546.logger_proofs)
  inherited(d564.inherited,d563.inherited,d562.inherited,d561.inherited,d560.inherited,previous546.logger_proofs)
  inherited(d564.inherited,d563.inherited,d562.inherited,d561.inherited,previous546.logger_proofs)
  inherited(d564.inherited,d563.inherited,d562.inherited,previous546.logger_proofs)
  inherited(d564.inherited,d563.inherited,previous546.logger_proofs)
  inherited(d564.inherited,previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX563_ARTIFACT,'dist/melonx563'),
                       d549.download(HOST_ARTIFACT,'dist/melonx-host'),d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),
                       d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558 engine and 562 host evidence as 564 bound them, then the 564 engine, all on the delivered 564 tree.
  with d564.old_engine():report['engine563Evidence']=inherited(d564.inherited,d563.inherited,d562.inherited,d558.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=inherited(d564.engine_evidence)
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=d564.engine_run()
  report['engine563']=previous.completed(MELONX563_RUN,MELONX563_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
  report['host562']=host_run()
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
