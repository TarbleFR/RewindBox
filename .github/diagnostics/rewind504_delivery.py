"""Build 504: tested Rewind Motion startup; byte-identical delivered native/core inputs.

Only presentation changes. Require the successful exact Flutter candidate and
reuse Build 503's native checks after a closed source/toolchain comparison.
The existing device, signature and final IPA validators still execute.
"""
import argparse
import hashlib
import json
import os
import bubbles503_delivery as previous

base = previous.base
BASELINE = '654263ac09ad192360064f92dedcb4f9442bde38'
BASELINE_RUN = 39838471053
TESTED = 'df81491d4ad683fe6a28f1864b23158cefcf202d'
TESTED_RUN = 39843627554
TEST_JOB = 'Startup readiness, recovery and accessibility'
NATIVE_SOURCE = '409ee862ab61b5cc7bba76a96e686632c2d63c28'
NATIVE_RUN = 39843086776
NATIVE_JOB = 'Static launch geometry and iPhone storyboard'
UI = {
    'lib/main.dart', 'lib/widgets/rewind_startup.dart',
    'lib/widgets/rewind_mark_path.dart',
    'lib/widgets/permission_check_wrapper.dart',
    'lib/screens/systems_screen/system_content.dart',
}
DELIVERY = {
    '.github/diagnostics/rewind504_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/delivery-504-chatgpt-recipient.pem',
    'docs/rewind-motion-build504.md',
}

# The completed, unchanged ABI 30 RPCS3 core and PSP memory identity checks.
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_psp_core_identity = previous.validate_psp_core_identity


def source_closure():
    if os.environ.get('GITHUB_REF_NAME') != 'Claude':
        raise ValueError('Build 504 is authorized on Claude only')
    changed = set(base.command(['git', 'diff', '--name-only', BASELINE, 'HEAD', '--', *previous.previous.PRODUCT_PATHS]).splitlines())
    if changed != UI:
        raise ValueError('Unexpected product delta from delivered 503: ' + ', '.join(sorted(changed ^ UI)))
    # Every implementation byte, test and CI recipe of the successful UI run
    # must remain identical. Only these delivery/evidence files may follow it.
    after = set(base.command(['git', 'diff', '--name-only', TESTED, 'HEAD']).splitlines())
    working = set(base.command(['git', 'diff', '--name-only', TESTED]).splitlines())
    if (after | working) - DELIVERY:
        raise ValueError('Changed a validated UI/test input: ' + ', '.join(sorted((after | working) - DELIVERY)))
    workflow = (base.ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    delivered_recipe = base.command(['git', 'show', BASELINE + ':.github/workflows/retroarch-delivery.yml'])
    expected_recipe = delivered_recipe.replace('bubbles503_delivery', 'rewind504_delivery').replace('503', '504')
    expected_recipe = expected_recipe.replace(
        '        python3 build-utils/configure_external_display_ios.py\n',
        '        python3 build-utils/configure_external_display_ios.py\n        python3 build-utils/configure_rewind_launch.py\n')
    if workflow.strip() != expected_recipe.strip():
        raise ValueError('Delivery recipe changed beyond build identity, evidence reader and recipient')
    for marker in ('name: RewindBox RetroArch • Build 504 • SideStore',
                   "inputs.build_number || '504'", 'build-utils/delivery-504-chatgpt-recipient.pem',
                   '- .github/diagnostics/rewind504_delivery.py'):
        if marker not in workflow:
            raise ValueError('Missing Build 504 delivery marker: ' + marker)
    native_paths = ['build-utils/configure_rewind_launch.py', 'build-utils/rewind-motion', 'test/rewind_launch_test.py']
    if base.command(['git', 'diff', '--name-only', NATIVE_SOURCE, 'HEAD', '--', *native_paths]):
        raise ValueError('Native launch resource changed after its successful Xcode proof')
    proof_recipe = base.command(['git', 'show', NATIVE_SOURCE + ':.github/workflows/rewind504-checks.yml']).split('  native:\n', 1)[1]
    current_recipe = (base.ROOT / '.github/workflows/rewind504-checks.yml').read_text().split('  native:\n', 1)[1]
    current_recipe = current_recipe.replace("    if: ${{ !contains(github.event.head_commit.message, '[startup-flutter-only]') }}\n", '', 1)
    if current_recipe.strip() != proof_recipe.strip():
        raise ValueError('Native launch proof recipe changed')
    data = (base.ROOT / previous.previous.INDEX).read_bytes()
    if data != (base.ROOT / previous.previous.BUNDLED).read_bytes():
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
        print('PASS exact tested Build 504 presentation and unchanged Build 503 engines/data')
        return
    records = [
        base.successful_run(BASELINE_RUN, BASELINE, ['checks', 'native', 'Release device build • cold']),
        base.successful_run(TESTED_RUN, TESTED, [TEST_JOB]),
        base.component_run(NATIVE_RUN, NATIVE_SOURCE, [NATIVE_JOB], 'failure'),
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
    print('PASS Build 504 startup tests, native launch resource proof and unchanged Build 503 engines')


if __name__ == '__main__':
    main()
