#!/usr/bin/env python3
"""Which steps of .github/workflows/skin-orientation-checks.yml a push needs.

Usage: python3 tools/skins/ci_areas.py BASE HEAD   (BASE "all": every step)
Prints "<area>=true|false" lines for $GITHUB_OUTPUT and a summary on stderr.

BASE is the last commit of the branch that a completed run already checked (or, for
a new branch, its merge base with Claude). A step runs only when a file it builds or
reads changed since BASE: nothing is redone from scratch for an unrelated change.
A change to this file or to the workflow alone runs only the host steps (seconds);
"Run workflow" (input "all") checks everything when wanted.
"""
import re
import subprocess
import sys

DOLPHIN = 'packages/dolphin_internal_bridge/'
AREAS = {
    # test/libretro_frontend_test.py and test/libretro_ios_syntax_test.py
    'libretro': r'^packages/libretro_internal_bridge/|^test/libretro_',
    # verify_pocket_skins.py, pocket_skin_input_chain_test.py (reads the DOLSkinOverlay and
    # ARMSX2SkinOverlay tables, compiles DOLSkinHitTest.h), dolphin_session_chrome_test.py
    'pocket': r'^assets/skins/pocket/|^tools/skins/|^docs/design/pocket/|^test/pocket_skin_input_chain_test\.py$'
              r'|^test/dolphin_session_chrome_test\.py$|^test/orientation_policy/'
              r'|^' + DOLPHIN + r'ios/Classes/(DOLSkinHitTest\.h|DOLSessionChromePolicy\.h|DOLSkinOverlay\.mm'
              r'|DolphinInternalBridgePlugin\.mm)$'
              r'|^packages/armsx2_internal_bridge/ios/Classes/ARMSX2SkinOverlay\.mm$'
              r'|^\.github/workflows/skin-orientation-checks\.yml$|^tools/skins/ci_areas\.py$',
    'dolphin_compile': r'^' + DOLPHIN + r'ios/Classes/(DOL|TouchController/TCManagerInterface\.h)',
    'armsx2': r'^packages/armsx2_internal_bridge/(ios/Classes/ARMSX2|ci/)|^assets/skins/pocket/ps2-',
    # ci/test_skin_overlay_ui.rb: DOLSkinOverlay.mm, the recorder, the two Original archives
    'dolphin_skin_sim': r'^' + DOLPHIN + r'ios/Classes/(DOLSkin|DOLOrientationPolicy\.h|TouchController/TCManagerInterface\.h)'
                        r'|^' + DOLPHIN + r'ci/(SkinOverlay|DolphinSkinOverlayTests|test_skin_overlay_ui)'
                        r'|^assets/skins/pocket/(gamecube|wii)-pocket-original',
    # ci/test_orientation_ui.rb
    'dolphin_orientation_sim': r'^' + DOLPHIN + r'ios/Classes/(DOLOrientation|DolphinSessionLifecycle)'
                               r'|^' + DOLPHIN + r'ci/(DolphinOrientation|test_orientation_ui)',
    # ci/test_session_ui.rb (session menu, overlays, recorder, TouchController, two pods)
    'dolphin_session_sim': r'^' + DOLPHIN + r'ios/(Classes/(Dolphin(SessionMenu|PerformanceOverlay|RecordingController'
                           r'|FramePacing|ExternalDisplay|RetroAchievementsAccount|SessionLifecycle)|DOLOrientation'
                           r'|TouchController/)|TouchResources/)'
                           r'|^' + DOLPHIN + r'ci/(Session|PerformanceOverlay|RecordingController|DolphinMenuOrientation'
                           r'|test_session_ui|build_support|device_info)'
                           r'|^packages/(neo_cheat_catalog|external_display)/ios/Classes/',
}
def areas(changed):
    if changed is None:
        return {name: True for name in AREAS}
    return {name: any(re.search(pattern, path) for path in changed) for name, pattern in AREAS.items()}


def main():
    base, head = sys.argv[1], sys.argv[2]
    changed = None
    if base != 'all':
        try:
            out = subprocess.run(['git', 'diff', '--name-only', base, head], check=True, capture_output=True, text=True)
            changed = [line for line in out.stdout.splitlines() if line]
        except subprocess.CalledProcessError:
            changed = None  # base not reachable: check everything
    result = areas(changed)
    for name, value in result.items():
        print(f'{name}={"true" if value else "false"}')
    print(f'base: {base}; changed files: {"all" if changed is None else len(changed)}', file=sys.stderr)
    for name, value in result.items():
        print(f'  {name}: {"run" if value else "skip (unchanged)"}', file=sys.stderr)


if __name__ == '__main__':
    main()
