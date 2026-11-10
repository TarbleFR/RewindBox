#!/usr/bin/env python3
"""Compile-check the RPCS3 host bridge for the iPhone without building an application (macOS runner, Xcode).

The bridge (Objective-C++) is otherwise compiled only by an application build. This check parses and type-checks the
files named below with the iPhone SDK, the C++ standard and ARC mode of the pod, a Flutter header stub and the public
headers of the pods the bridge imports, staged as <pod/Header.h>. It proves that the sources compile for the device
SDK; it does not link, run or exercise them.

    python3 test/rpcs3_host_bridge_ios_syntax_test.py [--report OUT.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
SOURCES = ('Rpcs3InternalBridgePlugin.mm', 'Rpcs3SessionMenu.mm')
PODS = ('neo_swap', 'neo_touch_layout', 'achievement_translation', 'retro_achievements_session', 'external_display')
FLUTTER_STUB = '''#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
typedef void (^FlutterResult)(id _Nullable result);
FOUNDATION_EXPORT NSObject* const FlutterMethodNotImplemented;
@protocol FlutterBinaryMessenger <NSObject>
@end
@class FlutterMethodCall;
@class FlutterMethodChannel;
@protocol FlutterPluginRegistrar <NSObject>
@property(nonatomic, readonly) NSObject<FlutterBinaryMessenger>* messenger;
@property(nonatomic, readonly, nullable) UIViewController* viewController;
- (void)addMethodCallDelegate:(id)delegate channel:(FlutterMethodChannel*)channel;
@end
@protocol FlutterPlugin <NSObject>
+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar;
@end
@interface FlutterViewController : UIViewController
@end
@interface FlutterMethodCall : NSObject
@property(nonatomic, readonly) NSString* method;
@property(nonatomic, readonly) id arguments;
@end
@interface FlutterMethodChannel : NSObject
+ (instancetype)methodChannelWithName:(NSString*)name
                  binaryMessenger:(NSObject<FlutterBinaryMessenger>*)messenger;
- (void)invokeMethod:(NSString*)method arguments:(id)arguments;
@end
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if sys.platform != 'darwin' or not shutil.which('xcrun'):
        print('SKIP: needs macOS with Xcode (the iPhone SDK); nothing was checked')
        return 2
    sdk = subprocess.run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], capture_output=True, text=True, check=True).stdout.strip()
    report = {'sdk': sdk, 'xcode': subprocess.run(['xcodebuild', '-version'], capture_output=True, text=True).stdout.strip(), 'sources': {}}
    with tempfile.TemporaryDirectory(prefix='rpcs3-bridge-syntax-') as temporary:
        stub = Path(temporary)
        (stub / 'Flutter').mkdir()
        (stub / 'Flutter/Flutter.h').write_text(FLUTTER_STUB)
        for pod in PODS:
            staged = stub / 'include' / pod
            staged.mkdir(parents=True)
            headers = sorted((ROOT / 'packages' / pod / 'ios/Classes').glob('*.h')) + sorted((ROOT / 'packages' / pod / 'ios/Classes/Public').glob('*.h'))
            if not headers:
                print(f'FAIL: no header found for the pod {pod}')
                return 1
            for header in headers:
                shutil.copyfile(header, staged / header.name)
        common = ['xcrun', '--sdk', 'iphoneos', 'clang++', '-std=c++20', '-fobjc-arc', '-fblocks', '-fsyntax-only', '-x', 'objective-c++',
                  '-isysroot', sdk, '-target', 'arm64-apple-ios17.4', f'-I{stub}', f'-I{stub}/include', f'-I{CLASSES}']
        failed = False
        for name in SOURCES:
            source = CLASSES / name
            result = subprocess.run([*common, str(source)], capture_output=True, text=True)
            errors = [line for line in result.stderr.splitlines() if ' error: ' in line or ' fatal error: ' in line]
            report['sources'][name] = {'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'returncode': result.returncode, 'errors': errors[:40]}
            print(f"{name}: {'compiles for arm64 iPhone (syntax and types)' if result.returncode == 0 else 'DOES NOT COMPILE'}")
            if result.returncode:
                failed = True
                print(result.stderr[-6000:])
    report['result'] = 'failed' if failed else 'passed'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=1) + '\n')
    print('FAIL' if failed else 'PASS: the RPCS3 host bridge sources parse and type-check with the iPhone SDK (no link, no run)')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
