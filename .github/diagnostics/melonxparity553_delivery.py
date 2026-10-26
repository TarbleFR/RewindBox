"""Private553: the MeloNX standalone-parity files (62626c0) and their engine and host on the validated 552 product tree (551 tree + RPCS3 launch-crash fix)."""
import argparse,hashlib,json,os,re
from pathlib import Path
import melonxparity553_tree as tree
import rpcs3fix552_delivery as fix552
import rpcs3cell551_delivery as d551
import liquidglass550_delivery as d550
import melonxthreading549_delivery as d549
import rpcs3cell546_delivery as previous546
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
BUILD='553'
HOST_TREE=close.BASE
# Engine and iPhone host built and tested from 62626c0, taken by ID and digest.
MELONX_SOURCE=tree.SOURCE_PARITY
MELONX_RUN=40328874348
MELONX_ARTIFACT=(12654516832,'4ed4f40c0a2fb5f037178f4b5d9f06873199d94a676b123725732e11a0893689')
# The iPhone host is built and tested from a487268: the 62626c0 host with the
# review fixes in two Swift files (the engine does not change).
HOST_SOURCE,HOST_RUN=tree.SOURCE_HOST,None
HOST_ARTIFACT=(None,None)
# The RPCS3 Core is the 551 one and its two host files are the 552 fix's, byte for byte.
CORE_SOURCE,CORE_RUN,HOST,HOST551=fix552.CORE_SOURCE,fix552.CORE_RUN,fix552.HOST,fix552.HOST551
FIX_SOURCE,HOST552,FIX_CORE_INPUTS=fix552.FIX_SOURCE,fix552.HOST552,fix552.FIX_CORE_INPUTS
validate_rpc_core_identity=fix552.validate_rpc_core_identity
validate_rpc_core_pin=fix552.validate_rpc_core_pin
validate_psp_core_identity=fix552.validate_psp_core_identity
command=previous.command
HOST546,LOGGER=previous546.HOST546,previous546.LOGGER
SHIPPED=d550.SHIPPED
at=close.at
shipped_interface=d550.shipped_interface
# Shipped MeloNX files: 549's (threading, FPS counter) and the parity ones, all at 62626c0.
PRODUCT_PARITY=set(tree.SHIPPED_PARITY)
PRODUCT549=d549.PRODUCT549
PRODUCT=PRODUCT549|PRODUCT_PARITY
DART549=d549.DART549
SERVICE='lib/services/melonx_internal_service.dart'
# The parity change removes exactly the import of the standalone's stored threading value.
IMPORT_OFF=b"""    // BackendThreading enum: 0=Auto, 1=Off, 2=On. Auto resolves to On for the
    // Vulkan backend, so only an explicit Off maps to disabled.
    if (source['backendThreading'] is int)
      result['backendThreading'] = source['backendThreading'] != 1;
"""
IMPORT_IGNORED=b"""    // backendThreading is not imported: standalone MeloNX stores Off by
    // default but forces On at every launch (RyujinxController), so its
    // saved value never reached the engine there either.
"""
ENGINE_INPUTS=sorted(set(d549.ENGINE_INPUTS)|{p for p in tree.PARITY if not p.startswith(('lib/','packages/','docs/melonx-persona')) and p not in tree.HOST_FILES})
LOCAL=tree.LOCAL
# The MeloNX frontend tests re-run on the exact 553 tree (550's set, the
# changed threading test and the standalone parity checks).
MELONX_COUNTS=d550.MELONX_COUNTS
PARITY_CHECKS=33
ENGINE_STEPS=d549.ENGINE_STEPS
HOST_STEPS=d549.HOST_STEPS
assert not PRODUCT_PARITY&(HOST546|HOST552|set(tree.previous.previous.previous.UI))

def evidence():
 return json.loads((ROOT/LOCAL).read_text())

def bind_550_trees(receipt):
 """The 550 receipts ran on the 553 tree with every shipped 551/552/553 file at its 550 version."""
 assert receipt['productTrees']==tree.product_trees_550(),receipt['productTrees']
 changed={p for p,h in tree.product_trees().items() if h!=receipt['productTrees'][p]}
 assert changed=={p.split('/')[0] for p in tree.previous.SHIPPED552+tree.SHIPPED_PARITY},changed

def validate_interface():
 """The 550 interface receipt: unchanged inputs, the 550 trees under the RPCS3 and MeloNX files."""
 local=d550.evidence()['interface']
 assert local['result']=='passed' and local['physicalDeviceTested'] is False
 assert local['source']==tree.SOURCE_UI and local['flutter']=='3.47.2'
 assert local['passedTests']>=400 and local['testSummary']['failed']==0
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 assert set(local['inputs'])==set(tree.previous.previous.previous.UI)
 assert not set(local['inputs'])&(set(tree.previous.previous.CELL551)|set(tree.previous.FIX552)|set(tree.PARITY))
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 bind_550_trees(local)
 return local

def validate_service():
 """melonx_internal_service.dart: 549's additions to the 547 file, minus the threading import."""
 delivered549=at(tree.previous.previous.previous.SOURCE549,SERVICE)
 assert d549.only_added(at(tree.HOST_TREE,SERVICE),delivered549)
 assert delivered549.count(IMPORT_OFF)==1
 assert delivered549.replace(IMPORT_OFF,IMPORT_IGNORED,1)==(ROOT/SERVICE).read_bytes()

def validate_fix_tests():
 """The 552 fix receipt, produced on the exact 552 tree: this tree with the
 MeloNX parity files at their 552 versions (the two sets share no file)."""
 local=fix552.local552()
 assert local['result']=='passed' and local['physicalDeviceTested'] is False and local['build']==552
 assert local['source']==FIX_SOURCE and local['coreSource']==CORE_SOURCE
 assert local['productTrees']==tree.product_trees_552(),local['productTrees']
 assert local['productTrees551']==tree.product_trees_551()
 assert not set(local['inputs'])&set(tree.PARITY)
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 assert set(tree.previous.FIX552)-{'docs/rpcs3-crash552.md'}<=set(local['inputs'])
 profiles=local['profiles']
 assert profiles['passedTests']>=12 and profiles['failed']==0 and '+12: All tests passed!' in profiles['log']
 cell=local['cell551WithFixProfile']
 assert cell['result']=='passed' and cell['gow3DatabaseLeaves']==19
 for mode in ('sanitized','thread'):
  scenario=cell['scenarios'][mode]
  assert scenario['failures']==0 and scenario['observedSnapshot']=={'inherited':19,'kept':0},scenario
 for p,h in cell['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 durable=local['coreLogDurable']
 assert durable['passed'] and durable['contract']['writer']=='core_log synchronous, other stages asynchronous'
 assert durable['contract']['coreFatalHandler']=='emit_log(1, text) then std::abort()'
 for p,h in durable['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 return local

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # The pinned index differs from the validated 542 host by the MeloNX close
 # fix (544), the 546 host files (two at their 552 fix versions), the 549 and
 # parity MeloNX files and the interface only.
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--',*SHIPPED).splitlines())
 ui=changed&shipped_interface()
 fixed=close.CHANGED|HOST546|PRODUCT
 assert not ui&fixed,sorted(ui&fixed)
 expected=fixed|ui
 assert changed==expected,changed^expected
 for p in ui:assert (ROOT/p).read_bytes()==at(tree.SOURCE_UI,p),p
 interface=validate_interface()
 fix=validate_fix_tests()
 for p in close.CHANGED-PRODUCT:assert (ROOT/p).read_bytes()==at(close.HOST_SOURCE,p),p
 for p in HOST546-HOST552:assert (ROOT/p).read_bytes()==at(tree.HOST_TREE,p),p
 for p in HOST552:assert (ROOT/p).read_bytes()==at(FIX_SOURCE,p),p
 for p in PRODUCT:assert (ROOT/p).read_bytes()==at(HOST_SOURCE if p in tree.HOST_FILES else MELONX_SOURCE,p),p
 for p in DART549-PRODUCT_PARITY:assert d549.only_added(at(tree.HOST_TREE,p),(ROOT/p).read_bytes()),p
 validate_service()
 fix552.native.pin_module().validate_source_contract()
 for p,h in fix552.native.inputs().items():
  assert hashlib.sha256(at(FIX_SOURCE if p in FIX_CORE_INPUTS else CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in ENGINE_INPUTS:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=int(BUILD),hostTree=tree.HOST_TREE,source547=tree.previous.previous.previous.SOURCE547,
  source548=tree.previous.previous.previous.SOURCE548,source549=tree.previous.previous.previous.SOURCE549,sourceInterface=tree.SOURCE_UI,
  source551=tree.SOURCE551,source552=FIX_SOURCE,sourceParity=MELONX_SOURCE,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],hostFiles=tree.HOST_FILES,
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,rpcs3HostFiles=sorted(HOST552),fixCoreInputs=sorted(FIX_CORE_INPUTS),profileTests=fix['profiles']['passedTests'],
  melonxChanged=sorted(PRODUCT_PARITY),interfaceChanged=sorted(ui),interfaceTests=interface['passedTests'],
  changed=sorted(expected),pinnedFiles=kept,productTrees=tree.product_trees(),productTrees552=tree.product_trees_552(),
  productTrees551=tree.product_trees_551(),productTrees550=tree.product_trees_550(),physicalDeviceTested=False,
  crashFixDeviceVerified=False,standaloneMoltenVkDeviceTested=False,flickerFixClaimed=False)

def validate_melonx_rerun(receipt):
 """The MeloNX frontend tests re-run on the exact 553 tree; the 537 import run
 stays valid for its unchanged inputs."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-close.CHANGED-PRODUCT:
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 rerun=evidence()['melonx']
 assert rerun['result']=='passed' and rerun['source']==MELONX_SOURCE and rerun['executor']=='local Linux'
 assert rerun['hostTree']==tree.HOST_TREE and rerun['physicalDeviceTested'] is False
 assert set(previous.IMPORT_INPUTS|close.CHANGED|DART549|PRODUCT_PARITY)<=set(rerun['inputs'])
 assert not set(rerun['inputs'])&set(tree.previous.previous.previous.UI),'the MeloNX inputs and the interface are disjoint'
 for p,h in rerun['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 # The tests ran on exactly the shipped lib, native, packages, assets and pubspec.
 assert rerun['productTrees']==tree.product_trees(),rerun['productTrees']
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=false reproduced' in rerun['closeStatus']['log']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in MELONX_COUNTS:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 # The new threading test fails on the 552 migration (c605eafd), which imported Off.
 assert '+2 -1: Some tests failed.' in rerun['threading']['negativeControl']['log']
 assert f'PASS {PARITY_CHECKS} standalone parity checks' in rerun['parity']['log']
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 assert f"{rerun['analyzerBaselineIssues']} issues found." in rerun['analyzerLog']
 return rerun

def retain_checks():
 """Import receipts are reused for unchanged inputs; the 550 interface and the 552 fix receipt stay bound under the other shipped files."""
 previous.completed(close.rpc.BASE_RUN,close.rpc.RETAINED_SOURCE)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 rerun=validate_melonx_rerun(receipt)
 (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
 # The reused 549 MeloNX validator reads its frontend receipt under this name.
 (out/'melonx-threading549-tests.json').write_text(json.dumps(rerun,indent=2)+'\n')
 (out/'liquid-glass-ui550-tests.json').write_text(json.dumps(validate_interface(),indent=2)+'\n')
 (out/'rpcs3-cell551-tests.json').write_text(json.dumps(d551.validate_core_tests(),indent=2)+'\n')
 (out/'rpcs3-fix552-tests.json').write_text(json.dumps(validate_fix_tests(),indent=2)+'\n')
 print('Reused the 12 local import checks; bound the 553 MeloNX re-run to the pinned tree, the 550 interface and the 552 fix receipt under the other shipped files.')

def engine_evidence():
 """The downloaded engine (62626c0) and host (a487268) carry the parity changes."""
 identity=json.loads((ROOT/'dist/melonx/ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE
 for name in ('neostation_melonx_performance_snapshot','neostation_melonx_select_moltenvk','neostation_melonx_set_present_target_fps'):
  assert name in identity['exports'],name
 for p,h in identity['adaptations'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 for p in PRODUCT_PARITY:
  if p.startswith('native/'):assert identity['adaptations'][p]==hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),p
 session=json.loads((ROOT/'dist/melonx/session-checks.json').read_bytes())
 assert session['passedCases']==25
 display=json.loads((ROOT/'dist/melonx/display-checks.json').read_bytes())
 assert display['result']=='passed' and 'PASS 69 graphics, FPS snapshot' in display['summary']
 smoke=json.loads((ROOT/'dist/melonx/runtime-smoke/actual-runtime.json').read_bytes())
 assert smoke['result']=='passed' and smoke['homebrewSimulatorSessions']==2
 assert smoke['performanceSnapshotStaleAndEndedRefused'] and smoke['livePerformanceSnapshotSessions']>=1
 graph=json.loads((ROOT/'dist/melonx-host/memory.json').read_bytes())
 assert graph['result']=='passed' and graph['fpsLabelTested']
 checks=json.loads((ROOT/'dist/melonx-host/checks.json').read_bytes())
 assert checks['source']==HOST_SOURCE and checks['iphoneSDKTypecheck']
 # The UIKit probe compiled the shipped plugin with the parity file.
 presentation=json.loads((ROOT/'dist/melonx-host/presentation.json').read_bytes())
 assert presentation['result']=='passed' and presentation['source']==HOST_SOURCE
 for p in tree.SHIPPED_PARITY:
  if p.startswith('packages/'):assert checks['inputs'][p]==hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),p
 for receipt in (session,display,smoke,graph,checks,presentation):
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
 p.add_argument('--output',default='build/delivery/reused-validation553.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:previous546.logger_proofs();print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(HOST_ARTIFACT,'dist/melonx-host')]
 if a.engine_evidence:report['engineEvidence']=engine_evidence()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,HOST_STEPS)
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
