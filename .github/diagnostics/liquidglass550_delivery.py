"""Private550: the e12f1d4 interface on the validated 549 product tree (546 delivery tree, RPCS3 547 Core, MeloNX threading and FPS counter)."""
import argparse,hashlib,json,os,re
from pathlib import Path
import liquidglass550_tree as tree
import melonxthreading549_delivery as d549
import rpcs3cell547_delivery as previous547
import rpcs3cell546_delivery as previous546
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
BUILD='550'
HOST_TREE=close.BASE
# Engine, host and RPCS3 Core are the 549 ones, byte for byte.
MELONX_SOURCE,MELONX_RUN,MELONX_ARTIFACT=d549.MELONX_SOURCE,d549.MELONX_RUN,d549.MELONX_ARTIFACT
HOST_SOURCE,HOST_RUN,HOST_ARTIFACT=d549.HOST_SOURCE,d549.HOST_RUN,d549.HOST_ARTIFACT
CORE_SOURCE,CORE_RUN,HOST=d549.CORE_SOURCE,d549.CORE_RUN,d549.HOST
validate_rpc_core_identity=d549.validate_rpc_core_identity
validate_rpc_core_pin=d549.validate_rpc_core_pin
validate_psp_core_identity=d549.validate_psp_core_identity
command=previous.command
HOST546,LOGGER=previous546.HOST546,previous546.LOGGER
PRODUCT549,DART549,ENGINE_INPUTS=d549.PRODUCT549,d549.DART549,d549.ENGINE_INPUTS
LOCAL=tree.LOCAL
at=close.at
# The 549 frontend tests re-run on the 550 tree, and the interface suite.
MELONX_COUNTS=[('audioHandoff',5),('launchRoute',7),('launchFlow',11),('display',4),('threading',3)]
SHIPPED=('lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock')

def shipped_interface():
 return {p for p in tree.UI if p.startswith(('lib/','packages/'))}

def evidence():
 return json.loads((ROOT/LOCAL).read_text())

def validate_interface():
 """The interface receipt: analyzer and suite on the exact pinned 550 tree."""
 local=evidence()['interface']
 assert local['result']=='passed' and local['physicalDeviceTested'] is False
 assert local['source']==tree.SOURCE_UI and local['flutter']=='3.47.2'
 assert local['passedTests']>=400 and local['testSummary']['failed']==0
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 assert set(local['inputs'])==set(tree.UI)
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 assert local['productTrees']==tree.product_trees(),local['productTrees']
 return local

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # The pinned index differs from the validated 542 host by the MeloNX close
 # fix (544), the 546 host files, the 549 MeloNX files and the interface only.
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--',*SHIPPED).splitlines())
 ui=changed&shipped_interface()
 fixed=close.CHANGED|HOST546|PRODUCT549
 assert not ui&fixed,sorted(ui&fixed)
 expected=fixed|ui
 assert changed==expected,changed^expected
 for p in ui:assert (ROOT/p).read_bytes()==at(tree.SOURCE_UI,p),p
 interface=validate_interface()
 for p in close.CHANGED-PRODUCT549:assert (ROOT/p).read_bytes()==at(close.HOST_SOURCE,p),p
 for p in HOST546-{LOGGER}:assert (ROOT/p).read_bytes()==at(tree.HOST_TREE,p),p
 assert (ROOT/LOGGER).read_bytes()==at(CORE_SOURCE,LOGGER),LOGGER
 for p in PRODUCT549:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in DART549:assert d549.only_added(at(tree.HOST_TREE,p),(ROOT/p).read_bytes()),p
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
 return dict(source=head,build=int(BUILD),hostTree=tree.HOST_TREE,source547=tree.SOURCE547,source548=tree.SOURCE548,
  source549=tree.SOURCE549,sourceInterface=tree.SOURCE_UI,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  interfaceChanged=sorted(ui),interfaceTests=interface['passedTests'],changed=sorted(expected),pinnedFiles=kept,
  productTrees=tree.product_trees(),physicalDeviceTested=False,interfaceDeviceReviewed=False,
  threadingDeviceVerified=False,fpsCounterDeviceVerified=False)

def validate_melonx_rerun(receipt):
 """The 549 frontend tests re-run on the exact 550 tree; the 537 import run
 stays valid for its unchanged inputs (same rules as 549's)."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-close.CHANGED-PRODUCT549:
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 rerun=evidence()['melonx']
 assert rerun['result']=='passed' and rerun['source']==MELONX_SOURCE and rerun['executor']=='local Linux'
 assert rerun['hostTree']==tree.HOST_TREE and rerun['physicalDeviceTested'] is False
 assert set(previous.IMPORT_INPUTS|close.CHANGED|DART549)<=set(rerun['inputs'])
 assert not set(rerun['inputs'])&set(tree.UI),'the MeloNX inputs and the interface are disjoint'
 for p,h in rerun['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  source=tree.source_of(p) or tree.SOURCE549
  if p in tree.previous.MELONX549:source=MELONX_SOURCE
  assert (ROOT/p).read_bytes()==at(source,p),p
 # The tests ran on exactly the shipped lib, native, packages, assets and pubspec.
 assert rerun['productTrees']==tree.product_trees(),rerun['productTrees']
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=false reproduced' in rerun['closeStatus']['log']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in MELONX_COUNTS:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 assert '+1 -2: Some tests failed.' in rerun['threading']['negativeControl']['log']
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 assert f"{rerun['analyzerBaselineIssues']} issues found." in rerun['analyzerLog']
 return rerun

def retain_checks():
 """Import receipts are reused for unchanged inputs; the 550 re-runs cover the rest."""
 previous.completed(close.rpc.BASE_RUN,close.rpc.RETAINED_SOURCE)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 rerun=validate_melonx_rerun(receipt)
 (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
 # The reused 549 MeloNX validator reads its frontend receipt under this name.
 (out/'melonx-threading549-tests.json').write_text(json.dumps(rerun,indent=2)+'\n')
 (out/'liquid-glass-ui550-tests.json').write_text(json.dumps(validate_interface(),indent=2)+'\n')
 print('Reused the 12 local import checks; bound the 550 interface and MeloNX re-runs to the pinned shipped sources.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation550.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.logger_proofs:previous546.logger_proofs();print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.download_components:
  report['downloads']=[d549.download(MELONX_ARTIFACT,'dist/melonx'),d549.download(HOST_ARTIFACT,'dist/melonx-host')]
 if a.engine_evidence:report['engineEvidence']=d549.engine_evidence()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,d549.ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,d549.HOST_STEPS)
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
