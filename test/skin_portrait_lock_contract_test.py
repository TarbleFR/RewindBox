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
require('chosenSkinForOrientation:LibretroSkinOrientationPortrait' in mask
        and 'chosenSkinForOrientation:LibretroSkinOrientationLandscape' in mask, 'portrait and landscape are resolved separately')
chosen = body(session, '- (LibretroSkin *)chosenSkinForOrientation:')
require('[self settingValue:key]' in chosen, 'effective selection uses the game-then-console store lookup')
require('importedSkinWithIdentifier' in chosen and 'report:NO' in chosen, 'quiet load of the chosen skin')
require(mask.count('usableInOrientation:LibretroSkinOrientationPortrait') == 2
        and mask.count('usableInOrientation:LibretroSkinOrientationLandscape') == 2,
        'both skins are checked in both orientations (portrait AND landscape lock)')
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
require('DOLPolicyMask(_portrait != nil, _landscape != nil, _portraitSkinOffersLandscape)' in overlay, 'overlay uses the policy')
for path in DOL.iterdir():
    if path.suffix in ('.m', '.mm', '.h'):
        require(not re.search(r'#(import|include)[^\n]*Libretro', read(path)), path.name + ' must not import libretro files')
for path in LIB.iterdir():
    if path.suffix in ('.m', '.mm', '.h'):
        require(not re.search(r'#(import|include)[^\n]*DOL', read(path)), path.name + ' must not import Dolphin files')

# --- unchanged global files ---------------------------------------------------------
main = read(ROOT / 'lib/main.dart')
require('//DeviceOrientation.portraitUp' in main, 'lib/main.dart stays landscape only')
print('skin portrait lock contract: ok')
