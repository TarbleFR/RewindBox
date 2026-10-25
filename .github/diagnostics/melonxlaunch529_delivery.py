"""Private 529: launch fix over published IPA 527 and validated RPCS3 528, unrelated engines retained."""
import argparse,json,os,time,subprocess
from pathlib import Path
import melonxmemory519_delivery as old
base=old.base
ROOT=Path(__file__).resolve().parents[2]
SOURCE=HOST_SOURCE=APP_SOURCE=MELONX_SOURCE='084fdb5d71609d3529c39cca9efa26093459827d'
HOST_RUN=40143289245
APP_RUN=40143289228
MELONX_RUN=40144482367
MELONX_SOURCE='329d9de706a647481e9d192aee890e92bb0b56ef'
HEADER_SOURCE=old.HEADER_SOURCE
PRODUCT=old.PRODUCT|{'native/melonx/EmbeddedContent.cs','native/melonx/EmbeddedLaunchDiagnostics.cs','packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift'}
validate_rpc_core_identity=old.validate_rpc_core_identity
validate_rpc_core_pin=old.validate_rpc_core_pin
validate_psp_core_identity=old.validate_psp_core_identity
CORE_SOURCE=old.CORE_SOURCE
CORE_RUN=old.CORE_RUN
HOST=old.HOST
ALLOWED=["build-utils/validate_melonx_launch_ipa.py","test/stikjit_unified_build_test.py","test/stikjit_scoped_host_test.py","build-utils/prepare_release527_native_runtime.py",".github/diagnostics/melonxlaunch529_delivery.py","build-utils/delivery-529-recipient.pem","build-utils/melonx/reuse_display_validation.py","build-utils/validate_melonx_memory_ipa.py","build-utils/validate_rpcs3_529_ipa.py","docs/melonx-launch-investigation-2026-10-25.md","lib/services/melonx_internal_service.dart","native/melonx/EmbeddedContent.cs","native/melonx/EmbeddedLaunchDiagnostics.cs","packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift","packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift","test/melonx_launch_flow_test.py","test/melonx_launch_journal_test.py","test/melonx_presentation/Doubles.swift","test/melonx_runtime_smoke.py","test/melonx_session_host_test.py"]

CORE_SOURCE='17ee65469c39e560c91fdb6d55604ab590992f59'
CORE_RUN=40142369420
import hashlib
import rpcs3cell528_core as rpc528
HOST=old.HOST|rpc528.HOST_CHANGED
def validate_rpc_core_identity(identity):
 assert identity['host_commit']==CORE_SOURCE
 assert identity['sha256']=='0ad782b8ee49508165dfb694d19c9400f18c659c5584482228215bfdfc316dcb'
 assert identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and identity['legacy_core_bundled'] is False
 for p,h in identity['cell528_input_sha256'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 for p in paths:
  expected=__import__('subprocess').check_output(['git','show',CORE_SOURCE+':'+p],cwd=ROOT)
  assert expected==(ROOT/p).read_bytes(),p

def main():
 p=argparse.ArgumentParser();p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*');p.add_argument('--source-only',action='store_true');p.add_argument('--wait-for-components',action='store_true');p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope');p.add_argument('--output',default='build/delivery/reused-validation.json');a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 assert os.environ['BUILD_NUMBER']=='529'
 changed=set(base.command(['git','diff','--name-only','17ee65469c39e560c91fdb6d55604ab590992f59','HEAD']).splitlines())
 assert not changed-set(ALLOWED),sorted(changed-set(ALLOWED))
 for path in ['lib/services/melonx_internal_service.dart', 'native/melonx/EmbeddedContent.cs', 'native/melonx/EmbeddedLaunchDiagnostics.cs', 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift', 'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift']:
  assert base.command(['git','show',(MELONX_SOURCE if path.startswith('native/') else SOURCE)+':'+path])==(ROOT/path).read_text().strip(),path
 identity=json.loads((ROOT/'dist/rpcs3-native/identity.json').read_text()) if (ROOT/'dist/rpcs3-native/identity.json').exists() else None
 if identity:validate_rpc_core_identity(identity)
 record=dict(result='passed',source=base.command(['git','rev-parse','HEAD']),sourceBaseline='17ee65469c39e560c91fdb6d55604ab590992f59',baselineIpaBuild=527,baselineIpaSha256='884a44dea6e627fc9cd774d296dc2abf1ef683ca01572651d5c0e3425bd9756e',otherEnginesUnchanged=True,physicalDeviceTested=False)
 if not a.source_only:
  record['componentEvidence']=[]
  engine=base.api('actions/jobs/121022792003')
  assert engine['head_sha']==MELONX_SOURCE
  phases=['Reuse exact successful key, personal configuration and launch validation','Execute production input driver ownership','Exercise display ratios, existing memory settings and stale-session refusal','Compile NativeAOT library and verify exported ABI']
  assert all(next(s for s in engine['steps'] if s['name']==n)['conclusion']=='success' for n in phases)
  record['compiledEngineEvidence']={'run':MELONX_RUN,'source':MELONX_SOURCE,'passedPhases':phases,'overallConclusion':'failure','retainedFailure':'The smoke assertion searched for keysMissing in a journal format that records stage/status rather than an errorCode field. Corrected real-runtime verification is separate.'}
  while True:
   state=base.api('actions/runs/40145060306')
   assert state['head_sha']=='291439626dd6bc10ecd918e16f29e8fda5f111ed'
   if state['status']=='completed':break
   print('Waiting for corrected real NativeAOT verification',flush=True);time.sleep(20)
  record['actualRuntimeEvidence']=base.successful_run(40145060306,'291439626dd6bc10ecd918e16f29e8fda5f111ed',['actual-runtime'])
  for run,job in [(HOST_RUN,'host'),(APP_RUN,'flutter'),(40143289282,'display')]:
   while True:
    state=base.api('actions/runs/'+str(run));assert state['head_sha']==(MELONX_SOURCE if run==MELONX_RUN else SOURCE)
    if state['status']=='completed':break
    print('Waiting for validated component',run,flush=True);time.sleep(20)
   record['componentEvidence'].append(base.successful_run(run,(MELONX_SOURCE if run==MELONX_RUN else SOURCE),[job]))
 job=base.api('actions/jobs/121019312615')
 assert job['head_sha']==SOURCE
 names=['Analyze the final app and retired locale-key removal','Exercise the adjusted console and retirement scenarios']
 assert all(next(s for s in job['steps'] if s['name']==name)['conclusion']=='success' for name in names)
 record['retirementPassedPhases']=names
 record['retainedUnrelatedFailure']={'run':40143289284,'step':'Protect unchanged libraries, the remaining JIT helpers and routing','reason':'Six concurrent NeoSwap source identities differ; this candidate uses the exact 528 source identities checked against its Core artifact.'}
 out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':main()
