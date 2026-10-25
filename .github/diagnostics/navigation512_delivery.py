"""Close the targeted Switch/header proof over the delivered 511 native inputs."""
import argparse
import json
import os
from pathlib import Path
import sys

import rpcs3gow3_510_delivery as upstream

base = upstream.base
ROOT = Path(__file__).resolve().parents[2]
BASELINE = '2ed9a18ca6b22a00675dcbbe3a44985e26ed04d5'
DELIVERED = '12589d3fa7c3d5fd28537c456cde1b80a06cca98'
DELIVERED_RUN = 39894506630
TESTED = '377ff62b25e66565dc2e8f7835b999968b07284b'
TESTED_RUN = 39958450728
DELIVERY = {
    '.github/workflows/retroarch-delivery.yml', '.github/diagnostics/navigation512_delivery.py',
    'build-utils/delivery-512-chatgpt-recipient.pem', 'build-utils/validate_navigation512_ipa.py',
    'docs/navigation-build512.md', 'docs/evidence/navigation512-delivery.json',
}
validate_rpc_core_pin = upstream.validate_rpc_core_pin
validate_rpc_core_identity = upstream.validate_rpc_core_identity
validate_psp_core_identity = upstream.validate_psp_core_identity


def source_closure():
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude'
    assert os.environ.get('BUILD_NUMBER', '512') == '512'
    for revision in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', TESTED, *revision]).splitlines())
        assert not changed - DELIVERY, sorted(changed - DELIVERY)
    base.command(['python3', 'test/navigation512_scope_test.py'])
    upstream.core_module().validate_source_contract()
    upstream.core_module().validate_exact_pin(upstream.CORE_SOURCE)
    assert not base.command(['git', 'diff', '--name-only', DELIVERED, '--',
        'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock',
        'lib/services', 'lib/repositories', 'lib/data', 'lib/main.dart',
        'lib/screens/app_screen.dart', 'lib/utils', 'lib/widgets/main_menu_tab_strip.dart',
        'lib/widgets/mau_ali_tab_motion.dart', 'lib/widgets/mau_ali_tab_motion_data.dart',
        'lib/widgets/native_carousel.dart', 'lib/widgets/liquid_motion_clock.dart',
        'build-utils/sign_delivery.py', 'build-utils/delivery_benchmark.py'])
    old = base.command(['git', 'show', DELIVERED + ':.github/workflows/retroarch-delivery.yml'])
    current = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    for line in old.splitlines():
        if any(token in line for token in ['DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:',
            'ARMSX2_CORE_RUN_ID:', 'RPCS3_CORE_HOST_SHA:', 'RPCS3_CORE_RUN_ID:',
            'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:']):
            assert line in current, line
    for name in ['validate_rpcs3_ipa.py', 'validate_single_ipa_distribution.py',
        'validate_neoswap_ipa.py', 'validate_unified_cheats_ipa.py',
        'validate_hd_textures_ipa.py', 'validate_melonx_ipa.py',
        'validate_motion507_ipa.py', 'validate_melonx_delete509_ipa.py',
        'validate_rpcs3_gow3_ipa.py', 'validate_ui_correction511_ipa.py',
        'delivery_benchmark.py seal']:
        assert name in old and name in current, name
    assert 'validate_navigation512_ipa.py' in current
    return {'testedUI': TESTED, 'testedUIRun': TESTED_RUN,
        'baseline': BASELINE, 'delivered511Source': DELIVERED,
        'delivered511Run': DELIVERED_RUN, 'allNativeAndMotionInputsPreserved': True,
        'nativeCoresRebuilt': [], 'physicalDeviceTested': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', default='full')
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--wait-for-components', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument('--output', default='build/delivery/reused-validation.json')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    record = {'result': 'passed', 'source': base.command(['git', 'rev-parse', 'HEAD']),
        'sourceClosure': source_closure()}
    if not args.source_only:
        record['reusedEvidence'] = [
            base.successful_run(TESTED_RUN, TESTED, ['flutter']),
            base.successful_run(DELIVERED_RUN, DELIVERED,
                ['checks', 'native', 'Release device build • cold'])]
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS exact targeted Switch/header proof; delivered 511 native/motion evidence reused.')


if __name__ == '__main__':
    main()
