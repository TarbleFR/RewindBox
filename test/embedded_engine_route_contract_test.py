#!/usr/bin/env python3
"""Build 448: the built-in engine switches inside NeoStation's iOS router.

Every embedded route asks EmbeddedEnginePolicy before starting its engine;
a console switched off takes the RetroArch app when RetroArch can run it
(libretro consoles, PS2 games outside the ARMSX2 folder) and otherwise
returns a translated refusal, never another emulator. A refused external
handoff closes the session it registered, so the frontend media barrier
(previews, ambient music) is released at once. The behavior of each piece
is tested in Dart (test/console_manager_test.dart, test/libretro_consoles_tab_test.dart);
this file pins where the checks sit in the router.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise SystemExit('embedded engine route contract: ' + message)


def between(text, start, end):
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


router = read('lib/services/game/game_launch_service.dart')
POLICY = 'EmbeddedEnginePolicy.instance.allowsSystem(system)'

dolphin = between(router, '// DOLPHIN_ISOLATION_BEGIN: explicit_gc_wii_route',
                  '// DOLPHIN_ISOLATION_END: explicit_gc_wii_route')
require(dolphin.index(POLICY) < dolphin.index('DolphinInternalV2Service.launch('),
        'Dolphin asks the policy before starting')
require('return _embeddedEngineOff(context, system);' in dolphin, 'Dolphin off is an explicit refusal')
require('RetroArchLibraryService' not in dolphin and 'retroarch://' not in dolphin,
        'GameCube/Wii never fall through to RetroArch')

# KartPad (19 October 2026) then Dusklight and the Ports playlist
# (20 October 2026, docs/ports-removal-2026-10-20.md) left NeoStation: no
# route, refusal or session name of theirs is left in the router.
for retired in ("'ports'", 'ios_dusklight_internal', 'ios_kartpad_internal',
                'DusklightInternalService', 'KartPadInternalService',
                'isRemovedKartPadGamePath'):
    require(retired not in router, 'the router keeps no Ports route: ' + retired)

# The route itself, not the earlier dispatch-failure check of 7f88ee9b that
# tests the same folder name with '&& !result.success'. dart format may wrap
# the policy call (and add a trailing comma), so it is matched as a pattern.
switch = between(router, "if (Platform.isIOS && system.folderName.toLowerCase() == 'switch') {", 'final isArmsx2VirtualRom')
switch_policy = re.search(r'EmbeddedEnginePolicy\.instance\.allowsSystem\(\s*system\s*,?\s*\)', switch)
require(switch_policy is not None and switch_policy.start() < switch.index('MelonxInternalService.launch('),
        'Switch checks its embedded policy')
require('if (!allowed) return _embeddedEngineOff(context, system);' in switch, 'Switch off is an explicit refusal')
require('GameSessionManager.cancelGameLaunch();' in switch, 'failed Switch launch cancels its session')
require('MelonxInternalService.isRetiredLink' in switch, 'external-only rows require a file import')
require('launchUrl' not in switch and 'RetroArch' not in switch, 'Switch has no external fallback')
require('MelonxLibraryService' not in router, 'the external Switch route is absent')

ps3 = between(router, 'if (isPs3 &&', "'ios_rpcs3_internal'")
require(POLICY in ps3 and 'return _embeddedEngineOff(context, system);' in ps3,
        'RPCS3 asks the policy before registering its session')

libretro = between(router, '// LIBRETRO_INTERNAL_BEGIN: embedded_route', '// LIBRETRO_INTERNAL_END: embedded_route')
require(f'await {POLICY} &&\n              await LibretroInternalService.shouldLaunchEmbedded(system, game)' in libretro,
        'libretro asks the policy, then its per-game eligibility')
require(libretro.index(POLICY) < libretro.index('LibretroInternalService.launch('),
        'libretro asks the policy before starting')

generic = router[router.index("'ios_direct_launch'"):router.index("final configFileName = '${system.folderName}.json';")]
require('GameSessionManager.cancelGameLaunch();' in generic, 'a refused handoff cancels its session')
require(generic.count('return failExternal(') >= 5, 'every failure after the registration cancels it')
require('return GameLaunchResult.failure(' not in generic.replace('failExternal(GameLaunchResult.failure(', ''),
        'no failure escapes the cancellation')
ps2 = between(generic, "if (system.folderName.toLowerCase() == 'ps2') {", 'retroArchFailure()')
require(ps2.index('if (!embeddedAllowed) {') < ps2.index('Armsx2LibraryService.launchGameByRomPath'),
        'ARMSX2 asks the policy before starting')
require('return failExternal(_embeddedEngineOff(context, system));' in ps2,
        'an ARMSX2-owned game with ARMSX2 off is refused, never sent to RetroArch')
require('ConsoleManagerLocale.launchArmsx2Failed' in ps2, 'ARMSX2 failure translated, native detail kept')
require("'Could not launch this PS2 game in ARMSX2.'" not in router, 'no English user message')
require("'Could not launch this Nintendo Switch game in MeloNX.'" not in router, 'no English user message')
require('ConsoleManagerLocale.launchEngineOffRetroArch' in generic and 'retroArchStandsIn' in generic,
        'RetroArch standing in for an engine says why the game did not run in NeoStation')

session = read('lib/services/game/game_session_manager.dart')
cancel = between(session, 'static void cancelGameLaunch()', 'static void _startPlaytimeTimer()')
require("FrontendMediaGate.instance.release('gameSession');" in cancel, 'cancel releases the media barrier')
require('_savePlayTime' not in cancel, 'cancel records no playtime')

for path, console, launch in (
        ('lib/widgets/dolphin_internal_playlist_actions.dart', "policy.allows('wii')", 'launchWiiMenu'),
        ('lib/widgets/armsx2_internal_playlist_actions.dart', "policy.allows('ps2')", 'StikJitArmsx2Service.launchBios'),
):
    source = read(path)
    require(source.index(console) < source.index(launch), f'{path}: the side session asks the policy first')
    require('ConsoleManagerLocale.launchEngineOff' in source, f'{path}: refusal translated')

policy = read('lib/services/embedded_engine_policy.dart')
require("globalPreferenceKey =\n      'neostation_use_embedded_emulators_v1';" in policy, 'global switch key')
require("disabledPreferenceKey = 'console_engines_disabled_v1';" in policy, 'console switches key')
require('sqlite' not in policy.lower() and 'SystemRepository' not in policy, 'preferences only, no database')
print('embedded engine route contract: OK')
