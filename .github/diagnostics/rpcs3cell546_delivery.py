"""Private546: RPCS3 546 Core and bounded restore diagnostics on the 545 host (validated 542 host + MeloNX close teardown)."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import rpcs3cell546_payload as rpc
import rpcs3cell546_core as cell
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
# The 546 host files ship exactly as built and tested with the 546 Core.
HOST546=cell.HOST_ALLOWED
LOGGER='packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
LOGGER_CHANGE=(b'''// CELL546: one compact row per Core report window (~5 s, ~1.5 KiB): the
// current plus one previous generation cover several hours of play.
static const unsigned long long kRPCS3TimelineLimit = 1024 * 1024;''',b'''// CELL546: one compact row per Core report window (~5 s, ~1.9 KiB): each
// generation holds ~1100 windows (~90 min); with the previous one, ~3 h.
static const unsigned long long kRPCS3TimelineLimit = 2 * 1024 * 1024;''')

def source_contract():
 assert os.environ['BUILD_NUMBER']=='546' and os.environ.get('GITHUB_REF_NAME','Claude')=='Claude'
 head=command('git','rev-parse','HEAD');assert os.environ['GITHUB_SHA']==head
 # The host differs from the validated 542 host by the MeloNX close fix (544)
 # and the 546 diagnostics files.
 changed=set(command('git','diff','--name-only',HOST_TREE,'HEAD','--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock').splitlines())
 assert changed==close.CHANGED|HOST546,changed^(close.CHANGED|HOST546)
 for p in close.CHANGED:assert (ROOT/p).read_bytes()==close.at(HOST_SOURCE,p),p
 # The logger's timeline bound was raised after the Core build (1 -> 2 MiB per
 # generation); this delivery re-executes the logger tests on that file.
 for p in HOST546-{LOGGER}:assert (ROOT/p).read_bytes()==close.at(CORE_SOURCE,p),p
 logger=(ROOT/LOGGER).read_bytes()
 assert logger.replace(LOGGER_CHANGE[1],LOGGER_CHANGE[0])==close.at(CORE_SOURCE,LOGGER),LOGGER
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
 return dict(source=head,build=546,hostTree=HOST_TREE,melonxSource=MELONX_SOURCE,melonxRun=MELONX_RUN,
  hostSource=HOST_SOURCE,hostRun=HOST_RUN,rpcCoreSource=CORE_SOURCE,rpcCoreRun=CORE_RUN,
  changed=sorted(close.CHANGED|HOST546),physicalDeviceTested=False,closeTeardownDeviceVerified=False,
  jitCompressionDeviceMeasured=False)

def retain_checks():
 """Import receipts are reused; the changed logger is re-tested on macOS by the cold job."""
 previous.completed(close.rpc.BASE_RUN,close.rpc.RETAINED_SOURCE)
 out=ROOT/'build/delivery';out.mkdir(parents=True,exist_ok=True)
 receipt=json.loads((ROOT/'docs/evidence/melonx-audio537-local.json').read_text())
 rerun=close.validate_local_imports(receipt)
 (out/'melonx-import537-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
 (out/'melonx-close544-tests.json').write_text(json.dumps(rerun,indent=2)+'\n')
 print('Reused the 12 local import checks and the 544 re-run; the 546 logger proof is executed by this delivery.')

def logger_proofs():
 """Bind the Foundation logger runs of this job to the current sources."""
 head=command('git','rev-parse','HEAD')
 if str(ROOT/'test') not in sys.path:sys.path.insert(0,str(ROOT/'test'))
 from rpcs3_retention536_test import input_hashes as retention_inputs
 import rpcs3_diagnostics546_native_test as diag546
 retention=json.loads((ROOT/'build/delivery/retention536-tests.json').read_bytes())
 assert retention['passed'] and retention['source']==head and not retention['physicalDeviceTested']
 assert retention['inputs']==retention_inputs()
 assert retention['results']['before']['returncode']==-6 and retention['results']['after']['returncode']==0
 proof=json.loads((ROOT/'build/delivery/diagnostics546-tests.json').read_bytes())
 assert proof['passed'] and proof['source']==head and not proof['physicalDeviceTested']
 assert proof['inputs']=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in diag546.INPUTS}
 assert proof['results']['before']['returncode']==-6 and proof['results']['after']['returncode']==0
 return dict(retention536=retention,diagnostics546=proof)

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 p.add_argument('--retain-checks',action='store_true');p.add_argument('--wait-for-components',action='store_true')
 p.add_argument('--source-only',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope')
 p.add_argument('--logger-proofs',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation546.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 report=source_contract()
 if a.retain_checks:retain_checks()
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
