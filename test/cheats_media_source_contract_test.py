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
# Contract replaced (27 October 2026): the lifecycle was compared with the
# reviewed d3e558fa after undoing the libretro, KartPad and Dusklight hunks.
# The MeloNX commits that followed (127b527f retired external route,
# 07407ed8 failed initialization keeps native audio, eabc057f quarantined
# close, validated by host run 40209413009) were never added to that list,
# so the check failed on every run. The reviewed reference is now eabc057f,
# the latest of those commits, and the file must still match it exactly.
original=subprocess.check_output(['git','show','eabc057f4058520192f79f361cbd92eba5795f98:lib/services/game_launch_manager.dart'],cwd=root,text=True)
assert 'kartpad' not in manager.lower(), 'KartPad must not come back to the session lifecycle'
assert 'dusklight' not in manager.lower(), 'Dusklight must not come back to the session lifecycle'
assert manager == original, 'unrelated lifecycle regression'
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
