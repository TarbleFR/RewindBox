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
- Settings profiles by game: stored by the native side (RewindBox's own preference, a copy in Documents/S2Arm, never the
  engine's S2AGame.<id> suite), made from the global values, given to the engine as the variables it reads before its
  NSUserDefaults keys (the global keys are never rewritten, a value already in the environment wins), and used by the
  in-game menu, which says when it shows the game's profile. With S2ARM_UPSTREAM (an S2Arm tree), the variable names and
  values are also read in its ios/settings.m.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/s2arm_engine_bridge/ios/Classes'
MENU = (CLASSES / 'S2ArmSessionMenu.m').read_text()
SETTINGS = (CLASSES / 'S2ArmSettings.m').read_text()
PLUGIN = (CLASSES / 'S2ArmEngineBridgePlugin.m').read_text()
MENU_HEADER = (CLASSES / 'S2ArmSessionMenu.h').read_text()
DART_LOCALE = ROOT / 'lib/l10n/switch2_settings_locale.dart'
# The engine variables a game's profile is given as, in the order of S2ArmSettings.m GameVariables, with the map key of each.
GAME_VARIABLES = {'S2A_RES_SCALE': 'resolutionScale', 'S2A_ANTI_ALIASING': 'antiAliasing', 'S2A_SCALING_FILTER': 'scalingFilter',
                  'S2A_FPS': 'frameRateLimit', 'S2A_DOCKED': 'docked', 'S2A_WIDESCREEN': 'widescreen'}
LANGUAGES = ['AmericanEnglish', 'BritishEnglish', 'French', 'CanadianFrench', 'German', 'Italian', 'Spanish',
             'LatinAmericanSpanish', 'Dutch', 'Portuguese', 'BrazilianPortuguese', 'Russian', 'Polish', 'Japanese',
             'Korean', 'SimplifiedChinese', 'TraditionalChinese', 'Thai']


def block(text, start, end='\n}\n'):
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def code_only(text):
    """The source without its // comments (string literals kept: no // inside the ones these tests read)."""
    return re.sub(r'//[^\n]*', '', text)


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
        prepare = block(SETTINGS, 'void S2ArmSettingsPrepareLaunch(NSString *gid)')
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
        self.assertLess(PLUGIN.index('S2ArmSettingsPrepareLaunch(gid);', launch), call)
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
        prepare = PLUGIN.index('S2ArmSettingsPrepareLaunch(gid);', launch)
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
        self.assertLess(body.index('S2ArmSettingsPrepareLaunch(gid);'), body.index('resumeRc = resume(error, sizeof error);'))
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


class GameProfiles(unittest.TestCase):
    """Settings profiles by game (S2ArmSettings.h): a game without one keeps the global settings; one is made from the global
    values of the moment and then changed for that game alone; the launch gives it to the engine without rewriting the global
    keys; the in-game menu reads and changes it, and says so."""

    def test_stored_natively_with_a_documents_copy_never_in_the_engine_suite(self):
        self.assertIn('static NSString *const kGameProfiles = @"RewindBoxS2ArmGameSettings";', SETTINGS)
        self.assertIn('static NSString *const kGameProfilesCopy = @"rewindbox-game-settings.json";', SETTINGS)
        path = block(SETTINGS, 'static NSString *ProfilesCopyPath(void) {')
        self.assertIn('NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES)', path)
        self.assertIn('stringByAppendingPathComponent:@"S2Arm"]', path)
        store = block(SETTINGS, 'static void StoreProfiles(')
        self.assertLess(store.index('setObject:profiles forKey:kGameProfiles'), store.index('writeToFile:path options:NSDataWritingAtomic'),
                        'the preference first, then its copy, written atomically')
        # An update that started with empty preferences (build 586): the copy is read back once and becomes the preference.
        restore = block(SETTINGS, 'static NSDictionary<NSString *, NSDictionary *> *StoredProfiles(void) {')
        self.assertIn('if (!stored && !restoreTried) {', restore)
        self.assertLess(restore.index('ReadProfilesCopy()'), restore.index('[defaults setObject:stored forKey:kGameProfiles];'))
        self.assertIn('KeepProfilesCopy();', block(SETTINGS, 'void S2ArmSettingsPrepareLaunch(NSString *gid)'))
        # The last profile removed leaves an empty map, so a missing preference still means one an update lost.
        self.assertNotIn('removeObjectForKey:kGameProfiles', SETTINGS)
        for name, text in (('S2ArmSettings.m', SETTINGS), ('S2ArmSessionMenu.m', MENU), ('S2ArmEngineBridgePlugin.m', PLUGIN)):
            self.assertNotIn('S2AGame.', code_only(text), f'{name} never touches the engine per-game suite')
            self.assertNotIn('initWithSuiteName', text, name)
            self.assertNotIn('S2AFps60', code_only(text), name)
            self.assertNotIn('S2AWidenForce', code_only(text), name)
            self.assertNotIn('S2A_LAUNCH_GAME_ID', code_only(text), name)

    def test_the_key_is_the_launch_title_id(self):
        key = block(SETTINGS, 'NSString *S2ArmSettingsGameKey(NSString *gid) {')
        self.assertIn('gid.length != 16', key)
        self.assertIn('@"0123456789ABCDEFabcdef"', key)
        self.assertIn('gid.uppercaseString', key)
        # The launch and the resume pass the gid they were given (S2ArmGamePreparation: %016llX of the program id).
        self.assertIn('@"gid" : [NSString stringWithFormat:@"%016llX", (unsigned long long)programId],',
                      (CLASSES / 'S2ArmGamePreparation.m').read_text())

    def test_a_profile_is_made_from_the_global_values_and_holds_every_setting(self):
        snapshot = re.findall(r'^    @"(\w+)" : ', block(SETTINGS, 'NSDictionary<NSString *, id> *S2ArmSettingsSnapshot(void) {'), re.M)
        self.assertEqual(len(snapshot), 9)
        valid = block(SETTINGS, 'static NSDictionary<NSString *, id> *ValidProfile(id stored) {')
        lists = re.findall(r'for \(NSString \*name in @\[ ([^\]]*) \]\)', valid)
        self.assertEqual(len(lists), 2)
        choices, flags = (re.findall(r'@"(\w+)"', text) for text in lists)
        self.assertEqual(set(choices) | set(flags), set(snapshot), 'a profile holds the nine settings of the map')
        self.assertIn('[S2ArmSettingsValues(name) containsObject:value]', valid, 'a profile only keeps the values offered (never 30)')
        self.assertIn('[value boolValue] ? @YES : @NO', valid)
        create = block(SETTINGS, 'NSDictionary<NSString *, id> *S2ArmSettingsGameCreateProfile(NSString *gid) {')
        self.assertLess(create.index('if (!profiles[key]) {'), create.index('profiles[key] = ValidProfile(S2ArmSettingsSnapshot());'),
                        'made from the global values of the moment, an existing profile kept')
        effective = block(SETTINGS, 'NSDictionary<NSString *, id> *S2ArmSettingsForGame(NSString *gid) {')
        self.assertIn('if (!profile) return global;', effective, 'a game without a profile keeps the global settings')
        self.assertIn('[settings addEntriesFromDictionary:profile];', effective)

    def test_a_profile_changes_alone_and_the_global_keys_never_for_it(self):
        apply = block(SETTINGS, 'NSDictionary<NSString *, id> *S2ArmSettingsGameApply(NSString *gid, NSDictionary *changes) {')
        self.assertIn('return found ? S2ArmSettingsForGame(key) : nil;', apply, 'nothing without a profile')
        self.assertNotIn('S2ArmSettingsApply(', apply)
        self.assertNotIn('NSUserDefaults', apply)
        self.assertIn('return S2ArmSettingsGameApply(gid, changes) ?: S2ArmSettingsApply(changes);',
                      block(SETTINGS, 'NSDictionary<NSString *, id> *S2ArmSettingsApplyForGame('))
        remove = block(SETTINGS, 'NSDictionary<NSString *, id> *S2ArmSettingsGameRemoveProfile(NSString *gid) {')
        self.assertIn('[profiles removeObjectForKey:key];', remove)
        self.assertIn('return S2ArmSettingsSnapshot();', remove)
        # The global keys are only ever written by S2ArmSettingsApply (and the existing launch cleanups), never by a profile.
        for name in ('kResolution', 'kAntiAliasing', 'kScalingFilter', 'kFrameRateLimit', 'kDocked', 'kWidescreen',
                     'kPerformanceOverlay', 'kGameLanguage', 'kFrameInterpolation'):
            writes = re.findall(r'(?:StoreChoice|StoreFlag)\(defaults, changes, @"\w+", %s\)' % name, SETTINGS)
            self.assertEqual(len(writes), 1, name)
            self.assertNotRegex(SETTINGS, r'set(?:Object|Bool):[^;]*forKey:%s\b' % name)

    def test_the_launch_gives_the_profile_as_the_engine_variables(self):
        names = re.findall(r'@"(S2A_\w+)"', block(SETTINGS, 'static NSArray<NSString *> *GameVariables(void) {'))
        self.assertEqual(names, list(GAME_VARIABLES))
        environment = block(SETTINGS, 'static NSDictionary<NSString *, NSString *> *GameEnvironment(NSDictionary *settings) {')
        for variable, key in GAME_VARIABLES.items():
            if key in ('docked', 'widescreen'):
                self.assertIn(f'NSString *{key} = [settings[@"{key}"] boolValue] ? @"1" : @"0";', environment)
                self.assertIn(f'@"{variable}" : {key},', environment)
            else:
                self.assertIn(f'@"{variable}" : settings[@"{key}"] ?: @"', environment)
        export = block(SETTINGS, 'static void ExportGameProfile(NSString *_Nullable gid) {')
        self.assertIn('NSDictionary<NSString *, NSString *> *wanted = profile ? GameEnvironment(S2ArmSettingsForGame(gid)) : @{};', export)
        self.assertIn('s2arm_game_env_decide(getenv(variable), gGameEnvironment[name].UTF8String, value.UTF8String)', export)
        # setenv without overwrite, except this bridge's own value of an earlier start of the process (a resume).
        self.assertIn('setenv(variable, value.UTF8String, action == S2ARM_GAME_ENV_REPLACE)', export)
        self.assertEqual(len(re.findall(r'\bsetenv\(', export)), 1, 'one setenv (unsetenv apart)')
        self.assertLess(export.index('} else if (action == S2ARM_GAME_ENV_UNSET) {'), export.index('unsetenv(variable);'))
        self.assertNotIn('NSUserDefaults', export, 'the global keys are never rewritten for a profile')
        for call in re.findall(r's2arm_journal\([^;]*\);', export, re.S):
            self.assertNotIn('value.UTF8String', call, 'the journal names the variables, never their values')
            self.assertNotIn('wanted', call)
        prepare = block(SETTINGS, 'void S2ArmSettingsPrepareLaunch(NSString *gid)')
        body = prepare[len('void S2ArmSettingsPrepareLaunch(NSString *gid) {'):].strip()
        self.assertTrue(body.endswith('ExportGameProfile(gid);'), 'the profile is exported last, after the language and the overlay')
        self.assertIn('NSString *language = S2ArmSettingsForGame(gid)[@"gameLanguage"];', prepare)
        # The C decision (test/s2arm_engine_bridge_test.py runs it): an unset variable is set, this bridge's own value replaced or
        # removed, anything else kept.
        decide = (CLASSES / 'S2ArmGameEnvironment.c').read_text()
        self.assertIn('int ours = current && mine && strcmp(current, mine) == 0;', decide)
        # Frame generation (read once a process) comes from the same profile.
        self.assertIn('int frameInterpolationProfile = setenv("S2A_RB_FI", S2ArmSettingsFrameInterpolation(gid) ? "1" : "0", 0);', PLUGIN)
        self.assertIn('return [S2ArmSettingsForGame(gid)[@"frameInterpolation"] boolValue];', SETTINGS)
        self.assertIn('@"settings":S2ArmSettingsForGame(gid)}', PLUGIN, 'the benchmark names the settings the game starts with')

    def test_the_engine_reads_these_variables_first(self):
        tree = os.environ.get('S2ARM_UPSTREAM', '')
        source = Path(tree) / 'ios/settings.m' if tree else None
        if not source or not source.is_file():
            self.skipTest('S2ARM_UPSTREAM (an S2Arm tree with ios/settings.m) is not set')
        engine = source.read_text()
        apply = block(engine, 'void s2a_ios_apply_graphics_settings(NSUserDefaults *defaults) {')
        rows = dict((env, re.findall(r'@"([^"]*)"', values)) for env, values in
                    re.findall(r'\{@"\w+", "(S2A_\w+)", @"[^"]*", @\[([^\]]*)\]\}', apply))
        for variable, key in GAME_VARIABLES.items():
            if key in ('docked', 'widescreen'):
                self.assertIn(f'getenv("{variable}")', apply, variable)
                continue
            self.assertIn(variable, rows, f'{variable} is one of the engine options read before their keys')
            mine = re.findall(r'@"([^"]*)"', block(SETTINGS, 'NSArray<NSString *> *S2ArmSettingsValues(NSString *key) {').split(
                f'isEqualToString:@"{key}"]) return', 1)[1].split(';', 1)[0])
            self.assertLessEqual(set(mine), set(rows[variable]), f'{variable}: every value offered is one the engine takes')
        explicit = apply[apply.index('for (size_t i = 0;'):]
        self.assertLess(explicit.index('const char *explicit = getenv(options[i].env);'), explicit.index('continue;'),
                        'a variable already set is used as it is (the key is not read, nor rewritten)')
        self.assertIn('if (setenv(name, value.UTF8String, 0) != 0)', engine, 'the engine itself never overwrites a set variable')
        self.assertIn('if (!getenv("S2A_WIDESCREEN") && [defaults objectForKey:@"S2AWidescreen"]', apply)
        self.assertIn('initWithSuiteName:[@"S2AGame." stringByAppendingString:@(gid)]', apply,
                      'the engine reads its own per-game suite, which this bridge never writes')

    def test_the_in_game_menu_uses_the_running_games_profile(self):
        self.assertIn('@property(nonatomic, copy, nullable) NSString *gameId;', MENU_HEADER)
        attach = block(PLUGIN, '- (void)attachSessionMenuTo:(UIViewController *)vc stop:(s2a_rb_guest_stop_fn)stop {')
        self.assertLess(attach.index('self.sessionMenu.gameId = self.runningGameId;'), attach.index('[self.sessionMenu attach];'))
        code = code_only(MENU)
        self.assertNotIn('S2ArmSettingsSnapshot(', code, 'the menu reads the game\'s settings, never the global map directly')
        self.assertNotIn('S2ArmSettingsApply(', code, 'the menu writes the game\'s profile when it has one')
        settings = block(MENU, '- (void)showSettings {')
        self.assertIn('BOOL profile = S2ArmSettingsGameHasProfile(gid);', settings)
        self.assertIn('NSDictionary *settings = S2ArmSettingsForGame(gid);', settings)
        self.assertIn('[self text:profile ? @"menu.gameSettings" : @"menu.settings"]', settings, 'the title says it is the game\'s')
        self.assertIn('[self text:profile ? @"menu.gameScope" : @"menu.globalScope"]', settings)
        create = settings[settings.index('if (!profile && S2ArmSettingsGameKey(gid)) {'):]
        self.assertLess(create.index('[self text:@"menu.gameCreate"]'), create.index('(void)S2ArmSettingsGameCreateProfile(gid);'))
        self.assertLess(create.index('(void)S2ArmSettingsGameCreateProfile(gid);'), create.index('[weakSelf showSettings];'))
        choices = block(MENU, '- (void)showChoices:(NSString *)setting {')
        self.assertIn('id current = S2ArmSettingsForGame(gid)[setting];', choices)
        self.assertIn('if (profile) note = [NSString stringWithFormat:@"%@\\n%@", [self text:@"menu.gameSettings"], note];', choices)
        # Stored in the game's profile (else globally), then applied at once where the engine can take it, as before.
        stored = choices.index('S2ArmSettingsApplyForGame(gid, @{setting : value});')
        self.assertLess(stored, choices.index('if (menu.applyNow) (void)menu.applyNow(setting, value);'))
        self.assertIn('BOOL hidden = !S2ArmSettingsPerformanceOverlay(self.gameId);', block(MENU, '- (void)applyOverlay {'))
        menu = block(MENU, '- (void)showMenu {')
        self.assertIn('BOOL overlayOn = S2ArmSettingsPerformanceOverlay(gid);', menu)
        self.assertIn('S2ArmSettingsSetPerformanceOverlay(gid, !overlayOn);', menu)
        self.assertIn('settings[@"performanceOverlay"] = @(S2ArmSettingsPerformanceOverlay(menu.gameId));', MENU)
        for key in ('menu.gameSettings', 'menu.gameScope', 'menu.globalScope', 'menu.gameCreate'):
            self.assertIn(key, english_keys())

    def test_the_channel_and_the_dart_service(self):
        start = PLUGIN.index('if ([call.method isEqualToString:@"getGameSettings"] || [call.method isEqualToString:@"createGameSettings"] ||')
        channel = PLUGIN[start:PLUGIN.index('result(FlutterMethodNotImplemented);', start)]
        self.assertIn('[call.method isEqualToString:@"setGameSettings"] || [call.method isEqualToString:@"removeGameSettings"]', channel)
        self.assertLess(channel.index('NSString *gid = S2ArmSettingsGameKey('), channel.index('result(nil);'))
        self.assertIn('(void)S2ArmSettingsGameCreateProfile(gid);', channel)
        self.assertIn('(void)S2ArmSettingsGameApply(gid, ', channel)
        self.assertIn('(void)S2ArmSettingsGameRemoveProfile(gid);', channel)
        self.assertNotIn('S2ArmSettingsApply(', channel, 'a game call never changes the global settings')
        self.assertIn('BOOL custom = S2ArmSettingsGameHasProfile(gid);', channel)
        self.assertIn('result(@{@"gid" : gid, @"custom" : @(custom), @"settings" : S2ArmSettingsForGame(gid)});', channel)
        service = (ROOT / 'lib/services/s2arm_internal_service.dart').read_text()
        for method in ('getGameSettings', 'createGameSettings', 'setGameSettings', 'removeGameSettings'):
            self.assertIn(f"_gameSettings('{method}', gameId", service)
        self.assertIn("'gid': gameId.toUpperCase(),", service)
        self.assertIn("if (settings != null) 'settings': settings.toMap(),", service)
        self.assertIn('return gid.toUpperCase();', service)


class Saves(unittest.TestCase):
    """The game's save folder is Documents/S2Arm/Saves/<game>, given to the engine as S2A_SAVE_FOLDER before the dlopen."""

    def test_the_bridge_sets_the_save_folder_before_the_engine_loads(self):
        prepare = PLUGIN.index('S2ArmPrepareSaveFolder(self.saveFolder, docs);')
        self.assertLess(PLUGIN.index('S2ArmSettingsPrepareLaunch(gid);'), prepare)
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
