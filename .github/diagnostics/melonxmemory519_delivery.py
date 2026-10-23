"""Close private Build 519 over owned donor, RAM display and delivered 518 components."""
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
BASELINE='555603e541dc586b60d27cac28b38e62f7df12a0'
DELIVERED='9d064ad1e757e27dc2fc133a17b3e791178a9871'
DELIVERED_RUN=40033179437
SOURCE='18005a8f7eb7fb7204ecc8bb7af74eff6c928bee'
HOST_SOURCE='5445f9bb3bd1b04ba88e4e4f03852e6dfbd4763e'
HEADER_SOURCE=SOURCE
HEADER='packages/melonx_internal_bridge/ios/Classes/MeloNXJitBridgePlugin.h'
HOST_RUN=40038955791
APP_SOURCE=HOST_SOURCE
APP_RUN=40038955747
MELONX_SOURCE='c8424c32d2437b930870222fee1a07481d2b117d'
MELONX_RUN=40038087907
PRODUCT=set(['lib/l10n/melonx_library_locale.dart', 'lib/services/melonx_internal_service.dart', 'lib/widgets/melonx_internal_playlist_actions.dart', 'native/melonx/EmbeddedGraphicsSettings.cs', 'native/melonx/EmbeddedMemory.cs', 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift', 'packages/melonx_internal_bridge/ios/Classes/MeloNXJitBridgePlugin.h', 'packages/melonx_internal_bridge/ios/Classes/MeloNXJitBridgePlugin.mm', 'packages/melonx_internal_bridge/ios/Classes/MeloNXMemoryGraph.swift', 'packages/melonx_internal_bridge/ios/Classes/MeloNXMemoryLease.swift', 'packages/melonx_internal_bridge/ios/Classes/MeloNXMetalSessionViewController.swift', 'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift', 'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionABI.h', 'packages/melonx_internal_bridge/ios/melonx_internal_bridge.podspec'])
ASSEMBLY={'packages/dolphin_internal_bridge/ci/verify_ipa.py','build-utils/validate_rpcs3_ipa.py','test/melonx_memory_ipa_test.py','.github/workflows/retroarch-delivery.yml',
 '.github/diagnostics/melonxmemory519_delivery.py',
 'build-utils/delivery-519-chatgpt-recipient.pem','build-utils/validate_melonx_memory_ipa.py',
 'build-utils/validate_melonx_keys_ipa.py',
 'docs/melonx-memory-display-build519.md','docs/evidence/melonx-memory519-delivery.json'}

def source_closure():
 assert os.environ.get('GITHUB_REF_NAME')=='Claude'
 assert os.environ.get('BUILD_NUMBER','519')=='519'
 for revision in (['HEAD'],[]):
  changed=set(base.command(['git','diff','--name-only',SOURCE,*revision]).splitlines())
  assert not changed-ASSEMBLY,sorted(changed-ASSEMBLY)
  product=set(base.command(['git','diff','--name-only',DELIVERED,*revision,'--',
   'lib','native','packages','assets','ios','pubspec.yaml','pubspec.lock']).splitlines())
  assert product-ASSEMBLY==PRODUCT,sorted((product-ASSEMBLY)^PRODUCT)
 for component,paths in [(HOST_SOURCE,sorted(p for p in PRODUCT if p.startswith('packages/') and p!=HEADER)),
                         (APP_SOURCE,sorted(p for p in PRODUCT if p.startswith('lib/')))]:
  assert not base.command(['git','diff','--name-only',component,'HEAD','--',*paths])
 assert not base.command(['git','diff','--name-only',HEADER_SOURCE,'HEAD','--',HEADER,'test/melonx_header_module_test.py'])
 old_header=base.command(['git','show',HOST_SOURCE+':'+HEADER])
 current_header=(ROOT/HEADER).read_text().strip()
 replacement='// CocoaPods flattens public headers into the framework\'s Headers directory.\n// The source-tree spelling remains available to standalone SDK checks.\n#if __has_include("MLXRamDonor.h")\n#import "MLXRamDonor.h"\n#else\n#import "../Memory/MLXRamDonor.h"\n#endif'
 assert current_header==old_header.replace('#import "../Memory/MLXRamDonor.h"',replacement)
 assert not base.command(['git','diff','--name-only','c8424c32d2437b930870222fee1a07481d2b117d','HEAD','--','test/melonx_presentation_widgets_test.dart','lib/widgets/melonx_internal_playlist_actions.dart'])
 previous.core_module().validate_source_contract()
 previous.core_module().validate_exact_pin(CORE_SOURCE)
 old=base.command(['git','show',DELIVERED+':.github/workflows/retroarch-delivery.yml'])
 current=(ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
 for line in old.splitlines():
  if any(key in line for key in ['DOLPHIN_CORE_HOST_SHA:','ARMSX2_CORE_HOST_SHA:',
   'ARMSX2_CORE_RUN_ID:','RPCS3_CORE_HOST_SHA:','RPCS3_CORE_RUN_ID:',
   'LIBRETRO_CORES_HOST_SHA:','LIBRETRO_CORES_RUN_ID:',
   'name: MeloNX-native-dependencies-','run-id: 39854858591']):assert line in current,line
 assert 'name: MeloNX-engine-'+MELONX_SOURCE in current and 'run-id: '+str(MELONX_RUN) in current
 for validator in ['validate_rpcs3_ipa.py','validate_single_ipa_distribution.py',
  'validate_neoswap_ipa.py','validate_unified_cheats_ipa.py','validate_hd_textures_ipa.py',
  'validate_melonx_ipa.py','validate_motion507_ipa.py','validate_melonx_delete509_ipa.py',
  'validate_rpcs3_gow3_ipa.py','validate_ui_correction511_ipa.py','validate_navigation512_ipa.py',
  'validate_melonx_launch_ipa.py','validate_melonx_keys_ipa.py','delivery_benchmark.py seal']:
  assert validator in old and validator in current,validator
 assert 'validate_melonx_memory_ipa.py' in current
 return dict(baseline=BASELINE,delivered518Source=DELIVERED,delivered518Run=DELIVERED_RUN,
  memoryDisplaySource=SOURCE,hostSource=HOST_SOURCE,hostRun=HOST_RUN,headerLayoutFixSource=HEADER_SOURCE,
  headerLayoutValidatedInDelivery=True,flutterSource=APP_SOURCE,flutterRun=APP_RUN,
  rebuiltMeloNXSource=MELONX_SOURCE,rebuiltMeloNXCoreRun=MELONX_RUN,
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
  record['componentEvidence']=[component(HOST_RUN,HOST_SOURCE,['host'],a.wait_for_components),component(APP_RUN,APP_SOURCE,['display'],a.wait_for_components),component(MELONX_RUN,MELONX_SOURCE,['core'],a.wait_for_components)]
  record['reusedEvidence']=[base.successful_run(40038088301,'c8424c32d2437b930870222fee1a07481d2b117d',['display']),base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
 out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
 print('PASS exact donor/display source, targeted proofs and preserved unrelated Build 518 components.')
if __name__=='__main__':main()
