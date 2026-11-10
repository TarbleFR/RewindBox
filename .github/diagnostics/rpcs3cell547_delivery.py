"""Private547: RPCS3 547 Core (fence wait, SPU compile pressure) on the validated 546 delivery host."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import rpcs3cell547_payload as rpc
import rpcs3cell547_tree as tree
import rpcs3cell546_delivery as previous546
import melonxclose544_delivery as close
import melonxaudio537_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
HOST_TREE=close.BASE
MELONX_SOURCE,MELONX_RUN=close.MELONX_SOURCE,close.MELONX_RUN
HOST_SOURCE,HOST_RUN=close.HOST_SOURCE,close.HOST_RUN
CORE_SOURCE,CORE_RUN,HOST=rpc.CORE_SOURCE,rpc.CORE_RUN,rpc.HOST
validate_rpc_core_identity=rpc.validate_rpc_core_identity
validate_rpc_core_pin=rpc.validate_rpc_core_pin
validate_psp_core_identity=rpc.validate_psp_core_identity
command=previous.command
logger_proofs=previous546.logger_proofs
HOST546=previous546.HOST546
LOGGER=previous546.LOGGER

def source_contract():
 assert os.environ['BUILD_NUMBER']=='547' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 kept=tree.verify()
 # The pinned index differs from the validated 542 host by the MeloNX close fix
 # (544) and the 546 host files; only the logger changed since 546 (PRESSURE547).
 changed=set(command('git','diff','--cached','--name-only',HOST_TREE,'--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())
 assert changed==close.CHANGED|HOST546,changed^(close.CHANGED|HOST546)
 for p in close.CHANGED:assert (ROOT/p).read_bytes()==close.at(HOST_SOURCE,p),p
 for p in HOST546-{LOGGER}:assert (ROOT/p).read_bytes()==close.at(tree.HOST_TREE,p),p
 assert (ROOT/LOGGER).read_bytes()==close.at(CORE_SOURCE,LOGGER),LOGGER
 rpc.native.pin_module().validate_source_contract()
 for p,h in rpc.native.inputs().items():
  assert hashlib.sha256(close.at(CORE_SOURCE,p)).hexdigest()==h,p
 regression=json.loads((ROOT/'docs/evidence/melonx-pipeline540-local.json').read_bytes())
 assert regression['result']=='passed' and not regression['physicalDeviceTested']
 for p,h in regression['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==close.at(MELONX_SOURCE,p),p
 for p in close.ENGINE_INPUTS:assert (ROOT/p).read_bytes()==close.at(MELONX_SOURCE,p),p
 identity=ROOT/'dist/rpcs3-native/identity.json'
 if identity.exists():validate_rpc_core_identity(json.loads(identity.read_bytes()))
 return dict(source=head,build=547,hostTree=tree.HOST_TREE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  changed=sorted(close.CHANGED|HOST546),pinnedFiles=kept,physicalDeviceTested=False,
  fenceWaitDeviceMeasured=False,compilePressureDeviceMeasured=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation547.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:previous546.retain_checks()
 if a.logger_proofs:logger_proofs();print('Bound the 536 retention and 546 logger runs of this job to the current sources.');return
 if a.wait_for_components:report['rpcCore']=previous.completed(CORE_RUN,CORE_SOURCE)
 if a.skin_session_evidence:
  report['engine']=previous.completed(MELONX_RUN,MELONX_SOURCE,[
   'Execute compiled GPU texture teardown ownership and deferred-release concurrency',
   'Exercise speculative pipeline recovery and preserve fatal GPU errors',
   'Retain effective graphics journal regression proof',
   'Exercise the selected Apple audio backend and update target selection',
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
