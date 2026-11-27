"""Compile the owned C ABI adapter and actual import channel against iPhoneOS.

Run in the existing Dolphin producer; no app, IPA or console data is created.
"""
import platform
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if platform.system() != 'Darwin':
        raise SystemExit('iPhoneOS SDK required; run this check in the Dolphin producer')
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    bridge = (ROOT / 'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm').read_text()
    start = bridge.index('  if ([call.method isEqualToString:@"wiimmfiCancelImport"])')
    end = bridge.index('  if ([call.method isEqualToString:@"saveIdentity"])', start)
    harness = r'''
#import <UIKit/UIKit.h>
#import <Network/Network.h>
#include "DOLWiimmfi.h"
typedef void (^FlutterResult)(id);
@interface FlutterMethodCall : NSObject
@property(nonatomic,copy) NSString* method;
@property(nonatomic,strong) id arguments;
@end
@interface FlutterError : NSObject
+(instancetype)errorWithCode:(NSString*)code message:(NSString*)message details:(id)details;
@end
@interface ImportProbe : NSObject
@property(atomic) BOOL wiimmfiImportActive;
@property(nonatomic, copy) NSDictionary<NSString*, id>* wiimmfiLastGame;
@property(nonatomic, assign) BOOL wiimmfiLastCoreConfigured;
@property(atomic) BOOL launchInProgress;
@property(atomic) BOOL stopInProgress;
@property(nonatomic,strong) UIViewController* dolphinController;
@property(nonatomic,strong) nw_path_monitor_t network;
- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result;
@end
@implementation ImportProbe { dispatch_queue_t _runtimeQueue; }
- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {
'''
    harness += bridge[start:end] + '\n}\n@end\n'
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'wiimmfi.mm'
        path.write_text(harness)
        subprocess.run(['xcrun', '--sdk', 'iphoneos', 'clang++', '-std=c++20',
                        '-target', 'arm64-apple-ios17.4', '-isysroot', sdk,
                        '-fobjc-arc', '-fblocks', '-fsyntax-only', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'packages/dolphin_internal_bridge/ios/Classes'), str(path)], check=True)
    print('PASS: Wiimmfi private storage/C ABI/import channel compile with iPhoneOS SDK')


if __name__ == '__main__':
    main()
