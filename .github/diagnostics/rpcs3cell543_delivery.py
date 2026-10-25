"""Private543: deferred RPCS3 shader publication and cache attribution on the validated 542 host, preserving MeloNX540."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
import rpcs3cell543_payload as rpc
import rpcs3cell543_tree as tree
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
BASE='97915e506fa71be02ab38794529e81fad6780803'
MELONX_SOURCE=BASE
MELONX_RUN=40196037086
CORE_SOURCE,CORE_RUN,HOST=rpc.CORE_SOURCE,rpc.CORE_RUN,rpc.HOST
validate_rpc_core_identity=rpc.validate_rpc_core_identity
validate_rpc_core_pin=rpc.validate_rpc_core_pin
validate_psp_core_identity=rpc.validate_psp_core_identity
command=previous.command

def source_contract():
 assert os.environ['BUILD_NUMBER']=='543' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 # The runner pinned the 542 host tree (see rpcs3cell543_tree.py); compare the index.
 rpcs3_files=tree.verify()
 changed=command('git','diff','--cached','--name-only',BASE,'--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock')
 assert not changed,changed
 rpc.native.pin_module().validate_source_contract()
 for p,h in rpc.native.inputs().items():
  assert hashlib.sha256(subprocess.check_output(['git','show',CORE_SOURCE+':'+p],cwd=ROOT)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',MELONX_SOURCE+':'+p],cwd=ROOT),p
 for p in ['build-utils/melonx/prepare_embedded.py','.github/workflows/melonx-core.yml']:
  assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',MELONX_SOURCE+':'+p],cwd=ROOT),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=543,baseline=BASE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,
  rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,hostSourcesUnchanged=True,hostTree=tree.HOST_TREE,rpcs3CoreFiles=rpcs3_files,
  physicalDeviceTested=False,personaVisualFixConfirmed=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--output',default='build/delivery/reused-validation543.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:
  previous.completed(rpc.BASE_RUN,rpc.RETAINED_SOURCE)
  previous.retain_checks()
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,[
   'Exercise speculative pipeline recovery and preserve fatal GPU errors',
   'Retain effective graphics journal regression proof',
   'Exercise the selected Apple audio backend and update target selection',
   'Retain exact unchanged runtime and graphics tests',
   'Compile NativeAOT library and verify exported ABI',
   'Exercise this exact rebuilt engine in an ARM64 iOS app'])
  report['host']=previous.completed(previous.HOST_RUN,previous.HOST_SOURCE,[
   'Compile the iPhone host and execute its native ABI scenarios',
   'Exercise audio ownership, route changes and presentation handoff',
   'Exercise registered plugin presentation and retry in actual UIKit'])
 if not a.source_only:
  out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
