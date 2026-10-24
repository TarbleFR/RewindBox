"""Close private 520 around the source-built v0.12 Core and preserved 519 app."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import rpcs3freeze515_delivery as previous
import rpcs3v012_core as native

ROOT=Path(__file__).resolve().parents[2]
base=previous.base
CORE_SOURCE='407ea8f7462db0645590e799adcdff9ed56b1b21'
CORE_RUN=40039707148
APP_SOURCE='df96b0d85f12d1442060e8d426175f3928fcb7bc'
DELIVERED='f93323768831428186c3aeb21b7e7a6130897836'
DELIVERY_DRIVER='df96b0d85f12d1442060e8d426175f3928fcb7bc'
DELIVERED_RUN=40043376467
PRODUCT={
 'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibility.h',
 'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibilityPolicy.h',
 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3JitBridgePlugin.mm',
}
HOST=previous.HOST|PRODUCT
ASSEMBLY={
 '.github/diagnostics/rpcs3v012_delivery.py','.github/workflows/rpcs3-v012-delivery.yml',
 'build-utils/validate_rpcs3_v012_ipa.py','build-utils/delivery-520-rpcs3-recipient.pem',
 'docs/rpcs3-xitrix-v012.md','docs/evidence/rpcs3-v012-delivery.json',
 'test/rpcs3_cpu_escrow_test.py','test/fixtures/rpcs3_v012_host_escrow.diff',
 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
}
validate_psp_core_identity=previous.validate_psp_core_identity
HOST_PATH='packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
HOST_DELTA='test/fixtures/rpcs3_v012_host_escrow.diff'
HOST_DELTA_SHA='36db0806d95d6c67fccd67880e46255cf26889e82819aa65ec4345bbee0ee655'
HOST_PROOF_SOURCE='faf2b951f1f55b8fb89ad8728e632a6e81fd30ef'
HOST_PROOF_RUN=40040875173
HOST_PROOF_INPUTS={HOST_PATH,
 'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibility.h',
 'packages/rpcs3_internal_bridge/ios/Classes/RPCS3CPUCompatibilityPolicy.h',
 'test/rpcs3_cpu_escrow_test.py',HOST_DELTA}

def digest(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()

def validate_host_proof(proof):
 assert proof['result']=='passed' and proof['productionInitializerCases']==8
 assert proof['preFixReservationReproduced'] and proof['iphoneSDKTypecheck']
 assert proof['actualFoundation'] and proof['actualDispatch'] and proof['sysctlAndEscrowDouble']
 assert proof['physicalDeviceTested'] is False and proof['gameplayTested'] is False
 assert set(proof['inputs'])==HOST_PROOF_INPUTS
 for path,expected in proof['inputs'].items():assert digest(path)==expected,path

def authenticate_host_proof():
 # The native job completed successfully; its sibling only awaited the now
 # superseded 519 app. Do not claim that entire delivery workflow succeeded.
 run=base.api('actions/runs/'+str(HOST_PROOF_RUN))
 assert run['head_sha']==HOST_PROOF_SOURCE
 jobs=base.api('actions/runs/'+str(HOST_PROOF_RUN)+'/jobs?per_page=100')['jobs']
 job=next(j for j in jobs if j['name']=='native')
 assert job['id']==120711477329 and job['status']=='completed' and job['conclusion']=='success'
 validate_host_proof(json.loads((ROOT/'build/delivery/rpcs3-cpu-escrow-proof.json').read_text()))
 print('PASS authenticated Apple SDK CPU bootstrap proof; all five production/test inputs unchanged')

@contextmanager
def core_input_view():
 """Original Core build inputs, with one separately tested host-only delta.

 The Core artifact and its identity are never rewritten. Every engine/recipe/
 test input remains byte-identical. Reverse the exact CPU/escrow initializer
 fixture to prove that no other host or ABI change is hidden by this view.
 """
 assert digest(HOST_DELTA)==HOST_DELTA_SHA
 core=native.pin_module()
 with tempfile.TemporaryDirectory(prefix='rpcs3-core-input-view-') as directory:
  view=Path(directory)
  for path in dict.fromkeys(core.CORE_INPUTS):
   pinned=subprocess.check_output(['git','show',CORE_SOURCE+':'+path],cwd=ROOT)
   target=view/path;target.parent.mkdir(parents=True,exist_ok=True)
   if path==HOST_PATH:
    target.write_bytes((ROOT/path).read_bytes())
    subprocess.run(['git','apply','--reverse','--check',str(ROOT/HOST_DELTA)],cwd=view,check=True)
    subprocess.run(['git','apply','--reverse',str(ROOT/HOST_DELTA)],cwd=view,check=True)
    assert target.read_bytes()==pinned,'Host changed beyond the tested CPU/escrow gate'
   else:
    assert (ROOT/path).read_bytes()==pinned,'Changed compiled Core input: '+path
    os.link(ROOT/path,target)
  for path in native.EXTRA_INPUTS:
   pinned=subprocess.check_output(['git','show',CORE_SOURCE+':'+path],cwd=ROOT)
   assert (ROOT/path).read_bytes()==pinned,'Changed extra Core proof input: '+path
  yield view

def validate_rpc_core_identity(identity):
 assert identity['host_commit']==CORE_SOURCE
 with core_input_view() as view:
  core=native.pin_module()
  core.validate_core_input_identity(identity,root=view)
  expected={**core.core_input_hashes(view),**{p:digest(p) for p in native.EXTRA_INPUTS}}
  assert identity['v012_input_sha256']==expected
 assert identity['cpu_baseline']=='armv8.4-a' and identity['legacy_core_bundled'] is False
 assert identity['device_runtime_tested'] is False

def validate_rpc_core_pin(pin,paths):
 assert pin==CORE_SOURCE
 core=native.pin_module()
 assert len(paths)==len(core.CORE_INPUTS) and set(paths)==set(core.CORE_INPUTS)
 native.source_contract()
 with core_input_view() as view:core.core_input_hashes(view)
 print('PASS exact v0.12 source pin, native tests, CPU guards, optional ABI and compiler inputs')

def source_closure():
 assert os.environ.get('GITHUB_REF_NAME')=='Claude'
 assert os.environ.get('BUILD_NUMBER','520')=='520'
 for revision in (['HEAD'],[]):
  changed=set(base.command(['git','diff','--name-only',APP_SOURCE,*revision]).splitlines())
  assert not changed-ASSEMBLY,sorted(changed-ASSEMBLY)
  product=set(base.command(['git','diff','--name-only',DELIVERED,*revision,'--',
    'lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock']).splitlines())
  assert product==PRODUCT,sorted(product^PRODUCT)
 validate_rpc_core_pin(CORE_SOURCE,list(native.pin_module().CORE_INPUTS))
 old=native.pin_module().workflow_source_text(base.command(['git','show',APP_SOURCE+':.github/workflows/retroarch-delivery.yml']))
 current=native.pin_module().workflow_source_text((ROOT/'.github/workflows/rpcs3-v012-delivery.yml').read_text())
 # The frozen 519 driver is an explicit separate identity. Its source snapshot
 # is only the baseline of unaffected app components, never our build identity.
 for token in ('DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:', 'ARMSX2_CORE_RUN_ID:',
               'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:',
               'name: MeloNX-engine-', 'name: MeloNX-native-dependencies-'):
  old_line=next(line.strip() for line in old.splitlines() if token in line)
  assert old_line in current,old_line
 for run in (40038087907,39854858591):
  assert 'run-id: '+str(run) in old and 'run-id: '+str(run) in current
 for validator in ('validate_rpcs3_ipa.py','validate_single_ipa_distribution.py','validate_neoswap_ipa.py',
   'validate_unified_cheats_ipa.py','validate_hd_textures_ipa.py','validate_melonx_ipa.py',
   'validate_motion507_ipa.py','validate_melonx_delete509_ipa.py','validate_ui_correction511_ipa.py',
   'validate_navigation512_ipa.py','validate_melonx_launch_ipa.py','validate_melonx_keys_ipa.py',
   'validate_melonx_memory_ipa.py','delivery_benchmark.py seal'):
  assert validator in old and validator in current,validator
 assert 'validate_rpcs3_v012_ipa.py' in current
 return dict(source=base.command(['git','rev-parse','HEAD']),nativeCore=CORE_SOURCE,nativeRun=CORE_RUN,
   preservedApp519=DELIVERED,delivered519Driver=DELIVERY_DRIVER,delivered519Run=DELIVERED_RUN,
   changedHost=sorted(PRODUCT),hostBootstrapDeltaSHA256=HOST_DELTA_SHA,
   unchangedOtherEmulatorSources=True,physicalDeviceTested=False)

def component(run,source,names,wait):
 if wait:
  end=time.monotonic()+10800
  while True:
   state=base.api('actions/runs/'+str(run));assert state['head_sha']==source
   if state['status']=='completed':break
   assert time.monotonic()<end
   print('Waiting for exact component',run,state['status'],flush=True);time.sleep(30)
 return base.successful_run(run,source,names)

def main():
 p=argparse.ArgumentParser();p.add_argument('--scope',default='full');p.add_argument('--source-only',action='store_true')
 p.add_argument('--wait-for-components',action='store_true');p.add_argument('--skin-session-evidence',action='store_true')
 p.add_argument('--verify-host-proof',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation.json');p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 a=p.parse_args()
 if a.verify_host_proof:authenticate_host_proof();return
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 record=dict(result='passed',sourceClosure=source_closure())
 if not a.source_only:
  record['reusedEvidence']=[
   component(CORE_RUN,CORE_SOURCE,['RPCS3 v0.12: native regressions and iPhone Core'],a.wait_for_components),
   component(DELIVERED_RUN,DELIVERY_DRIVER,['checks','native','Release device build • cold'],a.wait_for_components),
  ]
 out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
 print('PASS source closure and native input pin; binary/job validation not run' if a.source_only else
       'PASS exact v0.12 source and authenticated 519 components; no gameplay or device performance claim')

if __name__=='__main__':main()
