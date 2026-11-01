"""Run the affected608 suites and retain actual commands, exit codes and logs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time

import rewind608_baseline as tree
from rewind608_producers import execution, save

ROOT = tree.ROOT
FLUTTER_TESTS = (
    'test/achievement_translation_test.dart',
    'test/retro_achievements_service_test.dart',
    'test/retro_achievements_credentials_test.dart',
    'test/retro_achievements_repository_test.dart',
    'test/retro_achievements_resolver_test.dart',
    'test/retro_achievements_layout_test.dart',
    'test/secondary_achievement_item_test.dart',
    'test/external_menu_screen_test.dart',
    'test/retro_achievements_session_test.dart',
    'test/retro_achievements_migration_test.dart',
    'test/retro_achievements_account_consistency_test.dart',
    'test/retro_achievements_session_localization_test.dart',
    'test/retro_achievements_capabilities_test.dart',
    'test/armsx2_in_game_localization_test.dart',
    'test/armsx2_embedded_library_contract_test.dart',
)
ANALYZE = (
    'packages/achievement_translation/lib', 'packages/retro_achievements_session/lib',
    'lib/models/retro_achievements_session.dart', 'lib/services/retro_achievements_session_service.dart',
    'lib/services/retro_achievements_service.dart', 'lib/repositories/retro_achievements_repository.dart',
    'lib/providers/retro_achievements_dashboard_source.dart',
    'lib/providers/retro_achievements_provider.dart',
    'lib/screens/retro_achievements_screen', 'lib/widgets/translated_achievement_text.dart',
    'lib/l10n/achievement_translation_locale.dart',
    'lib/l10n/app_widget_localizations.dart',
    'lib/services/dolphin_internal_v2_service.dart', 'lib/services/libretro_internal_service.dart',
    'lib/services/stikjit_armsx2_service.dart', 'packages/armsx2_internal_bridge/lib',
)
GROUPS = {
    'flutter': (
        ('delivery-contract-tests', ('python3', '-B', 'test/rewind608_delivery_contract_test.py')),
        ('translation-source', ('python3', '-B', 'test/achievement_translation_contract_test.py')),
        ('central-harness-contract', ('python3', '-B', 'test/retro_achievements_session_native_test.py', '--check-only')),
        ('libretro-policy', ('python3', '-B', 'test/libretro_ra_policy_test.py')),
        ('libretro-retired-account', ('python3', '-B', 'test/libretro_legacy_ra_contract_test.py')),
        ('libretro-native-labels', ('python3', '-B', 'test/cheat_bootstrap_test.py',
                                   'Bootstrap.test_native_label_contract',
                                   'Bootstrap.test_twelve_complete_locales')),
        ('dolphin-policy', ('python3', '-B', 'test/dolphin_ra_session_test.py')),
        ('dolphin-presentation', ('python3', '-B', 'test/achievement_translation_native_test.py')),
        ('dolphin-retired-account', ('python3', '-B', 'test/dolphin_account_267_test.py')),
        ('armsx2-policy', ('python3', '-B', 'test/armsx2_ra_launch_settings_test.py')),
        ('flutter-analysis', ('flutter', 'analyze', *ANALYZE)),
        ('flutter-behavior', ('flutter', 'test', '--reporter', 'expanded', *FLUTTER_TESTS)),
    ),
    'native': (
        ('translation-xctest', ('python3', '-B', '.github/diagnostics/rewind608_checks.py', 'translation')),
        ('central-session-xctest', ('python3', '-B', 'test/retro_achievements_session_native_test.py',
                                    '--output', 'build/ra-session-validation')),
        ('dolphin-menu-xctest', ('python3', '-B', 'test/dolphin_account_267_test.py', '--native')),
        ('armsx2-menu-xctest', ('python3', '-B', 'test/armsx2_graphics_ui_test.py')),
        ('libretro-host-behavior', ('python3', '-B', 'test/libretro_host_test.py')),
        ('libretro-device-compile', ('python3', '-B', 'test/libretro_ios_syntax_test.py')),
        ('actual-flutter-host-compile', ('python3', '-B', '.github/diagnostics/rewind608_checks.py', 'hosts')),
    ),
}


def command_names(group):
    return [name for name, _ in GROUPS[group]]


def validate_central_receipt(value):
    methods = value.get('contract', {}).get('test_methods', [])
    summary = value.get('xctest_summary', {})
    total = summary.get('totalTestCount')
    tree.require(value.get('status') == 'passed' and isinstance(methods, list) and
                 len(methods) >= 35 and len(set(methods)) == len(methods) and
                 isinstance(total, int) and total >= len(methods) and
                 summary.get('failedTests') == 0 and summary.get('skippedTests') == 0,
                 'The central XCTest harness lacks complete actual passing results')
    return value


def translation():
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], text=True).strip()
    runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-' + sdk.replace('.', '-')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j']))['devices']
    matches = [d for d in devices.get(runtime, []) if d['name'].startswith('iPhone') and d.get('isAvailable')]
    tree.require(sdk.startswith('18.') and matches, 'Xcode16.4 needs a matching available iOS18 simulator')
    subprocess.run(['xcodegen', 'generate', '--spec', 'packages/achievement_translation/ci/project.yml',
                    '--project', 'packages/achievement_translation/ci'], cwd=ROOT, check=True)
    result = ROOT / 'build/AchievementTranslation608.xcresult'
    tree.require(not result.exists(), 'Refusing to reuse a previous Translation XCTest bundle')
    subprocess.run(['xcodebuild', '-project', 'packages/achievement_translation/ci/AchievementTranslation.xcodeproj',
        '-scheme', 'AchievementTranslation', '-destination',
        'platform=iOS Simulator,id=' + matches[0]['udid'] + ',arch=' + platform.machine(),
        '-parallel-testing-enabled', 'NO', '-resultBundlePath', str(result),
        'test', 'CODE_SIGNING_ALLOWED=NO'], cwd=ROOT, check=True, timeout=1200)
    tree.require(result.is_dir(), 'XCTest produced no Translation result bundle')


def flutter_device_framework(flutter_root):
    """Select the real iPhone slice by XCFramework metadata, not folder spelling."""
    bundle = Path(flutter_root) / 'bin/cache/artifacts/engine/ios/Flutter.xcframework'
    metadata = plistlib.loads((bundle / 'Info.plist').read_bytes())
    candidates = [library for library in metadata.get('AvailableLibraries', [])
                  if library.get('SupportedPlatform') == 'ios' and
                  not library.get('SupportedPlatformVariant') and
                  'arm64' in library.get('SupportedArchitectures', [])]
    tree.require(len(candidates) == 1, 'Expected one arm64 iPhoneOS slice in the real Flutter XCFramework')
    library = candidates[0]
    identifier, relative = library['LibraryIdentifier'], library['LibraryPath']
    tree.require(isinstance(identifier, str) and Path(identifier).name == identifier and
                 identifier not in ('', '.', '..') and relative == 'Flutter.framework',
                 'Unexpected Flutter XCFramework library path')
    framework = bundle / identifier / relative
    tree.require(all((framework / path).is_file() for path in
                     ('Flutter', 'Headers/Flutter.h', 'Modules/module.modulemap')),
                 'The selected real Flutter iPhoneOS framework is incomplete')
    print('Selected real Flutter iPhoneOS slice: ' + identifier, flush=True)
    return framework


def hosts():
    sys.path.insert(0, str(ROOT / 'test'))
    from libretro_ios_syntax_test import stage_dependency_headers
    from touch_layout_support import stage_touch_layout
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    framework = flutter_device_framework(Path(os.environ['FLUTTER_ROOT']))
    with tempfile.TemporaryDirectory(prefix='rewind608-public-headers-') as temporary:
        include = stage_touch_layout(stage_dependency_headers(Path(temporary)))
        tree.require((include / 'retro_achievements_session/RBRASession.h').is_file(),
                     'The central session public header was not staged')
        for package, filenames, helper in (
            ('armsx2_internal_bridge', ('Armsx2InternalBridgePlugin.mm', 'Armsx2TextureBridge.mm'), 'armsx2_jit_helper'),
            ('dolphin_internal_bridge', ('DolphinInternalBridgePlugin.mm',), 'dolphin_jit_helper'),
        ):
            for filename in filenames:
                path = ROOT / 'packages' / package / 'ios/Classes' / filename
                subprocess.run(['xcrun', 'clang++', '-std=c++20', '-fobjc-arc', '-fblocks', '-fsyntax-only',
                    '-Werror=implicit-function-declaration', '-Werror=incompatible-pointer-types',
                    '-x', 'objective-c++', '-isysroot', sdk, '-target', 'arm64-apple-ios18.0',
                    '-F', str(framework.parent), '-I', str(include),
                    '-I', str(ROOT / 'packages' / helper / 'ios/Classes'), str(path)],
                    cwd=ROOT, check=True, timeout=300)


def run(group):
    tree.require(group in GROUPS, 'Unknown608 test group')
    tree.verify()
    directory = ROOT / 'build/validation608' / group
    directory.mkdir(parents=True, exist_ok=True)
    receipt = dict(schema=1, result='running', group=group, execution=execution(),
        sourceScopeSHA256=tree.sha((ROOT / tree.CONFIG).read_bytes()), commands=[],
        physicalDeviceTested=False, translationModelsDownloaded=False)
    if group == 'native':
        receipt['xcodeVersion'] = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
        receipt['swiftVersion'] = subprocess.check_output(['xcrun', 'swift', '--version'], text=True).strip()
        tree.require(receipt['xcodeVersion'].startswith('Xcode 16.4\n'), 'Select Xcode16.4 before targeted tests')
    first_failure = 0
    for name, arguments in GROUPS[group]:
        start = time.monotonic()
        log = directory / (name + '.log')
        print('+ ' + ' '.join(arguments), flush=True)
        with log.open('wb') as output:
            try:
                process = subprocess.run(arguments, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                         timeout=1800)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 124
        raw = log.read_bytes()
        print(raw.decode(errors='replace')[-18000:], flush=True)
        receipt['commands'].append(dict(name=name, argv=list(arguments), exitCode=code,
            seconds=round(time.monotonic() - start, 3), log=log.name, logSHA256=tree.sha(raw)))
        if code:
            first_failure = first_failure or code
            receipt['result'] = 'failed'
        save(directory / 'validation.json', receipt)
    if first_failure:
        # Keep independent diagnostics from this exact source while preserving
        # the failed prerequisite: no native producer or IPA can consume it.
        raise SystemExit(first_failure)
    receipt['result'] = 'passed'
    if group == 'native':
        result = json.loads((ROOT / 'build/ra-session-validation/validation.json').read_bytes())
        receipt['centralSessionXCTest'] = validate_central_receipt(result)
    return save(directory / 'validation.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['flutter', 'native', 'translation', 'hosts'])
    args = parser.parse_args()
    if args.operation in GROUPS:
        print(json.dumps(run(args.operation), indent=2))
    else:
        globals()[args.operation]()
