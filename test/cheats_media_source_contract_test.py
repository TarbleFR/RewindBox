from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
for pkg, cls in [('dolphin_internal_bridge','DOLManualCheatEditor'),('armsx2_internal_bridge','ARMSX2ManualCheatEditor')]:
    for name in ('NeoCheatParser.h','NeoCheatDocument.h','NeoCheatStore.h','NeoCheatLabels.h'):
        assert (root/'native/cheats'/name).read_bytes()==(root/'packages'/pkg/'ios/Classes'/name).read_bytes(),name
    expected=(root/'native/cheats/NeoManualCheatEditor.template.h').read_text().replace('NEO_EDITOR_CLASS',cls)
    assert expected==(root/'packages'/pkg/'ios/Classes'/f'{cls}.h').read_text()
labels=(root/'native/cheats/NeoCheatLabels.h').read_text()
for locale in ('en','fr','de','es','it','pt','ru','id','ja','ko','zh','zh_Hant'):
    assert '@"'+locale+'": @{' in labels,locale
manager=(root/'lib/services/game_launch_manager.dart').read_text()
original=subprocess.check_output(['git','show','d3e558fad05feeb0838b4d3d80fc854546eaf0a4:lib/services/game_launch_manager.dart'],cwd=root,text=True)
# The embedded libretro engine (requested 9 Oct 2026) adds one in-process
# executable; it is polled through EmbeddedIOSSessionStatus like RPCS3.
# KartPad left NeoStation on 19 October 2026 (maintainer decision): its
# session monitor, executable and audio restore are the only other removals.
KARTPAD_SESSION = """    if (Platform.isIOS && emulatorExe == 'ios_kartpad_internal') {
      _embeddedSessionSubscription = KartPadInternalBridge.sessionEvents.listen(
        (event) {
          final exitReason = event['exitReason']?.toString() ?? 'unknown';
          _log.i(
            '[GameLaunchManager] KartPad host result=$exitReason '
            'message=${event['reason'] ?? 'unknown'} '
            '(success=${event['success']}, runtimeReleased=${event['runtimeReleased']})',
          );
          if (_phase != GameLaunchPhase.playing || _isClosing) return;

          if (exitReason == 'userReturn' ||
              exitReason == 'languageRestart' ||
              exitReason == 'normalTermination' ||
              exitReason == 'runtimeFailure' ||
              exitReason == 'crash' ||
              exitReason == 'launchFailure') {
            _triggerClose();
          }
        },
      );
      if (KartPadInternalBridge.didEndSession && !_isClosing) {
        _triggerClose();
      }
      return;
    }

"""
KARTPAD_REMOVAL = [
    ("import 'package:dusklight_internal_bridge/dusklight_internal_bridge.dart';\n",
     "import 'package:dusklight_internal_bridge/dusklight_internal_bridge.dart';\n"
     "import 'package:kartpad_internal_bridge/kartpad_internal_bridge.dart';\n"),
    ("import 'audio_policy_service.dart';\n",
     "import 'audio_policy_service.dart';\nimport 'home_music_service.dart';\n"),
    ("    'ios_dusklight_internal',\n", "    'ios_dusklight_internal',\n    'ios_kartpad_internal',\n"),
    ("""      await AudioPolicyService().restoreAfterGameSession();
      await MusicPlayerService().resumeAfterGame();
""", """      await AudioPolicyService().restoreAfterGameSession();
      if (Platform.isIOS && _activeEmulatorExe == 'ios_kartpad_internal') {
        await HomeMusicService().beforeSharedEngineRestart();
        try {
          await MusicPlayerService().restoreAfterKartPad();
        } finally {
          await HomeMusicService().afterSharedEngineRestart();
        }
      } else {
        await MusicPlayerService().resumeAfterGame();
      }
"""),
    ("    if (Platform.isIOS && emulatorExe == 'ios_armsx2_internal') {\n",
     KARTPAD_SESSION + "    if (Platform.isIOS && emulatorExe == 'ios_armsx2_internal') {\n"),
]
# Dusklight and the Ports playlist left NeoStation on 20 October 2026
# (maintainer decision, docs/ports-removal-2026-10-20.md): its bridge,
# executable and session monitor are restored first, then KartPad's.
DUSKLIGHT_SESSION = """    if (Platform.isIOS && emulatorExe == 'ios_dusklight_internal') {
      _embeddedSessionSubscription = DusklightInternalBridge.sessionEvents.listen(
        (event) {
          if (_phase == GameLaunchPhase.playing && !_isClosing) {
            _log.i(
              '[GameLaunchManager] Dusklight returned to NeoStation: '
              '${event['reason']} (runtimeReleased=${event['runtimeReleased']})',
            );
            // A normal return now retains the suspended Dusklight runtime so
            // the same disc can reopen instantly. Build 321's early RPCS3 JIT
            // escrow remains reserved before Dusklight can allocate memory.
            _triggerClose();
          }
        },
      );
      if (DusklightInternalBridge.didEndSession && !_isClosing) {
        _triggerClose();
      }
      return;
    }

"""
DUSKLIGHT_REMOVAL = [
    ("import 'package:armsx2_internal_bridge/armsx2_internal_bridge.dart';\n",
     "import 'package:armsx2_internal_bridge/armsx2_internal_bridge.dart';\n"
     "import 'package:dusklight_internal_bridge/dusklight_internal_bridge.dart';\n"),
    ("    'ios_armsx2_internal',\n", "    'ios_dusklight_internal',\n    'ios_armsx2_internal',\n"),
    ("    if (Platform.isIOS && emulatorExe == 'ios_armsx2_internal') {\n",
     DUSKLIGHT_SESSION + "    if (Platform.isIOS && emulatorExe == 'ios_armsx2_internal') {\n"),
]
assert 'kartpad' not in manager.lower(), 'KartPad must not come back to the session lifecycle'
assert 'dusklight' not in manager.lower(), 'Dusklight must not come back to the session lifecycle'
for current, removed in DUSKLIGHT_REMOVAL:
    assert manager.count(current)==1, current
    manager = manager.replace(current, removed, 1)
for current, removed in KARTPAD_REMOVAL:
    assert manager.count(current)==1, current
    manager = manager.replace(current, removed, 1)
manager_without_current_engines = manager.replace("    'ios_melonx_internal',\n", '')
manager_without_current_engines = manager_without_current_engines.replace(
    "    'ios_dolphin_internal',\n    'ios_rpcs3_internal',\n    'ios_libretro_internal',\n", '')
assert manager_without_current_engines == original, 'unrelated lifecycle regression'
for file in ('lib/screens/game_screen/my_games_list.dart','lib/screens/secondary_screen/secondary_screen.dart','lib/widgets/shaders/shader_gif_widget.dart'):
    data=(root/file).read_text();assert 'FrontendMediaGate.instance.register' in data,file
    assert 'FrontendMediaGate.instance.unregister' in data,file
service=(root/'lib/services/game/game_launch_service.dart').read_text()
assert service.index('await FrontendMediaGate.instance.quiet')<service.index('await _launchGameImpl')
print('PASS: exact retained lifecycle (KartPad, Dusklight removed), all preview factories gated, 12 native cheat locales, generated sources match')

import re
bridge='packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm'
old_bridge=subprocess.check_output(['git','show','ae7d46f90dff64ce698b8c18e0c12510dbae96fe:'+bridge],cwd=root,text=True)
pattern=r'extern "C" \{(.*?)\n\}'
# Header declarations, exported entrypoints and types must remain donor-compatible.
old_decl=re.search(pattern,old_bridge,re.S)
new_decl=re.search(pattern,(root/bridge).read_text(),re.S)
assert old_decl and new_decl and old_decl.group(1)==new_decl.group(1), 'Dolphin core ABI changed'
