"""Private551: the RPCS3 551 Core (4e5bf59) and its host files on the validated 550 product tree."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
import rpcs3cell551_tree as tree
import rpcs3cell551_core as native
import liquidglass550_delivery as d550
import melonxthreading549_delivery as d549
import rpcs3cell546_delivery as previous546
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
BUILD='551'
HOST_TREE=close.BASE
# Engine and MeloNX host are the 549/550 ones, byte for byte.
MELONX_SOURCE,MELONX_RUN,MELONX_ARTIFACT=d550.MELONX_SOURCE,d550.MELONX_RUN,d550.MELONX_ARTIFACT
HOST_SOURCE,HOST_RUN,HOST_ARTIFACT=d550.HOST_SOURCE,d550.HOST_RUN,d550.HOST_ARTIFACT
CORE_SOURCE=tree.SOURCE551
CORE_RUN=40247161327
HOST=d550.HOST
# Host files bound to the 551 Core commit, as the 547 recipe bound the logger.
HOST551={'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm','lib/services/rpcs3_game_profile_service.dart'}
validate_psp_core_identity=d550.validate_psp_core_identity
command=previous.command
HOST546,LOGGER=previous546.HOST546,previous546.LOGGER
PRODUCT549,DART549,ENGINE_INPUTS=d550.PRODUCT549,d550.DART549,d550.ENGINE_INPUTS
SHIPPED=d550.SHIPPED
at=close.at
shipped_interface=d550.shipped_interface
assert HOST551<=HOST546 and set(tree.SHIPPED551)==HOST551

def validate_rpc_core_identity(identity):
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 assert identity['source_patch_sha256']==native.manifest()['patch_sha256']
 assert identity['native_source_sha256']==native.manifest()['files_sha256']
 assert identity['cell551_input_sha256']==native.inputs()
 for p,h in identity['cell551_input_sha256'].items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 for p in paths:assert at(source,p)==(ROOT/p).read_bytes(),p

def evidence():
 return d550.evidence()

def bind_550_trees(receipt):
 """The 550 receipts ran on the 551 tree minus the shipped 551 files."""
 assert receipt['productTrees']==tree.product_trees_550(),receipt['productTrees']
 changed={p for p,h in tree.product_trees().items() if h!=receipt['productTrees'][p]}
 assert changed=={p.split('/')[0] for p in tree.SHIPPED551},changed

def validate_interface():
 """The 550 interface receipt: unchanged inputs, the 550 trees under the 551 files."""
 local=evidence()['interface']
 assert local['result']=='passed' and local['physicalDeviceTested'] is False
 assert local['source']==tree.SOURCE_UI and local['flutter']=='3.47.2'
 assert local['passedTests']>=400 and local['testSummary']['failed']==0
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 assert set(local['inputs'])==set(tree.previous.UI) and not set(local['inputs'])&set(tree.CELL551)
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 bind_550_trees(local)
 return local

def source_contract():
 assert os.environ['BUILD_NUMBER']==BUILD and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # Same shipped paths as 550: the 551 host files are two of the 546 host files.
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--',*SHIPPED).splitlines())
 ui=changed&shipped_interface()
 fixed=close.CHANGED|HOST546|PRODUCT549
 assert not ui&fixed,sorted(ui&fixed)
 expected=fixed|ui
 assert changed==expected,changed^expected
 for p in ui:assert (ROOT/p).read_bytes()==at(tree.SOURCE_UI,p),p
 interface=validate_interface()
 for p in close.CHANGED-PRODUCT549:assert (ROOT/p).read_bytes()==at(close.HOST_SOURCE,p),p
 for p in HOST546-HOST551:assert (ROOT/p).read_bytes()==at(tree.HOST_TREE,p),p
 for p in HOST551:assert (ROOT/p).read_bytes()==at(CORE_SOURCE,p),p
 for p in PRODUCT549:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in DART549:assert d549.only_added(at(tree.HOST_TREE,p),(ROOT/p).read_bytes()),p
 native.pin_module().validate_source_contract()
 for p,h in native.inputs().items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in ENGINE_INPUTS:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=int(BUILD),hostTree=tree.HOST_TREE,source547=tree.previous.SOURCE547,
  source548=tree.previous.SOURCE548,source549=tree.previous.SOURCE549,sourceInterface=tree.SOURCE_UI,source551=CORE_SOURCE,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  rpcs3HostFiles=sorted(HOST551),interfaceChanged=sorted(ui),interfaceTests=interface['passedTests'],changed=sorted(expected),
  pinnedFiles=kept,productTrees=tree.product_trees(),productTrees550=tree.product_trees_550(),physicalDeviceTested=False,
  fpsGainMeasured=False,asyncSubmitsDeviceTested=False,configInheritanceDeviceTested=False)

def validate_melonx_rerun(receipt):
 """The 550 MeloNX re-run stays valid: its inputs are unchanged and it ran
 on the 551 tree minus the shipped 551 files (same rules as 550's)."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-close.CHANGED-PRODUCT549:
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 rerun=evidence()['melonx']
 assert rerun['result']=='passed' and rerun['source']==MELONX_SOURCE and rerun['executor']=='local Linux'
 assert rerun['hostTree']==tree.HOST_TREE and rerun['physicalDeviceTested'] is False
 assert set(previous.IMPORT_INPUTS|close.CHANGED|DART549)<=set(rerun['inputs'])
 assert not set(rerun['inputs'])&(set(tree.previous.UI)|set(tree.CELL551))
 for p,h in rerun['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  source=tree.source_of(p) or tree.previous.SOURCE549
  if p in tree.previous.previous.MELONX549:source=MELONX_SOURCE
  assert (ROOT/p).read_bytes()==at(source,p),p
 bind_550_trees(rerun)
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=false reproduced' in rerun['closeStatus']['log']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in d550.MELONX_COUNTS:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 assert '+1 -2: Some tests failed.' in rerun['threading']['negativeControl']['log']
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 assert f"{rerun['analyzerBaselineIssues']} issues found." in rerun['analyzerLog']
 return rerun

def validate_core_tests():
 """The 551 Core receipt: the cell551 tests ran on exactly the 4e5bf59 inputs."""
 local=json.loads(at(CORE_SOURCE,'docs/evidence/rpcs3-cell551-local.json'))
 assert local==json.loads((ROOT/'docs/evidence/rpcs3-cell551-local.json').read_bytes())
 assert local['physicalDeviceTested'] is False and local['fpsClaimed'] is False
 return local

def retain_checks():
 """Import receipts are reused for unchanged inputs; the 550 re-runs stay bound under the 551 files."""
 previous.completed(close.rpc.BASE_RUN,close.rpc.RETAINED_SOURCE)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 rerun=validate_melonx_rerun(receipt)
 (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
 # The reused 549 MeloNX validator reads its frontend receipt under this name.
 (out/'melonx-threading549-tests.json').write_text(json.dumps(rerun,indent=2)+'\n')
 (out/'liquid-glass-ui550-tests.json').write_text(json.dumps(validate_interface(),indent=2)+'\n')
 (out/'rpcs3-cell551-tests.json').write_text(json.dumps(validate_core_tests(),indent=2)+'\n')
 print('Reused the 12 local import checks; bound the 550 interface and MeloNX re-runs to the 551 tree minus the 551 host files.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true');p.add_argument('--download-components',action='store_true')
 p.add_argument('--engine-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation551.json');a=p.parse_args()
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
