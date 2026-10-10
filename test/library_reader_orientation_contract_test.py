#!/usr/bin/env python3
"""Contract of portrait orientation for the Library readers (Build 437).

The Info.plist and lib/main.dart stay landscape only. A reader gets portrait
through one method of the libretro bridge (the app-level orientation mask
the embedded games already use) plus Flutter's preferred orientations, in
an order UIKit accepts, and never while a libretro game owns the mask.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise SystemExit('library reader orientation contract: ' + message)


def block_after(text, marker, opener='{'):
    """Text of the brace block that follows the first `marker`."""
    start = text.index(marker) + len(marker)
    open_at = text.index(opener, start)
    closer = {'{': '}', '[': ']'}[opener]
    depth = 0
    for index in range(open_at, len(text)):
        char = text[index]
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[open_at:index + 1]
    raise SystemExit('library reader orientation contract: unbalanced block after ' + marker)


# --- Native side --------------------------------------------------------------
plugin = read('packages/libretro_internal_bridge/ios/Classes/LibretroInternalBridgePlugin.m')
handler = block_after(plugin, '- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result')
marker = 'isEqualToString:@"setReaderOrientation"'
require(handler.count(marker) == 1, 'setReaderOrientation handled exactly once')
branch = block_after(handler, marker)
require(handler.index(marker) < handler.index('isEqualToString:@"launch"'),
        'the branch is reached before the launch fallthrough')

refusal = branch.index('if (self.session.active || self.launching)')
refusal_block = block_after(branch, 'if (self.session.active || self.launching)')
require('result(@NO);' in refusal_block and 'return;' in refusal_block,
        'refused (NO) while a libretro session is active or launching')
first_mask = branch.index('LibretroOrientationSetGameMask(')
require(refusal < first_mask, 'the refusal is checked before the mask changes')
require('@"allowPortrait"' in branch, 'reads the allowPortrait argument')
require('LibretroOrientationSetGameMask(UIInterfaceOrientationMaskAllButUpsideDown)' in branch,
        'allowing portrait sets AllButUpsideDown')
restore = re.search(
    r'dispatch_async\(dispatch_get_main_queue\(\),\s*\^\{\s*LibretroOrientationSetGameMask\(0\);\s*\}\);',
    branch)
require(restore is not None, 'the restore is queued on the main queue after Flutter\'s update')
require(branch.index('UIInterfaceOrientationMaskAllButUpsideDown') < restore.start(),
        'allow branch first, deferred restore in the else branch')
require(branch.count('result(@YES);') == 1, 'answers YES once the mask was applied or queued')
require('LIBRETRO_' not in branch, 'no new native error code (all codes are translated elsewhere)')
require('requestGeometryUpdate' not in branch, 'never forces a geometry update')

# --- Dart bridge ----------------------------------------------------------------
bridge = read('packages/libretro_internal_bridge/lib/libretro_internal_bridge.dart')
method = block_after(bridge, 'static Future<bool> setReaderOrientation({required bool allowPortrait})')
require("'setReaderOrientation'" in method and "'allowPortrait': allowPortrait" in method,
        'Dart calls the native method with allowPortrait')
require('on MissingPluginException' in method and 'on PlatformException' in method,
        'a missing plugin or a platform error reports false')

# --- Orientation service -----------------------------------------------------------
service = read('lib/services/library_reader_orientation.dart')
allow = block_after(service, 'Future<void> _allowPortrait() async')
native_allow = allow.index('setNativePortraitAllowed(true)')
guard = allow.index('if (!granted) return;')
flutter_portrait = allow.index('setPreferredOrientations(readerOrientations)')
require(native_allow < guard < flutter_portrait,
        'enter: native mask first, Flutter portrait only when it was granted')

restore_dart = block_after(service, 'Future<void> _restoreLandscape() async')
flutter_landscape = restore_dart.index('setPreferredOrientations(landscape)')
native_restore = restore_dart.index('setNativePortraitAllowed(false)')
require(flutter_landscape < native_restore, 'exit: Flutter landscape first, then the native restore')

orientations = block_after(service, 'static const List<DeviceOrientation> readerOrientations', '[')
require('DeviceOrientation.portraitUp' in orientations and 'portraitDown' not in orientations,
        'readers allow portrait up (never upside down) and keep landscape')
landscape = block_after(service, 'static const List<DeviceOrientation> landscape', '[')
require('landscapeLeft' in landscape and 'landscapeRight' in landscape and 'portrait' not in landscape,
        'exit restores the app\'s two landscape orientations')
require('Platform.isIOS' in service, 'portrait is only requested on iOS')

# The locked app configuration is not used to get portrait.
main = read('lib/main.dart')
require('setReaderOrientation' not in main and 'LibraryReaderOrientation' not in main,
        'lib/main.dart is untouched by the readers')

print('library reader orientation contract: OK')
