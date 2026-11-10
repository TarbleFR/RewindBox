"""Private567: the RPCS3 Core 567 (67dd222, its own Core run) on the delivered 566 product tree.

567 ships the 566 product (the 565 product with the MeloNX engine of
86c2b4d; RPCS3 Core 565, God of War III without the 30 fps limiter) and swaps
only the RPCS3 Core: the 565 Core (07e416c) becomes the 567 one, built and
tested from 67dd222 (the RSX thread priority and the pooled-worker QoS
reset). The Core recipe files the 566 tree pins at 07e416c (canonical delta,
manifest, build script, Core pin test, Core workflow) change with it, so the
566 recipe runs unchanged on the delivered 566 tree, which as_566() puts in
place of the pinned 567 one for the duration of each inherited check (a
scratch index, the 567 files' 566 versions in the working tree and their
Python modules, and BUILD_NUMBER 566, all restored afterwards); the 566
recipe puts the 565 tree back for its own inherited checks in turn. The
MeloNX engine, its downloaded evidence and every shipped file are the 566
ones. The 567 Core identity and its receipt are checked on the pinned 567
tree. The source contract is computed once per job and reused on the same
bytes (build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,importlib,json,os,sys,tempfile
from pathlib import Path
import rpcs3cell567_tree as tree
import rpcs3cell567_core as native
import melonxjit566_delivery as d566
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='567'
HOST_TREE=d566.HOST_TREE
# The MeloNX engine (566), the MeloNX hosts (558, 562) and every shipped file are the 566 ones.
for name in ('HOST_SOURCE','HOST_RUN','HOST_ARTIFACT','HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553',
             'ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP','command','at','shipped_interface','HOST562_SOURCE',
             'HOST562_RUN','HOST562_ARTIFACT','HOST562_WORKFLOW','HOST_STEPS562','SHIPPED562','host_run',
             'MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','MELONX_WORKFLOW','ENGINE_STEPS566',
             'MELONX564_SOURCE','MELONX564_RUN','MELONX564_ARTIFACT','MELONX563_SOURCE','MELONX563_RUN',
             'MELONX563_ARTIFACT','INSTALLED','CORE551_SOURCE','CORE551_RUN','CORE559_SOURCE','CORE559_RUN',
             'CORE560_SOURCE','CORE560_RUN','CORE561_SOURCE','CORE561_RUN','CORE563_SOURCE','CORE563_RUN'):
 globals()[name]=getattr(d566,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565=(d566.previous,d566.previous546,d566.d549,
 d566.d557,d566.d558,d566.d559,d566.d560,d566.d561,d566.d562,d566.d563,d566.d564,d566.d565)
CORE565_SOURCE,CORE565_RUN=d566.CORE_SOURCE,d566.CORE_RUN
CORE_SOURCE=tree.SOURCE567
CORE_RUN=40547296252
CORE_WORKFLOW='.github/workflows/rpcs3-cell567-core.yml'
CORE_STEPS=['Authenticate the 565 Core and execute every 567 native case on ARM64',
            'Compile actual iPhone Core from the verified source',
            'Verify actual Core, exact exports, passive loading and 567 identity',
            'Upload source-built567 Core']
HOST_EVIDENCE='docs/evidence/rpcs3-cell567-host-linux.json'
MAC_EVIDENCE='docs/evidence/rpcs3-cell567-macos.json'
assert CORE565_SOURCE==tree.SOURCE565 and CORE563_SOURCE==tree.SOURCE563 and MELONX_SOURCE==tree.SOURCE566
# Python modules of 567 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in tree.CELL567 if p.endswith('.py'))

_active=[False]

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in tree.CELL567:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_566():
 """The delivered 566 tree in place of the pinned 567 one: a scratch copy of
 the index with the 567 files at their 566 versions and this recipe removed,
 the same 567 files in the working tree, their Python modules and build
 number 566. The installed 567 Core identity is set aside: the 566 recipe
 checks an installed identity against the 565 Core when one is present, and
 this one checks it against 567. The 567 bytes, modules, the identity, the
 index in use and the environment are restored on exit; a check already
 inside the 566 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_566()
 files={p:s for p,s in versions.items() if p in tree.CELL567}
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
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d566.BUILD
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
 # Nothing of the 566 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert (INSTALLED.read_bytes() if INSTALLED.is_file() else None)==installed
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 566 recipe, run on the delivered 566 tree."""
 with as_566():return function(*args,**kwargs)

@contextlib.contextmanager
def as_565_engine():
 """The delivered 565 tree with the 564 engine's evidence, through the 566 view."""
 with as_566(),d566.as_565_engine():yield

def validate_interface():
 return inherited(d566.validate_interface)

def host_evidence():
 """The 562 host and keyboard probe evidence, on the delivered 562 tree."""
 return inherited(d566.host_evidence)

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def validate_rpc_core_identity(identity):
 """The 567 Core identity, bound to its own commit: the canonical delta,
 every Core source and every recorded input equal the 67dd222 blobs and
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
             'cell561_input_sha256','cell563_input_sha256','cell565_input_sha256'}&set(identity),set(identity)
 recorded=identity['cell567_input_sha256'];current=native.inputs()
 assert set(recorded)==set(current),set(recorded)^set(current)
 for p,h in recorded.items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
  assert current[p]==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 assert paths and set(paths)<=set(native.inputs()),set(paths)-set(native.inputs())
 for p in paths:assert at(source,p)==(ROOT/p).read_bytes(),p

def core_receipt():
 """The 567 Core: its host evidence names the canonical delta and fixture of
 this checkout, its Mac evidence the Core the run built from them."""
 local=json.loads((ROOT/HOST_EVIDENCE).read_bytes())
 mac=json.loads((ROOT/MAC_EVIDENCE).read_bytes())
 manifest=native.manifest();record=manifest['cell567']
 assert local['build']==567 and local['passed'] and local['result']=='passed'
 assert local['physicalDeviceTested'] is False and local['gameplayMeasured'] is False
 assert local['sourceContract']['baseline']==record['baseline']
 assert local['sourceContract']['fixtureSHA256']==record['fixture_sha256']==sha(native.FIXTURE)
 assert local['sourceContract']['sourceSHA256']==record['after_sha256']
 assert all(e['passed'] and e['modes']==3 for e in local['experiment'].values())
 assert local['placement']=={'resetBeforeEveryJob':True,'singleMappingPath':True,'callersUnchanged':True,
                             'threadCppOtherwiseIdentical':True}
 assert mac['build']==567 and mac['result']=='passed' and mac['source']==CORE_SOURCE and mac['run']==CORE_RUN
 assert mac['physicalDeviceTested'] is False and mac['gameplayMeasured'] is False
 assert mac['core']['sourcePatchSHA256']==manifest['patch_sha256']==sha('build-utils/rpcs3/embedded-core.patch')
 assert mac['darwinKernelModes']==3
 assert record['device_tested'] is False and record['game_performance_measured'] is False
 assert record['codegen']==manifest['cell565']['codegen']==manifest['cell563']['codegen']
 return dict(coreSource=CORE_SOURCE,coreRun=CORE_RUN,core565Source=CORE565_SOURCE,core565Run=CORE565_RUN,
  core563Source=CORE563_SOURCE,core563Run=CORE563_RUN,core561Source=CORE561_SOURCE,core561Run=CORE561_RUN,
  core560Source=CORE560_SOURCE,core560Run=CORE560_RUN,core559Source=CORE559_SOURCE,core559Run=CORE559_RUN,
  core551Source=CORE551_SOURCE,core551Run=CORE551_RUN,sourcePatchSHA256=manifest['patch_sha256'],
  fixtureSHA256=record['fixture_sha256'],codegen=record['codegen'],optimizations=record['optimizations'],
  threadQos=record['thread_qos'],coreSHA256=mac['core']['sha256'],inputs=native.inputs(),hostEvidence=local,
  macEvidence=mac,physicalDeviceTested=False,fpsGainMeasured=False)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 566 contract, unchanged, on the delivered 566 tree.
 report=inherited(d566.source_contract)
 assert report['productTrees']==tree.product_trees_566(),report['productTrees']
 trees=tree.product_trees()
 # No product tree changes: only the Core, built by its own run, does.
 assert trees==report['productTrees'],trees
 # The pinned index differs from the delivered 566 tree by the 567 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_566()).splitlines())
 allowed=set(tree.CELL567)|set(tree.RECIPE)
 assert changed<=allowed,changed-allowed
 assert {p for p in tree.CELL567 if not p.startswith('docs/')}<=changed
 for p in tree.CELL567:
  if tree.source_of(p):assert (ROOT/p).read_bytes()==at(CORE_SOURCE,p),p
 # The MeloNX engine inputs and the God of War III profile, unchanged, on the pinned tree.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in d565.tree.FIX565:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 # The 567 Core contract and its inputs, on the pinned tree.
 native.source_contract()
 inputs=native.inputs()
 for p,h in inputs.items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core=core_receipt()
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build566=report['build'],source566Recipe=report['source'],
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,rpcCore565Source=CORE565_SOURCE,rpcCore565Run=CORE565_RUN,
  rpcCore563Source=CORE563_SOURCE,rpcCore563Run=CORE563_RUN,rpcCore561Source=CORE561_SOURCE,rpcCore561Run=CORE561_RUN,
  rpcCore560Source=CORE560_SOURCE,rpcCore560Run=CORE560_RUN,rpcCore559Source=CORE559_SOURCE,rpcCore559Run=CORE559_RUN,
  rpcCore551Source=CORE551_SOURCE,rpcCore551Run=CORE551_RUN,replaced567=tree.REPLACED,changed567=sorted(changed),
  pinnedFiles=kept,productTrees=trees,productTrees566=report['productTrees'],coreInputs=len(inputs),
  optimizations=core['optimizations'],coreSHA256=core['coreSHA256'],physicalDeviceTested=False,fpsGainMeasured=False)

def core_run():
 """The Core run: the exact commit, its own workflow, each Core step passed."""
 state=previous.api(f'actions/runs/{CORE_RUN}')
 assert state['head_sha']==CORE_SOURCE and state['path']==CORE_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(CORE_RUN,CORE_SOURCE,CORE_STEPS)

def retain_checks():
 """The 566 receipts stay bound to the delivered 566 tree (and its 565 to 554 views); the 567 Core receipt to the pinned tree."""
 inherited(d566.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'rpcs3-cell567-core.json').write_text(json.dumps(dict(core_receipt(),run=core_run()),indent=2)+'\n')
 print('Bound the 566 receipts to the delivered 566 tree and the 567 Core receipt to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation567.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=memo.reuse(BUILD,source_contract,declared=[INSTALLED])
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 566 binding on the delivered 566 tree (its own views in turn), then the pinned tree.
  views=[d566.inherited,d565.inherited,d564.inherited,d563.inherited,d562.inherited,d561.inherited,
         d560.inherited,d559.inherited,d558.inherited,d557.inherited]
  for depth in (10,8,7,6,5,4,3,2,1):inherited(*views[:depth],previous546.logger_proofs)
  inherited(previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),
                       d549.download(MELONX563_ARTIFACT,'dist/melonx563'),d549.download(HOST_ARTIFACT,'dist/melonx-host'),
                       d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:
  # The 558, 564 and 566 engines and the 562 host on the delivered 566 tree, as 566 bound them.
  with d566.old_engine():
   with d564.old_engine():
    report['engine563Evidence']=inherited(d566.inherited,d565.inherited,d564.inherited,d563.inherited,d562.inherited,
                                          d558.engine_evidence)
   report['engine564Evidence']=inherited(d566.inherited,d565.inherited,d564.engine_evidence)
  report['host562Evidence']=host_evidence()
  report['engineEvidence']=inherited(d566.engine_evidence)
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=d566.engine_run()
  report['engine564']=d564.engine_run()
  report['engine563']=previous.completed(MELONX563_RUN,MELONX563_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
  report['host562']=host_run()
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
