#!/usr/bin/env python3
"""Run the changed UIKit material and native power stream in the iOS Simulator.

Reuse the existing real-Flutter UI refresh harness. The display-rate hook itself
is unchanged; its small original regression set also protects the modified
plugin registration. No emulator, download, game or physical-device claim.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import ui_refresh_rate_hook_test as harness

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / 'packages/neo_cheat_catalog/ios/Classes/RBLiquidProgressView.m'
HEADER = VIEW.parent / 'Public/RBLiquidProgressView.h'
TESTS = r'''
- (void)testLiquidMeasurementsPauseFailureAndUnknownDuration {
  UIView *root = UIApplication.sharedApplication.keyWindow.rootViewController.view;
  if (!root) root = UIApplication.sharedApplication.windows.firstObject.rootViewController.view;
  XCTAssertNotNil(root);
  NSMutableArray *views = [NSMutableArray array];
  NSArray *amounts = @[@0, @.37, @.63, @1, @0];
  for (NSUInteger i = 0; i < amounts.count; i++) {
    RBLiquidProgressView *view = [[RBLiquidProgressView alloc] initWithFrame:CGRectMake(20, 40 + i * 30, 280, 14)];
    view.progress = [amounts[i] doubleValue];
    view.status = i == 1 ? RBLiquidProgressPaused : i == 2 ? RBLiquidProgressError : i == 3 ? RBLiquidProgressSuccess : RBLiquidProgressRunning;
    view.indeterminate = i == 4;
    [root addSubview:view]; [views addObject:view];
    [view liquidTick:100.5]; [view layoutIfNeeded];
    XCTAssertEqualWithAccuracy(view.progress, [amounts[i] doubleValue], .000001);
    if (i == 1 || i == 2 || i == 3) XCTAssertFalse(view.wantsLiquidMotion);
  }
  RBLiquidProgressView *paused = views[1];
  paused.status = RBLiquidProgressRunning;
  XCTAssertEqualWithAccuracy(paused.progress, .37, .000001);
  paused.progress = .12;
  XCTAssertEqualWithAccuracy(paused.progress, .12, .000001);
  paused.progress = NAN;
  XCTAssertEqual(paused.progress, 0);
  paused.indeterminate = YES;
  paused.status = RBLiquidProgressPaused;
  XCTAssertFalse(paused.wantsLiquidMotion);
  UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(320, 220)];
  UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
    [UIColor.blackColor setFill]; UIRectFill(CGRectMake(0, 0, 320, 220));
    [root.layer renderInContext:context.CGContext];
  }];
  XCTAttachment *attachment = [XCTAttachment attachmentWithImage:image];
  attachment.name = @"Production UIKit liquid states";
  attachment.lifetime = XCTAttachmentLifetimeKeepAlways;
  [self addAttachment:attachment];
  for (UIView *view in views) [view removeFromSuperview];
}

- (void)testPowerNotificationsUseRealBooleanAndCancelTheObserver {
  id<FlutterStreamHandler> plugin = (id<FlutterStreamHandler>)[UiRefreshRatePlugin new];
  NSMutableArray *values = [NSMutableArray array];
  XCTAssertNil([plugin onListenWithArguments:nil eventSink:^(id value) { [values addObject:value]; }]);
  XCTAssertEqual(values.count, 1u);
  XCTAssertEqual(CFGetTypeID((__bridge CFTypeRef)values.lastObject), CFBooleanGetTypeID());
  XCTAssertEqualObjects(values.lastObject, NSProcessInfo.processInfo.lowPowerModeEnabled ? @YES : @NO);
  [NSNotificationCenter.defaultCenter postNotificationName:NSProcessInfoPowerStateDidChangeNotification object:nil];
  XCTAssertEqual(values.count, 2u);
  XCTAssertNil([plugin onCancelWithArguments:nil]);
  [NSNotificationCenter.defaultCenter postNotificationName:NSProcessInfoPowerStateDidChangeNotification object:nil];
  XCTAssertEqual(values.count, 2u);
}
'''

def main():
    output = ROOT / 'build/motion-native'
    output.mkdir(parents=True, exist_ok=True)
    includes = output / 'headers/neo_cheat_catalog'
    includes.mkdir(parents=True, exist_ok=True)
    (includes / HEADER.name).write_bytes(HEADER.read_bytes())
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    for source in [VIEW.parent / 'NeoUnifiedCheatBrowser.m', ROOT / 'packages/neo_texture_catalog/ios/Classes/NeoTextureHDPage.m']:
        subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-fmodules', '-fsyntax-only',
            '-target', 'arm64-apple-ios18.0', '-isysroot', sdk, '-I', str(includes.parent), str(source)], check=True)
    harness.SOURCES.append(VIEW)
    harness.TESTS = '#import "' + str(HEADER) + '"\n' + harness.TESTS
    position = harness.TESTS.rfind('@end')
    harness.TESTS = harness.TESTS[:position] + TESTS + harness.TESTS[position:]
    harness.native()
    result = ROOT / 'build/ui-refresh-rate/UiRefreshRate440.xcresult'
    summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], text=True)
    (output / 'summary.json').write_text(summary)
    subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(result), '--output-path', str(output / 'attachments')], check=True)
    sources = [VIEW, HEADER, ROOT / 'packages/ui_refresh_rate/ios/Classes/UiRefreshRatePlugin.m',
        VIEW.parent / 'NeoUnifiedCheatBrowser.m', ROOT / 'packages/neo_texture_catalog/ios/Classes/NeoTextureHDPage.m']
    (output / 'receipt.json').write_text(json.dumps({
        'result':'passed', 'source':subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'iphoneSdkTypecheck':True, 'simulatorExecuted':True, 'deviceTested':False,
    }, indent=2)+'\n')

if __name__ == '__main__': main()
