"""Build 506 closes tested MeloNX inputs and preserves the delivered 505 engines/UI."""
import argparse
import hashlib
import json
import os
import liquid505_delivery as previous
base=previous.base
validate_rpc_core_pin=previous.validate_rpc_core_pin
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_psp_core_identity=previous.validate_psp_core_identity
BASELINE='ca168102611f6a7f7247eb60727a2e338033f64e'
TESTED='721380dd7f241d1343fe6ae8fbf563e1b63f6d66'
APP_TESTED='4361c14e0e67a38a15bebe9ca6a968da89950f23'
CORE='38d997064cd81c5f17de6187ab36d2c78b0ba97c'
HOST='721380dd7f241d1343fe6ae8fbf563e1b63f6d66'
DELIVERY={'.github/diagnostics/melonx506_delivery.py','.github/workflows/retroarch-delivery.yml',
          'build-utils/delivery-506-chatgpt-recipient.pem','docs/evidence/melonx506-delivery.json',
          'docs/melonx-embedded-build506.md','AGENTS.md',
          '.github/workflows/bubbles503-checks.yml','docs/evidence/liquid-glass-airplay505-delivery.json',
          'docs/liquid-glass-airplay-build505.md', 'test/legal_bundle_preflight_test.py',
          'assets/legal/melonx/license-sources.json','build-utils/validate_melonx_ipa.py',
          'test/melonx_runtime_smoke.py', '.github/workflows/melonx-runtime-smoke.yml',
          'build-utils/melonx/package_runtime.py'}

def unchanged(source,paths):
    delta=base.command(['git','diff','--name-only',source,'HEAD','--',*paths])
    if delta:raise ValueError('Validated source changed: '+delta)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scope',default='full')
    parser.add_argument('--source-only',action='store_true');parser.add_argument('--skin-session-evidence',action='store_true')
    parser.add_argument('--output',default='build/delivery/reused-validation.json')
    parser.add_argument('--rpc-core-inputs');parser.add_argument('core_paths',nargs='*');args=parser.parse_args()
    if args.rpc_core_inputs:validate_rpc_core_pin(args.rpc_core_inputs,args.core_paths);return
    assert os.environ.get('GITHUB_REF_NAME')=='Claude','Final IPA must be built on Claude'
    delta=set(base.command(['git','diff','--name-only',TESTED,'HEAD']).splitlines())
    if delta-DELIVERY:raise ValueError('Changed a final validated input: '+', '.join(sorted(delta-DELIVERY)))
    unchanged(APP_TESTED,['lib','pubspec.yaml','pubspec.lock','packages/**/*.dart','packages/**/pubspec.yaml'])
    unchanged(BASELINE,['packages/dolphin_internal_bridge','packages/armsx2_internal_bridge',
       'packages/rpcs3_internal_bridge','packages/libretro_internal_bridge','packages/stikjit_bridge',
       'native',':!native/melonx',':!native/melonx_internal_helper',':!packages/dolphin_internal_bridge/ci/verify_ipa.py'])
    unchanged(BASELINE,['lib/main.dart','lib/screens/app_screen.dart','lib/screens/airplay_screen.dart',
       'lib/widgets/rewind_startup.dart','lib/widgets/rewind_mark_path.dart','lib/widgets/neo_glass_bubble.dart',
       'lib/widgets/console_bubble_transition.dart','lib/widgets/header.dart','lib/widgets/main_menu_tab_strip.dart',
       'native/textures/catalogue/manifest.json.gz','packages/neo_texture_catalog/ios/Resources/manifest.json.gz'])
    unchanged(CORE,['native/melonx','build-utils/melonx/source.json','build-utils/melonx/prepare_embedded.py',
       'build-utils/melonx/adapt_session.py','build-utils/melonx/adapt_input.py','build-utils/melonx/adapt_runtime.py','build-utils/melonx/adapt_firmware.py'])
    unchanged(HOST,['packages/melonx_internal_bridge/ios/Classes','build-utils/melonx/vendor_controller.py','build-utils/melonx/ui-strings.json'])
    records=[base.successful_run(39846745630,BASELINE,['checks','native','Release device build • cold']),
       base.successful_run(39857539994,APP_TESTED,['host']),
       base.successful_run(39858967222,CORE,['core']),
       base.successful_run(39859362301,HOST,['host']),
       base.successful_run(39854858591,'66737aa9c959eb5915264bf178f179bda8643314',['dependencies']),
       base.successful_run(39859909967,'a54de8e4adc38df42be8f36d7e907195a18e5dd2',['actual-runtime'])]
    out=base.ROOT/args.output;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'result':'passed','source':base.command(['git','rev-parse','HEAD']),
       'reusedEvidence':records,'unrelatedEnginesAndStartup505Preserved':True,
       'meloNXActualSimulatorInitializationVerified':True,'deviceGameplayTested':False,
       'neoSwapLiveLoanConnected':False,'newCore':'MeloNX only'},indent=2)+'\n')
    print('PASS closed MeloNX integration, actual runtime bootstrap and unchanged delivered engines/UI.')
if __name__=='__main__':main()
