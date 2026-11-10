#!/usr/bin/env python3
"""Scope guard of the Build 440 "120 Hz interface" option (any OS).

The option must only act on the Flutter engine's own refresh-rate request:
one class method of Flutter.framework is wrapped, nothing that an emulator
uses (CADisplayLink, UIScreen, NSBundle, the Info.plist key) is replaced or
rewritten, and no emulator bridge or native core is involved. The simulator
test (ui_refresh_rate_hook_test.py, macOS) exercises the same hook against
the real Flutter.xcframework.
"""
from __future__ import annotations

import os
import re
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/ui_refresh_rate'
CLASSES = PACKAGE / 'ios/Classes'
HOOK = CLASSES / 'UiRefreshRateEngineHook.m'
HOOK_HEADER = CLASSES / 'UiRefreshRateEngineHook.h'
PLUGIN = CLASSES / 'UiRefreshRatePlugin.m'
PREFERENCE_KEY = 'NeoStation.UI.HighRefreshRate.Enabled'
SWIZZLING_APIS = (
    'method_setImplementation',
    'method_exchangeImplementations',
    'class_replaceMethod',
    'class_addMethod',
    'imp_implementationWithBlock',
    'object_setClass',
    'objc_allocateClassPair',
)


def code(path: Path) -> str:
    """Source without comments or string literals (so prose cannot match)."""
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    text = re.sub(r'//[^\n]*', ' ', text)
    return text


def without_strings(text: str) -> str:
    return re.sub(r'@?"(?:\\.|[^"\\])*"', '""', text)


def testing_block_removed(text: str) -> str:
    return re.sub(r'#ifdef NEO_UI_REFRESH_TESTING.*?#endif', ' ', text, flags=re.S)


class HookScopeTests(unittest.TestCase):
    def test_only_the_engine_seam_is_replaced_once(self) -> None:
        source = code(HOOK)
        production = testing_block_removed(source)
        self.assertEqual(production.count('method_setImplementation('), 1)
        for api in SWIZZLING_APIS[1:]:
            self.assertNotIn(api, source, api)
        self.assertEqual(
            re.findall(r'objc_getClass\((\w+)\)', source),
            ['kNeoUiRefreshEngineClass', 'kNeoUiRefreshEngineClass'],
        )
        self.assertIn('kNeoUiRefreshEngineClass = "FlutterDisplayLinkManager";', source)
        self.assertIn('kNeoUiRefreshEngineSelector = "displayRefreshRate";', source)
        # The replaced method must be the class's own, with the validated
        # encoding; otherwise nothing is replaced.
        self.assertIn('class_copyMethodList(meta', source)
        self.assertIn('NeoUiRefreshExpectedTypeEncoding[] = "d16@0:8";', source)
        self.assertIn('NeoUiRefreshHookStatusSignatureMismatch', source)
        self.assertIn('NeoUiRefreshHookStatusClassMissing', source)
        self.assertIn('NeoUiRefreshHookStatusMethodMissing', source)

    def test_emulator_facing_apis_are_never_touched(self) -> None:
        for path in (HOOK, PLUGIN):
            stripped = without_strings(code(path))
            for symbol in ('CADisplayLink', 'NSBundle', 'preferredFrameRateRange',
                           'preferredFramesPerSecond', 'CADisableMinimumFrameDurationOnPhone',
                           'setValue:', 'infoDictionary'):
                self.assertNotIn(symbol, stripped, f'{path.name}: {symbol}')
        # The plugin only reads the screen maximum, never replaces anything.
        plugin = code(PLUGIN)
        for api in SWIZZLING_APIS:
            self.assertNotIn(api, plugin, api)
        self.assertNotIn('UIScreen', without_strings(code(HOOK)))

    def test_policy_constants(self) -> None:
        source = code(HOOK)
        self.assertIn(f'NeoUiRefreshPreferenceKey = @"{PREFERENCE_KEY}";', source)
        # Default enabled: no change from Build 437 for users who never chose.
        self.assertIn('const BOOL NeoUiRefreshDefaultEnabled = YES;', source)
        self.assertIn('const double NeoUiRefreshCappedHz = 60.0;', source)
        # Read once per process (applied at the next launch).
        self.assertEqual(source.count('dispatch_once(&gNeoUiRefreshActiveOnce'), 1)
        policy = source.split('double NeoUiRefreshPolicy(', 1)[1].split('\n}', 1)[0]
        self.assertIn('if (!(engineHz > 0)) return engineHz;', policy)
        self.assertIn('if (enabled) return engineHz;', policy)

    def test_hook_is_installed_from_load_of_the_registered_class(self) -> None:
        plugin = code(PLUGIN)
        body = plugin.split('+ (void)load {', 1)[1].split('\n}', 1)[0]
        self.assertEqual(body.strip(), 'NeoUiRefreshInstallEngineHook();')
        self.assertIn('@implementation UiRefreshRatePlugin', plugin)
        self.assertIn('pluginClass: UiRefreshRatePlugin', (PACKAGE / 'pubspec.yaml').read_text())
        # setEnabled stores only; it never changes the running snapshot.
        set_enabled = plugin.split('isEqualToString:@"setEnabled"', 1)[1]
        self.assertIn('NeoUiRefreshStoreEnabled(', set_enabled)
        self.assertNotIn('NeoUiRefreshTestingSetActiveEnabled', plugin)
        self.assertIn('@"SAVE_FAILED"', PLUGIN.read_text(encoding='utf-8'))

    def test_test_seams_are_not_compiled_into_the_app(self) -> None:
        for path in (HOOK, HOOK_HEADER):
            outside = testing_block_removed(path.read_text(encoding='utf-8'))
            self.assertNotIn('NeoUiRefreshTesting', outside, path.name)
        podspec = (PACKAGE / 'ios/ui_refresh_rate.podspec').read_text()
        self.assertNotIn('NEO_UI_REFRESH_TESTING', podspec)


class PackageWiringTests(unittest.TestCase):
    def test_workspace_member_and_dependency(self) -> None:
        pubspec = (ROOT / 'pubspec.yaml').read_text()
        workspace = pubspec.split('workspace:', 1)[1].split('\n\n', 1)[0]
        self.assertIn('  - packages/ui_refresh_rate', workspace)
        self.assertIn('  ui_refresh_rate:\n    path: packages/ui_refresh_rate\n', pubspec)
        package = (PACKAGE / 'pubspec.yaml').read_text()
        self.assertIn('resolution: workspace', package)
        self.assertNotIn('ui_refresh_rate', (ROOT / 'pubspec.lock').read_text())

    def test_static_objc_pod_linked_into_runner(self) -> None:
        podspec = (PACKAGE / 'ios/ui_refresh_rate.podspec').read_text()
        self.assertIn("s.source_files     = 'Classes/**/*.{h,m}'", podspec)
        self.assertIn('s.static_framework = true', podspec)
        self.assertIn("s.dependency 'Flutter'", podspec)
        self.assertNotIn('vendored', podspec)
        self.assertEqual(
            sorted(p.name for p in CLASSES.iterdir()),
            ['UiRefreshRateEngineHook.h', 'UiRefreshRateEngineHook.m',
             'UiRefreshRatePlugin.h', 'UiRefreshRatePlugin.m'],
        )


class RepositoryScopeTests(unittest.TestCase):
    def iter_sources(self, base: Path):
        for path in base.rglob('*'):
            if path.is_file() and path.suffix in {'.m', '.mm', '.h', '.swift', '.c', '.cpp', '.py', '.json', '.dart'}:
                yield path

    def test_no_emulator_or_native_file_uses_the_seam_or_the_preference(self) -> None:
        offenders = []
        bases = [ROOT / 'native', ROOT / 'build-utils']
        bases += [p for p in (ROOT / 'packages').iterdir() if p.is_dir() and p.name != 'ui_refresh_rate']
        for base in bases:
            for path in self.iter_sources(base):
                text = path.read_text(encoding='utf-8', errors='ignore')
                if ('FlutterDisplayLinkManager' in text or PREFERENCE_KEY in text
                        or 'NeoUiRefresh' in text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_info_plist_key_is_never_written_by_the_build(self) -> None:
        writers = []
        for base in (ROOT / 'build-utils', ROOT / 'scripts', ROOT / 'packages'):
            for path in base.rglob('*'):
                if path.is_file() and path.suffix in {'.py', '.rb', '.sh', '.plist', '.m', '.mm', '.swift'}:
                    text = path.read_text(encoding='utf-8', errors='ignore')
                    if path == HOOK_HEADER:
                        continue
                    if 'CADisableMinimumFrameDurationOnPhone' in text:
                        writers.append(str(path.relative_to(ROOT)))
        self.assertEqual(writers, [])
        delivery = (ROOT / '.github/workflows/retroarch-delivery.yml').read_text(encoding='utf-8')
        # Since 48867389 (Build 506) the step is a YAML double-quoted scalar:
        # decode its escaped line breaks ('\\' + newline + indent) and escaped
        # spaces ('\\ ') so the Python it runs is compared as written.
        delivery = re.sub(r'\\\n[ \t]*', '', delivery).replace('\\ ', ' ')
        self.assertGreaterEqual(
            delivery.count("assert info.get('CADisableMinimumFrameDurationOnPhone') is True"),
            max(1, delivery.count('name: Release device build')),
            'the delivered IPA must keep the ProMotion opt-in the emulators were validated with',
        )

    def test_dart_side_never_touches_emulators_or_stored_config(self) -> None:
        service = (ROOT / 'lib/services/ui_refresh_rate_service.dart').read_text(encoding='utf-8')
        row = (ROOT / 'lib/screens/settings_screen/new_settings_options/widgets/'
               'ui_refresh_rate_setting_row.dart').read_text(encoding='utf-8')
        for text in (service, row):
            for forbidden in ('SqliteConfigProvider', 'ConfigService', 'SharedPreferences',
                              'internal_bridge', 'Ticker(', 'scheduleFrame'):
                self.assertNotIn(forbidden, text, forbidden)
        app_screen = (ROOT / 'lib/screens/app_screen.dart').read_text(encoding='utf-8')
        self.assertIn('UiRefreshRateService.instance.startProbe();', app_screen)

    def test_native_test_harness_is_wired(self) -> None:
        workflow = (ROOT / '.github/workflows/ui-refresh-rate-check.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch', workflow)
        self.assertIn('python3 test/ui_refresh_rate_hook_test.py', workflow)
        self.assertIn('flutter precache --ios', workflow)
        hook_test = (ROOT / 'test/ui_refresh_rate_hook_test.py').read_text(encoding='utf-8')
        self.assertIn('NEO_UI_REFRESH_TESTING=1', hook_test)
        self.assertIn("'CADisableMinimumFrameDurationOnPhone': True", hook_test)


def flutter_engine_source() -> Path | None:
    candidates = []
    if os.environ.get('FLUTTER_ROOT'):
        candidates.append(Path(os.environ['FLUTTER_ROOT']))
    for name in ('flutter', 'flutter.bat'):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found).resolve().parents[1])
    for root in candidates:
        source = root / 'engine/src/flutter/shell/platform/darwin/ios/framework/Source'
        if source.is_dir():
            return source
    return None


class EngineSeamTests(unittest.TestCase):
    """Re-checked whenever the Flutter SDK carries the engine sources."""

    def setUp(self) -> None:
        self.source = flutter_engine_source()
        if self.source is None:
            self.skipTest('Flutter engine sources not available (FLUTTER_ROOT)')

    def test_seam_signature(self) -> None:
        swift = (self.source / 'DisplayLinkManager.swift').read_text(encoding='utf-8')
        self.assertIn('@objc(FlutterDisplayLinkManager)', swift)
        self.assertRegex(swift, r'@objc\s+public static var displayRefreshRate: Double')

    def test_engine_reads_the_seam_through_objc_dispatch_only(self) -> None:
        callers = {
            'vsync_waiter_ios.mm': 3,
            'FlutterMetalLayer.mm': 2,
            'FlutterViewController.mm': 1,
            'FlutterKeyboardInsetManager.mm': 1,
        }
        for name, minimum in callers.items():
            text = (self.source / name).read_text(encoding='utf-8')
            self.assertGreaterEqual(text.count('FlutterDisplayLinkManager.displayRefreshRate'), minimum, name)
        # A Swift caller would use static dispatch and bypass the hook.
        for path in self.source.glob('*.swift'):
            if path.name in {'DisplayLinkManager.swift'} or path.name.endswith('Test.swift'):
                continue
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('DisplayLinkManager.displayRefreshRate', text, path.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
