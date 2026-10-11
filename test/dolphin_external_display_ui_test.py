#!/usr/bin/env python3
"""Real UIKit/XCTest checks of the Build 442 external-display output in the iOS
Simulator (macOS CI: dolphin-motion-check).

Reuses the simulator/project harness of dolphin_account_267_test.py with the
production DolphinExternalDisplay.mm, DolphinFramePacing.mm and
DolphinSessionMenu.mm. The external screen is a seam (any UIScreen) and the
window a factory, so the Metal-view move, the Off/Fit/Fill placement, the
disconnect/stop return path and the Display settings row execute without an
Apple TV. No emulator runs; AirPlay itself remains an iPhone + Apple TV check.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
origin = ROOT / 'test/dolphin_account_267_test.py'
source = origin.read_text().replace("'CLANG_ENABLE_OBJC_ARC': 'YES',", "'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_CXX_LANGUAGE_STANDARD': 'c++20',")
source = source.replace("{'sdk': 'UIKit.framework'}", "{'sdk': 'UniformTypeIdentifiers.framework'}, {'sdk': 'UIKit.framework'}")
source = source.replace('DolphinAccount267', 'DolphinExternalDisplay442').replace('DolphinAccountHost', 'DolphinExternalDisplayHost').replace('DolphinAccountTests', 'DolphinExternalDisplayTests')
source = source.replace('dolphin-account-tests-', 'dolphin-external-display-tests-')
ns = {'__file__': str(origin), '__name__': 'external_display_tests'}
exec(compile(source, str(origin), 'exec'), ns)
ns['TESTS'] = r'''
#import <XCTest/XCTest.h>
#import <MetalKit/MetalKit.h>
#import "DolphinExternalDisplay.h"
#import "DolphinFramePacing.h"
static char kScreensSetterKey;
@interface ExternalDisplay442Tests : XCTestCase
@end
@implementation ExternalDisplay442Tests {
  UIView* _placeholder;
  UIView* _render;
  UIView* _overlay;
  UIWindow* _external;
  NSMutableArray<NSNumber*>* _states;
}
- (void)setUp {
  [NSUserDefaults.standardUserDefaults removeObjectForKey:DOLExternalDisplayModeKey];
  _placeholder = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 852, 393)];
  _render = [[UIView alloc] initWithFrame:_placeholder.bounds];
  _render.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  _overlay = [[UIView alloc] initWithFrame:_placeholder.bounds];
  [_placeholder addSubview:_render];
  [_placeholder addSubview:_overlay];
  _external = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 1920, 1080)];
  _states = [NSMutableArray array];
}
- (void)tearDown {
  [NSUserDefaults.standardUserDefaults removeObjectForKey:DOLExternalDisplayModeKey];
  _external.hidden = YES;
}
- (DolphinExternalDisplay*)displayWithScreens:(NSArray<UIScreen*>*)screens {
  DolphinExternalDisplay* display = [[DolphinExternalDisplay alloc] initWithRenderView:_render placeholder:_placeholder];
  __block NSArray<UIScreen*>* current = screens;
  display.externalScreens = ^NSArray<UIScreen*>* { return current; };
  __weak UIWindow* window = _external;
  display.windowFactory = ^UIWindow*(UIScreen* screen) { return window; };
  NSMutableArray* states = _states;
  display.stateChanged = ^(BOOL active) { [states addObject:@(active)]; };
  objc_setAssociatedObject(display, &kScreensSetterKey, ^(NSArray<UIScreen*>* next) { current = next; }, OBJC_ASSOCIATION_COPY);
  return display;
}
- (void (^)(NSArray<UIScreen*>*))screensSetter:(DolphinExternalDisplay*)display {
  return objc_getAssociatedObject(display, &kScreensSetterKey);
}
- (void)testFitMovesOnlyTheRenderViewAndKeepsTheControlsOnThePhone {
  DolphinExternalDisplay* display = [self displayWithScreens:@[UIScreen.mainScreen]];
  [display start];
  XCTAssertTrue(display.active);
  XCTAssertEqual(display.mode, DOLExternalDisplayModeFit, @"Fit is the default");
  XCTAssertEqualObjects(_states, @[@YES]);
  XCTAssertEqual(_render.superview, _external.rootViewController.view, @"render view on the external window");
  XCTAssertEqual(_overlay.superview, _placeholder, @"controls stay on the phone");
  XCTAssertFalse(_external.hidden);
  const CGFloat scale = DOLExternalDisplayScale(CGSizeMake(1920, 1080), CGSizeMake(852, 393), DOLExternalDisplayModeFit);
  XCTAssertEqualWithAccuracy(_render.transform.a, scale, 0.001);
  XCTAssertEqualWithAccuracy(_render.transform.d, scale, 0.001);
  XCTAssertEqualWithAccuracy(_render.bounds.size.width, 852, 0.001, @"the drawable keeps the iPhone size");
  XCTAssertEqualWithAccuracy(_render.bounds.size.height, 393, 0.001);
  XCTAssertEqualWithAccuracy(_render.center.x, 960, 0.001);
  XCTAssertEqualWithAccuracy(_render.center.y, 540, 0.001);
  [display stop];
  XCTAssertFalse(display.active);
  XCTAssertEqual(_render.superview, _placeholder);
  XCTAssertEqual([_placeholder.subviews indexOfObject:_render], 0U, @"back below the controls");
  XCTAssertTrue(CGAffineTransformIsIdentity(_render.transform));
  XCTAssertTrue(CGRectEqualToRect(_render.frame, _placeholder.bounds));
  XCTAssertEqual(_render.autoresizingMask, UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight);
  XCTAssertTrue(_external.hidden);
  XCTAssertEqualObjects(_states, (@[@YES, @NO]));
}
- (void)testOffPreferenceAndDisconnectReturnTheViewAndNotificationReapplies {
  [NSUserDefaults.standardUserDefaults setObject:@0 forKey:DOLExternalDisplayModeKey];
  DolphinExternalDisplay* display = [self displayWithScreens:@[UIScreen.mainScreen]];
  [display start];
  XCTAssertFalse(display.active, @"Off keeps system mirroring");
  XCTAssertEqual(_render.superview, _placeholder);
  XCTAssertEqual(_states.count, 0U);
  [NSUserDefaults.standardUserDefaults setObject:@2 forKey:DOLExternalDisplayModeKey];
  [NSNotificationCenter.defaultCenter postNotificationName:DOLExternalDisplayChangedNotification object:nil];
  XCTAssertTrue(display.active, @"the settings notification applies the new mode");
  XCTAssertEqual(display.mode, DOLExternalDisplayModeFill);
  const CGFloat fill = DOLExternalDisplayScale(CGSizeMake(1920, 1080), CGSizeMake(852, 393), DOLExternalDisplayModeFill);
  XCTAssertEqualWithAccuracy(_render.transform.a, fill, 0.001);
  [self screensSetter:display](@[]);
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidDisconnectNotification object:nil];
  XCTAssertFalse(display.active, @"disconnect returns the view");
  XCTAssertEqual(_render.superview, _placeholder);
  XCTAssertEqualObjects(_states, (@[@YES, @NO]));
  [self screensSetter:display](@[UIScreen.mainScreen]);
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidConnectNotification object:nil];
  XCTAssertTrue(display.active, @"reconnect moves it again");
  [display stop];
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidConnectNotification object:nil];
  XCTAssertFalse(display.active, @"stopped: notifications are ignored");
  XCTAssertEqualObjects(_states, (@[@YES, @NO, @YES, @NO]));
}
- (void)testMetalViewKeepsItsDrawableSizeAndScaleAcrossTheMove {
  id<MTLDevice> device = MTLCreateSystemDefaultDevice();
  if (!device) { NSLog(@"No Metal device in this simulator; MTKView move not exercised"); return; }
  MTKView* metal = [[MTKView alloc] initWithFrame:_placeholder.bounds device:device];
  metal.paused = YES; metal.enableSetNeedsDisplay = NO;
  metal.contentScaleFactor = 3;
  metal.drawableSize = CGSizeMake(2556, 1179);
  [_render removeFromSuperview];
  [_placeholder insertSubview:metal atIndex:0];
  DolphinExternalDisplay* display = [[DolphinExternalDisplay alloc] initWithRenderView:metal placeholder:_placeholder];
  display.externalScreens = ^NSArray<UIScreen*>* { return @[UIScreen.mainScreen]; };
  __weak UIWindow* window = _external;
  display.windowFactory = ^UIWindow*(UIScreen* screen) { return window; };
  [display start];
  XCTAssertTrue(display.active);
  XCTAssertFalse(metal.autoResizeDrawable, @"UIKit must not resize the drawable Dolphin sized");
  XCTAssertEqualWithAccuracy(metal.contentScaleFactor, 3, 0.001, @"layer scale preserved on a scale-1 screen");
  XCTAssertEqualWithAccuracy(metal.drawableSize.width, 2556, 0.5);
  XCTAssertEqualWithAccuracy(metal.drawableSize.height, 1179, 0.5);
  [display stop];
  XCTAssertTrue(metal.autoResizeDrawable, @"restored");
  XCTAssertEqualWithAccuracy(metal.contentScaleFactor, 3, 0.001);
  XCTAssertEqual(metal.superview, _placeholder);
}
- (void)testDisplaySettingsRowOffersOffFitFillInTwelveLanguagesAndWritesThePreference {
  for (NSString* lang in @[@"en",@"fr",@"de",@"es",@"it",@"pt",@"ru",@"id",@"ja",@"ko",@"zh",@"zh_Hant"]) {
    for (NSString* key in @[@"external",@"externalOff",@"externalFit",@"externalFill",@"externalHelp",@"externalActive",@"externalNone",@"hzDefaultHelp"])
      XCTAssertNotEqualObjects(DOLPacingText(key, lang), key, @"%@ %@", lang, key);
  }
  DolphinFramePacing* pacing = [DolphinFramePacing new]; pacing.locale = @"fr";
  UITableViewController* page = (id)[pacing settingsController];
  UIWindow* host = [(id)UIApplication.sharedApplication.delegate window];
  UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:page];
  XCTestExpectation* presented = [self expectationWithDescription:@"settings"];
  [host.rootViewController presentViewController:navigation animated:NO completion:^{ [presented fulfill]; }];
  [self waitForExpectations:@[presented] timeout:5];
  XCTAssertEqual([page.tableView.dataSource tableView:page.tableView numberOfRowsInSection:0], 6);
  UITableViewCell* row = [page.tableView.dataSource tableView:page.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
  XCTAssertEqualObjects(row.textLabel.text, DOLPacingText(@"external", @"fr"));
  XCTAssertTrue([row.detailTextLabel.text containsString:DOLPacingText(@"externalFit", @"fr")], @"Fit by default");
  XCTAssertTrue([row.detailTextLabel.text containsString:DOLPacingText(@"externalNone", @"fr")]);
  XCTAssertTrue([[page.tableView.dataSource tableView:page.tableView titleForFooterInSection:0] containsString:DOLPacingText(@"externalHelp", @"fr")]);
  XCTAssertTrue([[page.tableView.dataSource tableView:page.tableView titleForFooterInSection:0] containsString:DOLPacingText(@"hzDefaultHelp", @"fr")]);
  [page.tableView.delegate tableView:page.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
  UIAlertController* sheet = (id)page.presentedViewController;
  XCTAssertTrue([sheet isKindOfClass:UIAlertController.class]);
  XCTAssertEqual(sheet.actions.count, 4U, @"Off, Fit, Fill, Cancel");
  XCTAssertEqualObjects(sheet.actions[2].title, DOLPacingText(@"externalFill", @"fr"));
  __block BOOL notified = NO;
  id token = [NSNotificationCenter.defaultCenter addObserverForName:DOLExternalDisplayChangedNotification object:nil queue:nil usingBlock:^(NSNotification* n) { notified = YES; }];
  void (^handler)(UIAlertAction*) = [sheet.actions[2] valueForKey:@"handler"];
  handler(sheet.actions[2]);
  [NSNotificationCenter.defaultCenter removeObserver:token];
  XCTAssertEqualObjects([NSUserDefaults.standardUserDefaults objectForKey:DOLExternalDisplayModeKey], @2);
  XCTAssertTrue(notified, @"the live session is told to re-apply");
  XCTestExpectation* dismissed = [self expectationWithDescription:@"dismissed"];
  [sheet dismissViewControllerAnimated:NO completion:^{
    [host.rootViewController dismissViewControllerAnimated:NO completion:^{ [dismissed fulfill]; }];
  }];
  [self waitForExpectations:@[dismissed] timeout:5];
  // The 60 Hz default and the trace summary carry the new fields.
  [NSUserDefaults.standardUserDefaults removeObjectForKey:@"NeoStation.Dolphin.DisplayTrial.Refresh"];
  XCTAssertEqualObjects(pacing.summary[@"preferenceHz"], @60, @"Build 442 default display rate");
  [pacing recordFrameTimeMs:16.7]; [pacing recordFrameTimeMs:31]; [pacing recordFrameTimeMs:64]; [pacing recordFrameTimeMs:0]; [pacing recordFrameTimeMs:NAN];
  NSDictionary* frames = [pacing frameTimeSummary];
  XCTAssertEqualObjects(frames[@"frameSampleTotal"], @3);
  XCTAssertEqualObjects(frames[@"slowSampleTotal"], @2);
  XCTAssertEqualObjects(frames[@"verySlowSampleTotal"], @1);
  XCTAssertEqualWithAccuracy([frames[@"worstFrameTimeMs"] doubleValue], 64, 0.001);
  UIView* view = [UIView new];
  [pacing startWithView:view];
  [pacing appendPerformance:@{@"fps": @60} inputMs:0 refreshed:NO];
  NSDictionary* last = pacing.samples.lastObject;
  XCTAssertEqualObjects(last[@"frameSamples"], @3);
  XCTAssertEqualWithAccuracy([last[@"frameTimeMaxMs"] doubleValue], 64, 0.001);
  XCTAssertEqualWithAccuracy([last[@"frameTimeMinMs"] doubleValue], 16.7, 0.001);
  XCTAssertEqualObjects(last[@"slowSamples"], @2);
  XCTAssertTrue([last[@"memoryFootprintMB"] doubleValue] > 0);
  [pacing appendPerformance:@{@"fps": @60} inputMs:0 refreshed:NO];
  XCTAssertEqualObjects(pacing.samples.lastObject[@"frameSamples"], @0, @"interval counters reset per row");
  XCTAssertEqualObjects(pacing.summary[@"frameSampleTotal"], @3, @"session totals persist");
  [pacing stop];
}
@end
'''
ns['APP'] = ns['APP'].replace('#import <UIKit/UIKit.h>', '#import <UIKit/UIKit.h>\n#import <objc/runtime.h>')
ns['TESTS'] = '#import <objc/runtime.h>\n' + ns['TESTS']
ns['native']()
print('PASS: external display move/return, Off/Fit/Fill, disconnect, MTKView drawable preservation, settings row, 60 Hz default and frame-time counters executed on the iOS Simulator')
