#!/usr/bin/env python3
"""XeniOS touch controls on the shared touch-layout layer (Build 484 contract).

Host checks of the native sources (UIKit is not available here):
identifiers, stock frames and XInput bits of every control; Xbox 360 face
layout; Y axis up; the RPCS3 merge policy; the shared hide rule; the editor
pausing the game with a neutral pad; preview registration; the layout key in
every closed list of the shared layer; localized in-game menu.
docs/xenios-playlist.md § Touch controls.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/xenia_internal_bridge/ios/Classes'
TOUCH = (CLASSES / 'XeniaTouchControls.mm').read_text()
PLUGIN = (CLASSES / 'XeniaInternalBridgePlugin.mm').read_text()

XINPUT = {'kXeniaUp': 0x0001, 'kXeniaDown': 0x0002, 'kXeniaLeft': 0x0004, 'kXeniaRight': 0x0008,
          'kXeniaStart': 0x0010, 'kXeniaBack': 0x0020, 'kXeniaL3': 0x0040, 'kXeniaR3': 0x0080,
          'kXeniaLB': 0x0100, 'kXeniaRB': 0x0200, 'kXeniaA': 0x1000, 'kXeniaB': 0x2000,
          'kXeniaX': 0x4000, 'kXeniaY': 0x8000}


def fail(message: str) -> None:
    raise SystemExit('xenia touch controls: ' + message)


def main() -> None:
    # XInput bits (xenia/hid/input.h X_INPUT_GAMEPAD_*).
    for name, value in XINPUT.items():
        if not re.search(rf'{name} = 0x{value:04X}\b', TOUCH):
            fail(f'{name} is not X_INPUT bit 0x{value:04X}')
    legends = {'A': 'kXeniaA', 'B': 'kXeniaB', 'X': 'kXeniaX', 'Y': 'kXeniaY', 'LB': 'kXeniaLB',
               'RB': 'kXeniaRB', 'L3': 'kXeniaL3', 'R3': 'kXeniaR3', 'BACK': 'kXeniaBack',
               'START': 'kXeniaStart', '↑': 'kXeniaUp', '↓': 'kXeniaDown', '←': 'kXeniaLeft',
               '→': 'kXeniaRight', 'LT': 'kXeniaTagLeftTrigger', 'RT': 'kXeniaTagRightTrigger'}
    for legend, tag in legends.items():
        if f'padButton:@"{legend}" tag:{tag}]' not in TOUCH:
            fail(f'{legend} does not send {tag}')
    # Every element of the layout has a stock frame, in both orientations.
    order = re.search(r'_order = @\[(.*?)\];', TOUCH, re.S).group(1)
    identifiers = re.findall(r'@"([a-z0-9.]+)"', order) + ['dpad', 'stick.left', 'stick.right']
    identifiers = sorted(set(identifiers) - {'dpad', 'stick.left', 'stick.right'}) + ['dpad', 'stick.left', 'stick.right']
    frames = re.search(r'stockFramesForBounds:.*?return frames;', TOUCH, re.S).group(0)
    for identifier in identifiers:
        constant = {'dpad': 'kXeniaDPad', 'stick.left': 'kXeniaLeftStick', 'stick.right': 'kXeniaRightStick'}.get(identifier)
        if f'frames[@"{identifier}"]' not in frames and (constant is None or f'frames[{constant}]' not in frames):
            fail(f'no stock frame for {identifier}')
    if frames.count('if (portrait)') != 1:
        fail('the stock layout must cover portrait and landscape')
    # Xbox 360 face layout: Y top, A bottom, X left, B right.
    for button, offset in (('y', '37, face.origin.y + 0'), ('a', '37, face.origin.y + 74'),
                           ('x', '0, face.origin.y + 37'), ('b', '74, face.origin.y + 37')):
        if f'frames[@"{button}"] = [NSValue valueWithCGRect:CGRectMake(face.origin.x + {offset}' not in frames:
            fail(f'{button} is not at its Xbox 360 position')
    # XInput thumb Y is positive up; the screen grows down.
    if 'self.valueChanged((float)x, (float)-y);' not in TOUCH:
        fail('the stick Y axis is not reported up')
    # The shared layer contract.
    for needed in ('NeoTouchLayoutApplier applyLayout:', 'captureDefaultGeometryInCanvas:self',
                   'releaseAllInput', 'NeoTouchLayoutStoreDidChangeNotification',
                   'registerPreviewFactory:', 'preview.userInteractionEnabled = NO',
                   'UIInterfaceOrientationMaskAllButUpsideDown'):
        if needed not in TOUCH:
            fail(f'missing shared-layer piece: {needed}')
    # Session: shared hide rule, RPCS3 merge, editor with a neutral pad and the game paused.
    for needed in ('NeoTouchControlsShouldHide(XeniaTouchLayoutKey, _monitor.connected, YES,',
                   'merged.buttons = a.buttons | b.buttons;', 'merged.lt = MAX(a.lt, b.lt);',
                   'hypotf(a.lx, a.ly) >= hypotf(b.lx, b.ly)',
                   'if (self.menuOpen || self.editingTouchControls) {',
                   'initWithHost:_touch', 'layoutKey:XeniaTouchLayoutKey',
                   '_touch.userInteractionEnabled = NO;', '[self.owner setUserPaused:YES];',
                   'XeniaTouchControlsRegisterPreview();', 'NeoTouchControllerPreferenceDidChangeNotification',
                   "NeoTouchLayoutText(@\"editTouchControls\", self.locale)",
                   '[self text:@"resume" fallback:', '[self text:@"quit" fallback:'):
        if needed not in PLUGIN:
            fail(f'session lacks: {needed}')
    if 'accessibilityLabel = @"Resume"' in PLUGIN or 'actionWithTitle:@"▶︎"' in PLUGIN:
        fail('the in-game menu must use localized labels')
    if "s.dependency 'neo_touch_layout'" not in (ROOT / 'packages/xenia_internal_bridge/ios/xenia_internal_bridge.podspec').read_text():
        fail('the bridge pod does not depend on neo_touch_layout')
    # The layout key in every closed list of the shared layer.
    if '@"xbox360"' not in (ROOT / 'packages/neo_touch_layout/ios/Classes/NeoTouchLayoutPlugin.m').read_text():
        fail('NeoTouchLayoutPlugin does not map the xbox360 console')
    if "'xbox360'" not in (ROOT / 'packages/neo_touch_layout/lib/neo_touch_layout.dart').read_text():
        fail('NeoTouchLayout.consoles lacks xbox360')
    if "'xbox360' => _t('layoutXbox360')" not in (ROOT / 'lib/widgets/embedded_touch_controls_panel.dart').read_text():
        fail('the settings panel has no Xbox 360 layout name')
    strings = json.loads((ROOT / 'tools/touch_layout/strings.json').read_text())
    for locale in strings['locales']:
        if strings['values'][locale].get('layoutXbox360') != 'Xbox 360':
            fail(f'layoutXbox360 missing in {locale}')
    print('xenia touch controls: OK')


if __name__ == '__main__':
    main()
