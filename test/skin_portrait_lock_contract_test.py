#!/usr/bin/env python3
"""Source wiring of the portrait-only and landscape-only skin lock (libretro and Dolphin bridges).

This is a TEXT contract of the call order, not a UIKit run: rotation itself
is only observable on an iPhone or in the simulator. The decision table is
executed by test/orientation_policy/policy_test.c (compiled and run here).
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'packages/libretro_internal_bridge/ios/Classes'
DOL = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
A2 = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'


def read(path):
    return path.read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise SystemExit('skin portrait lock contract: ' + message)


def body(text, signature):
    start = text.index(signature)
    depth, begun = 0, False
    for index in range(text.index('{', start), len(text)):
        if text[index] == '{':
            depth, begun = depth + 1, True
        elif text[index] == '}':
            depth -= 1
            if begun and depth == 0:
                return text[start:index + 1]
    raise SystemExit('unbalanced ' + signature)


# --- decision table, really compiled and run -----------------------------------
with tempfile.TemporaryDirectory() as tmp:
    binary = Path(tmp) / 'policy_test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(ROOT / 'test/orientation_policy/policy_test.c'), '-o', str(binary)], check=True)
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    require(run.returncode == 0, 'decision table failed:\n' + run.stdout)

# --- libretro --------------------------------------------------------------------
session = read(LIB / 'LibretroSession.m')
require('#import "LibretroOrientationPolicy.h"' in session, 'policy imported')
launch = session[session.index('[_controller setLoading:YES];'):]
mask_at = launch.index('LibretroOrientationSetGameMask([self gameOrientationMask]);')
present_at = launch.index('[presenter presentViewController:_controller')
require(mask_at < present_at, 'the mask is set BEFORE the game is presented')
require('UIInterfaceOrientationMaskAllButUpsideDown);\n  [presenter present' not in launch[:present_at],
        'no unconditional all-orientations mask before presenting')
require('_controller.allowedOrientations = [self gameOrientationMask];' in session, 'controller starts with the same mask')
mask = body(session, '- (UIInterfaceOrientationMask)gameOrientationMask')
require('_legacyLandscapeOnly) return UIInterfaceOrientationMaskLandscape' in mask,
        'the documented legacy Vulkan landscape exception wins')
require('LibretroSelectedOrientationMask(' in mask and '[self gameScopeKey]' in mask,
        'the mask comes from the portable selection resolver with the game scope')
require('failedSkins' in mask and 'importedSkinWithIdentifier' in mask and 'report:NO' in mask,
        'a refused skin does not load and the load is quiet')
require('usableInOrientation' in mask, 'usability is judged per chosen skin and orientation')
selection = read(LIB / 'LibretroOrientationSelection.m')
require('LibretroSettingSkinPortrait' in selection and 'LibretroSettingSkinLandscape' in selection
        and 'valueForKey:key console:console game:' in selection,
        'both keys are resolved through the store (game, then console)')
require('LibretroPolicyMask(portraitChosen, landscapeChosen)' in selection
        and 'orientationsForIPad' in selection, 'chosen = selected AND a layout there; file capabilities are not an input')
legacy = body(session, '- (void)keepLandscapeForLegacyPicture')
require('_legacyLandscapeOnly = YES' in legacy, 'legacy exception recorded')
for name in ('frontendSettingsDidChange', 'rejectSkin:(LibretroSkin *)skin representation'):
    require('[self refreshOrientationLock]' in body(session, '- (void)' + name), name + ' refreshes the lock')
restore = body(session, 'static void LibretroRestoreAppOrientations')
require('LibretroOrientationSetGameMask(0)' in restore, 'restore releases the mask')
for name in ('finishStop', 'failStartWithResult'):
    block = body(session, '- (void)' + name)
    done = block[block.index('dispatch_block_t done = ^{'):]
    require('LibretroRestoreAppOrientations(presenter);' in done.split('};')[0],
            name + ' restores in the dismissal completion')

# --- Dolphin ---------------------------------------------------------------------
plugin = read(DOL / 'DolphinInternalBridgePlugin.mm')
overlay = read(DOL / 'DOLSkinOverlay.mm')
require('DOLOrientationInstall();' in body(plugin, '+ (void)registerWithRegistrar:'), 'coordinator installed at registration')
supported = body(plugin, '- (UIInterfaceOrientationMask)supportedInterfaceOrientations')
require('self.skinOverlay.supportedOrientationMask' in supported and 'portraitAvailable' not in supported,
        'controller mask comes from the policy, not from portraitAvailable alone')
set_at = plugin.index('DOLOrientationSetGameMask(controller.skinOverlay.supportedOrientationMask);')
present_at = plugin.index('[root presentViewController:controller animated:NO completion:nil];')
require(set_at < present_at and present_at - set_at < 400, 'app mask set right before the presentation')
cleanup = body(plugin, '- (void)cleanupSharedResourcesAndUI')
require(re.search(r'DOLDismissSessionController\(controller, \^\{\s*DOLOrientationSetGameMask\(0\);', cleanup),
        'released in the dismissal completion (stop AND failed launch share this path)')
require('finishFailedLaunch' in plugin and 'cleanupSharedResourcesAndUI];' in body(plugin, '- (NSDictionary*)finishFailedLaunch'),
        'a failed launch goes through the same release')
require('DOLPolicyMask(_portrait != nil, _landscape != nil)' in overlay and 'OffersLandscape' not in overlay,
        'overlay uses the choice-based policy')
menu = read(DOL / 'DolphinSessionMenu.mm')
require('DOLOrientationGameMask()' in body(menu, '- (UIInterfaceOrientationMask)supportedInterfaceOrientations'),
        'the Dolphin session menu follows the session mask (no landscape-only menu under a portrait app mask)')
require('return UIInterfaceOrientationMaskLandscape; }' not in menu, 'no unconditional landscape-only menu is left')
ci = read(ROOT / 'packages/dolphin_internal_bridge/ci/test_session_ui.rb')
require('DOLOrientation.mm' in ci and 'DolphinOrientationTests.mm' in ci, 'the simulator harness builds and runs the orientation tests')
for path in DOL.iterdir():
    if path.suffix in ('.m', '.mm', '.h'):
        require(not re.search(r'#(import|include)[^\n]*Libretro', read(path)), path.name + ' must not import libretro files')
for path in LIB.iterdir():
    if path.suffix in ('.m', '.mm', '.h'):
        require(not re.search(r'#(import|include)[^\n]*DOL', read(path)), path.name + ' must not import Dolphin files')

# --- Dolphin and ARMSX2 headers stay pure Objective-C importing UIKit only (pod umbrella) --------
for header in (DOL / 'DOLSkinOverlay.h', A2 / 'ARMSX2SkinOverlay.h'):
    imports = re.findall(r'^#(?:import|include)\s+(\S+)', read(header), re.M)
    require(imports == ['<UIKit/UIKit.h>'], header.name + ' imports only UIKit (module umbrella): %s' % imports)

# --- ARMSX2 (PS2) ------------------------------------------------------------------------------------
a2_plugin = read(A2 / 'Armsx2InternalBridgePlugin.mm')
a2_menu = read(A2 / 'Armsx2SessionMenu.mm')
a2_overlay = read(A2 / 'ARMSX2SkinOverlay.mm')
require('ARMSX2OrientationInstall();' in body(a2_plugin, '+ (void)registerWithRegistrar:'), 'ARMSX2 coordinator installed')
set_at = a2_plugin.index('ARMSX2OrientationSetGameMask(controller.skinOverlay.supportedOrientationMask);')
present_at = a2_plugin.index('[root presentViewController:controller animated:NO completion:nil];')
require(set_at < present_at and present_at - set_at < 200, 'ARMSX2: app mask set right before the presentation')
require('if (controller.skinOverlay.hasSkin)' in a2_plugin[set_at - 80:set_at], 'ARMSX2: only a session with a skin changes the mask')
release = body(a2_plugin, '- (void)dismissGameControllerWithCompletion:')
require('ARMSX2OrientationSetGameMask(0);' in release[release.index('releaseView'):], 'ARMSX2: released in the dismissal completion')
require('dismissGameController];' in body(a2_plugin, '- (void)failTransaction:'), 'ARMSX2: a failed launch goes through the same release')
require('ARMSX2OrientationGameMask()' in body(a2_menu, '- (UIInterfaceOrientationMask)supportedInterfaceOrientations'),
        'the ARMSX2 session menu follows the session mask')
require('supportedOrientationMask' in body(a2_plugin, '- (UIInterfaceOrientationMask)supportedInterfaceOrientations'), 'ARMSX2 game controller mask')
require('ARMSX2PolicyMask(_portrait != nil, _landscape != nil)' in a2_overlay, 'ARMSX2 overlay uses the choice-based policy')
require('api->set_button' in a2_plugin and 'skin.buttonChanged' in a2_plugin and 'skin.sticksChanged' in a2_plugin,
        'ARMSX2 skin inputs reach the Core pad')
require('skin.menuHandler = ^{ [weakSelf menuPressed]; };' in a2_plugin, 'the skin Menu opens the session menu')
require('[self.skinOverlay releaseAllInputs];' in body(a2_plugin, '- (void)resetInput {'), 'resetInput releases the skin too (menu, stop)')
require('UIApplicationWillResignActiveNotification' in a2_plugin, 'background releases the inputs')
require('self.controlsView.hidden = hiddenByPolicy || shown;' in a2_plugin, 'the skin replaces the stock controls while it is drawn')
for path in A2.iterdir():
    if path.suffix in ('.m', '.mm', '.h'):
        require(not re.search(r'#(import|include)[^\n]*(Libretro|DOL[A-Z]|Dolphin)', read(path)), path.name + ' must not import other engines')

# --- unchanged global files ---------------------------------------------------------
main = read(ROOT / 'lib/main.dart')
require('//DeviceOrientation.portraitUp' in main, 'lib/main.dart stays landscape only')
print('skin portrait lock contract: ok')
