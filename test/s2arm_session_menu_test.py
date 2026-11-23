#!/usr/bin/env python3
"""Switch 2 (S2Arm) settings and in-game menu: the contract between the Dart side and the native bridge.

    python3 -B test/s2arm_session_menu_test.py

Static checks on the sources (the native code is compiled by .github/workflows/s2arm-bridge-ios.yml; nothing here runs
on a device):
- The menu strings Dart sends at launch (lib/l10n/switch2_settings_locale.dart, `menu.*`) are exactly the keys of the
  native English fallback table, and every key the menu shows is in that table.
- The values and game languages offered are the same on both sides, and the native side stores them under the engine's
  own NSUserDefaults keys (S2Arm ios/settings.m at the pinned commit).
- The bridge answers getSettings / setSettings, prepares the launch (game language, engine overlay) before the dlopen,
  attaches the menu only after a successful start, and closes the game view before it reports the session end.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/s2arm_engine_bridge/ios/Classes'
MENU = (CLASSES / 'S2ArmSessionMenu.m').read_text()
SETTINGS = (CLASSES / 'S2ArmSettings.m').read_text()
PLUGIN = (CLASSES / 'S2ArmEngineBridgePlugin.m').read_text()
DART_LOCALE = ROOT / 'lib/l10n/switch2_settings_locale.dart'
LANGUAGES = ['AmericanEnglish', 'BritishEnglish', 'French', 'CanadianFrench', 'German', 'Italian', 'Spanish',
             'LatinAmericanSpanish', 'Dutch', 'Portuguese', 'BrazilianPortuguese', 'Russian', 'Polish', 'Japanese',
             'Korean', 'SimplifiedChinese', 'TraditionalChinese', 'Thai']


def block(text, start, end='\n}\n'):
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def english_keys():
    return set(re.findall(r'@"(menu\.[A-Za-z0-9]+)"\s*:', block(MENU, 'static NSDictionary<NSString *, NSString *> *EnglishStrings')))


class Strings(unittest.TestCase):
    def test_every_shown_key_has_an_english_fallback(self):
        shown = set(re.findall(r'@"(menu\.[A-Za-z0-9]+)"', MENU))
        self.assertTrue(english_keys(), 'the English table is found')
        self.assertLessEqual(shown, english_keys())

    def test_dart_sends_exactly_the_native_keys(self):
        if not DART_LOCALE.is_file():
            self.skipTest('lib/l10n/switch2_settings_locale.dart is not in this tree')
        dart = set(re.findall(r"'(menu\.[A-Za-z0-9]+)'", DART_LOCALE.read_text()))
        self.assertEqual(dart, english_keys())

    def test_dart_names_the_same_languages(self):
        if not DART_LOCALE.is_file():
            self.skipTest('lib/l10n/switch2_settings_locale.dart is not in this tree')
        text = DART_LOCALE.read_text()
        for name in LANGUAGES:
            self.assertIn(f"'{name}'", text, name)


class Settings(unittest.TestCase):
    def test_the_engine_keys(self):
        for key in ('S2AResolutionScale', 'S2AAntiAliasing', 'S2AScalingFilter', 'S2AFrameRateLimit', 'S2ADockedMode',
                    'S2AWidescreen', 'S2APerfHUD'):
            self.assertIn(f'@"{key}"', SETTINGS, key)

    def test_the_offered_values(self):
        values = block(SETTINGS, 'NSArray<NSString *> *S2ArmSettingsValues')
        for row in ('@[ @"0.5", @"0.75", @"1" ]', '@[ @"None", @"SmaaMedium", @"SmaaHigh" ]', '@[ @"Bilinear", @"Nearest" ]',
                    '@[ @"60", @"120", @"0" ]'):
            self.assertIn(row, values)
        languages = re.findall(r'@"([A-Za-z]+)"', block(SETTINGS, 'static NSArray<NSString *> *GameLanguages'))
        self.assertEqual(languages, ['auto'] + LANGUAGES)

    def test_the_launch_sets_the_language_and_the_engine_overlay(self):
        prepare = block(SETTINGS, 'void S2ArmSettingsPrepareLaunch(void)')
        self.assertIn('unsetenv("S2A_SYSTEM_LANGUAGE")', prepare)
        self.assertIn('setenv("S2A_SYSTEM_LANGUAGE", language.UTF8String, 1)', prepare)
        self.assertIn('setBool:YES forKey:kEngineBriefHud', prepare)

    def test_the_launch_decides_the_free_space_for_the_guest_memory_files(self):
        # IPA 778 (17 Nov): the engine's statfs gave 7901 MB under its 12288 MB while Settings showed about 50 GB, so the guest
        # memory stayed anonymous and the engine's storage page covered the game. The files held at most 5094 MB in 25
        # sessions. The bridge measures as iOS does for a task the user asked for (purgeable space counted, as the import).
        space = block(PLUGIN, 'static void S2ArmGuestFileSpace(void) {')
        self.assertLess(space.index('if (getenv("S2A_GUEST_FILE_MIN_FREE_MB")) {'), space.index('setenv('), 'a value already set is kept')
        self.assertIn('const unsigned long long needMB = 6144;', space)
        self.assertIn('statfs(tmp.fileSystemRepresentation, &fs) == 0', space)
        self.assertIn('NSURLVolumeAvailableCapacityForImportantUsageKey', space)
        self.assertIn('unsigned long long thresholdMB = statfsMB >= needMB || importantMB >= needMB ? 0 : needMB;', space)
        self.assertEqual(space.count('setenv("S2A_GUEST_FILE_MIN_FREE_MB",'), 1)
        self.assertIn('s2arm_journal("guestFileSpace", thresholdMB ? "short" : "enough",', space)
        self.assertNotIn('S2A_GUEST_FILE_MIN_FREE_MB', SETTINGS)
        # Only the first launch configures the engine: the call sits between the settings and the dlopen, not in the resume.
        launch = PLUGIN.index('- (NSDictionary *)runLaunchWithGid')
        call = PLUGIN.index('S2ArmGuestFileSpace();', launch)
        self.assertLess(PLUGIN.index('S2ArmSettingsPrepareLaunch();', launch), call)
        self.assertLess(call, PLUGIN.index('dlopen(enginePath', launch))
        self.assertEqual(PLUGIN.count('S2ArmGuestFileSpace();'), 1)

    def test_the_launch_selects_park_compatible_workgroup_default(self):
        # IPA 783: the active frame workgroup refused the park. Preserve explicit A/B values before dlopen.
        launch = PLUGIN.index('- (NSDictionary *)runLaunchWithGid')
        park = PLUGIN.index('setenv("S2A_RB_PARK_COMPAT", "1", 0);', launch)
        mode = PLUGIN.index('BOOL parkEnabled = parkCompat && strcmp(parkCompat, "1") == 0;', park)
        wg = PLUGIN.index('setenv("S2A_WORKGROUP", parkEnabled ? "0" : "1", 0);', mode)
        self.assertLess(PLUGIN.index('setenv("MTL_SHADER_CACHE_SIZE"', launch), park)
        self.assertLess(wg, PLUGIN.index('dlopen(enginePath', launch))
        self.assertEqual(PLUGIN.count('setenv("S2A_WORKGROUP"'), 1)


class Bridge(unittest.TestCase):
    def test_settings_methods(self):
        self.assertIn('isEqualToString:@"getSettings"', PLUGIN)
        self.assertIn('isEqualToString:@"setSettings"', PLUGIN)
        self.assertIn('S2ArmSettingsApply(', PLUGIN)

    def test_launch_order(self):
        # The first launch (runLaunchWithGid): settings after the engine's environment, before the dlopen.
        launch = PLUGIN.index('- (NSDictionary *)runLaunchWithGid')
        prepare = PLUGIN.index('S2ArmSettingsPrepareLaunch();', launch)
        self.assertLess(PLUGIN.index('setenv("MTL_SHADER_CACHE_SIZE"', launch), prepare)
        self.assertLess(prepare, PLUGIN.index('rb_s2arm_engine_mark_loading();', launch))
        self.assertLess(prepare, PLUGIN.index('dlopen(enginePath', launch))
        start = PLUGIN.index('startRc = start(error, sizeof error);', launch)
        menu = re.compile(r'\}\s*else\s*\{?\s*\[self attachSessionMenuTo:vc stop:stop\];')
        on_start = menu.search(PLUGIN, start)
        self.assertIsNotNone(on_start)
        attach = on_start.start()
        self.assertLess(start, attach, 'the menu is attached only after a successful start')
        # The resume of a parked game (patch 0010): settings changed meanwhile apply, the menu follows a successful resume.
        resume = PLUGIN.index('- (NSDictionary *)resumeParkedGame:')
        body = PLUGIN[resume:PLUGIN.index('static NSDictionary *launchFail(', resume)]
        self.assertLess(body.index('S2ArmSettingsPrepareLaunch();'), body.index('resumeRc = resume(error, sizeof error);'))
        self.assertLess(body.index('self.parkedGameId = nil;\n                           resumeRc ='), body.index('resumeRc = resume(error, sizeof error);'))
        on_resume = menu.search(body)
        self.assertIsNotNone(on_resume)
        self.assertLess(body.index('resumeRc = resume(error, sizeof error);'), on_resume.start())
        self.assertIn('dlsym(engine, S2A_RB_GUEST_STOP)', PLUGIN)

    def test_the_session_end_closes_the_game_view_first(self):
        for signature in (
            'static void s2arm_session_ended(int code, const char *reason, void *context) {',
            'static void s2arm_session_parked(const char *reason, void *context) {',
        ):
            ended = block(PLUGIN, signature)
            self.assertLess(ended.index('[self closeSessionViewWithCompletion:^{'), ended.index('self.runningGameId = nil;'))
            self.assertLess(ended.index('self.runningGameId = nil;'), ended.index('invokeMethod:@"sessionEnded"'))
        close = block(PLUGIN, '- (void)closeSessionViewWithCompletion:(dispatch_block_t)completion {')
        self.assertIn('[self.sessionMenu detach];', close)
        self.assertIn('dismissViewControllerAnimated:NO completion:completion', close)
        self.assertIn('completion();', close)


class Menu(unittest.TestCase):
    def test_opening_and_overlay(self):
        self.assertIn('pad.buttonOptions.isPressed && pad.buttonMenu.isPressed', MENU)
        self.assertIn('@"hud.brief"', MENU)
        self.assertIn('systemImageNamed:@"line.3.horizontal"', MENU)

    def test_quit_asks_first_and_stops_once(self):
        quit_ = block(MENU, '- (void)confirmQuit {')
        self.assertIn('UIAlertControllerStyleAlert', quit_)
        self.assertIn('menu.stopping = YES;', quit_)
        self.assertLess(quit_.index('menu.stopping = YES;'), quit_.index('menu.stop();'))

    def test_the_engine_menus_are_not_replaced(self):
        present = block(MENU, '- (BOOL)present:(UIViewController *)controller {')
        self.assertIn('if (host.presentedViewController != self.presented) return NO;', present)


class Saves(unittest.TestCase):
    """The game's save folder is Documents/S2Arm/Saves/<game>, given to the engine as S2A_SAVE_FOLDER before the dlopen."""

    def test_the_bridge_sets_the_save_folder_before_the_engine_loads(self):
        prepare = PLUGIN.index('S2ArmPrepareSaveFolder(self.saveFolder, docs);')
        self.assertLess(PLUGIN.index('S2ArmSettingsPrepareLaunch();'), prepare)
        self.assertLess(prepare, PLUGIN.index('dlopen(enginePath'))
        body = block(PLUGIN, 'static void S2ArmPrepareSaveFolder(NSString *folder, NSString *docs) {')
        self.assertIn('!S2ArmPathInside(folder, documents)', body, 'only a folder inside Documents')
        self.assertIn('setenv("S2A_SAVE_FOLDER", folder.fileSystemRepresentation, 1);', body)
        self.assertLess(body.index('copyItemAtPath'), body.index('setenv("S2A_SAVE_FOLDER"'))
        self.assertNotIn('removeItemAtPath', body, 'the old private save is never deleted')

    def test_open_folder_stays_in_documents(self):
        body = PLUGIN[PLUGIN.index('isEqualToString:@"openFolder"'):PLUGIN.index('isEqualToString:@"setSettings"')]
        self.assertIn('S2ArmPathInside(folder, documents)', body)
        self.assertIn('url.scheme = @"shareddocuments";', body)

    def test_dart_passes_the_folder_and_imports_inside_the_activity(self):
        service = (ROOT / 'lib/services/s2arm_internal_service.dart').read_text()
        self.assertIn("static Future<Directory> savesDirectory() => _child('Saves');", service)
        self.assertIn("if (saveFolder != null) 'saveFolder': saveFolder.path,", service)
        start = service.index('static Future<S2ArmSaveImportResult?> importSave(')
        self.assertIn('StorageImportActivity.run(() async {', service[start:start + 300])
        self.assertIn("Directory('${target.path} (backup)')", service, 'the previous save is kept')


if __name__ == '__main__':
    unittest.main(verbosity=2)
