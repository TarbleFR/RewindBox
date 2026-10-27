"""Private577: the interface and controller files of 48b9865 (system bubbles option, controller back after a game, latched `⋯` menu) on the delivered 576 product tree.

577 ships the 576 product (the 575 product with the MeloNX engine of
301e0f8; RPCS3 Core 575, God of War III without the 30 fps limiter, MeloNX
keyboard and L3/R3) and changes only Dart interface files, the iOS gamepads
bridge and the RPCS3 input bridge, none of which is an input of the RPCS3
Core or of the MeloNX engine. The 576 recipe therefore runs unchanged on the
delivered 576 tree, which as_576() puts in place of the pinned 577 one for
each inherited check (a scratch index, the 577 files' 576 versions in the
working tree and BUILD_NUMBER 576, all restored afterwards); the 576 recipe
puts the 575 tree and the 572 engine's evidence back for its own inherited
checks in turn. The 577 files, their tests and their compiled markers are
checked on the pinned 577 tree and in the IPA (validate_interface577_ipa).
The source contract is computed once per job and reused on the same bytes
(build-utils/delivery_contract_memo.py).
"""
import argparse,contextlib,hashlib,json,os,sys,tempfile
from pathlib import Path
import interface577_tree as tree
import melonxwarm576_delivery as d576
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build-utils'))
import delivery_contract_memo as memo
BUILD='577'
HOST_TREE=d576.HOST_TREE
# The RPCS3 Core 575, the MeloNX engine of 301e0f8, the MeloNX hosts (558, 562)
# and every file 577 does not ship are the 576 ones.
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
             'MELONX572_SOURCE','MELONX572_RUN','MELONX572_ARTIFACT','MELONX_SOURCE','MELONX_RUN','MELONX_ARTIFACT',
             'ENGINE_STEPS576','EXPORTS576','SYMBOLS576','CORE_TEXT576','ENGINE576','ENGINE_PAYLOAD','engine_entry','sha'):
 globals()[name]=getattr(d576,name)
previous,previous546,d549,d557,d558,d559,d560,d561,d562,d563,d564,d565,d566,d567,d572,d573,d575=(d576.previous,
 d576.previous546,d576.d549,d576.d557,d576.d558,d576.d559,d576.d560,d576.d561,d576.d562,d576.d563,d576.d564,
 d576.d565,d576.d566,d576.d567,d576.d572,d576.d573,d576.d575)
SOURCE577=tree.SOURCE577
SHIPPED577=tree.SHIPPED577

_active=[False]

@contextlib.contextmanager
def as_576():
 """The delivered 576 tree in place of the pinned 577 one: a scratch copy of
 the index with the 577 files at their 576 versions (the two new tests
 absent) and this recipe removed, the same 577 files in the working tree and
 build number 576. The RPCS3 Core 575 and the MeloNX engine are the same in
 both trees. The 577 bytes, the index in use and the environment are
 restored on exit; a check already inside the 576 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_576()
 files={p:s for p,s in versions.items() if p in tree.FIX577}
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
 # Nothing of the 576 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 576 recipe, run on the delivered 576 tree."""
 with as_576():return function(*args,**kwargs)

@contextlib.contextmanager
def as_575_engine():
 """The delivered 575 tree with the 572 engine's evidence, through the 576 view."""
 with as_576(),d576.as_575_engine():yield

def derived_ipa(ipa):
 """The 576 recipe's 575-equivalent of this IPA (its engine entries swapped
 for the 572 ones), computed on the delivered 576 tree."""
 return inherited(d576.derived_ipa,ipa)

def validate_engine_ipa(ipa):
 return inherited(d576.validate_engine_ipa,ipa)

def engine_evidence():
 return inherited(d576.engine_evidence)

def validate_interface():
 return inherited(d576.validate_interface)

def host_evidence():
 return inherited(d576.host_evidence)

def sha_now(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 576 contract, unchanged, on the delivered 576 tree.
 report=inherited(d576.source_contract)
 assert report['productTrees']==tree.product_trees_576(),report['productTrees']
 trees=tree.product_trees()
 # Only the shipped 577 files change the product: Dart and plugin sources.
 assert {p for p in tree.TREES if trees[p]!=report['productTrees'][p]}=={'lib','packages'},trees
 # The pinned index differs from the delivered 576 tree by the 577 files and this recipe only.
 changed=set(command('git','diff','--cached','--name-only',tree.tree_576()).splitlines())
 expected=set(tree.FIX577)|set(tree.RECIPE)
 assert changed==expected,changed^expected
 for p in tree.FIX577:assert (ROOT/p).read_bytes()==at(SOURCE577,p),p
 # The MeloNX engine inputs, unchanged: the engine run of 301e0f8 built exactly these.
 for p in sorted(set(d558.ENGINE_INPUTS)|set(d564.ENGINE564)|d566.ENGINE566|d572.ENGINE572|ENGINE576):
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The RPCS3 Core 575 and the God of War III profile, unchanged, on the pinned tree.
 d575.native.source_contract()
 for p,h in d575.native.inputs().items():assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 core_receipt()
 for p in d565.tree.FIX565:assert (ROOT/p).read_bytes()==at(d565.tree.SOURCE565APP,p),p
 if INSTALLED.exists():validate_rpc_core_identity(json.loads(INSTALLED.read_bytes()))
 return dict(report,build=int(BUILD),source=head,build576=report['build'],source576Recipe=report['source'],
  source577=SOURCE577,replaced577=tree.REPLACED,shipped577=SHIPPED577,changed577=sorted(changed),
  inputs577={p:sha_now(p) for p in sorted(tree.FIX577)},pinnedFiles=kept,productTrees=trees,
  productTrees576=report['productTrees'],physicalDeviceTested=False,controllerTested=False,gameTested=False)

def retain_checks():
 """The 576 receipts stay bound to the delivered 576 tree (and its 575 to 554 views)."""
 inherited(d576.retain_checks)
 print('Bound the 576 receipts to the delivered 576 tree.')

def logger_proofs():
 """The 576 binding on the delivered 576 tree (its own views in turn), then the pinned tree."""
 views=[d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.inherited,d565.inherited,d564.inherited,
        d563.inherited,d562.inherited,d561.inherited,d560.inherited,d559.inherited,d558.inherited,d557.inherited]
 for depth in (14,12,11,10,9,8,7,6,5,4,3,2,1):inherited(d576.inherited,*views[:depth],previous546.logger_proofs)
 inherited(d576.inherited,previous546.logger_proofs);inherited(previous546.logger_proofs);previous546.logger_proofs()

def engines_576():
 """The 558, 564, 566 and 572 engines and the 562 host as 576 bound them, then the 576 engine."""
 report={}
 with d576.old_engine():
  with d572.old_engine():
   with d566.old_engine():
    with d564.old_engine():
     report['engine563Evidence']=d576.inherited(d575.inherited,d573.inherited,d572.inherited,d567.inherited,
      d566.inherited,d565.inherited,d564.inherited,d563.inherited,d562.inherited,d558.engine_evidence)
    report['engine564Evidence']=d576.inherited(d575.inherited,d573.inherited,d572.inherited,d567.inherited,
     d566.inherited,d565.inherited,d564.engine_evidence)
   report['engine566Evidence']=d576.inherited(d575.inherited,d573.inherited,d572.inherited,d567.inherited,d566.engine_evidence)
  report['engine572Evidence']=d576.inherited(d575.inherited,d573.inherited,d572.engine_evidence)
 report['host562Evidence']=d576.host_evidence()
 report['engineEvidence']=d576.engine_evidence()
 return report

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
  logger_proofs()
  print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(MELONX572_ARTIFACT,'dist/melonx572engine'),
                       d549.download(MELONX566_ARTIFACT,'dist/melonx566engine'),d549.download(MELONX564_ARTIFACT,'dist/melonx564engine'),
                       d549.download(MELONX563_ARTIFACT,'dist/melonx563'),d549.download(HOST_ARTIFACT,'dist/melonx-host'),
                       d549.download(HOST_ARTIFACT553,'dist/melonx-host553'),d549.download(HOST562_ARTIFACT,'dist/melonx-host562')]
 if a.engine_evidence:report.update(inherited(engines_576))
 if a.wait_for_components:report['rpcCore']=inherited(core_run)
 if a.skin_session_evidence:
  report['engine']=inherited(d576.engine_run)
  report['engine572']=inherited(d572.engine_run)
  report['engine566']=inherited(d566.engine_run)
  report['engine564']=inherited(d564.engine_run)
  report['engine563']=previous.completed(MELONX563_RUN,MELONX563_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
  report['host562']=inherited(host_run)
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
