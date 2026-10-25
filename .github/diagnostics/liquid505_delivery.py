"""Build 505: combined startup 504, liquid material and sequential AirPlay.

Close the exact tested UI, preserve the delivered startup/native bytes, reuse
their successful evidence and retain all existing IPA/signature/core gates.
"""
import argparse
import hashlib
import json
import os
import rewind504_delivery as previous

base = previous.base
BASELINE = 'd27a06f6ad386a79c55ac4e9304e5475c1c0c9a9'
BASELINE_RUN = 39843964056
TESTED = '01f6e9d44943b5f6bc8df3447ed9ddd465e3971b'
TESTED_RUN = 39846213108
TEST_JOB = 'Liquid material and sequential AirPlay navigation'
PRODUCT_PATHS = ['lib', 'assets', 'packages', 'native', 'ios',
                 'pubspec.yaml', 'pubspec.lock', 'build-utils/libretro']
UI = {
    'lib/screens/app_screen.dart', 'lib/screens/airplay_screen.dart',
    'lib/utils/nav_tabs.dart', 'lib/widgets/console_bubble_transition.dart',
    'lib/widgets/header.dart', 'lib/widgets/main_menu_tab_strip.dart',
    'lib/widgets/neo_glass_bubble.dart', 'lib/widgets/neoplay_dialog.dart',
}
DELIVERY = {
    '.github/diagnostics/liquid505_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    '.github/workflows/bubbles503-checks.yml',
    '.github/workflows/liquid-glass-airplay-checks.yml',
    'build-utils/delivery-505-chatgpt-recipient.pem',
    'docs/liquid-glass-airplay-build505.md',
    'docs/evidence/liquid-glass-airplay505-delivery.json',
}

CLEANUP = """
  cleanup_liquid_branch:
    name: Remove the integrated temporary UI branch
    needs: cold
    if: ${{ github.ref == 'refs/heads/Claude' && needs.cold.result == 'success' }}
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions:
      contents: write
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0, persist-credentials: false}
      - name: Delete only the exact tested branch after successful IPA delivery
        run: |
          python3 - <<'PYTHON'
          import json, os, subprocess
          expected = '01f6e9d44943b5f6bc8df3447ed9ddd465e3971b'
          endpoint = 'repos/TarbleFR/RewindBox/git/refs/heads/work/liquid-glass-airplay-20261022'
          subprocess.run(['git', 'merge-base', '--is-ancestor', expected, os.environ['GITHUB_SHA']], check=True)
          current = json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True))
          assert current['object']['sha'] == expected, 'Temporary branch advanced; preserve it for review'
          subprocess.run(['gh', 'api', '--method', 'DELETE', endpoint], check=True)
          print('Removed the exact integrated temporary UI branch; Claude/main preserved')
          PYTHON
"""


validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_psp_core_identity = previous.validate_psp_core_identity


def source_closure():
    if os.environ.get('GITHUB_REF_NAME') != 'Claude':
        raise ValueError('Build 505 is authorized on Claude only')
    changed = set(base.command(['git', 'diff', '--name-only', BASELINE,
                                'HEAD', '--', *PRODUCT_PATHS]).splitlines())
    if changed != UI:
        raise ValueError('Unexpected product delta from startup 504: ' +
                         ', '.join(sorted(changed ^ UI)))
    after = set(base.command(['git', 'diff', '--name-only', TESTED, 'HEAD']).splitlines())
    working = set(base.command(['git', 'diff', '--name-only', TESTED]).splitlines())
    if (after | working) - DELIVERY:
        raise ValueError('Changed a validated UI/test input: ' +
                         ', '.join(sorted((after | working) - DELIVERY)))
    # Startup geometry, initialization, permissions, scan, import, engines,
    # dependencies, artwork and all twelve language maps are outside UI above.
    recipe = (base.ROOT / '.github/workflows/retroarch-delivery.yml').read_text()
    delivered = base.command(['git', 'show', BASELINE +
                             ':.github/workflows/retroarch-delivery.yml'])
    expected = delivered.replace('rewind504_delivery', 'liquid505_delivery').replace('504', '505') + '\n' + CLEANUP
    if recipe.strip() != expected.strip():
        raise ValueError('Delivery recipe changed beyond identity, evidence reader, recipient and leased branch cleanup')
    data = (base.ROOT / 'native/textures/catalogue/manifest.json.gz').read_bytes()
    bundled = base.ROOT / 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz'
    if data != bundled.read_bytes():
        raise ValueError('Hosted and bundled HD catalogues differ')
    return {
        'baseline': BASELINE, 'baselineRun': BASELINE_RUN,
        'testedSource': TESTED, 'testedRun': TESTED_RUN,
        'presentationChanges': sorted(changed), 'deliveryChanges': sorted(after),
        'catalogueSHA256': hashlib.sha256(data).hexdigest(),
        'startup504Preserved': True, 'nativeAndCoreInputsReused': True,
        'rebuiltCores': [],
    }


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
        print('PASS exact combined UI and preserved Build 504 startup/engines')
        return
    records = [
        base.successful_run(BASELINE_RUN, BASELINE,
                            ['checks', 'native', 'Release device build • cold']),
        base.successful_run(TESTED_RUN, TESTED, [TEST_JOB]),
    ]
    record = {
        'result': 'passed', 'testedSHA': TESTED,
        'candidateSHA': base.command(['git', 'rev-parse', 'HEAD']),
        'sourceClosure': closure, 'reusedEvidence': records,
        'validationWasReused': True, 'unchangedDartSource': TESTED,
        'unchangedNativeSource': BASELINE, 'deviceGameplayValidated': False,
        'physicalDeviceAnimationPerformanceValidated': False, 'rebuiltCores': [],
    }
    if args.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'],
                      tool='Flutter 3.47.2, Ubuntu 24.04')
    if args.libretro_evidence:
        xcode = base.command(['xcodebuild', '-version'])
        sdk = base.command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'])
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Native toolchain changed; prior evidence cannot be reused')
        record.update(xcode=xcode, iphoneSDK=sdk)
    output = base.ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS combined liquid-glass/AirPlay tests and unchanged delivered startup 504')


if __name__ == '__main__':
    main()
