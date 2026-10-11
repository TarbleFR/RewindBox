#!/usr/bin/env python3
"""Execute the Build 442 external-display placement policy on macOS.

Compiles the production DolphinExternalDisplayLayout.h with Foundation and
CoreGraphics only and runs test/dolphin_external_display_test.mm. The window
lifecycle (connect, disconnect, Off/Fit/Fill, stop) runs in the iOS Simulator
through dolphin_external_display_ui_test.py. Skipped where clang++ or the
Apple frameworks are unavailable. No device claim.
"""
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'

header = (CLASSES / 'DolphinExternalDisplayLayout.h').read_text(encoding='utf-8')
assert '<UIKit/' not in header and '<MetalKit/' not in header, 'the placement policy stays executable without UIKit'
assert 'DOLExternalDisplayModeFit = 1' in header and 'DOLExternalDisplayModeFill = 2' in header
implementation = (CLASSES / 'DolphinExternalDisplay.mm').read_text(encoding='utf-8')
for token in ('autoResizeDrawable = NO', 'CGAffineTransformMakeScale(scale, scale)', 'insertSubview:render atIndex:0',
              'UIScreenDidConnectNotification', 'UIScreenDidDisconnectNotification', 'DOLExternalDisplayChangedNotification'):
    assert token in implementation, token
assert 'ResizeSurface' not in implementation and 'drawableSize' not in implementation, \
    'the render view keeps the drawable Dolphin sized; only a transform maps it to the TV'
host = (CLASSES / 'DolphinInternalBridgePlugin.mm').read_text(encoding='utf-8')
assert '[container addSubview:_metalView]' in host and 'self.view = container' in host, 'the Metal view is a movable subview'
assert host.index('[self.dolphinController.externalDisplay stop]') < host.index('[self.dolphinController.framePacing stop]'), \
    'the Metal view returns to the iPhone before the core shuts down'

if platform.system() != 'Darwin' or not shutil.which('clang++'):
    print('SKIP: external display placement execution requires macOS Foundation/CoreGraphics; source contracts checked')
    raise SystemExit(0)
with tempfile.TemporaryDirectory() as folder:
    binary = Path(folder) / 'external-display'
    subprocess.run(['clang++', '-std=c++20', '-fobjc-arc', '-I' + str(CLASSES), str(ROOT / 'test/dolphin_external_display_test.mm'),
                    '-framework', 'Foundation', '-framework', 'CoreGraphics', '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
