"""Reuse Build 471; require the exact new common return-label witness."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import nestopia_delivery as previous

ROOT = previous.ROOT
UI_REF = 'a5e8fe6ee42c53bd20a2ce6f8b96a763f59a262e'
UI_RUN = 39086239948
UI_INPUTS = {'lib/widgets/game_launch_dialog.dart',
             'test/game_close_status_test.py', '.github/workflows/game-close-status.yml'}
DELIVERY_ONLY = previous.DELIVERY_ONLY | {
    '.github/diagnostics/game_close_delivery.py',
    '.github/diagnostics/game_close_delivery_test.py', 'docs/build472-close-status.md'}


def validate_changed_paths(paths):
    invalid = set(paths) - DELIVERY_ONLY - UI_INPUTS
    if invalid:
        raise ValueError('Unvalidated product or core changes: ' + ', '.join(sorted(invalid)))


def source_closure():
    for args in (['git', 'diff', '--name-only', previous.CORE_REF, 'HEAD'],
                 ['git', 'diff', '--name-only', previous.CORE_REF]):
        validate_changed_paths(previous.command(args).splitlines())
    # Only the exact UI source and test recipe that passed may differ from 471.
    previous.command(['git', 'diff', '--exit-code', UI_REF, '--', *sorted(UI_INPUTS)])
    previous.command(['git', 'diff', '--exit-code', previous.BASE_REF, previous.CORE_REF,
                      '--', 'lib', 'packages', 'assets', 'test', 'pubspec.yaml',
                      'pubspec.lock', 'build-utils'])
    previous.command(['git', 'diff', '--exit-code', previous.CORE_BINARY_REF,
                      previous.CORE_REF, '--', 'native/nestopia',
                      '.github/diagnostics/nestopia_bgcolor/build.py', 'build-utils/libretro'])
    paths = previous.command(['git', 'ls-files']).splitlines()
    unchanged = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths
                 if p not in DELIVERY_ONLY | UI_INPUTS and (ROOT / p).is_file()}
    targeted = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in UI_INPUTS}
    return unchanged, targeted


def validate_ui_verdict(record):
    expected = {'ios_libretro_internal', 'ios_dolphin_internal', 'ios_rpcs3_internal',
                'ios_armsx2_internal', 'ios_dusklight_internal', 'ios_kartpad_internal'}
    if (record.get('result') != 'passed' or record.get('source') != UI_REF
            or record.get('baseline') != '9429a1627a2f72dddc07a5fe3c4cda35cdbd7db9'
            or record.get('baselineReproductions') != 6
            or record.get('correctedReturnCases') != 6
            or record.get('desktopCases') != 1
            or set(record.get('embeddedExecutables', [])) != expected
            or record.get('cleanupBeforeNativeEnd') is not False
            or record.get('physicalDeviceValidated') is not False):
        raise ValueError('Missing actual first-return/cleanup witness')
    locales = record.get('locales', {})
    if set(locales) != {'app_locale_' + x for x in
                       ('en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'ja', 'ko', 'zh', 'zh_hant', 'id')}:
        raise ValueError('Incomplete twelve-language coverage')
    for values in locales.values():
        if set(values) != {'launchingGame', 'gameExecuting', 'closingGame'} or not all(values.values()):
            raise ValueError('Missing translated session label')
    return record


def ui_evidence():
    jobs = previous.successful_run(UI_RUN, UI_REF, '.github/workflows/game-close-status.yml', ['close-status'])
    if not any(s['name'] == 'Exercise first return frame and unchanged cleanup ownership'
               and s.get('conclusion') == 'success' for s in jobs[0]['steps']):
        raise ValueError('Actual Flutter return-label tests did not pass')
    with tempfile.TemporaryDirectory(prefix='game-close-witness-') as tmp:
        subprocess.run(['gh', 'run', 'download', str(UI_RUN), '--repo', 'TarbleFR/neostation-ios',
                        '--name', 'game-close-status-' + UI_REF, '--dir', tmp], check=True)
        paths = list(Path(tmp).rglob('verdict.json'))
        if len(paths) != 1:
            raise ValueError('Ambiguous or absent return-label verdict')
        return validate_ui_verdict(json.loads(paths[0].read_text()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dart-evidence', action='store_true')
    p.add_argument('--libretro-evidence', action='store_true')
    p.add_argument('--skin-session-evidence', action='store_true')
    p.add_argument('--scope', default='full', choices=['full'])
    p.add_argument('--output', default='build/delivery/reused-validation.json')
    args = p.parse_args()
    unchanged, targeted = source_closure()
    old = previous.evidence()
    new = ui_evidence()
    record = {'result': 'passed', 'testedSHA': previous.BASE_REF,
              'validationWasReused': True, 'reusedFromRun': previous.BASE_RUN,
              'unchangedInputsSHA256': unchanged, 'targetedUIInputsSHA256': targeted,
              'targetedUISource': UI_REF, 'targetedUIRun': UI_RUN, 'targetedUIEvidence': new,
              'compiledCoreSource': previous.CORE_BINARY_REF,
              'targetedCoreSource': previous.CORE_REF, 'targetedCoreRun': previous.CORE_RUN,
              'targetedCoreEvidence': old, 'deviceGameplayValidated': False}
    if args.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'], tool='Flutter 3.47.2, Ubuntu 24.04')
    if args.libretro_evidence:
        xcode = previous.command(['xcodebuild', '-version'])
        sdk = previous.command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'])
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Changed native toolchain')
        record.update(xcode=xcode, iphoneSDK=sdk)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('Reused unchanged Build 471 native/core/app checks; required the exact new Flutter return-label proof.')


if __name__ == '__main__':
    main()
