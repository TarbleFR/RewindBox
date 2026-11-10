"""Private552: the MeloNX standalone-parity files (62626c0) and their engine and host on the validated 551 product tree."""
import argparse,hashlib,json,os,re
from pathlib import Path
import melonxparity552_tree as tree
import rpcs3cell551_delivery as d551
import liquidglass550_delivery as d550
import melonxthreading549_delivery as d549
import rpcs3cell546_delivery as previous546
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
BUILD='552'
HOST_TREE=close.BASE
# Engine and iPhone host built and tested from 62626c0, taken by ID and digest.
MELONX_SOURCE=tree.SOURCE552
MELONX_RUN=40328874348
MELONX_ARTIFACT=(12654516832,'4ed4f40c0a2fb5f037178f4b5d9f06873199d94a676b123725732e11a0893689')
# The host run of 62626c0 failed only in its UIKit presentation probe, whose
# test doubles lacked the new MoltenVK argument; 0452528 fixed the probe and
# changed no shipped file, so its host run is the one bound here.
HOST_SOURCE,HOST_RUN='0452528a534ce065cdce675120770f28ab94af3b',40330047357
HOST_ARTIFACT=(12653474239,'4da865581a31b5cb94e659043ff0e8b616fa01ca036aa44b36d47ea106e5a5ec')
# The RPCS3 Core and its host files are the 551 ones, byte for byte.
CORE_SOURCE,CORE_RUN,HOST,HOST551=d551.CORE_SOURCE,d551.CORE_RUN,d551.HOST,d551.HOST551
validate_rpc_core_identity=d551.validate_rpc_core_identity
validate_rpc_core_pin=d551.validate_rpc_core_pin
validate_psp_core_identity=d551.validate_psp_core_identity
command=previous.command
HOST546,LOGGER=previous546.HOST546,previous546.LOGGER
SHIPPED=d550.SHIPPED
at=close.at
shipped_interface=d550.shipped_interface
# Shipped MeloNX files: 549's (threading, FPS counter) and 552's, all at 62626c0.
PRODUCT552=set(tree.SHIPPED552)
PRODUCT549=d549.PRODUCT549
PRODUCT=PRODUCT549|PRODUCT552
DART549=d549.DART549
SERVICE='lib/services/melonx_internal_service.dart'
# 552 removes exactly the import of the standalone's stored threading value.
IMPORT_OFF=b"""    // BackendThreading enum: 0=Auto, 1=Off, 2=On. Auto resolves to On for the
    // Vulkan backend, so only an explicit Off maps to disabled.
    if (source['backendThreading'] is int)
      result['backendThreading'] = source['backendThreading'] != 1;
"""
IMPORT_IGNORED=b"""    // backendThreading is not imported: standalone MeloNX stores Off by
    // default but forces On at every launch (RyujinxController), so its
    // saved value never reached the engine there either.
"""
ENGINE_INPUTS=sorted(set(d549.ENGINE_INPUTS)|{p for p in tree.PARITY552 if not p.startswith(('lib/','packages/','docs/melonx-persona'))})
LOCAL=tree.LOCAL
# The MeloNX frontend tests re-run on the exact 552 tree (550's set, the
# changed threading test and the standalone parity checks).
MELONX_COUNTS=d550.MELONX_COUNTS
PARITY_CHECKS=33
ENGINE_STEPS=d549.ENGINE_STEPS
HOST_STEPS=d549.HOST_STEPS
assert not PRODUCT552&(HOST546|set(tree.previous.SHIPPED551)|set(tree.previous.previous.UI))

def evidence():
 return json.loads((ROOT/LOCAL).read_text())

def bind_550_trees(receipt):
 """The 550 receipts ran on the 552 tree with the shipped 551 and 552 files at their 550 versions."""
 assert receipt['productTrees']==tree.product_trees_550(),receipt['productTrees']
 changed={p for p,h in tree.product_trees().items() if h!=receipt['productTrees'][p]}
 assert changed=={p.split('/')[0] for p in tree.previous.SHIPPED551+tree.SHIPPED552},changed

def validate_interface():
 """The 550 interface receipt: unchanged inputs, the 550 trees under the 551 and 552 files."""
 local=d550.evidence()['interface']
 assert local['result']=='passed' and local['physicalDeviceTested'] is False
 assert local['source']==tree.SOURCE_UI and local['flutter']=='3.47.2'
 assert local['passedTests']>=400 and local['testSummary']['failed']==0
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 assert set(local['inputs'])==set(tree.previous.previous.UI)
 assert not set(local['inputs'])&(set(tree.previous.CELL551)|set(tree.PARITY552))
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 bind_550_trees(local)
 return local

def validate_service():
 """melonx_internal_service.dart: 549's additions to the 547 file, minus the threading import."""
 delivered549=at(tree.previous.previous.SOURCE549,SERVICE)
 assert d549.only_added(at(tree.HOST_TREE,SERVICE),delivered549)
 assert delivered549.count(IMPORT_OFF)==1
 assert delivered549.replace(IMPORT_OFF,IMPORT_IGNORED,1)==(ROOT/SERVICE).read_bytes()

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # The pinned index differs from the validated 542 host by the MeloNX close
 # fix (544), the 546/551 host files, the 549 and 552 MeloNX files and the interface only.
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--',*SHIPPED).splitlines())
 ui=changed&shipped_interface()
 fixed=close.CHANGED|HOST546|PRODUCT
 assert not ui&fixed,sorted(ui&fixed)
 expected=fixed|ui
 assert changed==expected,changed^expected
 for p in ui:assert (ROOT/p).read_bytes()==at(tree.SOURCE_UI,p),p
 interface=validate_interface()
 for p in close.CHANGED-PRODUCT:assert (ROOT/p).read_bytes()==at(close.HOST_SOURCE,p),p
 for p in HOST546-HOST551:assert (ROOT/p).read_bytes()==at(tree.HOST_TREE,p),p
 for p in HOST551:assert (ROOT/p).read_bytes()==at(CORE_SOURCE,p),p
 for p in PRODUCT:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in DART549-PRODUCT552:assert d549.only_added(at(tree.HOST_TREE,p),(ROOT/p).read_bytes()),p
 validate_service()
 d551.native.pin_module().validate_source_contract()
 for p,h in d551.native.inputs().items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in ENGINE_INPUTS:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=int(BUILD),hostTree=tree.HOST_TREE,source547=tree.previous.previous.SOURCE547,
  source548=tree.previous.previous.SOURCE548,source549=tree.previous.previous.SOURCE549,sourceInterface=tree.SOURCE_UI,
  source551=tree.SOURCE551,source552=MELONX_SOURCE,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  rpcs3HostFiles=sorted(HOST551),melonxChanged=sorted(PRODUCT552),interfaceChanged=sorted(ui),interfaceTests=interface['passedTests'],
  changed=sorted(expected),pinnedFiles=kept,productTrees=tree.product_trees(),productTrees551=tree.product_trees_551(),
  productTrees550=tree.product_trees_550(),physicalDeviceTested=False,standaloneMoltenVkDeviceTested=False,
  flickerFixClaimed=False)

def validate_melonx_rerun(receipt):
 """The MeloNX frontend tests re-run on the exact 552 tree; the 537 import run
 stays valid for its unchanged inputs."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-close.CHANGED-PRODUCT:
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 rerun=evidence()['melonx']
 assert rerun['result']=='passed' and rerun['source']==MELONX_SOURCE and rerun['executor']=='local Linux'
 assert rerun['hostTree']==tree.HOST_TREE and rerun['physicalDeviceTested'] is False
 assert set(previous.IMPORT_INPUTS|close.CHANGED|DART549|PRODUCT552)<=set(rerun['inputs'])
 assert not set(rerun['inputs'])&set(tree.previous.previous.UI),'the MeloNX inputs and the interface are disjoint'
 for p,h in rerun['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 # The tests ran on exactly the shipped lib, native, packages, assets and pubspec.
 assert rerun['productTrees']==tree.product_trees(),rerun['productTrees']
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=false reproduced' in rerun['closeStatus']['log']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in MELONX_COUNTS:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 # The new threading test fails on the 551 migration, which imported Off.
 assert '+2 -1: Some tests failed.' in rerun['threading']['negativeControl']['log']
 assert f'PASS {PARITY_CHECKS} standalone parity checks' in rerun['parity']['log']
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 assert f"{rerun['analyzerBaselineIssues']} issues found." in rerun['analyzerLog']
 return rerun

def retain_checks():
 """Import receipts are reused for unchanged inputs; the 550 interface stays bound under the 551 and 552 files."""
 previous.completed(close.rpc.BASE_RUN,close.rpc.RETAINED_SOURCE)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 rerun=validate_melonx_rerun(receipt)
 (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
 # The reused 549 MeloNX validator reads its frontend receipt under this name.
 (out/'melonx-threading549-tests.json').write_text(json.dumps(rerun,indent=2)+'\n')
 (out/'liquid-glass-ui550-tests.json').write_text(json.dumps(validate_interface(),indent=2)+'\n')
 (out/'rpcs3-cell551-tests.json').write_text(json.dumps(d551.validate_core_tests(),indent=2)+'\n')
 print('Reused the 12 local import checks; bound the 552 MeloNX re-run to the pinned tree and the 550 interface under the 551 and 552 files.')

def engine_evidence():
 """The downloaded engine and host are the 62626c0 builds with the 552 changes."""
 identity=json.loads((ROOT/'dist/melonx/ios-arm64/identity.json').read_bytes())
 assert identity['host']==MELONX_SOURCE
 for name in ('neostation_melonx_performance_snapshot','neostation_melonx_select_moltenvk','neostation_melonx_set_present_target_fps'):
  assert name in identity['exports'],name
 for p,h in identity['adaptations'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 for p in PRODUCT552:
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
 for p in tree.SHIPPED552:
  if p.startswith('packages/'):assert checks['inputs'][p]==hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),p
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
 p.add_argument('--output',default='build/delivery/reused-validation552.json');a=p.parse_args()
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
