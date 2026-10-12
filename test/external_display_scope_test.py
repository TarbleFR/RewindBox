#!/usr/bin/env python3
"""Scope guard of the external_display plugin (any OS).

The plugin owns the external window and nothing else: it imports no
emulation bridge, uses the deprecated UIScreen window APIs only inside the
isolated legacy fallback, registers a frozen plugin list on the menu's
second Flutter engine (never GeneratedPluginRegistrant), and every bridge
that adopts NeoExternalRenderHost declares the pod dependency. The two
plugins that pick a scene (NeoPlay overlay, 120 Hz screen) filter the
application role so the external scene never hosts them.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/external_display'
CLASSES = PACKAGE / 'ios/Classes'
COORDINATOR = CLASSES / 'NeoExternalDisplayCoordinator.m'
MENU_ENGINE = CLASSES / 'NeoExternalDisplayMenuEngine.m'
EXPECTED_FILES = [
    'ExternalDisplayPlugin.h', 'ExternalDisplayPlugin.m',
    'NeoExternalDisplayCoordinator.h', 'NeoExternalDisplayCoordinator.m',
    'NeoExternalDisplayLabels.h', 'NeoExternalDisplayLayout.h',
    'NeoExternalDisplayMenuEngine.h', 'NeoExternalDisplayMenuEngine.m',
    'NeoExternalDisplayPreferences.h', 'NeoExternalDisplayPreferences.m',
    'NeoExternalDisplaySceneDelegate.h', 'NeoExternalDisplaySceneDelegate.m',
    'NeoExternalRenderHost.h',
]
# Frozen registry of the second engine (docs/external-display-universal.md
# § 4): the four plugins SecondaryScreen needs, each resolved by name and
# skipped when absent; Swift plugins also by their module-qualified name.
EXPECTED_MENU_PLUGINS = [
    'SqflitePlugin',
    'FLTPathProviderPlugin',
    'PathProviderPlugin',
    'path_provider_foundation.PathProviderPlugin',
    'FVPVideoPlayerPlugin',
    'SharedPreferencesPlugin',
    'shared_preferences_foundation.SharedPreferencesPlugin',
]
BRIDGE_TOKENS = ('Libretro', 'Dolphin', 'RPCS3', 'Rpcs3', 'ARMSX2', 'Armsx2', 'Dusklight', 'KartPad', 'Kartpad',
                 'NeoSwap', 'StikJIT', 'Stikjit', 'stikjit', 'NeoPlay', 'Neoplay')
BRIDGE_PLUGIN_CLASSES = ('LibretroInternalBridgePlugin', 'DolphinInternalBridgePlugin', 'Rpcs3InternalBridgePlugin',
                         'Armsx2InternalBridgePlugin', 'DusklightInternalBridgePlugin', 'KartpadInternalBridgePlugin',
                         'NeoSwapPlugin', 'StikjitBridgePlugin', 'UiRefreshRatePlugin', 'ExternalDisplayPlugin',
                         'NeoplayBridgePlugin', 'ExternalFolderAccessPlugin', 'GeneratedPluginRegistrant')
DEPRECATED_WINDOW_APIS = ('UIScreen.screens', 'UIScreen.mainScreen', 'window.screen =', 'setScreen:',
                          'sharedApplication.keyWindow', 'sharedApplication.windows', 'UIApplication.sharedApplication.delegate.window')
PREFERENCE_KEYS = {
    'NeoStation.ExternalDisplay.Enabled', 'NeoStation.ExternalDisplay.Mode', 'NeoStation.ExternalDisplay.MenuOnTV',
    'NeoStation.Dolphin.ExternalDisplay.Mode', 'NeoStation.ExternalDisplayChanged', 'NeoStation.ExternalDisplayStateChanged',
}


def code(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def without_strings(text: str) -> str:
    return re.sub(r'@?"(?:\\.|[^"\\])*"', '""', text)


def method_body(source: str, signature: str) -> str:
    start = source.index(signature)
    end = re.search(r'\n[-+@]', source[start + len(signature):])
    assert end is not None, signature
    return source[start:start + len(signature) + end.start()]


class PluginScopeTests(unittest.TestCase):
    def test_file_set_is_the_contract(self) -> None:
        self.assertEqual(sorted(p.name for p in CLASSES.iterdir()), EXPECTED_FILES)

    def test_no_bridge_is_imported_or_named(self) -> None:
        for name in EXPECTED_FILES:
            source = code(CLASSES / name)
            for line in re.findall(r'#(?:import|include)\s*(.+)', source):
                line = line.strip()
                self.assertTrue(
                    line.startswith(('<Flutter/', '<UIKit/', '<Foundation/', '<CoreGraphics/', '<MetalKit/', '<objc/', '<math.h>'))
                    or re.fullmatch(r'"(?:NeoExternal\w+|ExternalDisplayPlugin)\.h"', line),
                    f'{name}: unexpected import {line}')
            # The Build 442 preference key is the only Dolphin reference (read only).
            stripped = re.sub(r'\w*[Ll]egacyDolphinMode\w*', '', without_strings(source))
            for token in BRIDGE_TOKENS:
                self.assertNotIn(token, stripped, f'{name}: {token}')

    def test_deprecated_window_apis_only_in_the_legacy_method(self) -> None:
        coordinator = code(COORDINATOR)
        legacy = method_body(coordinator, '- (void)activateLegacyIfNeeded {')
        outside = coordinator.replace(legacy, '')
        for api in ('UIScreen.screens', 'UIScreen.mainScreen', 'window.screen ='):
            self.assertIn(api, legacy, api)
        for api in DEPRECATED_WINDOW_APIS:
            self.assertNotIn(api, outside, f'coordinator outside activateLegacyIfNeeded: {api}')
        for name in EXPECTED_FILES:
            if name == COORDINATOR.name:
                continue
            source = code(CLASSES / name)
            for api in DEPRECATED_WINDOW_APIS:
                self.assertNotIn(api, source, f'{name}: {api}')
        # The deprecation pragma is confined to the legacy method and to the
        # observation of the (deprecated) UIScreen notifications it relies on.
        pragma = '#pragma clang diagnostic ignored "-Wdeprecated-declarations"'
        observe = method_body(coordinator, '- (void)observeScreenNotifications {')
        self.assertEqual(coordinator.count(pragma), 2)
        self.assertIn(pragma, legacy)
        self.assertIn(pragma, observe)
        for name in EXPECTED_FILES:
            if name != COORDINATOR.name:
                self.assertNotIn(pragma, code(CLASSES / name), name)
        # The legacy window is only ever created after the 1.5 s timer.
        self.assertEqual(coordinator.count('[self activateLegacyIfNeeded]'), 1)
        self.assertIn('[self activateLegacyIfNeeded]', method_body(coordinator, '- (void)legacyTimerFired:(NSTimer *)timer {'))

    def test_menu_engine_registry_is_frozen(self) -> None:
        source = code(MENU_ENGINE)
        block = source.split('kNeoExternalMenuPlugins[] = {', 1)[1].split('};', 1)[0]
        self.assertEqual(re.findall(r'@"([^"]+)"', block), EXPECTED_MENU_PLUGINS)
        for forbidden in BRIDGE_PLUGIN_CLASSES:
            self.assertNotIn(forbidden, source, forbidden)
        registration = method_body(source, '- (void)registerPluginsOnEngine:(FlutterEngine *)engine {')
        self.assertIn('NSClassFromString(name)', registration)
        self.assertIn('respondsToSelector:@selector(registerWithRegistrar:)', registration)
        self.assertIn('registrarForPlugin:key', registration)
        self.assertIn('[registered containsObject:pluginClass]', registration, 'a class reached by two names registers once')
        for name in EXPECTED_FILES:
            self.assertNotIn('GeneratedPluginRegistrant', code(CLASSES / name), name)
        # One engine group, one entrypoint pair, created only after configureMenuEngine.
        self.assertEqual(source.count('FlutterEngineGroup alloc]'), 1)
        self.assertIn('if (!self.configured) return nil;', source)

    def test_preference_keys_are_the_contract_and_nothing_else(self) -> None:
        keys = set()
        for name in EXPECTED_FILES:
            keys.update(re.findall(r'@"(NeoStation\.[^"]+)"', (CLASSES / name).read_text(encoding='utf-8')))
        self.assertEqual(keys, PREFERENCE_KEYS)
        for name in EXPECTED_FILES:
            stripped = without_strings(code(CLASSES / name))
            for forbidden in ('JIT', 'escrow', 'ptrace', 'dlopen', 'NSFileManager'):
                self.assertNotIn(forbidden, stripped, f'{name}: {forbidden}')


class BridgeAdoptionTests(unittest.TestCase):
    def test_every_bridge_using_the_host_depends_on_the_pod(self) -> None:
        adopters = []
        for package in sorted(p for p in (ROOT / 'packages').iterdir() if p.is_dir() and p.name != 'external_display'):
            ios = package / 'ios'
            if not ios.is_dir():
                continue
            podspecs = list(ios.glob('*.podspec'))
            uses = []
            for path in ios.rglob('*'):
                if path.suffix in {'.m', '.mm', '.h', '.swift'} and path.is_file():
                    text = path.read_text(encoding='utf-8', errors='ignore')
                    if 'NeoExternalRenderHost' in text or 'NeoExternalDisplayCoordinator' in text or 'NeoExternalDisplayPreferences' in text:
                        uses.append(path.relative_to(ROOT))
            if not uses:
                continue
            adopters.append(package.name)
            self.assertEqual(len(podspecs), 1, package.name)
            self.assertIn("s.dependency 'external_display'", podspecs[0].read_text(encoding='utf-8'),
                          f'{package.name} adopts the external display host but its podspec does not depend on external_display: {uses}')
        # Informational: the adopters present in this tree.
        print('external_display adopters:', ', '.join(adopters) or 'none yet')

    def test_scene_pickers_filter_the_application_role(self) -> None:
        controller = (ROOT / 'packages/neoplay_bridge/ios/Classes/NPController.swift').read_text(encoding='utf-8')
        overlay = controller.split('private func showOverlay(label: String) {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('$0.activationState == .foregroundActive && $0.session.role == .windowApplication', overlay)
        plugin = code(ROOT / 'packages/ui_refresh_rate/ios/Classes/UiRefreshRatePlugin.m')
        screen = method_body(plugin, '- (UIScreen *)currentScreen {')
        loop = screen.split('for (UIScene *connected in UIApplication.sharedApplication.connectedScenes) {', 1)[1]
        self.assertIn('[connected.session.role isEqualToString:UIWindowSceneSessionRoleApplication]', loop)
        self.assertIn('[connected isKindOfClass:UIWindowScene.class] &&', loop)


class PackageWiringTests(unittest.TestCase):
    def test_workspace_member_and_dependency(self) -> None:
        pubspec = (ROOT / 'pubspec.yaml').read_text(encoding='utf-8')
        workspace = pubspec.split('workspace:', 1)[1].split('\n\n', 1)[0]
        self.assertIn('  - packages/external_display', workspace)
        self.assertIn('  external_display:\n    path: packages/external_display\n', pubspec)
        package = (PACKAGE / 'pubspec.yaml').read_text(encoding='utf-8')
        self.assertIn('resolution: workspace', package)
        self.assertIn('pluginClass: ExternalDisplayPlugin', package)

    def test_dynamic_objc_pod(self) -> None:
        podspec = (PACKAGE / 'ios/external_display.podspec').read_text(encoding='utf-8')
        self.assertNotIn('static_framework', podspec)
        self.assertNotIn('vendored', podspec)
        self.assertNotIn('swift', podspec.lower())
        self.assertIn("s.dependency 'Flutter'", podspec)
        self.assertIn("s.frameworks = 'UIKit', 'Foundation', 'QuartzCore', 'MetalKit'", podspec)

    def test_dart_side_is_a_thin_channel_wrapper(self) -> None:
        dart = (PACKAGE / 'lib/external_display.dart').read_text(encoding='utf-8')
        for token in ("MethodChannel(\n    'neostation/external_display',\n  )", "EventChannel(\n    'neostation/external_display/events',\n  )",
                      "enum ExternalDisplayMode", "automatic(0)", "fit(1)", "fill(2)", "original(3)",
                      'factory ExternalDisplayState.fromMap', 'factory ExternalDisplayState.unreachable',
                      "'getState'", "'setEnabled'", "'setMode'", "'setMenuOnTV'", "'configureMenuEngine'", "'pushMenuState'",
                      'Stream<ExternalDisplayState> get events', 'on MissingPluginException'):
            self.assertIn(token, dart, token)
        for forbidden in ('dart:io', 'package:neostation', 'SharedPreferences', 'sqlite', 'internal_bridge'):
            self.assertNotIn(forbidden, dart, forbidden)


if __name__ == '__main__':
    unittest.main(verbosity=2)
