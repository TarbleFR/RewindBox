"""Private558: the MeloNX measurement files (cfce9f6), their engine (8f83748) and iPhone host (e2c9437) on the delivered 557 product tree.

558 replaces files that earlier receipts hash: nine files of the 553 parity
(Swift, header, build_core.sh, ui-strings.json, the parity test) and
prepare_embedded.py. The 557 recipe therefore runs unchanged on the delivered
557 tree, which as_557() puts in place of the pinned 558 one for the duration
of each inherited check (a scratch index, the 558 files' 557 versions in the
working tree and BUILD_NUMBER 557, all restored afterwards); the 557 recipe in
turn checks the 550 interface, 552 fix, 553 MeloNX and 554 import receipts on
the delivered 554 tree (its as_554), and its own receipt on the 557 tree. The
new engine and host are checked on the pinned 558 tree, and the 558 receipt
is bound to it.
"""
import argparse,contextlib,hashlib,json,os,re,tempfile
from pathlib import Path
import melonxperf558_tree as tree
import rpcs3libraryfiles557_delivery as d557
ROOT=Path(__file__).resolve().parents[2]
BUILD='558'
HOST_TREE=d557.HOST_TREE
for name in ('CORE_SOURCE','CORE_RUN','HOST','HOST551','FIX_SOURCE','HOST552','FIX_CORE_INPUTS',
             'validate_rpc_core_identity','validate_rpc_core_pin','validate_psp_core_identity','command',
             'HOST546','LOGGER','SHIPPED','at','shipped_interface','PRODUCT_PARITY','PRODUCT549','PRODUCT',
             'DART549','SERVICE','ENGINE_INPUTS','MELONX_COUNTS','PARITY_CHECKS','ENGINE_STEPS','HOST_STEPS',
             'FIX_SOURCE554','SHIPPED554','IMPORT_TESTS','FIX_SOURCE557','SHIPPED557','LIBRARY_TESTS'):
 globals()[name]=getattr(d557,name)
close,previous,previous546,d549,fix552,d554=d557.close,d557.previous,d557.previous546,d557.d549,d557.fix552,d557.d554
d553=d554.d553
# The engine and host the 553, 554 and 557 receipts are bound to.
MELONX_SOURCE553,MELONX_RUN553,MELONX_ARTIFACT553=d557.MELONX_SOURCE,d557.MELONX_RUN,d557.MELONX_ARTIFACT
HOST_SOURCE553,HOST_RUN553,HOST_ARTIFACT553=d557.HOST_SOURCE,d557.HOST_RUN,d557.HOST_ARTIFACT
# Engine built and tested from 8f83748 (its engine files are those of cfce9f6),
# taken by ID and digest.
MELONX_SOURCE='8f83748bd91fc759f4b199613225bfb4272c4574'
MELONX_RUN=40376664278
MELONX_ARTIFACT=(12676781705,'c3e60bdd7e1010e3230fa336367ae4dc2221e3368e4a2f238c143fae843edc6c')
# iPhone host built and tested from e2c9437 (its Swift files are those of
# cfce9f6), with the performance journal and parity Swift tests on macOS.
HOST_SOURCE='e2c9437843fb6db900e6680f02125c08bf27058f'
HOST_RUN=40385961915
HOST_ARTIFACT=(12682240349,'d88a3d05290a8fd790424e00c1714d4b1aebc0224da32547c0324b4d629ce7b2')
# The RAM graph proof (MeloNXMemoryGraph.swift, MeloNXJitBridgePlugin.mm and
# its test, unchanged since 553) stays the 553 host run's.
GRAPH_STEP='Exercise RAM measurement, graph bounds and timer lifetime in UIKit'
GRAPH_INPUTS=['packages/melonx_internal_bridge/ios/Classes/MeloNXMemoryGraph.swift',
              'packages/melonx_internal_bridge/ios/Classes/MeloNXJitBridgePlugin.mm','test/melonx_memory_graph_test.py']
HOST_STEPS558=[s for s in HOST_STEPS if s!=GRAPH_STEP]+[
 'Execute the per-second performance journal in Swift (threads, pause, line limit, summary, ports)',
 'Execute the stderr capture, repeated stubs, emulation priority and MoltenVK preference in Swift']
EXPORTS558=['neostation_melonx_performance_snapshot','neostation_melonx_select_moltenvk',
            'neostation_melonx_set_present_target_fps','neostation_melonx_audio_pacing']
SOURCE558=tree.SOURCE558
SHIPPED558=set(tree.SHIPPED558)
MELONX558=set(tree.SHIPPED_MELONX558)
DART558=set(tree.SHIPPED_DART558)
CLASSES558={p for p in tree.FIX558 if p.startswith(tree.CLASSES)}
ENGINE558={p for p in tree.FIX558 if p.startswith(('native/melonx/','build-utils/melonx/'))}
FIX557=set(tree.FIX557)
LOCAL=tree.LOCAL
# 558 touches no shipped file of 550, 551, 552, 554 or 557.
assert not SHIPPED558&(HOST546|HOST552|SHIPPED554|SHIPPED557|set(tree.UI550))
assert DART558.isdisjoint(DART549)

_active=[False]

@contextlib.contextmanager
def as_557():
 """The delivered 557 tree in place of the pinned 558 one: a scratch copy of
 the index with the 558 files at their 557 versions and this recipe removed,
 the same 558 files in the working tree, and build number 557. The 558
 bytes, the index in use and the environment are restored on exit; a check
 already inside the 557 view stays in it."""
 if _active[0]:
  yield
  return
 versions=tree.at_557()
 files={p:s for p,s in versions.items() if p in tree.FIX558}
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
   os.environ['GIT_INDEX_FILE']=index;os.environ['BUILD_NUMBER']=d557.BUILD
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
 # Nothing of the 557 view may leak into the pinned tree.
 for p,data in saved.items():
  assert ((ROOT/p).read_bytes() if (ROOT/p).is_file() else None)==data,p
 assert 'GIT_INDEX_FILE' not in os.environ or os.environ['GIT_INDEX_FILE']==env['GIT_INDEX_FILE']

def inherited(function,*args,**kwargs):
 """A check of the 557 recipe, run on the delivered 557 tree."""
 with as_557():return function(*args,**kwargs)

def validate_interface():
 return inherited(d557.validate_interface)

def validate_service():
 return inherited(d557.validate_service)

def validate_fix_tests():
 return inherited(d557.validate_fix_tests)

def validate_import_tests():
 return inherited(d557.validate_import_tests)

def validate_library_file_tests():
 return inherited(d557.validate_library_file_tests)

def validate_melonx_rerun(receipt):
 """The 553 MeloNX re-run, bound to the delivered 554 tree (through 557)."""
 return inherited(d557.inherited,d554.validate_melonx_rerun,receipt)

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def evidence():
 return json.loads((ROOT/LOCAL).read_text())

def validate_melonx_rerun558(receipt):
 """The MeloNX frontend tests re-run on the exact 558 tree (the 549 chain's
 frontend receipt); the 537 import run stays valid for its inputs that
 neither 557 nor 558 changed (557's are bound to its own receipt)."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-close.CHANGED-PRODUCT-FIX557:
  assert sha(p)==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 for p in previous.IMPORT_INPUTS&FIX557:
  assert (ROOT/p).read_bytes()==at(FIX_SOURCE557,p),p
 rerun=evidence()['melonx']
 assert rerun['result']=='passed' and rerun['source']==SOURCE558 and rerun['executor']=='local Linux'
 assert rerun['hostTree']==tree.HOST_TREE and rerun['physicalDeviceTested'] is False
 assert set(previous.IMPORT_INPUTS|close.CHANGED|DART549|PRODUCT|MELONX558|DART558)<=set(rerun['inputs'])
 assert not set(rerun['inputs'])&set(tree.UI550),'the MeloNX inputs and the interface are disjoint'
 for p,h in rerun['inputs'].items():
  assert sha(p)==h,p
 # The tests ran on exactly the shipped lib, native, packages, assets and pubspec.
 assert rerun['productTrees']==tree.product_trees(),rerun['productTrees']
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in MELONX_COUNTS:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 assert 'PASS 45 standalone parity checks' in rerun['parity']['log']
 assert rerun['residue']['passedTests']==1 and '+1: All tests passed!' in rerun['residue']['log']
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 return rerun

def validate_perf_tests():
 """The 558 receipt, produced on the exact pinned 558 tree."""
 local=evidence()
 assert local['result']=='passed' and local['physicalDeviceTested'] is False and local['build']==558
 assert local['source']==SOURCE558 and local['flutter']=='3.47.2'
 assert local['productTrees']==tree.product_trees(),local['productTrees']
 assert local['productTrees557']==tree.product_trees_557()
 assert local['productTrees557']==d557.evidence()['productTrees'],'the 557 view is the delivered 557 tree'
 assert {p for p in tree.FIX558 if not p.startswith('docs/')}<=set(local['inputs'])
 for p,h in local['inputs'].items():
  assert sha(p)==h,p
 for key,path,count in local['testPlan']:
  run=local['tests'][key]
  assert run['test']==path and run['exitCode']==0,key
  if count is not None:assert run['passed']==count,(key,run['passed'])
 for key,marker in (('parity','PASS 45 standalone parity checks'),('perfJournal','PASS 19 performance journal checks'),
                    ('audioPacing','PASS audio pacing counters, export and adapted Apple session')):
  assert marker in local['tests'][key]['log'],key
 assert '"assertions":35' in local['tests']['audioPacing']['log']
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert ('No issues found!' if local['analyzerIssues']==0 else f"{local['analyzerIssues']} issues found.") in local['analyzerLog']
 app=local['applicationAnalyzer']
 assert app['errors']==0 and app['warnings']==0 and app['errors557']==0
 # The whole Dart suite on both trees: the same failing tests (already on the
 # delivered 557 tree), and the 558 tests added.
 suite=local['fullSuite']
 assert set(suite['failedTests'])==set(suite['failedTests557']) and suite['failed']==suite['failed557'],suite
 assert suite['passed']>suite['passed557'],suite
 # Before the change, on the 557 tree: the live log stays behind a migration.
 control=local['negativeControl']
 assert control['tree']=='557' and control['productTrees']==local['productTrees557'],control
 assert control['migrationLog']['exitCode']!=0 and control['appendLog']['exitCode']!=0
 behaviour=control['migrationBehaviour']
 assert behaviour['exitCode']!=0 and '/old/app.log' in behaviour['log'] and 'Some tests failed.' in behaviour['log']
 return local

def engine_evidence():
 """The downloaded engine (8f83748) and host (e2c9437) carry the 558 changes;
 the RAM graph proof is the 553 host's, its inputs unchanged."""
 identity=json.loads((ROOT/'dist/melonx/ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE
 for name in EXPORTS558:assert name in identity['exports'],name
 for p,h in identity['adaptations'].items():assert sha(p)==h,p
 for p in ('native/melonx/EmbeddedAudioPacing.cs','native/melonx/EmbeddedAudioPacingExport.cs',
           'build-utils/melonx/adapt_audio_pacing.py','build-utils/melonx/prepare_embedded.py'):
  assert identity['adaptations'][p]==sha(p),p
 session=json.loads((ROOT/'dist/melonx/session-checks.json').read_bytes())
 assert session['passedCases']==25
 display=json.loads((ROOT/'dist/melonx/display-checks.json').read_bytes())
 assert display['result']=='passed' and 'PASS 69 graphics, FPS snapshot' in display['summary']
 smoke=json.loads((ROOT/'dist/melonx/runtime-smoke/actual-runtime.json').read_bytes())
 assert smoke['result']=='passed' and smoke['homebrewSimulatorSessions']==2
 assert smoke['performanceSnapshotStaleAndEndedRefused'] and smoke['livePerformanceSnapshotSessions']>=1
 checks=json.loads((ROOT/'dist/melonx-host/checks.json').read_bytes())
 assert checks['source']==HOST_SOURCE and checks['iphoneSDKTypecheck'] and checks['nativeABIDouble']
 presentation=json.loads((ROOT/'dist/melonx-host/presentation.json').read_bytes())
 assert presentation['result']=='passed' and presentation['source']==HOST_SOURCE
 for p in CLASSES558:assert checks['inputs'][p]==sha(p),p
 graph=json.loads((ROOT/'dist/melonx-host553/memory.json').read_bytes())
 assert graph['result']=='passed' and graph['fpsLabelTested']
 assert set(graph['inputs'])==set(GRAPH_INPUTS)
 for p in GRAPH_INPUTS:assert at(HOST_SOURCE553,p)==(ROOT/p).read_bytes(),p
 for receipt in (session,display,smoke,graph,checks,presentation):
  for p,h in receipt.get('inputs',{}).items():assert sha(p)==h,p
 return dict(coreSHA256=identity['sha256'],exports=EXPORTS558,sessionCases=session['passedCases'],
  displaySummary=display['summary'].splitlines()[-1],livePerformanceSnapshotSessions=smoke['livePerformanceSnapshotSessions'],
  threadedSimulatorRelaunches=smoke['homebrewSimulatorSessions'],fpsLabelCases=graph['cases'],graphSource=HOST_SOURCE553,
  iphoneSDKTypecheck=checks['iphoneSDKTypecheck'],nativeABIDouble=checks['nativeABIDouble'])

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 tree.parent_contract()
 kept=tree.verify()
 # The 557 contract, unchanged, on the delivered 557 tree.
 report=inherited(d557.source_contract)
 assert report['productTrees']==tree.product_trees_557(),report['productTrees']
 # The pinned index differs from the delivered 557 tree by the 558 files and this recipe only.
 with tempfile.TemporaryDirectory() as scratch:
  env=tree.index_with(tree.at_557(),os.path.join(scratch,'index'))
  view=tree.git('write-tree',env=env)
 changed=set(command('git','diff','--cached','--name-only',view).splitlines())
 expected=set(tree.FIX558)|set(tree.RECIPE)
 assert changed==expected,changed^expected
 for p in SHIPPED558:assert (ROOT/p).read_bytes()==at(SOURCE558,p),p
 # The engine and host runs built exactly these files.
 for p in ENGINE558|set(ENGINE_INPUTS):assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in CLASSES558:assert (ROOT/p).read_bytes()==at(HOST_SOURCE,p),p
 for p in set(tree.UI550):assert (ROOT/p).read_bytes()==at(FIX_SOURCE557 if p in FIX557 else tree.SOURCE_UI,p),p
 for p in SHIPPED554-SHIPPED557:assert (ROOT/p).read_bytes()==at(FIX_SOURCE554,p),p
 for p in SHIPPED557:assert (ROOT/p).read_bytes()==at(FIX_SOURCE557,p),p
 for p in PRODUCT-SHIPPED558:
  assert (ROOT/p).read_bytes()==at(tree.previous.previous.previous.source_of(p) if p in tree.PARITY else MELONX_SOURCE553,p),p
 local=validate_perf_tests()
 return dict(report,build=int(BUILD),source=head,source558=SOURCE558,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],
  graphSource=HOST_SOURCE553,graphRun=HOST_RUN553,graphArtifact=HOST_ARTIFACT553[0],
  melonx553Source=MELONX_SOURCE553,melonx553Run=MELONX_RUN553,
  melonxChanged=sorted(MELONX558),dartChanged=sorted(DART558),replaced=tree.REPLACED,
  perfTests={k:v.get('passed') for k,v in local['tests'].items()},fullSuite=local['fullSuite'],
  pinnedFiles=kept,productTrees=tree.product_trees(),productTrees557=report['productTrees'],
  changed558=sorted(expected),physicalDeviceTested=False,measurementOnly=True,stutterFixClaimed=False)

def retain_checks():
 """The 557 receipts stay bound to the delivered 557 tree (and its 554 view); the 558 receipts to the pinned tree."""
 inherited(d557.retain_checks)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 (out/'melonx-perf558-tests.json').write_text(json.dumps(validate_perf_tests(),indent=2)+'\n')
 # The reused 549 MeloNX validator reads its frontend receipt under this name:
 # the 558 re-run on the pinned tree replaces the 553 one written above.
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 (out/'melonx-threading549-tests.json').write_text(json.dumps(validate_melonx_rerun558(receipt),indent=2)+'\n')
 print('Bound the 558 MeloNX measurement receipt and the 558 MeloNX re-run to the pinned tree.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation558.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:
  inherited(d557.inherited,previous546.logger_proofs);print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(HOST_ARTIFACT,'dist/melonx-host'),
                       d549.download(HOST_ARTIFACT553,'dist/melonx-host553')]
 if a.engine_evidence:report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS558)
  report['graph']=previous.completed(HOST_RUN553,HOST_SOURCE553,[GRAPH_STEP])
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
