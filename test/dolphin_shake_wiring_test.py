#!/usr/bin/env python3
"""Portable guards for the Wii Shake wiring that only macOS can execute.

Behaviour is executed by dolphin_touch_shake_test.py, dolphin_shake_assignment_test.py
and dolphin_touch_shake_ui_test.py on macOS CI. These checks catch, on any host,
the build and threading mistakes those tests cannot see before a macOS run:
a C++ header leaking into the Swift umbrella, a queue hop that would deadlock
the runtime queue, or the arbiter gaining a UIKit dependency.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / 'packages/dolphin_internal_bridge/ios'
TOUCH = IOS / 'Classes/TouchController'

podspec = (IOS / 'dolphin_internal_bridge.podspec').read_text(encoding='utf-8')
private = re.search(r"s\.private_header_files\s*=\s*(.+)", podspec).group(1)
assert "'Classes/TouchController/DolphinShakeAssignment.h'" in private, 'C++ header must stay out of the Swift umbrella'

arbiter = (TOUCH / 'DolphinShakeInput.swift').read_text(encoding='utf-8')
assert sorted(re.findall(r'^import (\w+)', arbiter, re.M)) == ['CoreGraphics', 'Foundation'], \
    'the arbiter stays executable by swiftc on macOS without UIKit'

transaction = (TOUCH / 'DolphinShakeAssignment.mm').read_text(encoding='utf-8')
code = re.sub(r'//[^\n]*|/\*.*?\*/', '', transaction, flags=re.S)
for forbidden in (r'\bdispatch_sync\b', r'\bdispatch_get_main_queue\b', r'<UIKit/', r'\bUI[A-Z][A-Za-z]+\b'):
    assert not re.search(forbidden, code), forbidden + ' in the runtime-queue transaction'

plugin = (IOS / 'Classes/DolphinInternalBridgePlugin.mm').read_text(encoding='utf-8')
apply_block = plugin.split('menu.applySettings = ^(NSDictionary* request, void (^completion)(BOOL)) {', 1)[1]
apply_block = apply_block.split('menu.readCheats = ^', 1)[0]
runtime = apply_block.split('dispatch_async(bridge->_runtimeQueue, ^{', 1)[1]
intercept, generic = runtime.split('NSData* data = DOLSerializeMenuRequest(request);', 1)
intercept = re.sub(r'//[^\n]*|/\*.*?\*/', '', intercept, flags=re.S)
assert 'DOLIsShakeAssignmentRequest(request)' in intercept and 'DOLApplyShakeAssignmentRequestOnRuntime(request)' in intercept
assert 'return;' in intercept, 'a Shake request never reaches the donor as an unknown kind'
assert 'dispatch_sync' not in intercept, 'already on the runtime queue: no dispatch_sync'
assert 'neostation_dolphin_menu_apply' not in intercept

overlay = (TOUCH / 'DolphinTouchOverlay.swift').read_text(encoding='utf-8')
assert 'insertSubview(view, at: 0)' in overlay and 'addSubview(view)' not in overlay, 'pad stays below the Shake control'
# The arbiter calls this emitter from the phone input queue and the touch-hold
# release queue; as a UIView member it would otherwise be main-actor isolated.
assert re.search(r'\bnonisolated\s+private\s+static\s+func\s+emitShake\b', overlay), \
    'the shake emitter must not inherit UIView main-actor isolation'
assert 'DolphinShakeInput(emit: DolphinTouchOverlay.emitShake)' in overlay

print('PASS: Wii Shake private header, Foundation-only arbiter, nonisolated emitter, runtime-queue intercept without queue hop')
