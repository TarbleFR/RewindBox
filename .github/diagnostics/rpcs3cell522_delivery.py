"""Bind private Build 522 to the changed source-built Core and preserved 520 app."""
import argparse,json,os
from pathlib import Path
import rpcs3v012_delivery as previous
import rpcs3cell522_core as native
ROOT=Path(__file__).resolve().parents[2]
base=previous.base
CORE_SOURCE='1ae41b6400688d20a8d72173d3d80d0a1fe19710'
CORE_RUN=40095061758
APP_SOURCE='a4b2f27775b4038b7bd143d6cf723a6fc56f5a13'
HOST=previous.HOST|{'packages/neo_swap/ios/Classes/NeoSwap.cpp','native/neoswap-storage/FrameClient.h','native/neoswap-storage/SourceClient.cpp'}
HOST_DELTA_SHA=previous.HOST_DELTA_SHA
validate_host_proof=previous.validate_host_proof
authenticate_host_proof=previous.authenticate_host_proof
validate_psp_core_identity=previous.validate_psp_core_identity
PRODUCT={'native/neoswap-storage/FrameClient.h','native/neoswap-storage/SourceClient.cpp',
 'native/neoswap-storage/tests/frame_archive_test.cpp','native/neoswap-storage/tests/source_archive_test.cpp',
 'packages/neo_swap/ios/Classes/NeoSwap.cpp'}
ASSEMBLY={'.github/diagnostics/rpcs3cell522_delivery.py','.github/workflows/rpcs3-cell522-delivery.yml',
 'build-utils/delivery-522-rpcs3-recipient.pem','build-utils/validate_rpcs3_cell522_ipa.py',
 'build-utils/analyze_rpcs3_cell_sessions.py','docs/rpcs3-cell522.md',
 'docs/evidence/rpcs3-cell522-log-baseline.json','docs/evidence/rpcs3-cell522-validation.json'}
def validate_rpc_core_identity(identity):
 assert identity['host_commit']==CORE_SOURCE
 native.pin_module().validate_core_input_identity(identity)
 assert identity['cell522_input_sha256']==native.inputs()
 assert identity['cpu_baseline']=='armv8.4-a' and identity['legacy_core_bundled'] is False
 assert identity['device_runtime_tested'] is False
def validate_rpc_core_pin(pin,paths):
 assert pin==CORE_SOURCE
 core=native.pin_module();assert len(paths)==len(core.CORE_INPUTS) and set(paths)==set(core.CORE_INPUTS)
 native.source_contract();core.validate_exact_pin(pin)
 print('PASS exact CELL522 source, recipe, inputs, ABI and preserved CPU policy')
def source_closure():
 assert os.environ.get('GITHUB_REF_NAME')=='Claude'
 assert os.environ.get('BUILD_NUMBER','522')=='522'
 native.source_contract()
 for revision in (['HEAD'],[]):
  changed=set(base.command(['git','diff','--name-only',CORE_SOURCE,*revision]).splitlines());assert not changed-ASSEMBLY,sorted(changed-ASSEMBLY)
  product=set(base.command(['git','diff','--name-only',APP_SOURCE,*revision,'--','lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock']).splitlines())
  assert product==PRODUCT,sorted(product^PRODUCT)
 old=native.pin_module().workflow_source_text(base.command(['git','show',APP_SOURCE+':.github/workflows/rpcs3-v012-delivery.yml']))
 current=native.pin_module().workflow_source_text((ROOT/'.github/workflows/rpcs3-cell522-delivery.yml').read_text())
 for token in ('DOLPHIN_CORE_HOST_SHA:','ARMSX2_CORE_HOST_SHA:','ARMSX2_CORE_RUN_ID:',
  'LIBRETRO_CORES_HOST_SHA:','LIBRETRO_CORES_RUN_ID:','name: MeloNX-engine-','name: MeloNX-native-dependencies-'):
  line=next(line.strip() for line in old.splitlines() if token in line);assert line in current,line
 for run in (40038087907,39854858591):assert 'run-id: '+str(run) in old and 'run-id: '+str(run) in current
 for validator in ('validate_rpcs3_ipa.py','validate_single_ipa_distribution.py','validate_neoswap_ipa.py',
  'validate_unified_cheats_ipa.py','validate_hd_textures_ipa.py','validate_melonx_ipa.py','validate_motion507_ipa.py',
  'validate_melonx_delete509_ipa.py','validate_ui_correction511_ipa.py','validate_navigation512_ipa.py',
  'validate_melonx_launch_ipa.py','validate_melonx_keys_ipa.py','validate_melonx_memory_ipa.py','delivery_benchmark.py seal'):
  assert validator in old and validator in current,validator
 return dict(source=base.command(['git','rev-parse','HEAD']),nativeCore=CORE_SOURCE,nativeRun=CORE_RUN,
  preservedAppSource=APP_SOURCE,changedProduct=sorted(PRODUCT),otherEmulatorSourcesPreserved=True,physicalDeviceTested=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('--scope',default='full');p.add_argument('--source-only',action='store_true')
 p.add_argument('--wait-for-components',action='store_true');p.add_argument('--skin-session-evidence',action='store_true')
 p.add_argument('--verify-host-proof',action='store_true');p.add_argument('--output',default='build/delivery/reused-validation.json')
 p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*');a=p.parse_args()
 if a.verify_host_proof:authenticate_host_proof();return
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 record=dict(result='passed',sourceClosure=source_closure())
 if not a.source_only:
  record['reusedEvidence']=[previous.component(CORE_RUN,CORE_SOURCE,['RPCS3 CELL522: writer counters and iPhone Core'],a.wait_for_components),
   previous.component(40044710281,'91040ba37e3ab0f5aef01ce3dff18f079568f3ed',['checks','native','Release device build • cold'],a.wait_for_components)]
 out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
 print('PASS scoped CELL522 source and preserved components; device gameplay remains unmeasured')
if __name__=='__main__':main()
