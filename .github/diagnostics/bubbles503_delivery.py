"""Build 503: tested glass UI; byte-identical delivered native/core inputs.

Only presentation changes. Require the successful exact Flutter candidate and
reuse Build 502's native checks after a closed source/toolchain comparison.
The existing device, signature and final IPA validators still execute.
"""
import argparse
import hashlib
import json
import os
import psprelaunch497_delivery as previous

base = previous.base
BASELINE = '3c59580b012919ae6f7179f59f0e8efcfd4818fb'
BASELINE_RUN = 39824551286
TESTED = '5f83c031b662e40661d337d92fa33ced33ea8fcd'
TESTED_RUN = 39837868898
TEST_JOB = 'Interactive glass, playlist ownership and input'
UI = {
    'lib/widgets/neo_glass_bubble.dart',
    'lib/widgets/console_bubble_transition.dart',
    'lib/widgets/main_menu_tab_strip.dart',
    'lib/widgets/header.dart',
    'lib/widgets/header_sort_dropdown.dart',
    'lib/widgets/game_view_mode_dropdown.dart',
    'lib/screens/settings_screen/new_settings_screen.dart',
    'lib/screens/systems_screen/my_systems_section/system_card.dart',
    'lib/screens/systems_screen/my_systems_section/my_systems_grid.dart',
    'lib/screens/systems_screen/my_systems_section/my_systems_carousel.dart',
}
DELIVERY = {
    '.github/diagnostics/bubbles503_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/delivery-503-chatgpt-recipient.pem',
    'docs/interactive-glass-build503.md',
}

# The completed, unchanged ABI 30 RPCS3 core and PSP memory identity checks.
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_psp_core_identity = previous.validate_psp_core_identity


def source_closure():
    if os.environ.get('GITHUB_REF_NAME') != 'Claude':
        raise ValueError('Build 503 is authorized on Claude only')
    changed = set(base.command(['git', 'diff', '--name-only', BASELINE, 'HEAD', '--', *previous.PRODUCT_PATHS]).splitlines())
    if changed != UI:
        raise ValueError('Unexpected product delta from delivered 502: ' + ', '.join(sorted(changed ^ UI)))
    # Every implementation byte, test and CI recipe of the successful UI run
    # must remain identical. Only these delivery/evidence files may follow it.
    after = set(base.command(['git', 'diff', '--name-only', TESTED, 'HEAD']).splitlines())
    working = set(base.command(['git', 'diff', '--name-only', TESTED]).splitlines())
    if (after | working) - DELIVERY:
        raise ValueError('Changed a validated UI/test input: ' + ', '.join(sorted((after | working) - DELIVERY)))
    workflow = (base.ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    delivered_recipe = base.command(['git', 'show', BASELINE + ':.github/workflows/retroarch-delivery.yml'])
    expected_recipe = delivered_recipe.replace('502', '503').replace('psprelaunch497_delivery', 'bubbles503_delivery').replace('default: build-utils/delivery-424-recipient.pem', 'default: build-utils/delivery-503-chatgpt-recipient.pem')
    if workflow.strip() != expected_recipe.strip():
        raise ValueError('Delivery recipe changed beyond build identity, evidence reader and recipient')
    for marker in ('name: RewindBox RetroArch • Build 503 • SideStore',
                   "inputs.build_number || '503'", 'build-utils/delivery-503-chatgpt-recipient.pem',
                   '- .github/diagnostics/bubbles503_delivery.py'):
        if marker not in workflow:
            raise ValueError('Missing Build 503 delivery marker: ' + marker)
    data = (base.ROOT / previous.INDEX).read_bytes()
    if data != (base.ROOT / previous.BUNDLED).read_bytes():
        raise ValueError('Hosted and bundled HD catalogues differ')
    return {'baseline': BASELINE, 'baselineRun': BASELINE_RUN,
            'testedSource': TESTED, 'testedRun': TESTED_RUN,
            'presentationChanges': sorted(changed), 'deliveryChanges': sorted(after),
            'catalogueSHA256': hashlib.sha256(data).hexdigest(),
            'nativeAndCoreInputsReused': True, 'rebuiltCores': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--dart-evidence', action='store_true')
    parser.add_argument('--libretro-evidence', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument('--scope', default='full', choices=['full'])
    parser.add_argument('--output', default='build/delivery/reused-validation.json')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    args = parser.parse_args()
    closure = source_closure()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    if args.source_only:
        print('PASS exact tested Build 503 presentation and unchanged Build 502 engines/data')
        return
    records = [
        base.successful_run(BASELINE_RUN, BASELINE, ['checks', 'native', 'Release device build • cold']),
        base.successful_run(TESTED_RUN, TESTED, [TEST_JOB]),
    ]
    record = {'result': 'passed', 'testedSHA': TESTED,
              'candidateSHA': base.command(['git', 'rev-parse', 'HEAD']),
              'sourceClosure': closure, 'reusedEvidence': records,
              'validationWasReused': True, 'unchangedDartSource': TESTED,
              'unchangedNativeSource': BASELINE, 'deviceGameplayValidated': False,
              'physicalDeviceAnimationPerformanceValidated': False, 'rebuiltCores': []}
    if args.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'], tool='Flutter 3.47.2, Ubuntu 24.04')
    if args.libretro_evidence:
        xcode = base.command(['xcodebuild', '-version'])
        sdk = base.command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'])
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Native toolchain changed; existing evidence cannot be reused')
        record.update(xcode=xcode, iphoneSDK=sdk)
    output = base.ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS Build 503 UI tests and unchanged Build 502 native evidence')


if __name__ == '__main__':
    main()
