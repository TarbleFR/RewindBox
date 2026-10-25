"""Private538: new RPCS3 Core; all final537 host/MeloNX sources preserved."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
import melonxaudio537_delivery as previous
import rpcs3cell538_core as native
ROOT=Path(__file__).resolve().parents[2]
BASE='961c37f158fc387b2fec418b794cb6e456fadf04'
BASE_RUN=40189073057
CORE_SOURCE='066a3fe6c015a3c25807a9feac07b392d2fc2cb4'
CORE_RUN=40190600339
HOST=previous.HOST
validate_psp_core_identity=previous.validate_psp_core_identity
command=previous.command

def validate_rpc_core_identity(identity):
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 assert identity['source_patch_sha256']==native.manifest()['patch_sha256']
 assert identity['native_source_sha256']==native.manifest()['files_sha256']
 assert identity['cell538_input_sha256']==native.inputs()
 for p,h in identity['cell538_input_sha256'].items():
  assert hashlib.sha256(subprocess.check_output(['git','show',CORE_SOURCE+':'+p],cwd=ROOT)).hexdigest()==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 for p in paths:assert subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)==(ROOT/p).read_bytes(),p

def source_contract():
 assert os.environ['BUILD_NUMBER']=='538' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 changed=command('git','diff','--name-only',BASE,'HEAD','--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock')
 assert not changed,changed
 native.pin_module().validate_source_contract()
 for p,h in native.inputs().items():assert hashlib.sha256(subprocess.check_output(['git','show',CORE_SOURCE+':'+p],cwd=ROOT)).hexdigest()==h,p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=538,hostBaseline=BASE,hostBaselineRun=BASE_RUN,hostSourcesUnchanged=True,otherEmulatorsUnchanged=True,coreSource=CORE_SOURCE,coreRun=CORE_RUN,physicalDeviceTested=False,physicalPerformanceMeasured=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true');p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope');p.add_argument('--output',default='build/delivery/reused-validation538.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:
  previous.completed(BASE_RUN,BASE)
  previous.retain_checks()
 if a.wait_for_components:report['core']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(previous.MELONX_RUN,previous.MELONX_SOURCE,[
   'Exercise the selected Apple audio backend and update target selection','Retain exact unchanged runtime and graphics tests','Compile NativeAOT library and verify exported ABI','Exercise this exact rebuilt engine in an ARM64 iOS app'])
  report['host']=previous.completed(previous.HOST_RUN,previous.HOST_SOURCE,[
   'Compile the iPhone host and execute its native ABI scenarios','Exercise audio ownership, route changes and presentation handoff','Exercise registered plugin presentation and retry in actual UIKit'])
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
