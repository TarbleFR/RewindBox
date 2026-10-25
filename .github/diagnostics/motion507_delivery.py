"""Close the tested UI source; reuse Build 506 native engines without replay."""
import argparse
import hashlib
import json
import os
import melonx506_delivery as previous
base = previous.base
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_psp_core_identity = previous.validate_psp_core_identity
TESTED = '37606051d6a0226a3861309a06a8069c70eb1f34'
TESTED_RUN = 39866371150
NATIVE_TESTED = '3dfd2d668ae6855094d24789b0ebc4cb683047d8'
NATIVE_RUN = 39864139925
BASELINE = '4fb8ffe6672c7802ea39d7144dfc762a7b9f1a18'
BASELINE_RUN = 39863280830
DELIVERY = {
    '.github/diagnostics/motion507_delivery.py', '.github/workflows/retroarch-delivery.yml',
    '.github/workflows/ui-refresh-rate-check.yml',
    'build-utils/delivery-507-chatgpt-recipient.pem', 'build-utils/validate_motion507_ipa.py',
    'docs/liquid-motion-build507.md', 'docs/evidence/liquid-motion507-delivery.json',
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', default='full', choices=['full'])
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument('--output', default='build/delivery/reused-validation.json')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude', 'IPA integration is authorized on Claude only'
    assert os.environ.get('BUILD_NUMBER', '507') == '507', '507 has one closed assembly source'
    delta = set(base.command(['git','diff','--name-only',TESTED,'HEAD']).splitlines())
    working = set(base.command(['git','diff','--name-only','HEAD']).splitlines())
    assert not ((delta | working) - DELIVERY), sorted((delta | working) - DELIVERY)
    base.command(['python3','test/liquid_motion_scope_test.py'])
    native_delta = base.command(['git','diff','--name-only',NATIVE_TESTED,'HEAD','--',
        'packages','native','pubspec.yaml','pubspec.lock','test/liquid_native_probe.py','test/ui_refresh_rate_hook_test.py'])
    assert not native_delta, 'Native probe inputs changed: '+native_delta
    records = [base.successful_run(BASELINE_RUN, BASELINE, ['checks','native','Release device build • cold']),
        base.successful_run(NATIVE_RUN, NATIVE_TESTED, ['flutter','native']),
        base.successful_run(TESTED_RUN, TESTED, ['flutter'])]
    baseline_recipe = base.command(['git','show',BASELINE+':.github/workflows/retroarch-delivery.yml'])
    current = (base.ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
    # Every existing source-built engine identity, package validation and
    # signature command remains intact. UI adds a post-sign bundle inspection.
    for token in ['RPCS3_CORE_RUN_ID:', 'LIBRETRO_CORES_RUN_ID:', 'ARMSX2_CORE_RUN_ID:']:
        old = next(line for line in baseline_recipe.splitlines() if token in line)
        assert old in current, old
    for name in ['validate_rpcs3_ipa.py','validate_single_ipa_distribution.py','validate_neoswap_ipa.py',
                 'validate_unified_cheats_ipa.py','validate_hd_textures_ipa.py',
                 'validate_melonx_ipa.py','delivery_benchmark.py seal']:
        assert name in current and name in baseline_recipe, name
    signer_delta = base.command(['git','diff','--name-only',BASELINE,'HEAD','--',
        'build-utils/delivery_benchmark.py','build-utils/sign_delivery.py'])
    assert not signer_delta, 'The preserved assembly/signature implementation changed: '+signer_delta
    hosted = (base.ROOT/'native/textures/catalogue/manifest.json.gz').read_bytes()
    assert hosted == (base.ROOT/'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    output = base.ROOT/args.output; output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'result':'passed', 'source':base.command(['git','rev-parse','HEAD']),
        'reusedEvidence':records, 'testedUI':TESTED, 'testedUIRun':TESTED_RUN,
        'startup505Preserved':True, 'build506EnginesPreserved':True,
        'downloadAndStorageServicesUnchanged':True,
        'catalogueSHA256':hashlib.sha256(hosted).hexdigest(),
        'rebuiltCores':[], 'physicalDeviceTested':False},indent=2)+'\n')
    print('PASS: exact tested motion UI, Build 506 engines and startup preserved; no unchanged suite replay.')

if __name__ == '__main__': main()
