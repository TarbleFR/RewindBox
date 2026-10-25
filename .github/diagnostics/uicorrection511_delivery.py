"""Close the verified UI correction and reuse the concurrently pinned GoW3 Core."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import rpcs3gow3_510_delivery as previous

base = previous.base
ROOT = Path(__file__).resolve().parents[2]
TESTED = '554c8540570c9eab3c19da0a53123381051977bf'
TESTED_RUN = 39894280161
BASELINE = '8a79ae4e7855cde46e2922e8f71a2df81f0c7a7b'
DELIVERED = previous.DELIVERED
DELIVERED_RUN = previous.DELIVERED_RUN
DELIVERY = {
    '.github/workflows/retroarch-delivery.yml', '.github/diagnostics/uicorrection511_delivery.py',
    'build-utils/delivery-511-chatgpt-recipient.pem', 'build-utils/validate_ui_correction511_ipa.py',
    'docs/ui-correction-build511.md', 'docs/evidence/ui-correction511-delivery.json',
}
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_psp_core_identity = previous.validate_psp_core_identity


def source_closure():
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude'
    assert os.environ.get('BUILD_NUMBER', '511') == '511'
    for revision in (['HEAD'], []):
        delta = set(base.command(['git', 'diff', '--name-only', TESTED, *revision]).splitlines())
        assert not delta - DELIVERY, sorted(delta - DELIVERY)
    base.command(['python3', 'test/ui_correction_scope_test.py'])
    base.command(['python3', 'build-utils/extract_mau_ali_motion.py', '--check'])
    previous.core_module().validate_source_contract()
    previous.core_module().validate_exact_pin(previous.CORE_SOURCE)
    # UI work does not change any native engine, service, repository or storage.
    assert not base.command(['git', 'diff', '--name-only', BASELINE, '--',
        'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock', 'lib/services',
        'lib/repositories', 'lib/main.dart', 'lib/utils/nav_tabs.dart',
        'build-utils/sign_delivery.py', 'build-utils/delivery_benchmark.py'])
    old = base.command(['git', 'show', BASELINE + ':.github/workflows/retroarch-delivery.yml'])
    current = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    for line in old.splitlines():
        if any(token in line for token in ['DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:',
            'ARMSX2_CORE_RUN_ID:', 'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:',
            'RPCS3_CORE_HOST_SHA:', 'RPCS3_CORE_RUN_ID:']):
            assert line in current, line
    for name in ['validate_rpcs3_ipa.py', 'validate_single_ipa_distribution.py',
        'validate_neoswap_ipa.py', 'validate_unified_cheats_ipa.py', 'validate_hd_textures_ipa.py',
        'validate_melonx_ipa.py', 'validate_motion507_ipa.py', 'validate_melonx_delete509_ipa.py',
        'validate_rpcs3_gow3_ipa.py', 'delivery_benchmark.py seal']:
        assert name in old and name in current, name
    assert 'validate_ui_correction511_ipa.py' in current
    archive = ROOT / 'assets/data/mau-ali-tab-menu.lottie'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == '30ea694527e40c01a947b9e05a4a0eaa8b7ea100730f6d1fd0bad40e9713f6e0'
    return {'testedUI': TESTED, 'testedUIRun': TESTED_RUN, 'baseline': BASELINE,
        'delivered509Source': DELIVERED, 'delivered509Run': DELIVERED_RUN,
        'reusedRPCS3Core': previous.CORE_SOURCE, 'reusedRPCS3CoreRun': previous.CORE_RUN,
        'rebuiltCores': [], 'allOtherNativeInputsPreserved': True,
        'startupAndLiquidDownloadsPreserved': True, 'physicalDeviceTested': False}


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
            base.successful_run(DELIVERED_RUN, DELIVERED, ['checks', 'native', 'Release device build • cold']),
            previous.successful_core(args.wait_for_components)]
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS exact tested complete menu/Cover Flow correction; native/engine proofs reused without replay.')


if __name__ == '__main__':
    main()
