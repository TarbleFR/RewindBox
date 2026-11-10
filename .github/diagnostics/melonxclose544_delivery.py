"""Private544: MeloNX close teardown on the validated 542 host and RPCS3 542 Core."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
import rpcs3cell542_payload as rpc
import melonxaudio537_delivery as previous
import melonxclose544_tree as tree
ROOT=Path(__file__).resolve().parents[2]
BASE=tree.HOST_TREE
MELONX_SOURCE='d9f35c2783f7368d31b61f644d970f41bb7bc47b'
MELONX_RUN=40210266656
HOST_SOURCE='eabc057f4058520192f79f361cbd92eba5795f98'
HOST_RUN=40209413009
CORE_SOURCE,CORE_RUN,HOST=rpc.CORE_SOURCE,rpc.CORE_RUN,rpc.HOST
validate_rpc_core_identity=rpc.validate_rpc_core_identity
validate_rpc_core_pin=rpc.validate_rpc_core_pin
validate_psp_core_identity=rpc.validate_psp_core_identity
command=previous.command
CHANGED={
 'lib/services/melonx_internal_service.dart',
 'lib/services/game_launch_manager.dart',
 'lib/widgets/game_launch_dialog.dart',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
}
ENGINE_INPUTS=['build-utils/melonx/adapt_gpu_lifetime.py','build-utils/melonx/prepare_embedded.py',
 '.github/workflows/melonx-core.yml','test/melonx_gpu_teardown_test.py',
 'test/melonx_gpu_teardown/Program.cs','test/melonx_gpu_teardown/Fakes.cs']
LOCAL='docs/evidence/melonx-close544-local.json'

def at(source,p):
 return subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)

def source_contract():
 assert os.environ['BUILD_NUMBER']=='544' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # The pinned index differs from the validated 542 host only in the close fix.
 changed=set(command('git','diff','--cached','--name-only',BASE,'--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())
 assert changed==CHANGED,changed^CHANGED
 for p in CHANGED:assert (ROOT/p).read_bytes()==at(HOST_SOURCE,p),p
 rpc.native.pin_module().validate_source_contract()
 for p,h in rpc.native.inputs().items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 for p in ENGINE_INPUTS:assert (ROOT/p).read_bytes()==at(MELONX_SOURCE,p),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=544,baseline=BASE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  changed=sorted(CHANGED),pinnedFiles=kept,physicalDeviceTested=False,closeTeardownDeviceVerified=False)

def validate_local_imports(receipt):
 """The 537 import run stays valid for unchanged inputs; 544 re-ran it on the changed service."""
 assert receipt==json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 assert receipt['result']=='passed' and receipt['source']==previous.SOURCE and receipt['passedTests']==12
 for p in previous.IMPORT_INPUTS-CHANGED:
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==receipt['inputs'][p],p
  assert (ROOT/p).read_bytes()==at(previous.SOURCE,p),p
 rerun=json.loads((ROOT/LOCAL).read_text())
 assert rerun['result']=='passed' and rerun['source']==HOST_SOURCE and rerun['executor']=='local Linux'
 assert rerun['physicalDeviceTested'] is False and set(previous.IMPORT_INPUTS|CHANGED)<=set(rerun['inputs'])
 for p,h in rerun['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==at(HOST_SOURCE,p),p
 assert rerun['imports']['passedTests']==12 and '+12: All tests passed!' in rerun['imports']['flutterLog']
 assert 'QUARANTINE_CASE fixedNative=false reproduced' in rerun['closeStatus']['log']
 assert 'QUARANTINE_CASE fixedNative=true passed' in rerun['closeStatus']['log']
 for key,count in [('audioHandoff',5),('launchRoute',7),('launchFlow',11)]:
  assert rerun[key]['passedTests']==count and f'+{count}: All tests passed!' in rerun[key]['log'],key
 assert not re.search(r'^\s*(?:error|warning) ',rerun['analyzerLog'],re.M)
 assert f"{rerun['analyzerBaselineIssues']} issues found." in rerun['analyzerLog']
 return rerun

def retain_checks():
 previous.completed(rpc.BASE_RUN,rpc.RETAINED_SOURCE)
 # Same retained 537 import and 536 logger proofs as 542, with the changed
 # MeloNX service bound to its 544 re-run instead of the 537 source.
 previous.validate_local_imports=validate_local_imports
 previous.retain_checks()
 out=ROOT/'build/delivery/melonx-close544-tests.json'
 out.write_text(json.dumps(validate_local_imports(json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())),indent=2)+'\n')

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--output',default='build/delivery/reused-validation544.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,[
   'Execute compiled GPU texture teardown ownership and deferred-release concurrency',
   'Exercise speculative pipeline recovery and preserve fatal GPU errors',
   'Retain effective graphics journal regression proof',
   'Exercise the selected Apple audio backend and update target selection',
   # This engine run executed the runtime regressions instead of reusing them.
   'Execute production audio accounting and Vulkan failure regressions',
   'Compile NativeAOT library and verify exported ABI',
   'Exercise this exact rebuilt engine in an ARM64 iOS app'])
  report['host']=previous.completed(HOST_RUN,HOST_SOURCE,[
   'Compile the iPhone host and execute its native ABI scenarios',
   'Exercise audio ownership, route changes and presentation handoff',
   'Exercise registered plugin presentation and retry in actual UIKit'])
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
