#!/usr/bin/env python3
"""Build 484: compile every changed native source for iPhone (macOS, real SDK).

The shared neo_touch_layout pod, the ARMSX2 and RPCS3 touch controls, input
controller, menus and plugins, and the Dolphin adapter, menu and plugin are
compiled for arm64 iPhoneOS with the pods' headers staged as the frameworks
publish them, and the Dolphin Swift touch controls generate the very
dolphin_internal_bridge-Swift.h the Objective-C side imports. The pod and the
new controls are then linked into one library: a declared NeoTouch*,
Armsx2Touch*, RPCS3Touch* or DOLTouchLayout* symbol left undefined fails here
instead of in the cold Xcode build of the delivery. Compilation only: nothing
runs here (test/touch_layout_ui_test.py runs the UIKit behaviour).
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from libretro_ios_syntax_test import stage_dependency_headers, public_headers  # noqa: E402
import touch_layout_support as touch  # noqa: E402

ARMS = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'
DOL = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
RPC = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
TARGET = 'arm64-apple-ios17.4'
OWN_SYMBOLS = ('NeoTouch', 'Armsx2Touch', 'RPCS3Touch', 'DOLTouchLayout', 'RPCS3GameInputController',
               'Armsx2VirtualStick', 'RPCS3InputPassthrough')


def run(command, **kwargs):
    print('+ ' + ' '.join(str(part) for part in command[:6]) + (' ...' if len(command) > 6 else ''), flush=True)
    return subprocess.run([str(part) for part in command], check=True, **kwargs)


def main():
    if sys.platform != 'darwin':
        raise SystemExit('The iPhone build check runs on macOS.')
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='touch-layout-ios-') as temporary:
        work = Path(temporary)
        include = stage_dependency_headers(work)
        touch.stage_touch_layout(include)
        staged = include / 'neo_swap'
        staged.mkdir(exist_ok=True)
        for header in public_headers('neo_swap', ROOT / 'packages/neo_swap/ios'):
            shutil.copyfile(header, staged / header.name)
        # The real Swift interface of the Dolphin touch controls.
        swift_header = include / 'dolphin_internal_bridge' / 'dolphin_internal_bridge-Swift.h'
        swift_header.parent.mkdir(parents=True)
        swift_sources = sorted((DOL / 'TouchController').glob('*.swift'))
        run(['xcrun', '--sdk', 'iphoneos', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk,
             '-target', TARGET, '-module-name', 'dolphin_internal_bridge',
             '-import-objc-header', DOL / 'TouchController/TCManagerInterface.h',
             '-emit-objc-header-path', swift_header, *swift_sources])
        assert 'cancelTouchInteractions' in swift_header.read_text(), 'Swift touch-layout API not exported'
        print(f'PASS Swift: {len(swift_sources)} Dolphin touch-control sources typecheck; Objective-C header generated',
              flush=True)

        common = ['-target', TARGET, '-isysroot', sdk, '-fobjc-arc', '-fblocks', '-fmodules', '-Wall',
                  '-Wno-unused-function', '-I', include, '-I', ROOT / 'test/libretro_host/stubs',
                  '-I', touch.CLASSES, '-I', touch.PUBLIC]
        objects = []
        failed = []

        def compile_source(source, language, syntax_only=False, extra=()):
            output = work / ('_'.join(source.relative_to(ROOT).with_suffix('.o').parts))
            command = ['xcrun', '--sdk', 'iphoneos', 'clang++' if language == 'objective-c++' else 'clang',
                       *common, *extra, '-x', language]
            if language == 'objective-c++':
                command += ['-std=c++20']
            command += ['-fsyntax-only', str(source)] if syntax_only else ['-c', str(source), '-o', str(output)]
            result = subprocess.run([str(part) for part in command], capture_output=True, text=True)
            status = 'ok' if result.returncode == 0 else 'FAILED'
            print(f'{status:6} {"syntax " if syntax_only else ""}{source.relative_to(ROOT)}', flush=True)
            if result.stderr.strip():
                print(result.stderr, flush=True)
            if result.returncode:
                failed.append(str(source.relative_to(ROOT)))
            elif not syntax_only:
                objects.append(output)

        for source in touch.sources(include_plugin=True):
            compile_source(source, 'objective-c')
        compile_source(ARMS / 'Armsx2TouchControls.mm', 'objective-c++', extra=['-I', ARMS])
        compile_source(RPC / 'RPCS3TouchControls.mm', 'objective-c++', extra=['-I', RPC])
        compile_source(RPC / 'RPCS3GameInputController.mm', 'objective-c++', extra=['-I', RPC])
        compile_source(DOL / 'DOLTouchLayout.mm', 'objective-c++', extra=['-I', DOL, '-I', DOL / 'TouchController'])
        for source in (ARMS / 'Armsx2SessionMenu.mm', ARMS / 'Armsx2InternalBridgePlugin.mm'):
            compile_source(source, 'objective-c++', syntax_only=True, extra=['-I', ARMS])
        for source in (RPC / 'Rpcs3SessionMenu.mm', RPC / 'Rpcs3InternalBridgePlugin.mm'):
            compile_source(source, 'objective-c++', syntax_only=True, extra=['-I', RPC])
        for source in (DOL / 'DolphinSessionMenu.mm', DOL / 'DolphinInternalBridgePlugin.mm'):
            compile_source(source, 'objective-c++', syntax_only=True, extra=['-I', DOL, '-I', DOL / 'TouchController'])
        if failed:
            raise SystemExit('iPhone compilation failed: ' + ', '.join(failed))

        library = work / 'libtouch_layout.dylib'
        run(['xcrun', '--sdk', 'iphoneos', 'clang++', '-dynamiclib', '-target', TARGET, '-isysroot', sdk, '-fobjc-arc',
             *objects, '-framework', 'UIKit', '-framework', 'Foundation', '-framework', 'GameController',
             '-Wl,-undefined,dynamic_lookup', '-o', library])
        undefined = subprocess.check_output(['xcrun', 'nm', '-u', str(library)], text=True).split()
        missing = sorted({name for name in undefined if any(token in name for token in OWN_SYMBOLS)})
        # The Dolphin adapter calls the Swift overlay, which lives in the bridge's Swift module.
        missing = [name for name in missing if 'DOLTouchOverlay' not in name]
        if missing:
            raise SystemExit('Declared but never defined: ' + ', '.join(missing))
    print(f'PASS: {len(objects)} touch-layout objects compile and link for iPhone; menus and plugins of the '
          'three engines pass the iPhone SDK syntax check')


if __name__ == '__main__':
    main()
