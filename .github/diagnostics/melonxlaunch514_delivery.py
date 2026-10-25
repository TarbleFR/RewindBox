"""Close the test IPA over verified MeloNX changes and preserved 512/513 work."""
import argparse
import json
import os
from pathlib import Path
import time

import rpcs3restore513_delivery as previous

ROOT = Path(__file__).resolve().parents[2]
base = previous.base
BASELINE = 'f3f953c15a86463427e75a921adba814fe6e759d'
SOURCE = 'e050961d6caabfabdef57dd140c774545976d0fd'
HOST_SOURCE = '7f88ee9be1681f10dcc66f0996ee9eaffbdb51c0'
APP_SOURCE = HOST_SOURCE
CORE_RUN = 39978893582
HOST_RUN = 39972191758
APP_RUN = 39972191726
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_psp_core_identity = previous.validate_psp_core_identity
PRODUCT = {
    'lib/services/game/game_launch_service.dart', 'lib/services/game_launch_manager.dart',
    'lib/services/melonx_internal_service.dart', 'lib/services/melonx_launch_diagnostics.dart',
    'lib/l10n/melonx_launch_failure_locale.dart',
    'native/melonx/EmbeddedBootstrap.cs', 'native/melonx/EmbeddedContent.cs',
    'native/melonx/EmbeddedRuntime.cs', 'native/melonx/EmbeddedSession.cs',
    'native/melonx/EmbeddedGraphicsSettings.cs', 'native/melonx/EmbeddedDarwinSignals.cs',
    'native/melonx/EmbeddedHomebrewAssets.cs',
    'native/melonx/EmbeddedLaunchDiagnostics.cs', 'native/melonx/EmbeddedLaunchPreflight.cs',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift',
}
DELIVERY = {
    '.github/workflows/retroarch-delivery.yml', '.github/diagnostics/melonxlaunch514_delivery.py',
    '.github/workflows/melonx-preserve-validation.yml', 'build-utils/delivery-514-chatgpt-recipient.pem',
    'build-utils/validate_melonx_launch_ipa.py', 'docs/melonx-launch-build514.md',
    'docs/evidence/melonx-launch514-delivery.json',
    'docs/evidence/rpcs3-restore513-delivery.json', 'docs/rpcs3-restore-build513.md',
}

def unchanged(source, paths):
    delta = base.command(['git', 'diff', '--name-only', source, 'HEAD', '--', *paths])
    assert not delta, 'Changed a verified input: ' + delta

def source_closure():
    assert os.environ.get('GITHUB_REF_NAME') == 'Claude'
    assert os.environ.get('BUILD_NUMBER', '514') == '514'
    for revision in (['HEAD'], []):
        changed = set(base.command(['git', 'diff', '--name-only', SOURCE, *revision]).splitlines())
        assert not changed - DELIVERY, sorted(changed - DELIVERY)
    changed_product = set(base.command(['git', 'diff', '--name-only', BASELINE, 'HEAD', '--',
        'lib', 'native', 'packages', 'assets', 'ios', 'pubspec.yaml', 'pubspec.lock']).splitlines())
    assert changed_product == PRODUCT, sorted(changed_product ^ PRODUCT)
    unchanged(HOST_SOURCE, ['packages/melonx_internal_bridge/ios/Classes'])
    unchanged(APP_SOURCE, ['lib', 'pubspec.yaml', 'pubspec.lock'])
    unchanged('70d7ef53756d9d8adfa471df2d767c09a3b186ca',
        ['docs/evidence/rpcs3-restore513-delivery.json', 'docs/rpcs3-restore-build513.md'])
    previous.core_module().validate_source_contract()
    previous.core_module().validate_exact_pin(previous.CORE_SOURCE)
    old = base.command(['git', 'show', BASELINE + ':.github/workflows/retroarch-delivery.yml'])
    current = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    for line in old.splitlines():
        if any(key in line for key in ['DOLPHIN_CORE_HOST_SHA:', 'ARMSX2_CORE_HOST_SHA:',
            'ARMSX2_CORE_RUN_ID:', 'RPCS3_CORE_HOST_SHA:', 'RPCS3_CORE_RUN_ID:',
            'LIBRETRO_CORES_HOST_SHA:', 'LIBRETRO_CORES_RUN_ID:']): assert line in current, line
    for validator in ['validate_rpcs3_ipa.py', 'validate_single_ipa_distribution.py',
        'validate_neoswap_ipa.py', 'validate_unified_cheats_ipa.py', 'validate_hd_textures_ipa.py',
        'validate_melonx_ipa.py', 'validate_motion507_ipa.py', 'validate_melonx_delete509_ipa.py',
        'validate_rpcs3_gow3_ipa.py', 'validate_ui_correction511_ipa.py', 'validate_navigation512_ipa.py']:
        assert validator in old and validator in current, validator
    assert 'validate_melonx_launch_ipa.py' in current
    return {'baseline': BASELINE, 'testedMeloNXSource': SOURCE,
        'preservedRPCS3Core': previous.CORE_SOURCE, 'preservedRPCS3Run': previous.CORE_RUN,
        'newCore': 'MeloNX only', 'switchImportAndPlaylistUnchanged': True,
        'otherEnginesAndMotionUnchanged': True, 'physicalDeviceTested': False}

def component(run, source, jobs, wait):
    if wait:
        deadline = time.monotonic() + 10800
        while True:
            state = base.api('actions/runs/' + str(run))
            assert state['head_sha'] == source
            if state['status'] == 'completed': break
            assert time.monotonic() < deadline, 'Timed out waiting for MeloNX proof'
            print('Waiting for exact MeloNX proof', run, state['status'], flush=True)
            time.sleep(30)
    return base.successful_run(run, source, jobs)

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
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths); return
    record = {'result': 'passed', 'source': base.command(['git', 'rev-parse', 'HEAD']),
        'sourceClosure': source_closure()}
    if not args.source_only:
        record['componentEvidence'] = [component(CORE_RUN, SOURCE, ['core'], args.wait_for_components),
            component(HOST_RUN, HOST_SOURCE, ['host'], args.wait_for_components),
            component(APP_RUN, APP_SOURCE, ['flutter'], args.wait_for_components),
            component(previous.CORE_RUN, previous.CORE_SOURCE, ['RPCS3 GoW3: targeted proofs and iPhone Core'], args.wait_for_components)]
        record['reusedEvidence'] = [base.successful_run(39959490510,
            '02a0273494c50bc849b092c0fff395d9e5fd7ebf', ['checks', 'native', 'Release device build • cold'])]
    out = ROOT / args.output; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS exact MeloNX launch inputs; 512 UI/import and 513 RPCS3 Core preserved.')

if __name__ == '__main__': main()
