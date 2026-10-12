#!/usr/bin/env python3
"""Scope guard of the external_display plugin (any OS).

The plugin owns the external window and nothing else: it imports no
emulation bridge, uses the deprecated UIScreen window APIs only inside the
isolated legacy fallback, registers a frozen plugin list on the menu's
second Flutter engine (never GeneratedPluginRegistrant), and every bridge
that adopts NeoExternalRenderHost declares the pod dependency. The two
plugins that pick a scene (NeoPlay overlay, 120 Hz screen) filter the
application role so the external scene never hosts them.

The TV menu engine never touches the database (review of 12 October 2026,
m11): the Dart import closure of its entrypoint is computed, the TV
engine's own files import and name nothing of the database layer, and the
shared files it reuses (SecondaryScreen and the services it uses) reach
that layer only through the pinned imports and members below, none of
which the TV engine calls.
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
# § 4), checked against the plugins the app pins (PINNED_PLUGIN_VERSIONS):
# the TV menu needs shared_preferences only (flutter_localization reads its
# stored language there); shared_preferences_foundation 2.5.6 is a Swift
# class without @objc name, so it resolves by its module-qualified name
# only. Retired entries (review of 12 October 2026, m3): SqflitePlugin
# (sqflite is not a dependency; the app uses sqlite3 through FFI and this
# engine never opens the database), FLTPathProviderPlugin / PathProviderPlugin
# / path_provider_foundation.PathProviderPlugin (path_provider_foundation
# 2.6.0 has no native class: FFI), FVPVideoPlayerPlugin (not the class of
# video_player_avfoundation 2.11.0, a Swift VideoPlayerPlugin; the TV menu
# has no video player: the relays send images only, docs § 8 bis) and the
# unqualified SharedPreferencesPlugin (never resolves for that Swift class).
EXPECTED_MENU_PLUGINS = [
    'shared_preferences_foundation.SharedPreferencesPlugin',
]
# The versions the registry above was checked against (pubspec.lock); a new
# version means the registry is checked again.
PINNED_PLUGIN_VERSIONS = {
    'shared_preferences_foundation': '2.5.6',
    'path_provider_foundation': '2.6.0',
    'video_player_avfoundation': '2.11.0',
    'flutter_localization': '0.4.1',
}
LIB = ROOT / 'lib'
TV_ENGINE = LIB / 'external_display'
TV_ENTRYPOINT = TV_ENGINE / 'external_display_entrypoint.dart'
DART_DIRECTIVE = re.compile(r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]""", re.M)
# The database layer: repositories, data sources, anything SQLite and the
# configuration service (it reads the database through the repositories).
DATABASE_LAYER = re.compile(r'(?:^|/)(?:repositories|data/datasources)/|sqlite|config_service')
DATABASE_PACKAGES = ('package:sqlite3', 'package:sqflite', 'package:drift', 'package:sqlcipher')
# Shared files of the TV menu that import a database-layer file (12 October
# 2026). They are outside the external display's files, so the imports stay
# (docs § 8 bis); a Dart import runs no code (static fields are initialised
# on first access), and the members below are the only database-layer ones
# they call, none reached by the TV engine:
# - ThemeProvider's instance methods (the TV engine never builds a
#   ThemeProvider; now_playing_helpers reads its static availableThemes, a
#   map of AppThemes, and app_themes looks a provider up that the TV engine
#   does not have);
# - RetroAchievementsRepository.getRAApiKey (flutter_secure_storage, not
#   SQLite) when an achievement is selected by a touch, impossible on the
#   non-interactive TV scene;
# - LoggerService.init (ConfigService.getLogFilePath), which only
#   main.dart calls.
PINNED_DATABASE_EDGES = {
    ('providers/theme_provider.dart', 'repositories/config_repository.dart'),
    ('providers/theme_provider.dart', 'services/config_service.dart'),
    ('screens/secondary_screen/secondary_screen.dart', 'repositories/retro_achievements_repository.dart'),
    ('services/logger_service.dart', 'services/config_service.dart'),
}
PINNED_DATABASE_CALLS = {
    'providers/theme_provider.dart': {'ConfigRepository.getThemeName', 'ConfigRepository.updateThemeName',
                                      'ConfigService.getUserDataPath'},
    'screens/secondary_screen/secondary_screen.dart': {'RetroAchievementsRepository.getRAApiKey'},
    'services/logger_service.dart': {'ConfigService.getLogFilePath'},
}
DATABASE_CALL = re.compile(r'\b(SqliteService|DatabaseService|ConfigService|\w*Repository)\s*\.\s*(\w+)')
DATABASE_NAMES = ('Repository', 'SqliteService', 'DatabaseService', 'ConfigService', 'sqlite', 'Sqlite', 'getUserConfig',
                  'openDatabase', 'user_config')
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
        lock = (ROOT / 'pubspec.lock').read_text(encoding='utf-8')
        for package, version in PINNED_PLUGIN_VERSIONS.items():
            match = re.search(rf'\n  {re.escape(package)}:\n(?:    .*\n)*?    version: "([^"]+)"', lock)
            self.assertIsNotNone(match, package)
            self.assertEqual(match.group(1), version, f'{package} {version}: check the frozen registry again')
        self.assertNotIn('\n  sqflite:', lock, 'sqflite is not a dependency')
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


def dart_code(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def dart_dependencies(path: Path) -> list[Path]:
    """The NeoStation files `path` imports, exports or includes as a part."""
    found = []
    for uri in DART_DIRECTIVE.findall(dart_code(path)):
        if uri.startswith('dart:'):
            continue
        if uri.startswith('package:neostation/'):
            found.append((LIB / uri[len('package:neostation/'):]).resolve())
        elif not uri.startswith('package:'):
            found.append((path.parent / uri).resolve())
    return found


def tv_engine_closure() -> tuple[set[Path], set[tuple[str, str]]]:
    """Every file the TV entrypoint reaches by imports without entering the
    database layer, and the edges from those files into it."""
    start = TV_ENTRYPOINT.resolve()
    seen = {start}
    pending = [start]
    edges = set()
    while pending:
        current = pending.pop()
        for dependency in dart_dependencies(current):
            relative = dependency.relative_to(LIB.resolve()).as_posix()
            if DATABASE_LAYER.search(relative):
                edges.add((current.relative_to(LIB.resolve()).as_posix(), relative))
                continue
            if dependency not in seen and dependency.is_file():
                seen.add(dependency)
                pending.append(dependency)
    return seen, edges


class TvEngineDatabaseIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.closure, self.edges = tv_engine_closure()
        self.relative = {path.relative_to(LIB.resolve()).as_posix(): path for path in self.closure}

    def test_the_closure_is_the_tv_menu(self) -> None:
        for expected in ('external_display/external_display_entrypoint.dart', 'external_display/external_menu_screen.dart',
                         'external_display/external_display_state_channel.dart', 'screens/secondary_screen/secondary_screen.dart'):
            self.assertIn(expected, self.relative, expected)
        for path in self.closure:
            self.assertIsNone(DATABASE_LAYER.search(path.relative_to(LIB.resolve()).as_posix()), path)

    def test_the_tv_engine_files_import_and_name_nothing_of_the_database(self) -> None:
        own = sorted(TV_ENGINE.glob('*.dart'))
        self.assertTrue(own)
        for path in own:
            for dependency in dart_dependencies(path):
                self.assertIsNone(DATABASE_LAYER.search(dependency.relative_to(LIB.resolve()).as_posix()), f'{path.name}: {dependency}')
            source = dart_code(path)
            for name in DATABASE_NAMES:
                self.assertNotIn(name, source, f'{path.name}: {name}')
        for importer, _ in self.edges:
            self.assertFalse(importer.startswith('external_display/'), importer)

    def test_no_new_import_reaches_the_database_layer(self) -> None:
        self.assertLessEqual(self.edges, PINNED_DATABASE_EDGES,
                             f'new import from the TV engine closure into the database layer: {sorted(self.edges - PINNED_DATABASE_EDGES)}')
        for path in self.closure:
            for uri in DART_DIRECTIVE.findall(dart_code(path)):
                self.assertFalse(uri.startswith(DATABASE_PACKAGES), f'{path}: {uri}')

    def test_only_the_pinned_database_members_are_named_and_none_is_reached(self) -> None:
        for relative, path in sorted(self.relative.items()):
            calls = {f'{owner}.{member}' for owner, member in DATABASE_CALL.findall(dart_code(path))}
            self.assertLessEqual(calls, PINNED_DATABASE_CALLS.get(relative, set()), relative)
            if relative != 'providers/theme_provider.dart':
                self.assertIsNone(re.search(r'\bThemeProvider\s*\(', dart_code(path)), f'{relative} builds a ThemeProvider')
            self.assertIsNone(re.search(r'LoggerService\.instance\s*\.\s*init\s*\(|\b_log\s*\.\s*init\s*\(', dart_code(path)),
                              f'{relative} initialises the file logger (ConfigService)')
            self.assertNotIn('getUserConfig', dart_code(path), relative)
        # The static map the TV menu reads is made of AppThemes only.
        provider = dart_code(LIB / 'providers/theme_provider.dart')
        themes = provider.split('static final Map<String, ThemeData> availableThemes = {', 1)[1].split('};', 1)[0]
        values = [value.strip() for value in re.findall(r":\s*([^,]+),", themes)]
        self.assertTrue(values)
        for value in values:
            self.assertTrue(value.startswith('AppThemes.'), value)
        helpers = dart_code(LIB / 'screens/secondary_screen/now_playing_helpers.dart')
        self.assertEqual(re.findall(r'\bThemeProvider\.(\w+)', helpers), ['availableThemes'])
        # The API key is read from the secure storage, on an achievement
        # selection only.
        repository = dart_code(LIB / 'repositories/retro_achievements_repository.dart')
        key = repository.split('static Future<String?> getRAApiKey() async {', 1)[1].split('}', 1)[0]
        self.assertEqual(key.strip(), 'return _storage.read(key: _raApiKeyStorageKey);')
        self.assertIn('FlutterSecureStorage', repository.split('static Future<String?> getRAApiKey()', 1)[0])
        screen = dart_code(LIB / 'screens/secondary_screen/secondary_screen.dart')
        self.assertEqual(screen.count('RetroAchievementsRepository.getRAApiKey()'), 1)
        loader = screen.split('Future<void> _loadAchievementComments(', 1)[1].split('\n  Future<void> ', 1)[0]
        self.assertIn('RetroAchievementsRepository.getRAApiKey()', loader)
        # The file logger is initialised by main.dart, never by the TV engine.
        logger = dart_code(LIB / 'services/logger_service.dart')
        init = logger.split('Future<void> init() async {', 1)[1]
        self.assertIn('ConfigService.getLogFilePath()', init)
        self.assertEqual(logger.count('ConfigService.'), 1)

    def test_the_entrypoint_gets_language_and_theme_from_its_arguments(self) -> None:
        entrypoint = dart_code(TV_ENTRYPOINT)
        self.assertIn('Future<void> externalDisplayMain(List<String> args) async {', entrypoint)
        self.assertIn('final menuArgs = ExternalDisplayMenuArgs.parse(args);', entrypoint)
        self.assertIn('await initializeExternalDisplayLocalization(menuArgs.languageCode);', entrypoint)
        self.assertIn('initialThemeName: menuArgs.themeName,', entrypoint)
        self.assertIn('localization.translate(language, save: false);', entrypoint)
        # runApp is reached whatever the localization does.
        main = entrypoint.split('Future<void> externalDisplayMain(List<String> args) async {', 1)[1].split('\n}\n', 1)[0]
        self.assertLess(main.index('await initializeExternalDisplayLocalization('), main.index('runApp('))
        initialize = entrypoint.split('Future<bool> initializeExternalDisplayLocalization(String languageCode) async {', 1)[1]
        self.assertLess(initialize.index('try {'), initialize.index('await localization.ensureInitialized();'))
        self.assertIn('} catch (error) {', initialize)


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
                      "'getState'", "'setEnabled'", "'setMode'", "'setMenuOnTV'", "'configureMenuEngine'", "'updateMenuEngine'",
                      "'pushMenuState'",
                      "'suspendForUnsupportedEngine'", "'resumeAfterUnsupportedEngine'",
                      'Stream<ExternalDisplayState> get events', 'on MissingPluginException'):
            self.assertIn(token, dart, token)
        for forbidden in ('dart:io', 'package:neostation', 'SharedPreferences', 'sqlite', 'internal_bridge'):
            self.assertNotIn(forbidden, dart, forbidden)


if __name__ == '__main__':
    unittest.main(verbosity=2)
