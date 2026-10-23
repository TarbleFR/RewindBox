"""Close private Build 518 over UIKit presentation and delivered 517 components."""
import argparse,json,os,time
from pathlib import Path
import rpcs3freeze515_delivery as previous
ROOT=Path(__file__).resolve().parents[2]
base=previous.base
HOST=previous.HOST
CORE_SOURCE=previous.CORE_SOURCE
CORE_RUN=previous.CORE_RUN
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin
validate_psp_core_identity=previous.validate_psp_core_identity
BASELINE='fa6d056e668e55fb7b96959b20cc15064e52e68a'
DELIVERED='05f04b9bbc9cb95137c8bc5df42a53606b358201'
DELIVERED_RUN=40025909494
SOURCE='37a926d200328409368d4a4285b6554e5cc882f5'
HOST_SOURCE='303d9084db73b3016d29a5dca9bf439fa44ed7c7'
HOST_RUN=40031804127
APP_SOURCE=SOURCE
APP_RUN=40033099656
MELONX_SOURCE='e0a1196d70469a28f04cc8a3628f43d484015581'
MELONX_RUN=40025760206
PRODUCT={
 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXPresentation.swift',
 'lib/widgets/melonx_internal_playlist_actions.dart'}
ASSEMBLY={'.github/workflows/retroarch-delivery.yml',
 '.github/diagnostics/melonxpresentation518_delivery.py',
 'build-utils/delivery-518-chatgpt-recipient.pem','build-utils/validate_melonx_presentation_ipa.py',
 'build-utils/split_encrypted_delivery.py',
 'docs/melonx-presentation-build518.md','docs/evidence/melonx-presentation518-delivery.json'}

def source_closure():
 assert os.environ.get('GITHUB_REF_NAME')=='Claude'
 assert os.environ.get('BUILD_NUMBER','518')=='518'
 for revision in (['HEAD'],[]):
  changed=set(base.command(['git','diff','--name-only',SOURCE,*revision]).splitlines())
  assert not changed-ASSEMBLY,sorted(changed-ASSEMBLY)
  product=set(base.command(['git','diff','--name-only',DELIVERED,*revision,'--',
   'lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock']).splitlines())
  assert product==PRODUCT,sorted(product^PRODUCT)
 for component,paths in [(HOST_SOURCE,sorted(p for p in PRODUCT if p.startswith('packages/'))),
                         (APP_SOURCE,sorted(p for p in PRODUCT if p.startswith('lib/')))]:
  assert not base.command(['git','diff','--name-only',component,'HEAD','--',*paths])
 previous.core_module().validate_source_contract()
 previous.core_module().validate_exact_pin(CORE_SOURCE)
 old=base.command(['git','show',DELIVERED+':.github/workflows/retroarch-delivery.yml'])
 current=(ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
 for line in old.splitlines():
  if any(key in line for key in ['DOLPHIN_CORE_HOST_SHA:','ARMSX2_CORE_HOST_SHA:',
   'ARMSX2_CORE_RUN_ID:','RPCS3_CORE_HOST_SHA:','RPCS3_CORE_RUN_ID:',
   'LIBRETRO_CORES_HOST_SHA:','LIBRETRO_CORES_RUN_ID:',
   'name: MeloNX-native-dependencies-','run-id: 39854858591',
   'name: MeloNX-engine-','run-id: '+str(MELONX_RUN)]):assert line in current,line
 assert 'name: MeloNX-engine-'+MELONX_SOURCE in current
 for validator in ['validate_rpcs3_ipa.py','validate_single_ipa_distribution.py',
  'validate_neoswap_ipa.py','validate_unified_cheats_ipa.py','validate_hd_textures_ipa.py',
  'validate_melonx_ipa.py','validate_motion507_ipa.py','validate_melonx_delete509_ipa.py',
  'validate_rpcs3_gow3_ipa.py','validate_ui_correction511_ipa.py','validate_navigation512_ipa.py',
  'validate_melonx_launch_ipa.py','validate_melonx_keys_ipa.py','delivery_benchmark.py seal']:
  assert validator in old and validator in current,validator
 assert 'validate_melonx_presentation_ipa.py' in current
 return dict(baseline=BASELINE,delivered517Source=DELIVERED,delivered517Run=DELIVERED_RUN,
  presentationSource=SOURCE,hostSource=HOST_SOURCE,hostRun=HOST_RUN,flutterSource=APP_SOURCE,flutterRun=APP_RUN,
  reusedMeloNXSource=MELONX_SOURCE,reusedMeloNXCoreRun=MELONX_RUN,
  changedProduct=sorted(PRODUCT),preservedRPCS3Core=CORE_SOURCE,preservedRPCS3Run=CORE_RUN,
  otherEnginesUnchanged=True,physicalDeviceTested=False)

def component(run,source,jobs,wait):
 if wait:
  deadline=time.monotonic()+10800
  while True:
   state=base.api('actions/runs/'+str(run));assert state['head_sha']==source
   if state['status']=='completed':break
   assert time.monotonic()<deadline,'Timed out waiting for exact presentation proof'
   print('Waiting for exact presentation proof',run,state['status'],flush=True);time.sleep(30)
 return base.successful_run(run,source,jobs)

def main():
 p=argparse.ArgumentParser();p.add_argument('--scope',default='full');p.add_argument('--source-only',action='store_true')
 p.add_argument('--wait-for-components',action='store_true');p.add_argument('--skin-session-evidence',action='store_true')
 p.add_argument('--output',default='build/delivery/reused-validation.json');p.add_argument('--rpc-core-inputs');p.add_argument('core_paths',nargs='*')
 a=p.parse_args()
 if a.rpc_core_inputs:validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths);return
 record=dict(result='passed',source=base.command(['git','rev-parse','HEAD']),sourceClosure=source_closure())
 if not a.source_only:
  record['componentEvidence']=[component(HOST_RUN,HOST_SOURCE,['host'],a.wait_for_components),component(APP_RUN,APP_SOURCE,['keys'],a.wait_for_components)]
  record['reusedEvidence']=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold']),base.successful_run(MELONX_RUN,MELONX_SOURCE,['core'])]
 out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
 print('PASS exact presentation source, targeted proofs and preserved Build 517 components.')
if __name__=='__main__':main()
