#!/usr/bin/env python3
"""Real UIKit/XCTest checks of the Wii touch Shake control and the Controls
menu Shake row in the iOS Simulator (macOS CI: dolphin-motion-check).

The host app compiles the production TouchController Swift sources,
DolphinSessionMenu.mm and its dependencies. TCManagerInterface is a stub that
records every touch input written for the emulator, and the donor nibs (not in
git) are replaced by small code-built pads with the same right column
(Nunchuk Z, B, A). The translated texts come from lib/l10n/dolphin_shake_locale.dart.
No emulator runs: game acceptance of the shake remains an iPhone check.
"""
from pathlib import Path
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
TOUCH = CLASSES / 'TouchController'
HOST = 'DolphinTouchShakeHost'
# Build 447: DolphinExternalDisplay.mm and DolphinFramePacing.mm import the
# external_display pod as <external_display/...> and call its coordinator and
# preferences. The host compiles the pod's Flutter-free sources and searches
# its public headers, staged by test/libretro_ios_syntax_test.py exactly as
# the pod publishes them (as dolphin_account_267_test.py does).
EXTERNAL_CLASSES = ROOT / 'packages/external_display/ios/Classes'
EXTERNAL_SOURCES = [EXTERNAL_CLASSES / 'NeoExternalDisplayCoordinator.m',
                    EXTERNAL_CLASSES / 'NeoExternalDisplayPreferences.m']
# Build 474: DolphinSessionMenu.mm imports the unified cheat catalogue pod as
# <neo_cheat_catalog/...>; the host compiles its Flutter-free sources (zlib)
# and searches the public headers of every pod the bridge depends on.
CATALOGUE_CLASSES = ROOT / 'packages/neo_cheat_catalog/ios/Classes'
CATALOGUE_SOURCES = sorted(path for path in CATALOGUE_CLASSES.glob('*.m') if path.name != 'NeoCheatCatalogPlugin.m')
sys.path.insert(0, str(ROOT / 'test'))
from libretro_ios_syntax_test import stage_dependency_headers  # noqa: E402

APP = r'''
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#import <objc/runtime.h>
#import "TouchController/TCManagerInterface.h"

// Every touch input the overlay writes: port, input, state, time, main thread.
static NSMutableArray<NSArray*>* DOLTestEventStore(void) {
  static NSMutableArray* events;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ events = [NSMutableArray array]; });
  return events;
}
// Called by the test bundle (BUNDLE_LOADER); also used below so the linker keeps them.
__attribute__((used, visibility("default"))) NSArray<NSArray*>* DOLTestTouchEvents(void) {
  @synchronized(DOLTestEventStore()) { return [DOLTestEventStore() copy]; }
}
__attribute__((used, visibility("default"))) void DOLTestResetTouchEvents(void) {
  @synchronized(DOLTestEventStore()) { [DOLTestEventStore() removeAllObjects]; }
}

@implementation TCManagerInterface
+ (void)setButtonStateFor:(NSInteger)button controller:(NSInteger)controllerId state:(BOOL)state {
  @synchronized(DOLTestEventStore()) {
    [DOLTestEventStore() addObject:@[@(controllerId), @(button), @(state ? 1 : 0),
                                     @(CACurrentMediaTime()), @(NSThread.isMainThread)]];
  }
}
+ (void)setAxisValueFor:(NSInteger)axis controller:(NSInteger)controllerId value:(float)value {}
+ (BOOL)preparePhoneShakeRouting { return YES; }
+ (NSInteger)phoneShakeRoutingStatus { return 0; }
+ (void)reportPhoneShakeSensorUnavailable {}
@end

// The donor TouchResources nibs are not in git. Build equivalent pads: the
// Wii right column (Nunchuk Z 201, B 101, A 100) anchored bottom-right, plus
// two centre buttons, all production TCButton instances.
static UIView* DOLTestPad(NSString* name) {
  UIView* root = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 844, 390)];
  root.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  Class buttonClass = NSClassFromString(@"DolphinTouchShakeHost.TCButton");
  if (!buttonClass) return root;
  NSArray* layout = [name isEqual:@"TCGameCubePad"] ? @[@[@0, @713, @265], @[@1, @634, @234]]
      : @[@[@201, @713, @77], @[@101, @713, @161], @[@100, @713, @265], @[@102, @634, @150], @[@105, @634, @234]];
  for (NSArray* item in layout) {
    UIButton* button = [[buttonClass alloc] initWithFrame:CGRectMake([item[1] doubleValue], [item[2] doubleValue], 64, 64)];
    button.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleTopMargin;
    [button setValue:item[0] forKey:@"controllerButton"];
    [root addSubview:button];
  }
  return root;
}

static IMP s_loadNib;
static NSArray* DOLTestLoadNib(id bundle, SEL command, NSString* name, id owner, NSDictionary* options) {
  if ([name hasPrefix:@"TC"] && [name hasSuffix:@"Pad"]) return @[DOLTestPad(name)];
  return ((NSArray* (*)(id, SEL, NSString*, id, NSDictionary*))s_loadNib)(bundle, command, name, owner, options);
}

@interface ShakeTestDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation ShakeTestDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end

int main(int argc, char** argv) {
  @autoreleasepool {
    Method method = class_getInstanceMethod(NSBundle.class, @selector(loadNibNamed:owner:options:));
    s_loadNib = method_setImplementation(method, (IMP)DOLTestLoadNib);
    DOLTestResetTouchEvents();
    if (DOLTestTouchEvents().count) return 1;
    return UIApplicationMain(argc, argv, nil, NSStringFromClass(ShakeTestDelegate.class));
  }
}
'''

TESTS = r'''
#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import <GameController/GameController.h>
#include <unistd.h>
#import "DolphinSessionMenu.h"

extern "C" NSArray<NSArray*>* DOLTestTouchEvents(void);
extern "C" void DOLTestResetTouchEvents(void);

@protocol DOLShakeOverlayTesting <NSObject>
- (instancetype)initWithWii:(BOOL)wii;
@property(nonatomic) BOOL sessionInputActive;
@property(nonatomic, copy, nullable) NSString* shakeAccessibilityLabel;
@property(nonatomic, copy, nullable) NSString* shakeAccessibilityHint;
- (void)updateExtension:(NSString*)name;
@end
typedef UIView<DOLShakeOverlayTesting> DOLOverlay;

static NSArray<NSArray*>* Shake(NSInteger state) {
  return @[@[@4, @132, @(state)], @[@4, @133, @(state)], @[@4, @134, @(state)]];
}
static NSArray<NSArray*>* PressRelease(void) {
  return [Shake(1) arrayByAddingObjectsFromArray:Shake(0)];
}
static NSArray<NSArray*>* Recorded(void) {
  NSMutableArray* result = [NSMutableArray array];
  for (NSArray* event in DOLTestTouchEvents()) [result addObject:[event subarrayWithRange:NSMakeRange(0, 3)]];
  return result;
}
static void Wait(NSTimeInterval seconds) {
  [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:seconds]];
}
static BOOL Eventually(BOOL (^condition)(void)) {
  NSDate* until = [NSDate dateWithTimeIntervalSinceNow:2];
  while (!condition() && until.timeIntervalSinceNow > 0) Wait(0.01);
  return condition();
}
static NSArray<UIButton*>* ShakeButtons(UIView* view) {
  NSMutableArray* found = [NSMutableArray array];
  if ([view isKindOfClass:UIButton.class] && [view.accessibilityIdentifier isEqual:@"dolphinTouchShake"])
    [found addObject:view];
  for (UIView* child in view.subviews) [found addObjectsFromArray:ShakeButtons(child)];
  return found;
}
static NSArray<UIView*>* PadButtons(UIView* view) {
  NSMutableArray* found = [NSMutableArray array];
  if ([NSStringFromClass(view.class) hasSuffix:@".TCButton"]) [found addObject:view];
  for (UIView* child in view.subviews) [found addObjectsFromArray:PadButtons(child)];
  return found;
}
static NSDictionary* Snapshot(NSArray<NSString*>* shake) {
  return @{@"device": @"iOS/4/Touchscreen",
    @"controls": @[
      @{@"id": @"Buttons/A", @"group": @"Buttons", @"name": @"A", @"expression": @"`Button 100`"},
      @{@"id": @"Shake/X", @"group": @"Shake", @"name": @"X", @"expression": shake[0]},
      @{@"id": @"Shake/Y", @"group": @"Shake", @"name": @"Y", @"expression": shake[1]},
      @{@"id": @"Shake/Z", @"group": @"Shake", @"name": @"Z", @"expression": shake[2]}],
    @"devices": @[@{@"name": @"MFi/0/Gamepad", @"inputs": @[
      @{@"name": @"Button A", @"expression": @"`MFi/0/Gamepad:Button A`"},
      @{@"name": @"R Shoulder", @"expression": @"`MFi/0/Gamepad:R Shoulder`"}]}],
    @"extensions": @[@{@"group": @"Attachments", @"index": @1, @"name": @"Nunchuk", @"selected": @YES}]};
}
static NSArray<NSString*>* TouchDefaults(void) {
  return @[@"`Button 132`", @"`Button 133`", @"`Button 134`"];
}

@interface DolphinTouchShakeTests : XCTestCase
@property(nonatomic, strong) NSMutableArray<UIView*>* overlays;
@end

@implementation DolphinTouchShakeTests

- (void)setUp {
  [super setUp];
  self.overlays = [NSMutableArray array];
  NSDate* until = [NSDate dateWithTimeIntervalSinceNow:10];
  while (UIApplication.sharedApplication.applicationState != UIApplicationStateActive && until.timeIntervalSinceNow > 0)
    Wait(0.05);
  XCTAssertEqual(UIApplication.sharedApplication.applicationState, UIApplicationStateActive);
  XCTAssertNotNil(NSClassFromString(@"DolphinTouchShakeHost.TCButton"), @"stub pads use production TCButton");
}

- (void)tearDown {
  for (UIView* overlay in self.overlays) [overlay removeFromSuperview];
  [self.overlays removeAllObjects];
  DOLTestResetTouchEvents();
  [super tearDown];
}

- (DOLOverlay*)overlay:(BOOL)wii {
  DOLOverlay* overlay = [[NSClassFromString(@"DOLTouchOverlay") alloc] initWithWii:wii];
  XCTAssertNotNil(overlay);
  overlay.shakeAccessibilityLabel = @"Secouer la Wiimote";
  overlay.shakeAccessibilityHint = @"Maintenez pour continuer à secouer.";
  UIWindow* window = UIApplication.sharedApplication.delegate.window;
  XCTAssertNotNil(window);
  // Like the game view, the overlay fills its window. A fixed landscape frame
  // would overflow a portrait simulator window, and the safe area UIKit gives
  // the overflowing part (hence the Shake placement) would decide the result.
  overlay.frame = window.bounds;
  [window addSubview:overlay];
  overlay.sessionInputActive = YES;
  [overlay setNeedsLayout];
  [overlay layoutIfNeeded];
  [overlay layoutIfNeeded];
  [self.overlays addObject:overlay];
  DOLTestResetTouchEvents();
  return overlay;
}

- (UIButton*)shakeButtonOf:(UIView*)overlay {
  NSArray<UIButton*>* buttons = ShakeButtons(overlay);
  XCTAssertEqual(buttons.count, 1U);
  return buttons.firstObject;
}

- (void)testWiiLayoutHasOneTranslatedShakeControlAboveThePad {
  DOLOverlay* overlay = [self overlay:YES];
  UIButton* button = [self shakeButtonOf:overlay];
  XCTAssertEqual(button.superview, overlay);
  UIView* pad = overlay.subviews.firstObject;
  XCTAssertTrue([NSStringFromClass(pad.class) hasSuffix:@".TCWiiPad"]);
  XCTAssertGreaterThan([overlay.subviews indexOfObject:button], 0U);
  XCTAssertFalse(button.hidden);
  XCTAssertEqualObjects(button.accessibilityLabel, @"Secouer la Wiimote");
  XCTAssertEqualObjects(button.accessibilityHint, @"Maintenez pour continuer à secouer.");
  XCTAssertTrue(button.isAccessibilityElement);
  XCTAssertTrue((button.accessibilityTraits & UIAccessibilityTraitButton) != 0);
  UIImage* image = [button imageForState:UIControlStateNormal];
  XCTAssertNotNil(image);
  XCTAssertGreaterThan(image.size.width, 0);
  XCTAssertEqualWithAccuracy(button.bounds.size.width, 56, 0.01);
  XCTAssertEqualWithAccuracy(button.bounds.size.height, 56, 0.01);
  CGRect frame = button.frame;
  CGRect safe = UIEdgeInsetsInsetRect(overlay.bounds, overlay.safeAreaInsets);
  XCTAssertTrue(CGRectContainsRect(safe, frame), @"%@ outside %@", NSStringFromCGRect(frame), NSStringFromCGRect(safe));
  NSArray<UIView*>* controls = PadButtons(pad);
  XCTAssertEqual(controls.count, 5U);
  for (UIView* control in controls)
    XCTAssertFalse(CGRectIntersectsRect([control convertRect:control.bounds toView:overlay], frame),
                   @"Shake covers %@", NSStringFromCGRect([control convertRect:control.bounds toView:overlay]));
  UIView* hit = [overlay hitTest:CGPointMake(CGRectGetMidX(frame), CGRectGetMidY(frame)) withEvent:nil];
  XCTAssertEqual(hit, button);
  XCTAssertEqual(Recorded().count, 0U, @"showing the control writes nothing");
}

- (void)testHeldPressShakesTheFirstWiiRemoteUntilRelease {
  UIButton* button = [self shakeButtonOf:[self overlay:YES]];
  [button sendActionsForControlEvents:UIControlEventTouchDown];
  XCTAssertEqualObjects(Recorded(), Shake(1));
  Wait(0.25);
  XCTAssertEqualObjects(Recorded(), Shake(1), @"still shaking while held");
  [button sendActionsForControlEvents:UIControlEventTouchUpInside];
  XCTAssertEqualObjects(Recorded(), PressRelease(), @"released at finger-up after a long hold");
  Wait(0.2);
  XCTAssertEqualObjects(Recorded(), PressRelease(), @"no late write");
}

- (void)testQuickTapStillShakesForTheMinimumWithoutTheMainThread {
  UIButton* button = [self shakeButtonOf:[self overlay:YES]];
  [button sendActionsForControlEvents:UIControlEventTouchDown];
  [button sendActionsForControlEvents:UIControlEventTouchUpInside];
  XCTAssertEqualObjects(Recorded(), Shake(1), @"a tap is not released at once");
  XCTAssertTrue(Eventually(^BOOL { return Recorded().count == 6; }));
  XCTAssertEqualObjects(Recorded(), PressRelease());
  NSArray* events = DOLTestTouchEvents();
  const double held = [events[3][3] doubleValue] - [events[0][3] doubleValue];
  XCTAssertGreaterThanOrEqual(held, 0.11);
  XCTAssertLessThan(held, 0.6);
  XCTAssertFalse([events[3][4] boolValue], @"the minimum release does not run on the UI thread");
  // A busy UI thread does not lengthen the next tap.
  DOLTestResetTouchEvents();
  [button sendActionsForControlEvents:UIControlEventTouchDown];
  [button sendActionsForControlEvents:UIControlEventTouchUpInside];
  usleep(400000);
  events = DOLTestTouchEvents();
  XCTAssertEqual(events.count, 6U, @"released while the UI thread was blocked");
  if (events.count == 6U) XCTAssertLessThan([events[3][3] doubleValue] - [events[0][3] doubleValue], 0.3);
}

- (void)testCancelledAndDraggedOutTouchesRelease {
  UIButton* button = [self shakeButtonOf:[self overlay:YES]];
  [button sendActionsForControlEvents:UIControlEventTouchDown];
  [button sendActionsForControlEvents:UIControlEventTouchCancel];
  XCTAssertEqualObjects(Recorded(), PressRelease(), @"touch cancel releases at once");
  Wait(0.2);
  XCTAssertEqualObjects(Recorded(), PressRelease());
  DOLTestResetTouchEvents();
  [button sendActionsForControlEvents:UIControlEventTouchDown];
  [button sendActionsForControlEvents:UIControlEventTouchUpInside];
  [button sendActionsForControlEvents:UIControlEventTouchCancel];
  XCTAssertEqualObjects(Recorded(), PressRelease(), @"cancel voids a pending minimum release");
  Wait(0.2);
  XCTAssertEqualObjects(Recorded(), PressRelease());
  DOLTestResetTouchEvents();
  [button sendActionsForControlEvents:UIControlEventTouchDown];
  Wait(0.15);
  [button sendActionsForControlEvents:UIControlEventTouchDragExit];
  XCTAssertEqualObjects(Recorded(), PressRelease(), @"finger dragged off");
  [button sendActionsForControlEvents:UIControlEventTouchDragEnter];
  XCTAssertEqual(Recorded().count, 9U, @"finger back on the control shakes again");
  Wait(0.15);
  [button sendActionsForControlEvents:UIControlEventTouchUpOutside];
  XCTAssertEqualObjects([Recorded() subarrayWithRange:NSMakeRange(6, 6)], PressRelease());
}

- (void)testEveryLifecycleExitReleasesAHeldShakeAtOnce {
  for (NSString* reason in @[@"hidden", @"interaction", @"session", @"background", @"gamepad", @"classic", @"removed"]) {
    DOLOverlay* overlay = [self overlay:YES];
    UIButton* button = [self shakeButtonOf:overlay];
    [button sendActionsForControlEvents:UIControlEventTouchDown];
    XCTAssertEqualObjects(Recorded(), Shake(1), @"%@", reason);
    if ([reason isEqual:@"hidden"]) overlay.hidden = YES;
    else if ([reason isEqual:@"interaction"]) overlay.userInteractionEnabled = NO;
    else if ([reason isEqual:@"session"]) overlay.sessionInputActive = NO;
    else if ([reason isEqual:@"background"])
      [NSNotificationCenter.defaultCenter postNotificationName:UIApplicationWillResignActiveNotification object:nil];
    else if ([reason isEqual:@"gamepad"])
      [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidConnectNotification object:nil];
    else if ([reason isEqual:@"classic"]) [overlay updateExtension:@"Classic"];
    else [overlay removeFromSuperview];
    XCTAssertEqualObjects(Recorded(), PressRelease(), @"%@ releases at once", reason);
    [button sendActionsForControlEvents:UIControlEventTouchDown];
    [button sendActionsForControlEvents:UIControlEventTouchUpInside];
    Wait(0.2);
    if ([reason isEqual:@"gamepad"]) {
      // The game view hides the overlay for a real gamepad; without one the
      // control stays usable after the hot-plug release.
      XCTAssertEqual(Recorded().count, 12U, @"%@", reason);
    } else {
      XCTAssertEqual(Recorded().count, 6U, @"%@: no shake while unavailable", reason);
    }
    if ([reason isEqual:@"background"])
      [NSNotificationCenter.defaultCenter postNotificationName:UIApplicationDidBecomeActiveNotification object:nil];
    DOLTestResetTouchEvents();
  }
}

- (void)testClassicHidesTheControlAndTheWiiRemoteLayoutRestoresIt {
  DOLOverlay* overlay = [self overlay:YES];
  UIButton* button = [self shakeButtonOf:overlay];
  [overlay updateExtension:@"Classic"];
  [overlay layoutIfNeeded];
  XCTAssertTrue(button.hidden);
  XCTAssertTrue([NSStringFromClass(overlay.subviews.firstObject.class) hasSuffix:@".TCClassicWiiPad"]);
  [overlay updateExtension:@"Nunchuk"];
  [overlay layoutIfNeeded];
  XCTAssertFalse(button.hidden);
  XCTAssertTrue([NSStringFromClass(overlay.subviews.firstObject.class) hasSuffix:@".TCWiiPad"]);
  XCTAssertEqual([self shakeButtonOf:overlay], button);
  XCTAssertGreaterThan([overlay.subviews indexOfObject:button], 0U);
  CGRect frame = button.frame;
  XCTAssertEqual([overlay hitTest:CGPointMake(CGRectGetMidX(frame), CGRectGetMidY(frame)) withEvent:nil], button);
  [button sendActionsForControlEvents:UIControlEventTouchDown];
  [button sendActionsForControlEvents:UIControlEventTouchCancel];
  XCTAssertEqualObjects(Recorded(), PressRelease());
}

- (void)testGameCubeHasNoShakeControlAndNeverWritesWiiRemoteShake {
  DOLOverlay* overlay = [self overlay:NO];
  XCTAssertEqual(ShakeButtons(overlay).count, 0U);
  XCTAssertTrue([NSStringFromClass(overlay.subviews.firstObject.class) hasSuffix:@".TCGameCubePad"]);
  [overlay updateExtension:@"Nunchuk"];
  [overlay updateExtension:@"Classic"];
  [overlay layoutIfNeeded];
  XCTAssertEqual(ShakeButtons(overlay).count, 0U);
  overlay.hidden = YES;
  overlay.hidden = NO;
  overlay.userInteractionEnabled = NO;
  overlay.sessionInputActive = NO;
  [NSNotificationCenter.defaultCenter postNotificationName:GCControllerDidConnectNotification object:nil];
  [overlay removeFromSuperview];
  Wait(0.2);
  XCTAssertEqual(DOLTestTouchEvents().count, 0U, @"GameCube never writes Wii Remote shake inputs");
}

- (void)testVoiceOverActivationGivesOneMinimumShake {
  UIButton* button = [self shakeButtonOf:[self overlay:YES]];
  XCTAssertTrue([button accessibilityActivate]);
  XCTAssertEqualObjects(Recorded(), Shake(1));
  XCTAssertTrue(Eventually(^BOOL { return Recorded().count == 6; }));
  XCTAssertEqualObjects(Recorded(), PressRelease());
}

// ---- In-game Controls menu ----

- (NSDictionary*)catalog {
  NSString* path = [[NSBundle bundleForClass:self.class] pathForResource:@"dolphin_shake_labels" ofType:@"json"];
  XCTAssertNotNil(path);
  NSDictionary* catalog = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:path] options:0 error:nil];
  XCTAssertEqual(catalog.count, 12U);
  return catalog;
}

- (NSDictionary*)labels:(NSString*)locale {
  NSMutableDictionary* labels = [[self catalog][locale] mutableCopy];
  for (NSString* key in @[@"unassigned", @"bindings", @"bindingsHelp", @"chooseInput", @"clearBinding", @"controls"])
    labels[key] = [NSString stringWithFormat:@"%@-%@", key, locale];
  labels[@"__locale"] = locale;
  return labels;
}

- (DolphinSessionMenu*)controlsForWiiSession:(BOOL)wii labels:(NSDictionary*)labels
                                  navigation:(UINavigationController* __autoreleasing*)navigation
                                    requests:(NSMutableArray*)requests {
  DolphinSessionMenu* root = [DolphinSessionMenu new];
  root.labels = labels;
  root.wii = wii;
  root.gameTitle = @"Test";
  root.applySettings = ^(NSDictionary* request, void (^done)(BOOL)) { [requests addObject:request]; done(YES); };
  UINavigationController* controller = [[UINavigationController alloc] initWithRootViewController:root];
  [controller loadViewIfNeeded];
  [root loadViewIfNeeded];
  NSUInteger row = [[root valueForKey:@"rootKeys"] indexOfObject:@"controls"];
  XCTAssertNotEqual(row, NSNotFound);
  [root tableView:root.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:(NSInteger)row inSection:0]];
  Wait(0.05);
  DolphinSessionMenu* controls = (DolphinSessionMenu*)controller.topViewController;
  XCTAssertNotEqual(controls, root);
  XCTAssertEqualObjects([controls valueForKey:@"page"], @5);
  [controls loadViewIfNeeded];
  [controls setValue:Snapshot(TouchDefaults()) forKey:@"snapshot"];
  *navigation = controller;
  return controls;
}

- (UITableViewCell*)shakeCell:(DolphinSessionMenu*)controls {
  return [controls tableView:controls.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:1]];
}

- (void)testWiiSessionControlsOfferTheShakeRowInTwelveLanguages {
  NSDictionary* catalog = [self catalog];
  for (NSString* locale in @[@"en", @"es", @"ru", @"zh", @"zh_Hant", @"pt", @"fr", @"de", @"it", @"id", @"ja", @"ko"]) {
    NSDictionary* labels = [self labels:locale];
    XCTAssertNotNil(catalog[locale][@"shakeAssign"], @"%@", locale);
    UINavigationController* navigation = nil;
    DolphinSessionMenu* controls = [self controlsForWiiSession:YES labels:labels navigation:&navigation
                                                      requests:[NSMutableArray array]];
    UITableView* table = controls.tableView;
    XCTAssertEqual([controls numberOfSectionsInTableView:table], 3);
    XCTAssertEqual([controls tableView:table numberOfRowsInSection:0], 6, @"Wii rows: five of Build 440 plus the sensitivity row");
    XCTAssertEqual([controls tableView:table numberOfRowsInSection:1], 1);
    XCTAssertEqual([controls tableView:table numberOfRowsInSection:2], 4);
    // Build 442: the phone-shake sensitivity row cycles a local preference and
    // never sends a core request; its texts come from the Dart catalog.
    [NSUserDefaults.standardUserDefaults removeObjectForKey:@"NeoStation.Dolphin.PhoneShake.Sensitivity"];
    NSIndexPath* sensitivityRow = [NSIndexPath indexPathForRow:5 inSection:0];
    UITableViewCell* sensitivity = [controls tableView:table cellForRowAtIndexPath:sensitivityRow];
    XCTAssertEqualObjects(sensitivity.textLabel.text, catalog[locale][@"shakeSensitivity"]);
    XCTAssertEqualObjects(sensitivity.detailTextLabel.text, catalog[locale][@"shakeSensitivityMedium"]);
    XCTAssertTrue([[controls tableView:table titleForFooterInSection:0] containsString:catalog[locale][@"shakeSensitivityHelp"]]);
    NSMutableArray* sensitivityRequests = [NSMutableArray array];
    controls.applySettings = ^(NSDictionary* request, void (^done)(BOOL)) { [sensitivityRequests addObject:request]; done(YES); };
    [controls tableView:table didSelectRowAtIndexPath:sensitivityRow];
    XCTAssertEqualObjects([NSUserDefaults.standardUserDefaults stringForKey:@"NeoStation.Dolphin.PhoneShake.Sensitivity"], @"high");
    XCTAssertEqualObjects([controls tableView:table cellForRowAtIndexPath:sensitivityRow].detailTextLabel.text, catalog[locale][@"shakeSensitivityHigh"]);
    [controls tableView:table didSelectRowAtIndexPath:sensitivityRow];
    XCTAssertEqualObjects([NSUserDefaults.standardUserDefaults stringForKey:@"NeoStation.Dolphin.PhoneShake.Sensitivity"], @"low");
    [controls tableView:table didSelectRowAtIndexPath:sensitivityRow];
    XCTAssertEqualObjects([NSUserDefaults.standardUserDefaults stringForKey:@"NeoStation.Dolphin.PhoneShake.Sensitivity"], @"medium");
    XCTAssertEqual(sensitivityRequests.count, 0U);
    [NSUserDefaults.standardUserDefaults removeObjectForKey:@"NeoStation.Dolphin.PhoneShake.Sensitivity"];
    UITableViewCell* cell = [self shakeCell:controls];
    XCTAssertEqualObjects(cell.textLabel.text, catalog[locale][@"shakeAssign"]);
    XCTAssertEqualObjects(cell.detailTextLabel.text, labels[@"unassigned"], @"Touch profile: touch/phone only");
    XCTAssertNil([controls tableView:table titleForHeaderInSection:1]);
    XCTAssertEqualObjects([controls tableView:table titleForFooterInSection:1], catalog[locale][@"shakeAssignHelp"]);
    XCTAssertEqualObjects([controls tableView:table titleForHeaderInSection:2], labels[@"bindings"]);
    XCTAssertEqualObjects([controls tableView:table titleForFooterInSection:2], labels[@"bindingsHelp"]);
    UITableViewCell* axis = [controls tableView:table cellForRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:2]];
    XCTAssertEqualObjects(axis.detailTextLabel.text, @"`Button 132`", @"per-axis rows unchanged");
    [controls setValue:Snapshot(@[@"(`R Shoulder`) | `iOS/4/Touchscreen:Button 132`", @"`L Shoulder`",
                                  @"`R Shoulder`"]) forKey:@"snapshot"];
    XCTAssertEqualObjects([self shakeCell:controls].detailTextLabel.text, catalog[locale][@"shakeMixed"]);
    [controls setValue:Snapshot(@[@"(`R Shoulder`) | `iOS/4/Touchscreen:Button 132`",
                                  @"(`R Shoulder`) | `iOS/4/Touchscreen:Button 133`",
                                  @"(`R Shoulder`) | `iOS/4/Touchscreen:Button 134`"]) forKey:@"snapshot"];
    XCTAssertEqualObjects([self shakeCell:controls].detailTextLabel.text, @"`R Shoulder`");
  }
}

- (void)testShakeRowSendsOneControllerButtonForTheThreeAxes {
  NSMutableArray* requests = [NSMutableArray array];
  UINavigationController* navigation = nil;
  DolphinSessionMenu* controls = [self controlsForWiiSession:YES labels:[self labels:@"fr"]
                                                  navigation:&navigation requests:requests];
  NSIndexPath* shakeRow = [NSIndexPath indexPathForRow:0 inSection:1];
  [controls tableView:controls.tableView didSelectRowAtIndexPath:shakeRow];
  Wait(0.05);
  DolphinSessionMenu* devices = (DolphinSessionMenu*)navigation.topViewController;
  XCTAssertEqualObjects([devices valueForKey:@"page"], @7);
  XCTAssertEqualObjects([devices valueForKey:@"binding"][@"id"], @"NeoStation/ShakeXYZ");
  [devices loadViewIfNeeded];
  XCTAssertEqual([devices tableView:devices.tableView numberOfRowsInSection:0], 2);
  [devices tableView:devices.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
  Wait(0.05);
  DolphinSessionMenu* inputs = (DolphinSessionMenu*)navigation.topViewController;
  XCTAssertEqualObjects([inputs valueForKey:@"page"], @8);
  [inputs loadViewIfNeeded];
  [inputs tableView:inputs.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
  Wait(0.05);
  XCTAssertEqualObjects(requests.lastObject, (@{@"kind": @"shakeBinding", @"expression": @"`MFi/0/Gamepad:R Shoulder`",
                                                @"wii": @YES, @"slot": @0}));
  XCTAssertEqual(navigation.topViewController, controls, @"success returns to Controls");

  // Clear: an empty input; the bridge keeps the touch/phone branch for player 1.
  [controls tableView:controls.tableView didSelectRowAtIndexPath:shakeRow];
  Wait(0.05);
  devices = (DolphinSessionMenu*)navigation.topViewController;
  [devices loadViewIfNeeded];
  [devices tableView:devices.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
  Wait(0.05);
  XCTAssertEqualObjects(requests.lastObject, (@{@"kind": @"shakeBinding", @"expression": @"", @"wii": @YES, @"slot": @0}));

  // Player 3 targets its own profile.
  controls.slot = 2;
  [controls tableView:controls.tableView didSelectRowAtIndexPath:shakeRow];
  Wait(0.05);
  devices = (DolphinSessionMenu*)navigation.topViewController;
  [devices loadViewIfNeeded];
  [devices tableView:devices.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
  Wait(0.05);
  inputs = (DolphinSessionMenu*)navigation.topViewController;
  [inputs loadViewIfNeeded];
  [inputs tableView:inputs.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
  Wait(0.05);
  XCTAssertEqualObjects(requests.lastObject, (@{@"kind": @"shakeBinding", @"expression": @"`MFi/0/Gamepad:Button A`",
                                                @"wii": @YES, @"slot": @2}));

  // A per-axis row still sends the existing single-control request.
  [controls tableView:controls.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:2]];
  Wait(0.05);
  devices = (DolphinSessionMenu*)navigation.topViewController;
  [devices loadViewIfNeeded];
  [devices tableView:devices.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
  Wait(0.05);
  inputs = (DolphinSessionMenu*)navigation.topViewController;
  [inputs loadViewIfNeeded];
  [inputs tableView:inputs.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
  Wait(0.05);
  XCTAssertEqualObjects(requests.lastObject, (@{@"kind": @"binding", @"id": @"Shake/X",
                                                @"expression": @"`MFi/0/Gamepad:Button A`", @"wii": @YES, @"slot": @2}));
  XCTAssertEqual(requests.count, 4U);
}

- (void)testGameCubeSessionsAndPagesNeverShowTheShakeRow {
  UINavigationController* navigation = nil;
  NSMutableArray* requests = [NSMutableArray array];
  DolphinSessionMenu* gameCube = [self controlsForWiiSession:NO labels:[self labels:@"fr"]
                                                  navigation:&navigation requests:requests];
  XCTAssertEqual([gameCube numberOfSectionsInTableView:gameCube.tableView], 2);
  XCTAssertEqual([gameCube tableView:gameCube.tableView numberOfRowsInSection:0], 3);
  XCTAssertEqualObjects([gameCube tableView:gameCube.tableView titleForHeaderInSection:1], @"bindings-fr");
  // A GameCube game browsing the Wii Remote page: no Shake row either.
  gameCube.wii = YES;
  XCTAssertEqual([gameCube numberOfSectionsInTableView:gameCube.tableView], 2);
  XCTAssertEqualObjects([gameCube tableView:gameCube.tableView titleForHeaderInSection:1], @"bindings-fr");
  // A Wii game browsing the GameCube controller page.
  DolphinSessionMenu* wii = [self controlsForWiiSession:YES labels:[self labels:@"fr"]
                                             navigation:&navigation requests:requests];
  wii.wii = NO;
  XCTAssertEqual([wii numberOfSectionsInTableView:wii.tableView], 2);
  XCTAssertEqual([wii tableView:wii.tableView numberOfRowsInSection:0], 3);
  // Pages built directly (older callers) keep their two sections.
  DolphinSessionMenu* direct = [DolphinSessionMenu new];
  direct.wii = YES;
  direct.labels = [self labels:@"fr"];
  [direct setValue:@5 forKey:@"page"];
  [direct setValue:Snapshot(TouchDefaults()) forKey:@"snapshot"];
  [direct loadViewIfNeeded];
  XCTAssertEqual([direct numberOfSectionsInTableView:direct.tableView], 2);
  XCTAssertEqual([direct tableView:direct.tableView numberOfRowsInSection:1], 4);
  XCTAssertEqual(requests.count, 0U);
}
@end
'''


def shake_catalog():
    text = (ROOT / 'lib/l10n/dolphin_shake_locale.dart').read_text(encoding='utf-8')
    body = text.split('static const values = <String, Map<String, String>>{', 1)[1].split('\n  };', 1)[0]
    catalog = {}
    for match in re.finditer(r"\n    '(\w+)': \{(.*?)\n    \},", body, re.S):
        catalog[match.group(1)] = dict(re.findall(r"'(\w+)':\s*'((?:[^'\\]|\\.)*)'", match.group(2)))
    assert len(catalog) == 12, sorted(catalog)
    assert all(set(values) == set(catalog['en']) for values in catalog.values())
    return catalog


def native():
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], text=True).strip()
    runtime_key = 'com.apple.CoreSimulator.SimRuntime.iOS-' + sdk.replace('.', '-')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j']))['devices']
    candidates = [device for runtime, items in devices.items() if runtime == runtime_key
                  for device in items if device['name'].startswith('iPhone') and device.get('isAvailable')]
    if not candidates:
        raise RuntimeError(f'A simulator matching the selected Xcode SDK {sdk} is required; installed: {sorted(devices)}')
    device = candidates[0]
    print(f"Testing on {device['name']} / iOS {sdk} / {device['udid']}", flush=True)
    if device.get('state') != 'Booted':
        subprocess.run(['xcrun', 'simctl', 'boot', device['udid']], check=True, timeout=60)
    subprocess.run(['xcrun', 'simctl', 'bootstatus', device['udid'], '-b'], check=True, timeout=180)
    with tempfile.TemporaryDirectory(prefix='dolphin-touch-shake-') as folder:
        directory = Path(folder)
        (directory / 'main.m').write_text(APP)
        (directory / 'DolphinTouchShakeTests.mm').write_text(TESTS)
        (directory / 'dolphin_shake_labels.json').write_text(json.dumps(shake_catalog(), ensure_ascii=False),
                                                              encoding='utf-8')
        sdk_dependencies = [{'sdk': name + '.framework'} for name in
                            ('UIKit', 'QuartzCore', 'CoreGraphics', 'Foundation', 'Security',
                             'UniformTypeIdentifiers', 'CoreMotion', 'GameController', 'MetalKit', 'Metal')]
        sdk_dependencies.append({'sdk': 'libz.tbd'})
        include = stage_dependency_headers(directory)
        host_sources = [str(directory / 'main.m'), str(CLASSES / 'DolphinSessionMenu.mm'),
                        str(CLASSES / 'DolphinRetroAchievementsAccount.mm'), str(CLASSES / 'DolphinFramePacing.mm'),
                        str(CLASSES / 'DolphinExternalDisplay.mm')]
        host_sources += [str(source) for source in EXTERNAL_SOURCES]
        host_sources += [str(source) for source in CATALOGUE_SOURCES]
        host_sources += [str(path) for path in sorted(TOUCH.glob('*.swift'))]
        project = {
            'name': 'DolphinTouchShake',
            'options': {'deploymentTarget': {'iOS': '17.4'}},
            'settings': {'base': {'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_ENABLE_MODULES': 'YES',
                                  'CLANG_CXX_LANGUAGE_STANDARD': 'c++20', 'SWIFT_VERSION': '5.0',
                                  'CODE_SIGNING_ALLOWED': 'YES', 'CODE_SIGN_IDENTITY': '-',
                                  'GENERATE_INFOPLIST_FILE': 'YES',
                                  'HEADER_SEARCH_PATHS': str(CLASSES) + ' ' + str(include)}},
            'targets': {
                HOST: {'type': 'application', 'platform': 'iOS', 'sources': host_sources,
                       'dependencies': sdk_dependencies,
                       'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.touchshake.host',
                                             'PRODUCT_MODULE_NAME': HOST,
                                             'SWIFT_OBJC_BRIDGING_HEADER': str(TOUCH / 'TCManagerInterface.h'),
                                             'INFOPLIST_KEY_UILaunchScreen_Generation': 'YES'}}},
                'DolphinTouchShakeTests': {'type': 'bundle.unit-test', 'platform': 'iOS',
                    'sources': [str(directory / 'DolphinTouchShakeTests.mm'),
                                {'path': str(directory / 'dolphin_shake_labels.json'), 'buildPhase': 'resources'}],
                    'dependencies': [{'target': HOST}] + sdk_dependencies,
                    'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': 'org.neostation.touchshake.tests',
                        'TEST_HOST': f'$(BUILT_PRODUCTS_DIR)/{HOST}.app/{HOST}',
                        'BUNDLE_LOADER': '$(TEST_HOST)'}}},
            },
            'schemes': {'DolphinTouchShake': {'build': {'targets': {HOST: 'all', 'DolphinTouchShakeTests': 'test'}},
                                              'test': {'targets': ['DolphinTouchShakeTests']}}},
        }
        spec = directory / 'project.json'
        spec.write_text(json.dumps(project))
        subprocess.run(['xcodegen', 'generate', '--spec', str(spec), '--project', str(directory)], check=True)
        result = ROOT / 'build/dolphin-motion/DolphinTouchShake.xcresult'
        result.parent.mkdir(parents=True, exist_ok=True)
        if result.exists():
            shutil.rmtree(result)
        subprocess.run(['xcodebuild', 'test', '-project', str(directory / 'DolphinTouchShake.xcodeproj'),
            '-scheme', 'DolphinTouchShake', '-destination', 'platform=iOS Simulator,id=' + device['udid'],
            '-destination-timeout', '60', '-parallel-testing-enabled', 'NO',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '120',
            '-maximum-test-execution-time-allowance', '240', '-resultBundlePath', str(result),
            'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'DEVELOPMENT_TEAM='], check=True, timeout=1200)


if __name__ == '__main__':
    shake_catalog()
    if platform.system() != 'Darwin':
        print('SKIP: UIKit simulator tests require macOS/Xcode (dolphin-motion-check); catalog parsed')
        raise SystemExit(0)
    native()
    print('PASS: real Wii touch Shake control lifecycle and Controls Shake row in the iOS Simulator; no device claim')
