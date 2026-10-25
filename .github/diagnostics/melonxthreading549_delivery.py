"""Private549: the Liquid Glass interface (548), the RPCS3 547 Core and MeloNX backend threading with the in-game FPS counter, on the 546 delivery tree."""
import argparse,difflib,hashlib,json,os,re,subprocess,tempfile,zipfile
from pathlib import Path
import melonxthreading549_tree as tree
import rpcs3cell547_delivery as previous547
import rpcs3cell546_delivery as previous546
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
import liquidglass_ui_delivery as glass
ROOT=Path(__file__).resolve().parents[2]
HOST_TREE=close.BASE
# Engine and host built and tested from 9bf068b. The engine run's first attempt
# died fetching the upstream source and left a same-named artifact holding the
# previous engine, so both artifacts are taken by ID and digest.
MELONX_SOURCE='9bf068b3a1dbbd16875f7d843ace4b44402fef13'
MELONX_RUN=40235589254
MELONX_ARTIFACT=(12614789426,'e8fef46d4015659ee1b932f4a8037ce9753bfdcf8b1aa5417567dc8ed08b2498')
HOST_SOURCE,HOST_RUN=MELONX_SOURCE,40235589280
HOST_ARTIFACT=(12615322102,'8a0f0497719722e5f151dc9b6a3db0c6dc46e4bb8fd2433c1ec4d952905b0ff6')
CORE_SOURCE,CORE_RUN,HOST=previous547.CORE_SOURCE,previous547.CORE_RUN,previous547.HOST
validate_rpc_core_identity=previous547.validate_rpc_core_identity
validate_rpc_core_pin=previous547.validate_rpc_core_pin
validate_psp_core_identity=previous547.validate_psp_core_identity
command=previous.command
HOST546,LOGGER=previous546.HOST546,previous546.LOGGER
# Shipped files of 05c2e03 (threading) and 9bf068b (FPS counter).
PRODUCT549={p for p in tree.MELONX549 if p.startswith(('lib/','native/','packages/'))}
DART549={p for p in PRODUCT549 if p.startswith('lib/')}
ENGINE_INPUTS=close.ENGINE_INPUTS+sorted(p for p in tree.MELONX549 if not p.startswith(('lib/','packages/','docs/melonx-persona')))
LOCAL='docs/evidence/melonx-threading549-local.json'
ENGINE_STEPS=['Execute session ownership and render teardown',
 'Execute compiled GPU texture teardown ownership and deferred-release concurrency',
 'Exercise speculative pipeline recovery and preserve fatal GPU errors',
 'Retain effective graphics journal regression proof',
 'Exercise the selected Apple audio backend and update target selection',
 'Execute production audio accounting and Vulkan failure regressions',
 'Exercise display ratios, existing memory settings and stale-session refusal',
 'Compile NativeAOT library and verify exported ABI',
 'Exercise this exact rebuilt engine in an ARM64 iOS app']
HOST_STEPS=['Compile the iPhone host and execute its native ABI scenarios',
 'Exercise audio ownership, route changes and presentation handoff',
 'Exercise registered plugin presentation and retry in actual UIKit',
 'Exercise RAM measurement, graph bounds and timer lifetime in UIKit']
at=close.at
GLASS_RUN=40238111186
# The 548 interface proofs are reused on this tree: rebind them to build 549, the
# RPCS3 547 Core and the host files other proofs fix, now including 549's.
glass.BUILD='549'
glass.CORE_SOURCE,glass.CORE_RUN=CORE_SOURCE,CORE_RUN
glass.HOST_FIXED=close.CHANGED|HOST546|PRODUCT549

def only_added(old,new):
 """True when new is old with lines inserted and nothing removed or rewritten."""
 ops=difflib.SequenceMatcher(None,old.decode().splitlines(),new.decode().splitlines(),autojunk=False).get_opcodes()
 return all(op in ('equal','insert') for op,*_ in ops)

def source_contract():
 assert os.environ['BUILD_NUMBER']=='549' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # The pinned index differs from the validated 542 host by the MeloNX close
 # fix (544), the 546 host files, the 548 interface and the 549 MeloNX files only.
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())
 ui=glass.ui_changed()
 assert ui<=set(tree.GLASS),sorted(ui-set(tree.GLASS))
 expected=close.CHANGED|HOST546|PRODUCT549|ui
 assert changed==expected,changed^expected
 for p in ui:assert (ROOT/p).read_bytes()==at(tree.SOURCE548,p),p
 interface=glass.validate_local_evidence()
 for p in close.CHANGED-PRODUCT549:assert (ROOT/p).read_bytes()==at(close.HOST_SOURCE,p),p
 for p in HOST546-{LOGGER}:assert (ROOT/p).read_bytes()==at(tree.HOST_TREE,p),p
 assert (ROOT/LOGGER).read_bytes()==at(CORE_SOURCE,LOGGER),LOGGER
 for p in PRODUCT549:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 # The Dart changes only add to the delivered 547 versions.
 for p in DART549:assert only_added(at(tree.HOST_TREE,p),(ROOT/p).read_bytes()),p
 previous547.rpc.native.pin_module().validate_source_contract()
 for p,h in previous547.rpc.native.inputs().items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in ENGINE_INPUTS:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=549,hostTree=tree.HOST_TREE,source547=tree.SOURCE547,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  liquidGlassSource=tree.SOURCE548,liquidGlassRun=GLASS_RUN,liquidGlassReceiptSource=interface['source'],
  liquidGlassChanged=sorted(ui),changed=sorted(expected),pinnedFiles=kept,productTrees=tree.product_trees(),
  physicalDeviceTested=False,threadingDeviceVerified=False,fpsCounterDeviceVerified=False,interfaceDeviceReviewed=False)

def validate_local_imports(receipt):
 """The 537 import run stays valid for unchanged inputs; 549 re-ran the rest on its pinned tree."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-close.CHANGED-PRODUCT549:
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 rerun=json.loads((ROOT/LOCAL).read_text())
 assert rerun['result']=='passed' and rerun['source']==MELONX_SOURCE and rerun['executor']=='local Linux'
 assert rerun['hostTree']==tree.HOST_TREE and rerun['physicalDeviceTested'] is False
 assert set(previous.IMPORT_INPUTS|close.CHANGED|DART549)<=set(rerun['inputs'])
 for p,h in rerun['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  if p!='test/melonx_threading549_test.dart':
   source=MELONX_SOURCE if p in tree.MELONX549 else tree.SOURCE548 if p in tree.GLASS else tree.HOST_TREE
   assert (ROOT/p).read_bytes()==at(source,p),p
 # The tests ran on exactly the shipped lib, native, packages, assets and pubspec.
 assert rerun['productTrees']==tree.product_trees(),rerun['productTrees']
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=false reproduced' in rerun['closeStatus']['log']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in [('audioHandoff',5),('launchRoute',7),('launchFlow',11),('display',4),('threading',3)]:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 assert '+1 -2: Some tests failed.' in rerun['threading']['negativeControl']['log']
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 assert f"{rerun['analyzerBaselineIssues']} issues found." in rerun['analyzerLog']
 return rerun

def retain_checks():
 """Import and interface receipts are reused for unchanged inputs; the 549 re-run covers the changed ones."""
 previous.completed(close.rpc.BASE_RUN,close.rpc.RETAINED_SOURCE)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 rerun=validate_local_imports(receipt)
 (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
 (out/'melonx-threading549-tests.json').write_text(json.dumps(rerun,indent=2)+'\n')
 (out/'liquid-glass-ui-tests.json').write_text(json.dumps(glass.validate_local_evidence(),indent=2)+'\n')
 print('Reused the 12 local import checks; bound the 549 re-run to the pinned shipped sources.')

def download(artifact,dest):
 """Fetch one exact artifact by ID and digest; never by name."""
 ident,digest=artifact
 dest=ROOT/dest;dest.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as temp:
  archive=Path(temp)/'artifact.zip'
  with archive.open('wb') as stream:
   subprocess.run(['gh','api',f'repos/TarbleFR/RewindBox/actions/artifacts/{ident}/zip'],stdout=stream,check=True)
  assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest,ident
  with zipfile.ZipFile(archive) as z:z.extractall(dest)
 return dict(artifact=ident,sha256=digest,path=str(dest.relative_to(ROOT)))

def engine_evidence():
 """The downloaded engine and host are the 9bf068b builds with the 549 changes."""
 identity=json.loads((ROOT/'dist/melonx/ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE and 'neostation_melonx_performance_snapshot' in identity['exports']
 for p,h in identity['adaptations'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 session=json.loads((ROOT/'dist/melonx/session-checks.json').read_bytes())
 assert session['source']==MELONX_SOURCE and session['passedCases']==25 and session['reexecuted']
 display=json.loads((ROOT/'dist/melonx/display-checks.json').read_bytes())
 assert display['result']=='passed' and 'PASS 57 graphics, FPS snapshot' in display['summary']
 smoke=json.loads((ROOT/'dist/melonx/runtime-smoke/actual-runtime.json').read_bytes())
 assert smoke['result']=='passed' and smoke['homebrewSimulatorSessions']==2
 assert smoke['performanceSnapshotStaleAndEndedRefused'] and smoke['livePerformanceSnapshotSessions']>=1
 graph=json.loads((ROOT/'dist/melonx-host/memory.json').read_bytes())
 assert graph['result']=='passed' and graph['fpsLabelTested']
 checks=json.loads((ROOT/'dist/melonx-host/checks.json').read_bytes())
 assert checks['source']==HOST_SOURCE and checks['iphoneSDKTypecheck']
 for receipt in (session,display,smoke,graph,checks):
  for p,h in receipt.get('inputs',{}).items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 return dict(coreSHA256=identity['sha256'],sessionCases=session['passedCases'],displaySummary=display['summary'].splitlines()[-1],
  livePerformanceSnapshotSessions=smoke['livePerformanceSnapshotSessions'],threadedSimulatorRelaunches=smoke['homebrewSimulatorSessions'],
  fpsLabelCases=graph['cases'],iphoneSDKTypecheck=checks['iphoneSDKTypecheck'])

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation549.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:previous546.logger_proofs();print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[download(MELONX_ARTIFACT,'dist/melonx'),download(HOST_ARTIFACT,'dist/melonx-host')]
 if a.engine_evidence:report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS)
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
