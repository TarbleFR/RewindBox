#!/usr/bin/env python3
"""Targeted native catalogue checks. No emulator recompilation or device claim."""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ARMS=ROOT/'packages/armsx2_internal_bridge/ios/Classes'
DOL=ROOT/'packages/dolphin_internal_bridge/ios/Classes'
RPC=ROOT/'packages/rpcs3_internal_bridge/ios/Classes'
def run(command):
    subprocess.run([str(x) for x in command],check=True,cwd=ROOT)

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rpcs3-store-only',action='store_true',
                    help='Check only the changed RPCS3 store with the iPhone SDK, then execute the Foundation store regression tests.')
parser.add_argument('--menus-only',action='store_true',help='Compile only the two changed direct PS2/Dolphin menu adapters.')
args=parser.parse_args()

with tempfile.TemporaryDirectory(prefix='unified-native-') as tmp:
    work=Path(tmp)
    if not args.rpcs3_store_only and not args.menus_only:
        compiler=shutil.which('clang++') or shutil.which('g++')
        assert compiler,'A C++ compiler is required'
        exe=work/'programs'
        run([compiler,'-std=c++20','-Wall','-Wextra','-Werror','-I',ARMS,ROOT/'test/unified_native_programs_test.cpp','-o',exe])
        run([exe])
        for name in ('NeoUnifiedNativeProgram.h','NeoUnifiedNativeImport.h'):
            assert (ARMS/name).read_bytes()==(DOL/name).read_bytes()
        # Check all newly introduced RPCS3 labels in the actual twelve-language
        # catalogue, including the Traditional Chinese selection path.
        labels=(RPC/'RPCS3UnifiedCheatLabels.h').read_text()
        rows=re.findall(r'@"([A-Za-z_]+)":@\{([^}]+)\}',labels)
        assert {lang for lang,_ in rows}=={'en','fr','de','es','it','pt','ru','id','ja','ko','zh','zh_Hant'}
        keys=None
        for lang,row in rows:
            this=set(re.findall(r'@"([A-Za-z]+)":',row)); keys=keys or this
            assert keys==this and len(this)==5,lang
        assert 'RPCS3CanonicalLocale(locale)' in labels
    if sys.platform!='darwin':
        print('SKIP: RPCS3 store SDK/Foundation checks require macOS.' if args.rpcs3_store_only else
              'SKIP: Apple SDK syntax checks and Foundation store execution require macOS; portable native checks passed.')
        sys.exit(0)
    if args.rpcs3_store_only:
        include=work/'include';include.mkdir()
    else:
        from libretro_ios_syntax_test import stage_dependency_headers,public_headers
        include=stage_dependency_headers(work)
        staged=include/'neo_swap';staged.mkdir(exist_ok=True)
        for header in public_headers('neo_swap',ROOT/'packages/neo_swap/ios'):
            shutil.copyfile(header,staged/header.name)
        # Build 484: the three menus and plugins import <neo_touch_layout/...>.
        from touch_layout_support import stage_touch_layout
        stage_touch_layout(include)
        # The plugin uses declarations exported by this unchanged Swift class.
        swift=include/'dolphin_internal_bridge';swift.mkdir()
        (swift/'dolphin_internal_bridge-Swift.h').write_text('''#import <UIKit/UIKit.h>
@interface DOLTouchOverlay : UIView
- (instancetype)initWithWii:(BOOL)wii;
@property(nonatomic) BOOL sessionInputActive;
@property(nonatomic,copy) NSString* shakeAccessibilityLabel;
@property(nonatomic,copy) NSString* shakeAccessibilityHint;
- (void)refreshPhoneShakeRouting;
- (void)updateExtension:(NSString*)name;
// Build 484 touch layouts.
@property(nonatomic,copy) void (^layoutPassHandler)(BOOL);
@property(nonatomic) BOOL touchLayoutEditing;
@property(nonatomic) BOOL shakeHiddenByLayout;
@property(nonatomic,readonly) NSString* touchLayoutKey;
@property(nonatomic,readonly) UIView* touchLayoutShakeControl;
- (NSArray<UIView*>*)touchLayoutControls;
- (NSString*)touchLayoutIdentifier:(UIView*)control;
- (NSInteger)touchLayoutKind:(UIView*)control;
- (NSString*)touchLayoutName:(UIView*)control;
- (void)cancelTouchInteractions;
@end
''')
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    base=['xcrun','--sdk','iphoneos','clang++','-target','arm64-apple-ios17.4','-isysroot',sdk,
          '-std=c++20','-fobjc-arc','-fblocks','-fmodules','-Wno-unused-function','-fsyntax-only',
          '-I',include,'-I',ROOT/'test/libretro_host/stubs','-I',ARMS,'-I',DOL,'-I',RPC]
    sources=[RPC/'RPCS3UnifiedCheats.mm'] if args.rpcs3_store_only else [
        ARMS/'Armsx2SessionMenu.mm',ARMS/'Armsx2InternalBridgePlugin.mm',
        DOL/'DolphinSessionMenu.mm',DOL/'DolphinInternalBridgePlugin.mm',
        RPC/'Rpcs3SessionMenu.mm',RPC/'Rpcs3InternalBridgePlugin.mm',RPC/'RPCS3UnifiedCheats.mm']
    if args.menus_only: sources=[ARMS/'Armsx2SessionMenu.mm',DOL/'DolphinSessionMenu.mm',RPC/'Rpcs3SessionMenu.mm',RPC/'Rpcs3InternalBridgePlugin.mm']
    for source in sources:
        run([*base,source]);print('PASS iPhone SDK syntax:',source.relative_to(ROOT),flush=True)
    if args.menus_only:
        print('PASS: both changed direct menu adapters compile with the actual iPhone SDK.',flush=True)
        sys.exit(0)
    host_sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
    store=work/'store'
    run(['xcrun','--sdk','macosx','clang++','-std=c++20','-fobjc-arc','-fblocks','-isysroot',host_sdk,
         '-I',ARMS,'-I',RPC,ROOT/'test/unified_native_store_test.mm',RPC/'RPCS3UnifiedCheats.mm',
         '-framework','Foundation','-o',store])
    run([store])
print('PASS: changed RPCS3 store compiles with the iPhone SDK; Foundation store behaviours executed.' if args.rpcs3_store_only else
      'PASS: changed native menus/plugins compile with real Apple SDKs; Foundation store behaviours executed.')
