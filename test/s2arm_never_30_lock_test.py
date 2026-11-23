#!/usr/bin/env python3
"""Mario Kart World never settles at 30 fps, and 30 is never offered as a frame-rate limit (lot 827, engine patch 0319).

    python3 -B test/s2arm_never_30_lock_test.py

IPA 825 on an iPhone 16 Pro Max (A18 Pro), frame-rate setting "no limit" in all four sessions: the game held present
interval 2 for a second after resolution pushes and one-frame spikes, the engine then held its reports at 33.2 ms and the
system ran the GPU slower at that pace, so the race stayed at 27 to 35 fps (17 to 22 during a screen recording) until a
relaunch. These static checks fail if any layer brings the 30 option or the lock back:
- engine: patch 0319 is in the series, its guard runs in the report hold, and no later patch takes it out or adds 30 back;
- bridge: the Mario Kart World profile turns the guard on, 30 is neither offered, nor shown, nor applied live, and a
  stored 30 is removed before the engine reads it;
- Flutter: the settings model, the settings panel and the 12 locales have no 30.
The engine code itself is tested by graphics/nvn/tests/t_rb_adaptive_drs.c (engine CI, [s2arm-thermal-checks]) and
runtime/tests/t_ios_settings.m.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/engine/patches'
CLASSES = ROOT / 'packages/s2arm_engine_bridge/ios/Classes'
GUARD = '0319-never-lock-an-alternating-game-at-30-and-drop-the-30-limit.patch'


def number(path: Path) -> int:
    return int(path.name[:4])


def added(patch: str) -> str:
    return '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))


def removed(patch: str) -> str:
    return '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('-') and not line.startswith('---'))


def block(text: str, start: str, end: str = '\n}\n') -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


class EnginePatch(unittest.TestCase):
    patch = (PATCHES / GUARD).read_text()

    def test_the_guard_patch_is_in_the_series(self):
        self.assertTrue((PATCHES / GUARD).is_file())
        self.assertEqual([p.name for p in PATCHES.glob('0319-*.patch')], [GUARD])

    def test_the_guard_runs_in_the_report_hold(self):
        new = added(self.patch)
        for piece in ('static inline int rb_drs_escape_step(', 'static inline int rb_drs_spike_pass(',
                      'static inline unsigned rb_drs_guard_level(', 'static inline uint64_t rb_drs_cap_ticks(',
                      'getenv("S2A_RB_DRS_NO_LOCK")', 'if (rb_drs_escape_now(f)) return top + rb_drs_cap_ticks(t - top, hold60);',
                      'if (guard) level = rb_drs_guard_level(1, serious, level);',
                      'if (t - top >= want) return rb_drs_past(f, t, top, want, guard && fps == 60);',
                      'int nvn_rb_game_interval(void) { return atomic_load(&g_game_itv); }'):
            self.assertIn(piece, new, piece)

    def test_the_guard_is_unit_tested(self):
        new = added(self.patch)
        self.assertIn('PASS guest DRS no-lock guard', new)
        self.assertIn('rb_drs_escape_step(&es,', new)

    def test_the_engine_settings_drop_30(self):
        new, old = added(self.patch), removed(self.patch)
        self.assertIn('@"values": @[@"30", @"60", @"120", @"0"]', old)
        self.assertIn('@"values": @[@"60", @"120", @"0"]', new)
        self.assertIn('{@"S2AFrameRateLimit", "S2A_FPS", @"0", @[@"60", @"120", @"0"]}', new)
        self.assertIn('<array><string>60</string><string>120</string><string>0</string></array>', new)
        self.assertIn('保存过的 30 按不限帧处理并清除', new)

    def test_the_pinned_engine_carries_the_guard(self):
        import hashlib, json
        pin = json.loads((ROOT / 'build-utils/s2arm/engine-pin.json').read_text())
        patches = {p['name']: p['sha256'] for p in pin['identity']['sourceIdentity']['patches']}
        self.assertEqual(patches.get(GUARD), hashlib.sha256((PATCHES / GUARD).read_bytes()).hexdigest(),
                         'the delivered engine is built with this exact patch 0319')

    def test_no_later_patch_undoes_it(self):
        later = sorted(p for p in PATCHES.glob('*.patch') if number(p) > 319)
        for path in later:
            text = path.read_text()
            gone = removed(text)
            for name in ('rb_drs_escape_now', 'rb_drs_escape_step', 'rb_drs_spike_pass', 'rb_drs_guard_level',
                         'S2A_RB_DRS_NO_LOCK', 'nvn_rb_game_interval'):
                self.assertNotIn(name, gone, f'{path.name} removes {name}')
            self.assertNotRegex(added(text), r'@\[@"30", @"60"', f'{path.name} offers 30 again')


class Bridge(unittest.TestCase):
    settings = (CLASSES / 'S2ArmSettings.m').read_text()
    menu = (CLASSES / 'S2ArmSessionMenu.m').read_text()
    plugin = (CLASSES / 'S2ArmEngineBridgePlugin.m').read_text()

    def test_mario_kart_world_turns_the_guard_on(self):
        self.assertIn('int noLockProfile = setenv("S2A_RB_DRS_NO_LOCK", kartRender, 0);', self.plugin)
        self.assertIn('const char *kartRender = marioKartWorld ? "1" : "0";', self.plugin)
        self.assertIn('displayTicksProfile || noLockProfile ||', self.plugin)

    def test_30_is_not_offered(self):
        values = block(self.settings, 'NSArray<NSString *> *S2ArmSettingsValues')
        self.assertIn('if ([key isEqualToString:@"frameRateLimit"]) return @[ @"60", @"120", @"0" ];', values)
        self.assertNotRegex(values, r'frameRateLimit[^\n]*@"30"')
        self.assertIn('@"frameRateLimit" : StoredChoice(defaults, kFrameRateLimit, @"0", S2ArmSettingsValues(@"frameRateLimit"))',
                      self.settings)

    def test_a_stored_30_is_removed_before_the_engine_reads_it(self):
        forget = block(self.settings, 'static void S2ArmSettingsForgetRetiredLimit(void)')
        self.assertIn('[S2ArmSettingsValues(@"frameRateLimit") containsObject:stored]', forget)
        self.assertIn('[defaults removeObjectForKey:kFrameRateLimit]', forget)
        prepare = block(self.settings, 'void S2ArmSettingsPrepareLaunch(void)')
        body = prepare[len('void S2ArmSettingsPrepareLaunch(void) {'):].lstrip()
        self.assertTrue(body.startswith('S2ArmSettingsForgetRetiredLimit();'), 'the first thing the launch does')

    def test_the_menu_has_no_30(self):
        self.assertNotIn('menu.fps30', self.menu)
        self.assertIn('@"frameRateLimit" : @{@"60" : @"menu.fps60", @"120" : @"menu.fps120", @"0" : @"menu.fpsUnlimited"}', self.menu)

    def test_a_live_change_applies_only_an_offered_limit(self):
        live = block(self.plugin, '- (BOOL)applyLiveSetting:(NSString *)setting value:(id)value {')
        check = 'if (![S2ArmSettingsValues(@"frameRateLimit") containsObject:value]) return NO;'
        self.assertIn(check, live)
        self.assertLess(live.index(check), live.index('int rc = set(fps);'))


class Flutter(unittest.TestCase):
    def test_the_model_has_no_30(self):
        model = (ROOT / 'lib/services/s2arm_settings.dart').read_text()
        self.assertIn("static const List<String> frameRateLimits = <String>['60', '120', '0'];", model)
        self.assertIn("this.frameRateLimit = '0',", model)

    def test_the_panel_has_no_30(self):
        panel = (ROOT / 'lib/widgets/switch2_engine_settings_panel.dart').read_text()
        fps = block(panel, 'static const Map<String, String> _fpsKeys', '};')
        self.assertNotIn("'30'", fps)
        self.assertEqual(re.findall(r"'(\d+)': 'fps", fps), ['60', '120', '0'])

    def test_no_locale_names_30(self):
        locale = (ROOT / 'lib/l10n/switch2_settings_locale.dart').read_text()
        self.assertNotIn('fps30', locale)


if __name__ == '__main__':
    unittest.main()
