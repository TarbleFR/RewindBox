#!/usr/bin/env python3
"""Real UIKit/XCTest checks of the Dolphin external-display adapter in the iOS
Simulator (macOS CI: dolphin-motion-check).

Reuses the simulator/project harness of dolphin_account_267_test.py with the
production DolphinExternalDisplay.mm, DolphinFramePacing.mm and
DolphinSessionMenu.mm, plus the production NeoExternalDisplayCoordinator.m
and NeoExternalDisplayPreferences.m of the external_display pod, whose public
headers that harness stages as <external_display/…> exactly as the pod
publishes them. Build 442 injected the screen and the window into DolphinExternalDisplay
itself; since Build 447 the adapter owns neither, so the external window
comes from the coordinator's windowFactory seam and the application's own
scene stands in for the external one through sceneDidConnect:/
sceneDidDisconnect: (the coordinator's public test seams, as in
external_display_ui_test.py). Executed: the Metal-view move on start and
the return below the controls on stop, the global Off/Automatic/Fit/Fill/
Original placement and its live re-application, disconnection and
reconnection while the game runs, a stopped host ignoring a new screen,
MTKView drawable preservation, the Build 442 key read as a fallback and
never written, and the Display settings row writing the global keys. No
emulator runs; AirPlay itself remains an iPhone + Apple TV check.
"""
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

origin = ROOT / 'test/dolphin_account_267_test.py'
source = origin.read_text()
# The coordinator and the preferences the adapter and the Display row call,
# and the <external_display/…> search path of the pod's public headers, are
# the harness's own since Build 447 (EXTERNAL_SOURCES; since Build 484 every
# pod header, stage_dependency_headers of test/libretro_ios_syntax_test.py,
# and the cheat catalogue the menu shows, CATALOGUE_SOURCES): nothing is
# added here.
assert "EXTERNAL_CLASSES / 'NeoExternalDisplayCoordinator.m'" in source, 'the harness no longer compiles the pod sources; adapt'
assert "EXTERNAL_CLASSES / 'NeoExternalDisplayPreferences.m'" in source, 'the harness no longer compiles the pod sources; adapt'
assert 'include = stage_dependency_headers(directory)' in source, 'the harness no longer stages the pod headers; adapt'
assert 'CATALOGUE_SOURCES' in source, 'the harness no longer compiles the cheat catalogue; adapt'
source = source.replace("'CLANG_ENABLE_OBJC_ARC': 'YES',", "'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_CXX_LANGUAGE_STANDARD': 'c++20',")
source = source.replace("{'sdk': 'UIKit.framework'}", "{'sdk': 'CoreGraphics.framework'}, {'sdk': 'UniformTypeIdentifiers.framework'}, {'sdk': 'UIKit.framework'}")
source = source.replace('DolphinAccount267', 'DolphinExternalDisplay447').replace('DolphinAccountHost', 'DolphinExternalDisplayHost').replace('DolphinAccountTests', 'DolphinExternalDisplayTests')
source = source.replace('dolphin-account-tests-', 'dolphin-external-display-tests-')
ns = {'__file__': str(origin), '__name__': 'external_display_tests'}
exec(compile(source, str(origin), 'exec'), ns)
ns['TESTS'] = r'''
#import <XCTest/XCTest.h>
#import <MetalKit/MetalKit.h>
#import <external_display/NeoExternalDisplayCoordinator.h>
#import <external_display/NeoExternalDisplayPreferences.h>
#import "DolphinExternalDisplay.h"
#import "DolphinFramePacing.h"

// UIScreenDidDisconnectNotification (deprecated since iOS 16) is the only
// signal of the coordinator's legacy fallback, posted by resetCoordinator.
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

@interface ExternalDisplay447Tests : XCTestCase
@end
@implementation ExternalDisplay447Tests {
  NeoExternalDisplayCoordinator* _coordinator;
  UIView* _placeholder;
  UIView* _render;
  UIView* _overlay;
  UIWindow* _external;
  NSMutableArray<NSNumber*>* _states;
}
- (UIWindowScene*)mainScene {
  for (UIScene* scene in UIApplication.sharedApplication.connectedScenes)
    if ([scene isKindOfClass:UIWindowScene.class]) return (UIWindowScene*)scene;
  return nil;
}
- (void)clearDefaults {
  for (NSString* key in @[NeoExternalDisplayEnabledKey, NeoExternalDisplayModeKey, NeoExternalDisplayMenuOnTVKey, NeoExternalDisplayLegacyDolphinModeKey])
    [NSUserDefaults.standardUserDefaults removeObjectForKey:key];
}
/// The coordinator is a process-wide singleton: every test starts it from a
/// cold app (public seams first, then the private flags by KVC as
/// external_display_ui_test.py does).
- (void)resetCoordinator {
  NeoExternalDisplayCoordinator* c = NeoExternalDisplayCoordinator.shared;
  if (c.renderHost) [c detachRenderHost:c.renderHost];
  [c resumeAfterUnsupportedEngine];
  if (c.connected) {
    if ([c.sceneRole isEqualToString:@"scene"]) [c sceneDidDisconnect:[self mainScene]];
    else {
      c.legacyScreens = ^NSArray<UIScreen*>* { return @[]; };
      [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidDisconnectNotification object:nil];
    }
  }
  [c detachMenuViewController];
  c.menuProvider = nil; c.windowFactory = nil; c.legacyScreens = nil; c.stateChanged = nil;
  c.buildSDKMajorVersion = nil; c.screenScaleReader = nil;
  [c setValue:@NO forKey:@"sceneEverConnected"];
  [c setValue:@NO forKey:@"menuSuppressed"];
  [c setValue:nil forKey:@"lastState"];
  // The set of connected external scenes (Build 447 review, M1) starts empty.
  [c setValue:[NSMutableArray array] forKey:@"connectedExternalScenes"];
  [c setValue:[NSMutableArray array] forKey:@"automaticScenes"];
}
- (void)setUp {
  [self clearDefaults];
  [self resetCoordinator];
  _coordinator = NeoExternalDisplayCoordinator.shared;
  _placeholder = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 852, 393)];
  _render = [[UIView alloc] initWithFrame:_placeholder.bounds];
  _render.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  _overlay = [[UIView alloc] initWithFrame:_placeholder.bounds];
  [_placeholder addSubview:_render];
  [_placeholder addSubview:_overlay];
  _external = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 1920, 1080)];
  __weak UIWindow* window = _external;
  _coordinator.windowFactory = ^UIWindow*(UIWindowScene* scene, UIScreen* screen) { return window; };
  _states = [NSMutableArray array];
}
- (void)tearDown {
  [self resetCoordinator];
  [self clearDefaults];
  _external.hidden = YES;
}
- (UIView*)externalRoot { return _external.rootViewController.view; }
/// The application's scene stands in for the external one (public seam).
- (void)connect {
  UIWindowScene* scene = [self mainScene];
  XCTAssertNotNil(scene, @"the application scene stands in for the external one");
  [_coordinator sceneDidConnect:scene];
}
- (void)disconnect { [_coordinator sceneDidDisconnect:[self mainScene]]; }
- (DolphinExternalDisplay*)displayWithRender:(UIView*)render {
  DolphinExternalDisplay* display = [[DolphinExternalDisplay alloc] initWithRenderView:render placeholder:_placeholder];
  NSMutableArray* states = _states;
  display.stateChanged = ^(BOOL active) { [states addObject:@(active)]; };
  return display;
}

- (void)testStartMovesOnlyTheRenderViewAndStopReturnsItBelowTheControls {
  [self connect];
  XCTAssertTrue(_coordinator.connected);
  XCTAssertTrue(_external.hidden, @"nothing of NeoStation's to show yet (no menu engine here): iOS mirrors");
  DolphinExternalDisplay* display = [self displayWithRender:_render];
  XCTAssertTrue(display.fixedDrawable, @"Dolphin sized the drawable: transform only");
  XCTAssertEqual(display.renderView, _render);
  XCTAssertEqual(display.placeholderView, _placeholder);
  [display start];
  XCTAssertTrue(display.started);
  XCTAssertTrue(display.active);
  XCTAssertEqual(_coordinator.renderHost, (id)display, @"attached to the coordinator");
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame);
  XCTAssertEqualObjects(_states, @[@YES]);
  XCTAssertEqual(_render.superview, [self externalRoot], @"render view on the external window");
  XCTAssertEqual(_overlay.superview, _placeholder, @"controls stay on the phone");
  XCTAssertFalse(_external.hidden);
  XCTAssertFalse(_external.isKeyWindow, @"never key: the iPhone keeps the keys");
  // Retired 442 assertion "display.mode == Fit by default": the adapter has
  // no mode of its own; the global default is Automatic, which the
  // coordinator places as Fit, and DOLExternalDisplayPreference() says so.
  XCTAssertEqual(_coordinator.mode, NeoExternalDisplayModeAutomatic);
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFit, @"Automatic is Fit for a game");
  const CGFloat scale = DOLExternalDisplayScale(CGSizeMake(1920, 1080), CGSizeMake(852, 393), DOLExternalDisplayModeFit);
  XCTAssertEqualWithAccuracy(_render.transform.a, scale, 0.001);
  XCTAssertEqualWithAccuracy(_render.transform.d, scale, 0.001);
  XCTAssertEqualWithAccuracy(_render.bounds.size.width, 852, 0.001, @"the drawable keeps the iPhone size");
  XCTAssertEqualWithAccuracy(_render.bounds.size.height, 393, 0.001);
  XCTAssertEqualWithAccuracy(_render.center.x, 960, 0.001);
  XCTAssertEqualWithAccuracy(_render.center.y, 540, 0.001);
  [display start];
  XCTAssertEqualObjects(_states, @[@YES], @"a second start attaches nothing twice");
  [display stop];
  XCTAssertFalse(display.started);
  XCTAssertFalse(display.active);
  XCTAssertNil(_coordinator.renderHost, @"detached before the core would stop");
  XCTAssertEqual(_render.superview, _placeholder);
  XCTAssertEqual([_placeholder.subviews indexOfObject:_render], 0U, @"back below the controls");
  XCTAssertTrue(CGAffineTransformIsIdentity(_render.transform));
  XCTAssertTrue(CGRectEqualToRect(_render.frame, _placeholder.bounds));
  XCTAssertEqual(_render.autoresizingMask, UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight);
  XCTAssertEqualObjects(_states, (@[@YES, @NO]));
  // Retired 442 assertion "_external.hidden after stop because the window
  // was released": the window belongs to the coordinator and outlives the
  // session; it is hidden here only because nothing else is shown on it.
  XCTAssertTrue(_coordinator.connected, @"the window stays for the next game");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(_external.hidden);
  [display stop];
  XCTAssertEqualObjects(_states, (@[@YES, @NO]), @"a second stop is harmless");
  [display start];
  XCTAssertTrue(display.active, @"the same adapter can attach again (next game of the session)");
  XCTAssertEqual(_render.superview, [self externalRoot]);
  [display stop];
  XCTAssertEqualObjects(_states, (@[@YES, @NO, @YES, @NO]));
}

- (void)testDisabledPreferenceAndDisconnectReturnTheViewAndTheGlobalWritesReapply {
  // Retired 442 assertion: the Dolphin key 0 (Off) plus the Dolphin
  // notification; the switch is now the global Enabled key and every write
  // of NeoExternalDisplayPreferences re-applies through the coordinator.
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:NO]);
  [self connect];
  DolphinExternalDisplay* display = [self displayWithRender:_render];
  [display start];
  XCTAssertFalse(display.active, @"Off keeps system mirroring");
  XCTAssertEqual(_render.superview, _placeholder);
  XCTAssertEqual(_states.count, 0U);
  XCTAssertEqual(_coordinator.renderHost, (id)display, @"remembered for when the output is enabled");
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeOff);
  XCTAssertTrue(_coordinator.mirroringActive);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]);
  XCTAssertFalse(display.active, @"a mode alone does not enable the output");
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:YES]);
  XCTAssertTrue(display.active, @"the settings write applies at once");
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFill);
  const CGSize tv = CGSizeMake(1920, 1080), phone = CGSizeMake(852, 393);
  XCTAssertEqualWithAccuracy(_render.transform.a, DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeFill), 0.001);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeOriginal]);
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeOriginal);
  XCTAssertEqualWithAccuracy(_render.transform.a, 1920.0 / 852.0, 0.001, @"Original: the phone format bounded by the TV width");
  XCTAssertEqualWithAccuracy(_render.transform.a, DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeOriginal), 0.001);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeAutomatic]);
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFit);
  XCTAssertEqualWithAccuracy(_render.transform.a, DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeFit), 0.001);
  XCTAssertEqualObjects(_states, @[@YES], @"mode changes re-place the view without leaving the TV");
  [self disconnect];
  XCTAssertFalse(display.active, @"disconnect returns the view");
  XCTAssertTrue(display.started, @"the game still runs: the host stays attached");
  XCTAssertEqual(_render.superview, _placeholder);
  XCTAssertEqual([_placeholder.subviews indexOfObject:_render], 0U);
  XCTAssertEqualObjects(_states, (@[@YES, @NO]));
  [self connect];
  XCTAssertTrue(display.active, @"reconnect moves it again");
  XCTAssertEqual(_render.superview, [self externalRoot]);
  XCTAssertEqualObjects(_states, (@[@YES, @NO, @YES]));
  [display stop];
  XCTAssertEqualObjects(_states, (@[@YES, @NO, @YES, @NO]));
  [self disconnect];
  [self connect];
  XCTAssertFalse(display.active, @"stopped: a new screen does not take the view");
  XCTAssertEqual(_render.superview, _placeholder);
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
  [self connect];
  DolphinExternalDisplay* display = [self displayWithRender:metal];
  [display start];
  XCTAssertTrue(display.active);
  XCTAssertEqual(metal.superview, [self externalRoot]);
  XCTAssertFalse(metal.autoResizeDrawable, @"UIKit must not resize the drawable Dolphin sized");
  XCTAssertEqualWithAccuracy(metal.contentScaleFactor, 3, 0.001, @"layer scale preserved on a scale-1 screen");
  XCTAssertEqualWithAccuracy(metal.drawableSize.width, 2556, 0.5);
  XCTAssertEqualWithAccuracy(metal.drawableSize.height, 1179, 0.5);
  [display stop];
  XCTAssertTrue(metal.autoResizeDrawable, @"restored");
  XCTAssertEqualWithAccuracy(metal.contentScaleFactor, 3, 0.001);
  XCTAssertEqual(metal.superview, _placeholder);
  XCTAssertEqual([_placeholder.subviews indexOfObject:metal], 0U);
}

- (void)testBuild442KeyIsReadAsAFallbackAndNeverWrittenBack {
  NSUserDefaults* defaults = NSUserDefaults.standardUserDefaults;
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFit, @"nothing stored: Automatic, Fit for a game");
  [defaults setObject:@0 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeOff, @"442 Off → disabled until the global switch is used");
  [defaults setObject:@1 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFit, @"442 Fit");
  [defaults setObject:@2 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFill, @"442 Fill");
  [defaults setObject:@"2" forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFit, @"a non-number is ignored");
  [defaults setObject:@0 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeOriginal]);
  // Retired assertion "a stored global mode ends the fallback" right after
  // storeMode: (it turned a 442 Off user's output on). Choosing a format now
  // persists the derived Enabled value first (review of 12 October 2026,
  // m1): the output stays off and the stored Original applies once the
  // global switch is used.
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayEnabledKey], @NO, @"the derived Enabled value is persisted first");
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayModeKey], @3, @"the mode is stored");
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeOff, @"choosing a format never turns the output on");
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:YES]);
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeOriginal, @"a stored global mode ends the fallback");
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayLegacyDolphinModeKey], @0, @"the 442 key is never rewritten");
  [self connect];
  DolphinExternalDisplay* display = [self displayWithRender:_render];
  [display start];
  XCTAssertTrue(display.active);
  [display stop];
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayLegacyDolphinModeKey], @0, @"nor by the adapter");
}

- (void)testDisplaySettingsRowOffersTheGlobalModesInTwelveLanguagesAndWritesTheGlobalKeys {
  for (NSString* lang in @[@"en",@"fr",@"de",@"es",@"it",@"pt",@"ru",@"id",@"ja",@"ko",@"zh",@"zh_Hant"]) {
    for (NSString* key in @[@"external",@"externalOff",@"externalAutomatic",@"externalFit",@"externalFill",@"externalOriginal",
                            @"externalHelp",@"externalActive",@"externalNone",@"externalSaveFailed",@"hzDefaultHelp"])
      XCTAssertNotEqualObjects(DOLPacingText(key, lang), key, @"%@ %@", lang, key);
  }
  XCTAssertNotEqualObjects(DOLPacingText(@"externalOriginal", @"zh_Hant"), DOLPacingText(@"externalOriginal", @"zh"), @"traditional Chinese selected");
  XCTAssertEqualObjects(DOLPacingText(@"externalOriginal", @"zh-Hant-TW"), DOLPacingText(@"externalOriginal", @"zh_Hant"));
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
  // Retired 442 assertion "Fit by default": the global default is Automatic.
  XCTAssertTrue([row.detailTextLabel.text containsString:DOLPacingText(@"externalAutomatic", @"fr")], @"Automatic by default");
  XCTAssertTrue([row.detailTextLabel.text containsString:DOLPacingText(@"externalNone", @"fr")]);
  XCTAssertTrue([[page.tableView.dataSource tableView:page.tableView titleForFooterInSection:0] containsString:DOLPacingText(@"externalHelp", @"fr")]);
  XCTAssertTrue([[page.tableView.dataSource tableView:page.tableView titleForFooterInSection:0] containsString:DOLPacingText(@"hzDefaultHelp", @"fr")]);
  [page.tableView.delegate tableView:page.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
  UIAlertController* sheet = (id)page.presentedViewController;
  XCTAssertTrue([sheet isKindOfClass:UIAlertController.class]);
  // Retired 442 assertion "4 actions: Off, Fit, Fill, Cancel": the row offers
  // the global modes (docs/external-display-universal.md § 3.1).
  XCTAssertEqual(sheet.actions.count, 6U, @"Off, Automatic, Fit, Fill, Original, Cancel");
  NSArray<NSString*>* titles = @[DOLPacingText(@"externalOff", @"fr"), DOLPacingText(@"externalAutomatic", @"fr"), DOLPacingText(@"externalFit", @"fr"),
                                 DOLPacingText(@"externalFill", @"fr"), DOLPacingText(@"externalOriginal", @"fr"), DOLPacingText(@"cancel", @"fr")];
  for (NSUInteger i = 0; i < titles.count; i++) XCTAssertEqualObjects(sheet.actions[i].title, titles[i]);
  XCTAssertEqual(sheet.actions.lastObject.style, UIAlertActionStyleCancel);
  NSUserDefaults* defaults = NSUserDefaults.standardUserDefaults;
  __block NSUInteger notified = 0;
  // Retired 442 assertion: DOLExternalDisplayChangedNotification; the global
  // write tells the coordinator through NeoExternalDisplayChangedNotification.
  id token = [NSNotificationCenter.defaultCenter addObserverForName:NeoExternalDisplayChangedNotification object:nil queue:nil usingBlock:^(NSNotification* n) { notified += 1; }];
  void (^(^handler)(NSUInteger))(UIAlertAction*) = ^(NSUInteger index) { return (void (^)(UIAlertAction*))[sheet.actions[index] valueForKey:@"handler"]; };
  handler(3)(sheet.actions[3]);
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayModeKey], @2, @"Fill written to the global key");
  XCTAssertNil([defaults objectForKey:NeoExternalDisplayLegacyDolphinModeKey], @"the 442 Dolphin key is never written");
  XCTAssertEqual(notified, 1U, @"enabled already: one verified write, one notification");
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFill);
  row = [page.tableView.dataSource tableView:page.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
  XCTAssertTrue([row.detailTextLabel.text containsString:DOLPacingText(@"externalFill", @"fr")], @"the row shows the stored value");
  handler(0)(sheet.actions[0]);
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayEnabledKey], @NO, @"Off is the global Enabled switch");
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayModeKey], @2, @"Off keeps the mode for later");
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeOff);
  XCTAssertEqual(notified, 2U);
  row = [page.tableView.dataSource tableView:page.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
  XCTAssertTrue([row.detailTextLabel.text containsString:DOLPacingText(@"externalOff", @"fr")]);
  handler(4)(sheet.actions[4]);
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayModeKey], @3, @"Original");
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayEnabledKey], @YES, @"a mode choice turns the output on again");
  XCTAssertEqual(notified, 4U, @"mode then enabled: two verified writes");
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeOriginal);
  handler(1)(sheet.actions[1]);
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayModeKey], @0, @"Automatic");
  XCTAssertEqual(DOLExternalDisplayPreference(), DOLExternalDisplayModeFit);
  XCTAssertNil(page.navigationItem.prompt, @"every write was kept: nothing to say");
  [NSNotificationCenter.defaultCenter removeObserver:token];
  pacing.externalDisplayActive = YES;
  row = [page.tableView.dataSource tableView:page.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:3 inSection:0]];
  XCTAssertTrue([row.detailTextLabel.text containsString:DOLPacingText(@"externalActive", @"fr")], @"the row says the game is on the TV");
  NSDictionary* summary = pacing.summary;
  XCTAssertEqualObjects(summary[@"externalDisplayMode"], @(DOLExternalDisplayModeFit));
  XCTAssertEqualObjects(summary[@"externalDisplayGlobalMode"], @(NeoExternalDisplayModeAutomatic));
  XCTAssertEqualObjects(summary[@"externalDisplayEnabled"], @YES);
  XCTAssertEqualObjects(summary[@"externalDisplayActive"], @YES);
  pacing.externalDisplayActive = NO;
  XCTestExpectation* dismissed = [self expectationWithDescription:@"dismissed"];
  [sheet dismissViewControllerAnimated:NO completion:^{
    [host.rootViewController dismissViewControllerAnimated:NO completion:^{ [dismissed fulfill]; }];
  }];
  [self waitForExpectations:@[dismissed] timeout:5];
  // The 60 Hz default and the trace summary carry the Build 442 fields.
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
if platform.system() != 'Darwin':
    print('SKIP: the Dolphin external display simulator harness needs macOS/Xcode; sources composed, no test executed')
    raise SystemExit(0)
ns['native']()
print('PASS: external display move/return through the coordinator, global Off/Automatic/Fit/Fill/Original, disconnect and reconnect, '
      'stopped host, MTKView drawable preservation, Build 442 key fallback, settings row writing the global keys, '
      '60 Hz default and frame-time counters executed on the iOS Simulator')
