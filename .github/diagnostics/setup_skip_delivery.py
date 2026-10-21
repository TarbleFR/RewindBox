"""Require the new first-run proof and reuse unchanged Build 472 evidence."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import game_close_delivery as previous

ROOT = previous.ROOT
BASE_REF = 'b8f5d81416c977cb165b4050f4349b33b8e84977'
SETUP_REF = '97fdd006ae30f9ab5b33d7e140fabf8bd98a9b52'
SETUP_RUN = 39088013240
SETUP_INPUTS = {'lib/widgets/setup_wizard.dart', 'test/setup_skip_test.py',
                '.github/workflows/setup-skip.yml'}
DELIVERY_ONLY = previous.DELIVERY_ONLY | {
    '.github/diagnostics/setup_skip_delivery.py',
    '.github/diagnostics/setup_skip_delivery_test.py', 'docs/build473-optional-setup.md'}
CASES = ['old-ios-skip-hidden', 'ios-touch-skip-scan-next-finish',
         'ios-gamepad-skip', 'busy-touch-and-gamepad-blocked',
         'disposed-post-frame-cancelled', 'twelve-locales-portrait-landscape',
         'android-desktop-footer-preserved']


def validate_changed_paths(paths):
    invalid = set(paths) - DELIVERY_ONLY - previous.UI_INPUTS - SETUP_INPUTS
    if invalid:
        raise ValueError('Unvalidated product or core changes: ' + ', '.join(sorted(invalid)))


def source_closure():
    core = previous.previous
    for args in (['git', 'diff', '--name-only', core.CORE_REF, 'HEAD'],
                 ['git', 'diff', '--name-only', core.CORE_REF]):
        validate_changed_paths(core.command(args).splitlines())
    if set(core.command(['git', 'diff', '--name-only', BASE_REF, SETUP_REF]).splitlines()) != SETUP_INPUTS:
        raise ValueError('Setup proof has unreviewed dependencies')
    core.command(['git', 'diff', '--exit-code', SETUP_REF, '--', *sorted(SETUP_INPUTS)])
    core.command(['git', 'diff', '--exit-code', previous.UI_REF, '--', *sorted(previous.UI_INPUTS)])
    core.command(['git', 'diff', '--exit-code', core.BASE_REF, core.CORE_REF,
                  '--', 'lib', 'packages', 'assets', 'test', 'pubspec.yaml',
                  'pubspec.lock', 'build-utils'])
    core.command(['git', 'diff', '--exit-code', core.CORE_BINARY_REF, core.CORE_REF,
                  '--', 'native/nestopia', '.github/diagnostics/nestopia_bgcolor/build.py',
                  'build-utils/libretro'])
    excluded = DELIVERY_ONLY | previous.UI_INPUTS | SETUP_INPUTS
    unchanged = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                 for p in core.command(['git', 'ls-files']).splitlines()
                 if p not in excluded and (ROOT / p).is_file()}
    targeted = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SETUP_INPUTS}
    return unchanged, targeted


def validate_setup_verdict(record):
    if (record.get('result') != 'passed' or record.get('source') != SETUP_REF
            or record.get('baseline') != BASE_REF or record.get('cases') != CASES
            or record.get('wizardSHA256') != hashlib.sha256((ROOT / 'lib/widgets/setup_wizard.dart').read_bytes()).hexdigest()
            or record.get('externalFolderChosen') is not False
            or record.get('physicalDeviceValidated') is not False):
        raise ValueError('Missing actual optional setup/navigation witness')
    locales = record.get('locales', {})
    if (set(locales) != {'en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'ja', 'ko', 'zh', 'zh_hant', 'id'}
            or not all(locales.values()) or locales.get('zh') == locales.get('zh_hant')):
        raise ValueError('Incomplete twelve-language skip labels')
    return record


def setup_evidence():
    jobs = previous.previous.successful_run(SETUP_RUN, SETUP_REF,
                                            '.github/workflows/setup-skip.yml', ['setup-skip'])
    if not any(s['name'] == 'Exercise optional library navigation and pending operations'
               and s.get('conclusion') == 'success' for s in jobs[0]['steps']):
        raise ValueError('Actual Flutter first-run tests did not pass')
    with tempfile.TemporaryDirectory(prefix='setup-skip-witness-') as tmp:
        subprocess.run(['gh', 'run', 'download', str(SETUP_RUN), '--repo', 'TarbleFR/RewindBox',
                        '--name', 'setup-skip-' + SETUP_REF, '--dir', tmp], check=True)
        paths = list(Path(tmp).rglob('verdict.json'))
        if len(paths) != 1:
            raise ValueError('Ambiguous or absent optional setup verdict')
        return validate_setup_verdict(json.loads(paths[0].read_text()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dart-evidence', action='store_true')
    p.add_argument('--libretro-evidence', action='store_true')
    p.add_argument('--skin-session-evidence', action='store_true')
    p.add_argument('--scope', default='full', choices=['full'])
    p.add_argument('--output', default='build/delivery/reused-validation.json')
    args = p.parse_args()
    unchanged, targeted = source_closure()
    core = previous.previous
    record = {'result': 'passed', 'testedSHA': core.BASE_REF,
              'validationWasReused': True, 'reusedFromRun': core.BASE_RUN,
              'unchangedInputsSHA256': unchanged, 'targetedSetupInputsSHA256': targeted,
              'targetedSetupSource': SETUP_REF, 'targetedSetupRun': SETUP_RUN,
              'targetedSetupEvidence': setup_evidence(),
              'targetedUISource': previous.UI_REF, 'targetedUIRun': previous.UI_RUN,
              'targetedUIEvidence': previous.ui_evidence(),
              'compiledCoreSource': core.CORE_BINARY_REF,
              'targetedCoreSource': core.CORE_REF, 'targetedCoreRun': core.CORE_RUN,
              'targetedCoreEvidence': core.evidence(), 'deviceGameplayValidated': False}
    if args.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'], tool='Flutter 3.47.2, Ubuntu 24.04')
    if args.libretro_evidence:
        xcode = core.command(['xcodebuild', '-version'])
        sdk = core.command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'])
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Changed native toolchain')
        record.update(xcode=xcode, iphoneSDK=sdk)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('Reused unchanged Build 472 inputs and evidence; required the exact optional iOS setup proof.')


if __name__ == '__main__':
    main()
