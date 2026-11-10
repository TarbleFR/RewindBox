"""Private552: the 551 launch-crash fix (6b527ca) on the validated 551 product tree, with the 551 Core."""
import argparse,hashlib,json,os,re
from pathlib import Path
import rpcs3fix552_tree as tree
import rpcs3cell551_delivery as d551
import rpcs3cell551_core as native
import liquidglass550_delivery as d550
import melonxthreading549_delivery as d549
import rpcs3cell546_delivery as previous546
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
BUILD='552'
HOST_TREE=close.BASE
# Engine, MeloNX host and RPCS3 Core are the 551 ones, byte for byte.
MELONX_SOURCE,MELONX_RUN,MELONX_ARTIFACT=d551.MELONX_SOURCE,d551.MELONX_RUN,d551.MELONX_ARTIFACT
HOST_SOURCE,HOST_RUN,HOST_ARTIFACT=d551.HOST_SOURCE,d551.HOST_RUN,d551.HOST_ARTIFACT
CORE_SOURCE,CORE_RUN,HOST=d551.CORE_SOURCE,d551.CORE_RUN,d551.HOST
FIX_SOURCE=tree.SOURCE552
# The two shipped 551 host files, now at their 552 versions.
HOST552={'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm','lib/services/rpcs3_game_profile_service.dart'}
HOST551=d551.HOST551
validate_psp_core_identity=d551.validate_psp_core_identity
validate_rpc_core_pin=d551.validate_rpc_core_pin
command=previous.command
HOST546,LOGGER=previous546.HOST546,previous546.LOGGER
PRODUCT549,DART549,ENGINE_INPUTS=d551.PRODUCT549,d551.DART549,d551.ENGINE_INPUTS
SHIPPED=d551.SHIPPED
at=close.at
shipped_interface=d551.shipped_interface
MELONX_COUNTS=d550.MELONX_COUNTS
LOCAL='docs/evidence/rpcs3-fix552-local.json'
assert HOST552==HOST551<=HOST546 and set(tree.SHIPPED552)==HOST552
# Inputs the 551 Core identity recorded that the fix changes: the game
# profiles, their Dart test and the native expectation of the 551 Core test.
# They are data and tests, not Core sources; the Core binary is unchanged.
FIX_CORE_INPUTS=set(native.inputs())&set(tree.FIX552)
assert FIX_CORE_INPUTS=={'lib/services/rpcs3_game_profile_service.dart','test/rpcs3_game_profile_service_test.dart',
                         'test/native/rpcs3_cell551.inc'},FIX_CORE_INPUTS

def validate_rpc_core_identity(identity):
 """The 551 Core identity, bound to its own commit: every recorded input
 equals the 4e5bf59 blob; every input the fix did not change also equals
 this checkout; the changed ones equal the fix commit."""
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 assert identity['source_patch_sha256']==native.manifest()['patch_sha256']
 assert identity['native_source_sha256']==native.manifest()['files_sha256']
 recorded=identity['cell551_input_sha256'];current=native.inputs()
 assert set(recorded)==set(current),set(recorded)^set(current)
 for p,h in recorded.items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
  if p in FIX_CORE_INPUTS:
   assert (ROOT/p).read_bytes()==at(FIX_SOURCE,p),p
  else:
   assert current[p]==h,p

def evidence():
 return d550.evidence()

def local552():
 return json.loads((ROOT/LOCAL).read_text())

def bind_550_trees(receipt):
 """The 550 receipts ran on the 552 tree minus the shipped 551/552 files."""
 assert receipt['productTrees']==tree.product_trees_550(),receipt['productTrees']
 changed={p for p,h in tree.product_trees().items() if h!=receipt['productTrees'][p]}
 assert changed=={p.split('/')[0] for p in tree.SHIPPED552},changed

def validate_interface():
 """The 550 interface receipt: unchanged inputs, the 550 trees under the shipped 552 files."""
 local=evidence()['interface']
 assert local['result']=='passed' and local['physicalDeviceTested'] is False
 assert local['source']==tree.SOURCE_UI and local['flutter']=='3.47.2'
 assert local['passedTests']>=400 and local['testSummary']['failed']==0
 assert not re.search(r'^\s*(?:error|warning) ',local['analyzerLog'],re.M)
 assert f"{local['analyzerIssues']} issues found." in local['analyzerLog']
 assert set(local['inputs'])==set(tree.previous.previous.UI)
 assert not set(local['inputs'])&(set(tree.previous.CELL551)|set(tree.FIX552))
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 bind_550_trees(local)
 return local

def validate_fix_tests():
 """The 552 local receipt: produced on the exact pinned 552 tree."""
 local=local552()
 assert local['result']=='passed' and local['physicalDeviceTested'] is False and local['build']==552
 assert local['source']==FIX_SOURCE and local['coreSource']==CORE_SOURCE
 assert local['productTrees']==tree.product_trees(),local['productTrees']
 assert local['productTrees551']==tree.product_trees_551()
 for p,h in local['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
 assert set(tree.FIX552)-{'docs/rpcs3-crash552.md'}<=set(local['inputs'])
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
 # Same shipped paths as 551: the 552 host files are the two 551 host files.
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--',*SHIPPED).splitlines())
 ui=changed&shipped_interface()
 fixed=close.CHANGED|HOST546|PRODUCT549
 assert not ui&fixed,sorted(ui&fixed)
 expected=fixed|ui
 assert changed==expected,changed^expected
 for p in ui:assert (ROOT/p).read_bytes()==at(tree.SOURCE_UI,p),p
 interface=validate_interface()
 fix=validate_fix_tests()
 for p in close.CHANGED-PRODUCT549:assert (ROOT/p).read_bytes()==at(close.HOST_SOURCE,p),p
 for p in HOST546-HOST552:assert (ROOT/p).read_bytes()==at(tree.HOST_TREE,p),p
 for p in HOST552:assert (ROOT/p).read_bytes()==at(FIX_SOURCE,p),p
 for p in PRODUCT549:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in DART549:assert d549.only_added(at(tree.HOST_TREE,p),(ROOT/p).read_bytes()),p
 native.pin_module().validate_source_contract()
 for p,h in native.inputs().items():
  assert hashlib.sha256(at(FIX_SOURCE if p in FIX_CORE_INPUTS else CORE_SOURCE,p)).hexdigest()==h,p
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
  source551=CORE_SOURCE,source552=FIX_SOURCE,
  melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,melonxArtifact=MELONX_ARTIFACT[0],
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,hostArtifact=HOST_ARTIFACT[0],rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  rpcs3HostFiles=sorted(HOST552),fixCoreInputs=sorted(FIX_CORE_INPUTS),interfaceChanged=sorted(ui),
  interfaceTests=interface['passedTests'],profileTests=fix['profiles']['passedTests'],changed=sorted(expected),
  pinnedFiles=kept,productTrees=tree.product_trees(),productTrees551=tree.product_trees_551(),
  productTrees550=tree.product_trees_550(),physicalDeviceTested=False,crashFixDeviceVerified=False,
  asyncSubmitsEnabledForTitles=[],asyncTextureStreamingEnabledForTitles=[])

def validate_melonx_rerun(receipt):
 """The 550 MeloNX re-run stays valid: its inputs are unchanged and it ran
 on the 552 tree minus the shipped 551/552 files (same rules as 551's)."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-close.CHANGED-PRODUCT549:
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 rerun=evidence()['melonx']
 assert rerun['result']=='passed' and rerun['source']==MELONX_SOURCE and rerun['executor']=='local Linux'
 assert rerun['hostTree']==tree.HOST_TREE and rerun['physicalDeviceTested'] is False
 assert set(previous.IMPORT_INPUTS|close.CHANGED|DART549)<=set(rerun['inputs'])
 assert not set(rerun['inputs'])&(set(tree.previous.previous.UI)|set(tree.previous.CELL551)|set(tree.FIX552))
 for p,h in rerun['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  source=tree.source_of(p) or tree.previous.previous.SOURCE549
  if p in tree.previous.previous.previous.MELONX549:source=MELONX_SOURCE
  assert (ROOT/p).read_bytes()==at(source,p),p
 bind_550_trees(rerun)
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=false reproduced' in rerun['closeStatus']['log']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in MELONX_COUNTS:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 assert '+1 -2: Some tests failed.' in rerun['threading']['negativeControl']['log']
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 assert f"{rerun['analyzerBaselineIssues']} issues found." in rerun['analyzerLog']
 return rerun

def validate_core_tests():
 """The 551 Core receipt still describes the Core this build ships."""
 return d551.validate_core_tests()

def retain_checks():
 """Import receipts are reused for unchanged inputs; the 550 re-runs stay bound under the shipped files."""
 previous.completed(close.rpc.BASE_RUN,close.rpc.RETAINED_SOURCE)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 rerun=validate_melonx_rerun(receipt)
 (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
 # The reused 549 MeloNX validator reads its frontend receipt under this name.
 (out/'melonx-threading549-tests.json').write_text(json.dumps(rerun,indent=2)+'\n')
 (out/'liquid-glass-ui550-tests.json').write_text(json.dumps(validate_interface(),indent=2)+'\n')
 (out/'rpcs3-cell551-tests.json').write_text(json.dumps(validate_core_tests(),indent=2)+'\n')
 (out/'rpcs3-fix552-tests.json').write_text(json.dumps(validate_fix_tests(),indent=2)+'\n')
 print('Reused the 12 local import checks; bound the 550 interface and MeloNX re-runs and the 552 fix receipt to the 552 tree.')

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
 if a.engine_evidence:report['engineEvidence']=d549.engine_evidence()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,d549.ENGINE_STEPS)
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,d549.HOST_STEPS)
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
