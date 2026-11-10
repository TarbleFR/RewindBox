"""Private559: the RPCS3 Core 559 (07c76ec, run 40403710130) on the delivered 558 product tree.

559 ships the 558 product byte for byte (interface, MeloNX engine and host,
library files, RPCS3 import and host files) and swaps only the RPCS3 Core:
the 551 Core (4e5bf59) becomes the 559 one, built and tested from 07c76ec
(the 551 Core with the 555 diagnostics and the 559 optimizations). The Core
recipe files the earlier receipts pin at the 551 commit (canonical delta,
manifest, build script, Core pin test, Core workflow) change with it, so the
558 recipe runs unchanged on the delivered 558 tree, which as_558() puts in
place of the pinned 559 one for the duration of each inherited check (a
scratch index, the 559 files' 558 versions in the working tree and their
Python modules, and BUILD_NUMBER 558, all restored afterwards). The 559 Core
identity and its receipt are checked on the pinned 559 tree.
"""
import argparse,contextlib,hashlib,importlib,json,os,sys,tempfile
from pathlib import Path
import rpcs3cell559_tree as tree
import rpcs3cell559_core as native
import melonxperf558_delivery as d558
ROOT=Path(__file__).resolve().parents[2]
BUILD='559'
HOST_TREE=d558.HOST_TREE
# The engine, the MeloNX host and every shipped file are the 558 ones.
for name in ('MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT','HOST_SOURCE','HOST_RUN','HOST_ARTIFACT',
             'HOST_SOURCE553','HOST_RUN553','HOST_ARTIFACT553','ENGINE_STEPS','HOST_STEPS558','GRAPH_STEP',
             'command','at','shipped_interface'):
 globals()[name]=getattr(d558,name)
previous,previous546,d549,d557=d558.previous,d558.previous546,d558.d549,d558.d557
CORE551_SOURCE,CORE551_RUN=d558.CORE_SOURCE,d558.CORE_RUN
CORE_SOURCE=tree.SOURCE559
CORE_RUN=40403710130
CORE_WORKFLOW='.github/workflows/rpcs3-cell559-core.yml'
CORE_STEPS=['Authenticate the 555 Core and execute every 559 native case with ARM64 measurements',
            'Compile actual iPhone Core from the verified source',
            'Verify actual Core, exact exports, passive loading and 559 identity',
            'Upload source-built559 Core']
HOST_EVIDENCE='docs/evidence/rpcs3-cell559-host-linux.json'
assert CORE551_SOURCE==tree.SOURCE551
# Python modules of 559 files: each tree imports its own version.
MODULES=sorted(Path(p).stem for p in tree.CELL559 if p.endswith('.py'))

_active=[False]
# The installed Core's identity: the 559 one, which only this recipe checks.
INSTALLED=ROOT/'dist/rpcs3-native/identity.json'

def _forget(modules):
 """Drops cached modules and bytecode, so the next import reads the current file."""
 for name in modules:
  sys.modules.pop(name,None)
 for p in tree.CELL559:
  if p.endswith('.py'):
   for cached in (ROOT/p).parent.glob('__pycache__/'+Path(p).stem+'.*.pyc'):cached.unlink(missing_ok=True)
 importlib.invalidate_caches()

@contextlib.contextmanager
def as_558():
 """The delivered 558 tree in place of the pinned 559 one: a scratch copy of
 the index with the 559 files at their 558 versions and this recipe removed,
 the same 559 files in the working tree, their Python modules and build
 number 558. The installed 559 Core identity is set aside: the earlier
 recipes check an installed identity against the 551 Core when one is
 present, and this one checks it against 559. The 559 bytes, modules, the
 identity, the index in use and the environment are restored on exit; a
 check already inside the 558 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_558()
 files={p:s for p,s in versions.items() if p in tree.CELL559}
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
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d558.BUILD
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
 # Nothing of the 558 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert (INSTALLED.read_bytes() if INSTALLED.is_file() else None)==installed
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 558 recipe, run on the delivered 558 tree."""
 with as_558():return function(*args,**kwargs)

def validate_interface():
 return inherited(d558.validate_interface)

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def validate_rpc_core_identity(identity):
 """The 559 Core identity, bound to its own commit: the canonical delta,
 every Core source and every recorded input equal the 07c76ec blobs and
 this checkout."""
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 manifest=native.manifest()
 assert identity['source_patch_sha256']==manifest['patch_sha256']
 assert identity['native_source_sha256']==manifest['files_sha256']
 assert identity['core_input_sha256']==native.pin_module().core_input_hashes()
 # The identity names this Core's inputs, not an earlier Core's.
 assert not {'cell551_input_sha256','cell555_input_sha256'}&set(identity),set(identity)
 recorded=identity['cell559_input_sha256'];current=native.inputs()
 assert set(recorded)==set(current),set(recorded)^set(current)
 for p,h in recorded.items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
  assert current[p]==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 assert paths and set(paths)<=set(native.inputs()),set(paths)-set(native.inputs())
 for p in paths:assert at(source,p)==(ROOT/p).read_bytes(),p

def core_receipt():
 """The 559 Core: its host and ARM64 evidence names the canonical delta and
 fixture of this checkout; the Core run built and tested them."""
 local=json.loads((ROOT/HOST_EVIDENCE).read_bytes())
 manifest=native.manifest();record=manifest['cell559']
 assert local['build']==559 and local['result']=='passed'
 assert local['physicalDeviceTested'] is False and local['gameplayMeasured'] is False
 assert local['sourcePatchSHA256']==manifest['patch_sha256']==sha('build-utils/rpcs3/embedded-core.patch')
 assert local['fixtureSHA256']==record['fixture_sha256']==sha(native.FIXTURE)
 assert local['hostPreflight']['proofAllTestsPassed'] and local['hostPreflight']['verifyReusePassed']
 assert local['hostPreflight']['proofInputSHA256Count']==len(native.inputs())
 assert all(result['passed'] for result in local['arm64Correctness']['results'].values())
 assert record['device_tested'] is False and record['game_performance_measured'] is False
 return dict(coreSource=CORE_SOURCE,coreRun=CORE_RUN,core551Source=CORE551_SOURCE,core551Run=CORE551_RUN,
  sourcePatchSHA256=manifest['patch_sha256'],fixtureSHA256=record['fixture_sha256'],codegen=record['codegen'],
  codegenAlias=record['codegen_alias'],optimizations=record['optimizations'],
  textureValidationEpoch=record['texture_validation_epoch'],inputs=native.inputs(),hostEvidence=local,
  physicalDeviceTested=False,fpsGainMeasured=False)

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 558 contract, unchanged, on the delivered 558 tree.
 report=inherited(d558.source_contract)
 trees=tree.product_trees()
 assert report['productTrees']==trees==tree.product_trees_558(),'559 ships the 558 product unchanged'
 # The pinned index differs from the delivered 558 tree by the 559 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_558()).splitlines())
 allowed=set(tree.CELL559)|set(tree.RECIPE)
 assert changed<=allowed,changed-allowed
 assert {p for p in tree.CELL559 if not p.startswith('docs/')}<=changed
 for p in tree.CELL559:
  if tree.source_of(p):assert (ROOT/p).read_bytes()==at(CORE_SOURCE,p),p
 # The 559 Core contract and its inputs, on the pinned tree.
 native.source_contract()
 inputs=native.inputs()
 for p,h in inputs.items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core=core_receipt()
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build558=report['build'],source558Recipe=report['source'],
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,rpcCore551Source=CORE551_SOURCE,rpcCore551Run=CORE551_RUN,
  replaced559=tree.REPLACED,changed559=sorted(changed),pinnedFiles=kept,productTrees=trees,
  productTrees558=report['productTrees'],coreInputs=len(inputs),optimizations=core['optimizations'],
  physicalDeviceTested=False,fpsGainMeasured=False)

def core_run():
 """The Core run: the exact commit, its own workflow, each Core step passed."""
 state=previous.api(f'actions/runs/{CORE_RUN}')
 assert state['head_sha']==CORE_SOURCE and state['path']==CORE_WORKFLOW,(state['head_sha'],state['path'])
 return previous.completed(CORE_RUN,CORE_SOURCE,CORE_STEPS)

def retain_checks():
 """The 558 receipts stay bound to the delivered 558 tree (and its 557 and 554 views); the 559 Core receipt to the pinned tree."""
 inherited(d558.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'rpcs3-cell559-core.json').write_text(json.dumps(dict(core_receipt(),run=core_run()),indent=2)+'\n')
 print('Bound the 558 receipts to the delivered 558 tree and the 559 Core receipt to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation559.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  # The 558 binding (through its 557 and 554 views), then the pinned tree.
  inherited(d558.inherited,d557.inherited,previous546.logger_proofs);previous546.logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(HOST_ARTIFACT,'dist/melonx-host'),
                       d549.download(HOST_ARTIFACT553,'dist/melonx-host553')]
 if a.engine_evidence:report['engineEvidence']=d558.engine_evidence()
 if a.wait_for_components:report['rpcCore']=core_run()
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
