#!/usr/bin/env python3
"""Targeted Build 482 checks: PS3 firmware preflight (Flutter) and ARMSX2 ABI 7 contracts.

Runs only what Build 482 changes outside the ARMSX2 Core workflow: analysis of
the changed Dart files, the new preflight dialog and locale tests, the firmware
gate and import-menu tests that share those widgets, the RPCS3 manager/ARMSX2
contract tests, the twelve-locale coverage and the portable C++ contract of the
ARMSX2 ABI/blending headers. The verdict records the SHA-256 of every tested
input so the delivery closure can prove it reuses exactly this run. Nothing here
compiles the Core, renders a game or claims an iPhone result.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/build482'
PRODUCT = [
    'lib/l10n/rpcs3_firmware_locale.dart',
    'lib/widgets/rpcs3_firmware_preflight_dialog.dart',
    'lib/screens/rpcs3_manager_screen.dart',
    'lib/widgets/rpcs3_internal_playlist_actions.dart',
    'packages/armsx2_internal_bridge/core/ARMSX2BlendingAccuracy.h',
    'packages/armsx2_internal_bridge/core/ARMSX2BlendingAccuracy.inc',
    'packages/armsx2_internal_bridge/core/ARMSX2Core.mm',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2InGameLocalization.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
    'build-utils/armsx2/source.json',
]
TESTS = [
    'test/rpcs3_firmware_preflight_test.dart',
    'test/rpcs3_firmware_library_test.dart',
    'test/rpcs3_rap_import_menu_test.dart',
    'test/rpcs3_internal_integration_test.dart',
    'test/armsx2_embedded_library_contract_test.dart',
    'test/armsx2_in_game_localization_test.dart',
    'test/localization_12_locale_coverage_test.py',
    'test/armsx2_bios_hacks_test.py',
    'test/armsx2_graphics_test.py',
    'test/armsx2_graphics_ui_test.py',
    'test/armsx2_blending_accuracy_test.mm',
    'test/build482_targeted_test.py',
    '.github/workflows/build482-checks.yml',
    '.github/workflows/armsx2-core.yml',
]
DART_TESTS = [t for t in TESTS if t.endswith('_test.dart')]
ANALYZED = [p for p in PRODUCT if p.endswith('.dart')] + DART_TESTS


def run(args, **kwargs):
    print('+', ' '.join(args), flush=True)
    started = time.monotonic()
    # UTF-8 sources on every host, including a cp1252 Windows console.
    env = {**os.environ, 'PYTHONUTF8': '1'}
    subprocess.run(args, cwd=ROOT, check=True, env=env, **kwargs)
    return round(time.monotonic() - started, 3)


def main():
    flutter = shutil.which('flutter') or 'flutter'
    python = sys.executable
    timings = {}
    timings['analyze'] = run([flutter, 'analyze', '--no-fatal-infos', *ANALYZED])
    timings['dartTests'] = run([flutter, 'test', *DART_TESTS])
    timings['twelveLocales'] = run([python, 'test/localization_12_locale_coverage_test.py'])
    # Portable C++ contract (ABI header, hack whitelist, five iPhone blending levels).
    timings['armsx2Contracts'] = run([python, 'test/armsx2_bios_hacks_test.py'])
    # Twelve native locales of the in-game menu, including the 19 new blending keys;
    # the Foundation/MRC adapter execution inside this script runs on macOS only.
    timings['armsx2GraphicsKeys'] = run([python, 'test/armsx2_graphics_test.py'])
    inputs = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PRODUCT + TESTS}
    OUT.mkdir(parents=True, exist_ok=True)
    verdict = {
        'result': 'passed',
        'build': 482,
        'source': os.environ.get('GITHUB_SHA', subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()),
        'host': platform.platform(),
        'flutter': subprocess.check_output([flutter, '--version', '--machine'], cwd=ROOT, text=True).strip(),
        'dartTests': DART_TESTS,
        'pythonChecks': ['test/localization_12_locale_coverage_test.py', 'test/armsx2_bios_hacks_test.py', 'test/armsx2_graphics_test.py'],
        'timingsSeconds': timings,
        'inputsSHA256': inputs,
        'coreRebuilt': False,
        'deviceValidated': False,
        'notes': [
            'The ARMSX2 Core, its Foundation/MRC adapter test and the UIKit menu run in armsx2-core.yml.',
            'Simulator and host results are not physical iPhone validation.',
        ],
    }
    (OUT / 'verdict.json').write_text(json.dumps(verdict, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'inputs': len(inputs), 'timingsSeconds': timings}, indent=2))


if __name__ == '__main__':
    main()
