#!/usr/bin/env python3
"""Real UIKit/XCTest checks of the external_display coordinator in the iOS
Simulator (macOS CI: external-display-check).

Reuses the simulator/project harness of dolphin_account_267_test.py with the
production NeoExternalDisplayCoordinator.m, NeoExternalDisplaySceneDelegate.m
and NeoExternalDisplayPreferences.m (UIKit only: the Flutter menu engine is
replaced by a provider returning a plain controller). The external window
is injected through the windowFactory seam (scene-less, 1920×1080), the
application's own scene stands in for the external one, and the legacy
fallback runs against the legacyScreens seam. Executed: connection and the
menu, the game in Automatic/Fit/Fill/Original, disconnection (view returned
before the window goes) and reconnection, disabled/suspended/menu-off
mirroring, the menu engine hidden during a game, never created while a game
holds the TV and destroyed for RPCS3, the 1.5 s legacy fallback, MTKView
drawable preservation, TV-resolution surfaces for a non-fixed host, the
Build 442 preference fallback, the state notification, and the iOS 27 scene
accessory registrations (one per presented controller, released once
dismissed) against a UISceneAccessory faked at run time when the SDK lacks
it. No emulator runs; AirPlay itself remains an iPhone + Apple TV check.
"""
import platform
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
origin = ROOT / 'test/dolphin_account_267_test.py'
source = origin.read_text()
source = source.replace("CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'",
                        "CLASSES = ROOT / 'packages/external_display/ios/Classes'")
source, replaced = re.subn(
    r"str\(CLASSES / 'DolphinSessionMenu\.mm'\),.*?str\(CLASSES / 'DolphinExternalDisplay\.mm'\)",
    "str(CLASSES / 'NeoExternalDisplayCoordinator.m'), str(CLASSES / 'NeoExternalDisplaySceneDelegate.m'), "
    "str(CLASSES / 'NeoExternalDisplayPreferences.m')",
    source, flags=re.S)
assert replaced == 1, 'the harness source list changed; adapt the substitution'
source = source.replace("{'sdk': 'UIKit.framework'}", "{'sdk': 'CoreGraphics.framework'}, {'sdk': 'UIKit.framework'}")
source = source.replace('DolphinAccount267', 'NeoExternalDisplay').replace('DolphinAccountHost', 'NeoExternalDisplayHost')
source = source.replace('DolphinAccountTests', 'NeoExternalDisplayTests').replace('dolphin-account-tests-', 'external-display-tests-')
source = source.replace('org.neostation.accounttests', 'org.neostation.externaldisplaytests')
ns = {'__file__': str(origin), '__name__': 'external_display_tests'}
exec(compile(source, str(origin), 'exec'), ns)
# The host lists the pod sources itself (above): the harness's own pod
# sources (Build 447, for the Dolphin adapter) would define them twice.
ns['EXTERNAL_SOURCES'] = []

ns['APP'] = r'''
#import <UIKit/UIKit.h>
@interface ExternalDisplayTestDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation ExternalDisplayTestDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
#pragma clang diagnostic pop
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char** argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(ExternalDisplayTestDelegate.class)); }
}
'''

ns['TESTS'] = r'''
#import <XCTest/XCTest.h>
#import <MetalKit/MetalKit.h>
#import "NeoExternalDisplayCoordinator.h"
#import "NeoExternalDisplayPreferences.h"
#import "NeoExternalDisplaySceneDelegate.h"
#import <objc/runtime.h>

#pragma clang diagnostic ignored "-Wdeprecated-declarations"

/// A bridge host: Dolphin/RPCS3/ARMSX2 (fixed drawable) or libretro (the
/// surface follows the TV). The render view sits below an overlay on an
/// iPhone-sized placeholder.
@interface FakeRenderHost : NSObject <NeoExternalRenderHost>
@property(nonatomic, strong) UIView* renderView;
@property(nonatomic, strong) UIView* placeholderView;
@property(nonatomic, strong) UIView* overlay;
@property(nonatomic, assign) BOOL fixedDrawable;
@property(nonatomic, strong) NSMutableArray<NSNumber*>* activeChanges;
@property(nonatomic, strong) NSMutableArray<NSValue*>* surfaces;
@property(nonatomic, strong) NSMutableArray<NSNumber*>* scales;
- (instancetype)initFixed:(BOOL)fixed render:(UIView*)render;
@end
@implementation FakeRenderHost
- (instancetype)initFixed:(BOOL)fixed render:(UIView*)render {
  if ((self = [super init])) {
    _fixedDrawable = fixed;
    _placeholderView = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 852, 393)];
    _renderView = render ?: [[UIView alloc] initWithFrame:_placeholderView.bounds];
    _renderView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    _overlay = [[UIView alloc] initWithFrame:_placeholderView.bounds];
    [_placeholderView addSubview:_renderView];
    [_placeholderView addSubview:_overlay];
    _activeChanges = [NSMutableArray array];
    _surfaces = [NSMutableArray array];
    _scales = [NSMutableArray array];
  }
  return self;
}
- (void)externalSurfaceDidChange:(CGSize)pointSize scale:(CGFloat)scale {
  [self.surfaces addObject:[NSValue valueWithCGSize:pointSize]];
  [self.scales addObject:@(scale)];
}
- (void)externalDisplayDidChange:(BOOL)active { [self.activeChanges addObject:@(active)]; }
@end

/// Stands in for NeoExternalDisplayMenuEngine (Flutter is not linked here).
@interface FakeMenuProvider : NSObject <NeoExternalMenuProvider>
@property(nonatomic, assign) BOOL configured;
@property(nonatomic, strong) UIViewController* controller;
@property(nonatomic, copy) NSString* status;
@property(nonatomic, assign) NSUInteger created;
@property(nonatomic, strong) NSMutableArray<NSString*>* destroyed;
@end
@implementation FakeMenuProvider
- (instancetype)init {
  if ((self = [super init])) { _status = @"none"; _destroyed = [NSMutableArray array]; _configured = YES; }
  return self;
}
- (UIViewController*)externalMenuViewControllerCreatingIfNeeded {
  if (!self.configured) return nil;
  if (!self.controller) {
    self.controller = [UIViewController new];
    self.controller.view.backgroundColor = UIColor.blackColor;
    self.created += 1;
    self.status = @"created";
  }
  return self.controller;
}
- (void)destroyExternalMenuEngineForReason:(NSString*)reason {
  if (!self.controller) return;
  [self.controller.view removeFromSuperview];
  self.controller = nil;
  self.status = @"destroyed";
  [self.destroyed addObject:reason];
}
- (NSString*)externalMenuEngineStatus { return self.status; }
@end

/// The iOS 27 scene accessory API, faked at run time when the SDK lacks it
/// (CI: iOS 26): the class UISceneAccessory with its documented factory and
/// registerSceneAccessory:/unregisterSceneAccessory: on UIViewController,
/// recording which controllers hold a registration and whether the
/// registration handed back is the one that was returned. With a real iOS
/// 27 SDK nothing is installed and the production API is exercised.
static NSMapTable<UIViewController*, id>* gFakeAccessoryRegistrations;
static NSUInteger gFakeRegisterCalls;
static NSUInteger gFakeUnregisterCalls;
static BOOL gFakeUnregisterMatched;
static BOOL InstallFakeSceneAccessoryIfNeeded(void) {
  static BOOL installed = NO;
  if (installed) return YES;
  if (NSClassFromString(@"UISceneAccessory") != Nil) return NO;
  gFakeAccessoryRegistrations = [NSMapTable strongToStrongObjectsMapTable];
  Class accessoryClass = objc_allocateClassPair(NSObject.class, "UISceneAccessory", 0);
  IMP factory = imp_implementationWithBlock(^id(id receiver, id configuration) {
    return configuration != nil ? [[accessoryClass alloc] init] : nil;
  });
  class_addMethod(object_getClass(accessoryClass), NSSelectorFromString(@"externalNonInteractiveSceneAccessoryWithConfiguration:"), factory, "@@:@");
  objc_registerClassPair(accessoryClass);
  IMP registerImp = imp_implementationWithBlock(^id(UIViewController* controller, id accessory) {
    gFakeRegisterCalls += 1;
    id registration = [NSObject new];
    [gFakeAccessoryRegistrations setObject:registration forKey:controller];
    return registration;
  });
  class_addMethod(UIViewController.class, NSSelectorFromString(@"registerSceneAccessory:"), registerImp, "@@:@");
  IMP unregisterImp = imp_implementationWithBlock(^(UIViewController* controller, id registration) {
    gFakeUnregisterCalls += 1;
    gFakeUnregisterMatched = registration != nil && [gFakeAccessoryRegistrations objectForKey:controller] == registration;
    if (gFakeUnregisterMatched) [gFakeAccessoryRegistrations removeObjectForKey:controller];
  });
  class_addMethod(UIViewController.class, NSSelectorFromString(@"unregisterSceneAccessory:"), unregisterImp, "v@:@");
  installed = YES;
  return YES;
}
static BOOL FakeAccessoryHolds(UIViewController* controller) {
  return [gFakeAccessoryRegistrations objectForKey:controller] != nil;
}

@interface ExternalDisplayCoordinatorTests : XCTestCase
@end
@implementation ExternalDisplayCoordinatorTests {
  NeoExternalDisplayCoordinator* _coordinator;
  UIWindow* _external;
  FakeMenuProvider* _menu;
  NSMutableArray<NSDictionary*>* _states;
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
  // Private flags of the singleton, reset so each test starts from a cold app.
  [c setValue:@NO forKey:@"sceneEverConnected"];
  [c setValue:@NO forKey:@"menuSuppressed"];
  [c setValue:nil forKey:@"lastState"];
}
- (void)setUp {
  [self clearDefaults];
  [self resetCoordinator];
  _coordinator = NeoExternalDisplayCoordinator.shared;
  _external = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 1920, 1080)];
  __weak UIWindow* window = _external;
  _coordinator.windowFactory = ^UIWindow*(UIWindowScene* scene, UIScreen* screen) { return window; };
  _menu = [FakeMenuProvider new];
  _coordinator.menuProvider = _menu;
  _states = [NSMutableArray array];
  NSMutableArray* states = _states;
  NeoExternalDisplayCoordinator* coordinator = _coordinator;
  _coordinator.stateChanged = ^{ [states addObject:[coordinator stateDictionary]]; };
}
- (void)tearDown {
  [self resetCoordinator];
  [self clearDefaults];
  _external.hidden = YES;
}
- (UIView*)externalRoot { return _external.rootViewController.view; }
- (void)connect {
  UIWindowScene* scene = [self mainScene];
  XCTAssertNotNil(scene, @"the application scene stands in for the external one");
  [_coordinator sceneDidConnect:scene];
}

- (void)testConnectShowsTheMenuThenTheGameTakesTheScreenInEachMode {
  [self connect];
  XCTAssertTrue(_coordinator.connected);
  XCTAssertEqualObjects(_coordinator.sceneRole, @"scene");
  XCTAssertEqual(_coordinator.content, NeoExternalContentMenu);
  XCTAssertEqual(_coordinator.window, _external, @"the window comes from the factory seam");
  XCTAssertFalse(_external.hidden);
  XCTAssertFalse(_external.isKeyWindow, @"never key: the iPhone keeps the keys");
  XCTAssertTrue([(id)UIApplication.sharedApplication.delegate window].isKeyWindow);
  XCTAssertEqual(_menu.created, 1U, @"the menu engine is created at the first connection");
  XCTAssertEqual(_coordinator.menuViewController, _menu.controller);
  XCTAssertEqual(_menu.controller.view.superview, [self externalRoot], @"menu controller placed in the external window");
  XCTAssertEqual(_menu.controller.parentViewController, _external.rootViewController);
  XCTAssertTrue(CGRectEqualToRect(_menu.controller.view.frame, CGRectMake(0, 0, 1920, 1080)), @"menu fills the TV: no bars");
  XCTAssertFalse(_menu.controller.view.hidden);
  XCTAssertEqualObjects(_coordinator.menuEngineStatus, @"attached");
  XCTAssertTrue(CGSizeEqualToSize(_coordinator.screenPointSize, CGSizeMake(1920, 1080)));
  XCTAssertEqual(_coordinator.mode, NeoExternalDisplayModeAutomatic, @"Automatic by default");

  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  UIView* render = host.renderView;
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame);
  XCTAssertEqual(render.superview, [self externalRoot], @"render view on the external window");
  XCTAssertEqual(host.overlay.superview, host.placeholderView, @"controls stay on the phone");
  XCTAssertTrue(_menu.controller.view.hidden, @"menu hidden during the game, not released");
  XCTAssertEqual(_coordinator.menuViewController, _menu.controller);
  XCTAssertEqual(_menu.destroyed.count, 0U);
  const CGSize tv = CGSizeMake(1920, 1080), phone = CGSizeMake(852, 393);
  const CGFloat fit = NeoExternalDisplayScale(tv, phone, NeoExternalDisplayModeFit);
  XCTAssertEqualWithAccuracy(render.transform.a, fit, 0.001, @"Automatic places a game as Fit");
  XCTAssertEqualWithAccuracy(render.transform.d, fit, 0.001);
  XCTAssertEqualWithAccuracy(render.bounds.size.width, 852, 0.001, @"the drawable keeps the iPhone size");
  XCTAssertEqualWithAccuracy(render.bounds.size.height, 393, 0.001);
  XCTAssertEqualWithAccuracy(render.center.x, 960, 0.001);
  XCTAssertEqualWithAccuracy(render.center.y, 540, 0.001);
  XCTAssertEqualObjects(host.activeChanges, @[@YES]);

  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill], @"the settings write re-applies through the notification");
  XCTAssertEqualWithAccuracy(render.transform.a, NeoExternalDisplayScale(tv, phone, NeoExternalDisplayModeFill), 0.001);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeOriginal]);
  XCTAssertEqualWithAccuracy(render.transform.a, 1920.0 / 852.0, 0.001, @"Original: the phone format bounded by the TV width");
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFit]);
  XCTAssertEqualWithAccuracy(render.transform.a, fit, 0.001);

  [_coordinator detachRenderHost:host];
  XCTAssertNil(_coordinator.renderHost);
  XCTAssertEqual(render.superview, host.placeholderView);
  XCTAssertEqual([host.placeholderView.subviews indexOfObject:render], 0U, @"back below the controls");
  XCTAssertTrue(CGAffineTransformIsIdentity(render.transform));
  XCTAssertTrue(CGRectEqualToRect(render.frame, host.placeholderView.bounds));
  XCTAssertEqual(render.autoresizingMask, UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight);
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO]));
  XCTAssertEqual(_coordinator.content, NeoExternalContentMenu, @"the menu is back");
  XCTAssertFalse(_menu.controller.view.hidden);

  [_coordinator sceneDidDisconnect:[self mainScene]];
  XCTAssertFalse(_coordinator.connected);
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertEqualObjects(_coordinator.sceneRole, @"none");
  XCTAssertNil(_coordinator.menuViewController);
  XCTAssertEqualObjects(_menu.destroyed, @[@"disconnect"], @"the menu engine is destroyed at disconnection");
  XCTAssertTrue(_external.hidden);
  XCTAssertNil(_external.rootViewController);
  XCTAssertTrue(CGSizeEqualToSize(_coordinator.screenPointSize, CGSizeZero));
}

- (void)testDisconnectReturnsTheRenderViewBeforeTheWindowGoesAndReconnectMovesItAgain {
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(host.renderView.superview, host.placeholderView, @"no window yet: the host is only remembered");
  XCTAssertEqual(host.activeChanges.count, 0U);
  [self connect];
  XCTAssertEqual(host.renderView.superview, [self externalRoot], @"the pending host moves at the connection");
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame);
  XCTAssertEqual(_menu.created, 0U, @"no menu engine is created while the game holds the TV");
  XCTAssertNil(_coordinator.menuViewController);
  [_coordinator sceneDidDisconnect:[self mainScene]];
  XCTAssertEqual(host.renderView.superview, host.placeholderView, @"returned to the phone at disconnection");
  XCTAssertEqual([host.placeholderView.subviews indexOfObject:host.renderView], 0U);
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO]));
  XCTAssertEqual(_coordinator.renderHost, host, @"the game is still running: the host stays attached");
  XCTAssertNil(_coordinator.window);
  [self connect];
  XCTAssertEqual(host.renderView.superview, [self externalRoot], @"reconnection moves it again");
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO, @YES]));
  XCTAssertEqual(_menu.created, 0U, @"still no menu engine: the game is back on the TV");
  [_coordinator detachRenderHost:host];
  XCTAssertEqual(host.renderView.superview, host.placeholderView);
  XCTAssertEqual(_menu.created, 1U, @"the menu engine is created once the menu is about to be shown");
  XCTAssertEqual(_coordinator.content, NeoExternalContentMenu);
  XCTAssertFalse(_menu.controller.view.hidden);
  [_coordinator sceneDidDisconnect:[self mainScene]];
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO, @YES, @NO]));
}

- (void)testDisabledSuspendedAndMenuOffFallBackToMirroring {
  [self connect];
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  XCTAssertFalse(_coordinator.mirroringActive);
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:NO]);
  XCTAssertFalse(_coordinator.enabled);
  XCTAssertTrue(_external.hidden, @"disabled: the window hides and iOS mirrors the iPhone");
  XCTAssertTrue(_coordinator.mirroringActive);
  XCTAssertEqual(host.renderView.superview, host.placeholderView, @"the game is drawn on the iPhone again");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(_coordinator.connected, @"still connected: the preference only hides the window");
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:YES]);
  XCTAssertFalse(_external.hidden);
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO, @YES]));

  [_coordinator suspendForUnsupportedEngine];
  XCTAssertTrue(_coordinator.suspended);
  XCTAssertTrue(_external.hidden, @"Dusklight/KartPad: window hidden, iOS resumes mirroring");
  XCTAssertEqual(host.renderView.superview, host.placeholderView);
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  [_coordinator resumeAfterUnsupportedEngine];
  XCTAssertFalse(_external.hidden);
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);

  [_coordinator detachRenderHost:host];
  XCTAssertEqual(_coordinator.content, NeoExternalContentMenu);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMenuOnTV:NO]);
  XCTAssertNil(_coordinator.menuViewController, @"menu off: the controller leaves the window");
  XCTAssertEqualObjects(_menu.destroyed.lastObject, @"menu_off");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(_external.hidden, @"nothing to show: iOS mirrors the iPhone");
  XCTAssertTrue([NeoExternalDisplayPreferences storeMenuOnTV:YES]);
  XCTAssertEqual(_menu.created, 2U, @"menu on again: recreated");
  XCTAssertEqual(_coordinator.content, NeoExternalContentMenu);
  XCTAssertFalse(_external.hidden);
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

- (void)testDestroyMenuEngineForMemoryKeepsItAwayUntilTheGameDetaches {
  [self connect];
  XCTAssertEqual(_menu.created, 1U);
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  [_coordinator destroyMenuEngineForMemory];
  XCTAssertEqualObjects(_menu.destroyed, @[@"memory"]);
  XCTAssertNil(_coordinator.menuViewController);
  XCTAssertEqualObjects(_coordinator.menuEngineStatus, @"destroyed");
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame, @"the game keeps the TV");
  [_coordinator refresh];
  [NSNotificationCenter.defaultCenter postNotificationName:UIApplicationDidBecomeActiveNotification object:nil];
  XCTAssertNil(_coordinator.menuViewController, @"not recreated while the RPCS3 host is attached");
  XCTAssertEqual(_menu.created, 1U);
  [_coordinator detachRenderHost:host];
  XCTAssertEqual(_menu.created, 2U, @"recreated once the game detached");
  XCTAssertEqual(_coordinator.content, NeoExternalContentMenu);
  XCTAssertEqualObjects(_coordinator.menuEngineStatus, @"attached");
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

- (void)testLegacyFallbackActivatesOnlyAfterTheDelayWithoutAScene {
  __block NSArray<UIScreen*>* screens = @[UIScreen.mainScreen];
  _coordinator.legacyScreens = ^NSArray<UIScreen*>* { return screens; };
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidConnectNotification object:nil];
  XCTAssertFalse(_coordinator.connected, @"UIKit gets 1.5 s to deliver the scene");
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.5]];
  XCTAssertFalse(_coordinator.connected, @"still waiting");
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:1.5]];
  XCTAssertTrue(_coordinator.connected, @"legacy window after the delay");
  XCTAssertEqualObjects(_coordinator.sceneRole, @"legacy");
  XCTAssertEqual(_coordinator.window, _external, @"built through the factory seam");
  XCTAssertEqual(_coordinator.content, NeoExternalContentMenu);
  XCTAssertFalse(_external.isKeyWindow);
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);
  screens = @[];
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidDisconnectNotification object:nil];
  XCTAssertFalse(_coordinator.connected, @"screen gone: legacy window released");
  XCTAssertEqual(host.renderView.superview, host.placeholderView, @"view returned before the window went");
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO]));
  [_coordinator detachRenderHost:host];
  // Once a scene was delivered, the fallback never fires again.
  [self connect];
  [_coordinator sceneDidDisconnect:[self mainScene]];
  screens = @[UIScreen.mainScreen];
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidConnectNotification object:nil];
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:2]];
  XCTAssertFalse(_coordinator.connected, @"scene regime proven: no legacy window");
  // And a scene arriving during the wait cancels the timer and wins.
  [_coordinator setValue:@NO forKey:@"sceneEverConnected"];
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidConnectNotification object:nil];
  [self connect];
  XCTAssertEqualObjects(_coordinator.sceneRole, @"scene");
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:2]];
  XCTAssertEqualObjects(_coordinator.sceneRole, @"scene", @"the timer was cancelled by the scene");
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

- (void)testMTKViewKeepsItsDrawableSizeAndScaleAcrossTheMove {
  id<MTLDevice> device = MTLCreateSystemDefaultDevice();
  if (!device) { NSLog(@"No Metal device in this simulator; MTKView move not exercised"); return; }
  MTKView* metal = [[MTKView alloc] initWithFrame:CGRectMake(0, 0, 852, 393) device:device];
  metal.paused = YES; metal.enableSetNeedsDisplay = NO;
  metal.contentScaleFactor = 3;
  metal.drawableSize = CGSizeMake(2556, 1179);
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:metal];
  [self connect];
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(metal.superview, [self externalRoot]);
  XCTAssertFalse(metal.autoResizeDrawable, @"UIKit must not resize the drawable the core sized");
  XCTAssertEqualWithAccuracy(metal.contentScaleFactor, 3, 0.001, @"layer scale preserved");
  XCTAssertEqualWithAccuracy(metal.drawableSize.width, 2556, 0.5);
  XCTAssertEqualWithAccuracy(metal.drawableSize.height, 1179, 0.5);
  [_coordinator detachRenderHost:host];
  XCTAssertTrue(metal.autoResizeDrawable, @"restored");
  XCTAssertEqualWithAccuracy(metal.contentScaleFactor, 3, 0.001);
  XCTAssertEqual(metal.superview, host.placeholderView);
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

- (void)testSurfaceFollowsTheTVForANonFixedHost {
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:NO render:nil];
  UIView* render = host.renderView;
  const CGFloat phoneScale = render.contentScaleFactor;
  [self connect];
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(render.superview, [self externalRoot]);
  XCTAssertTrue(CGAffineTransformIsIdentity(render.transform), @"no transform: the surface is rebuilt at the TV size");
  XCTAssertEqualWithAccuracy(render.bounds.size.width, 1920, 0.001, @"Fit surface = the whole 16:9 TV");
  XCTAssertEqualWithAccuracy(render.bounds.size.height, 1080, 0.001);
  XCTAssertEqualWithAccuracy(render.center.x, 960, 0.001);
  XCTAssertEqualWithAccuracy(render.contentScaleFactor, _coordinator.screenScale, 0.001, @"the TV's scale");
  XCTAssertEqual(host.surfaces.count, 1U);
  XCTAssertTrue(CGSizeEqualToSize(host.surfaces.lastObject.CGSizeValue, CGSizeMake(1920, 1080)));
  XCTAssertEqualWithAccuracy(host.scales.lastObject.doubleValue, _coordinator.screenScale, 0.001);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]);
  XCTAssertTrue(CGSizeEqualToSize(host.surfaces.lastObject.CGSizeValue, CGSizeMake(1920, 1440)), @"Fill: 4:3 frame, top and bottom cut");
  XCTAssertEqualWithAccuracy(render.bounds.size.height, 1440, 0.001);
  XCTAssertEqualWithAccuracy(render.center.y, 540, 0.001);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeOriginal]);
  XCTAssertEqualWithAccuracy(host.surfaces.lastObject.CGSizeValue.width, 1920, 0.01);
  XCTAssertEqualWithAccuracy(host.surfaces.lastObject.CGSizeValue.height, 393.0 * 1920.0 / 852.0, 0.01, @"Original: phone format");
  [_coordinator refresh];
  XCTAssertEqual(host.surfaces.count, 3U, @"an unchanged surface is not announced again");
  [_coordinator detachRenderHost:host];
  XCTAssertTrue(CGSizeEqualToSize(host.surfaces.lastObject.CGSizeValue, CGSizeZero), @"CGSizeZero = back on the iPhone");
  XCTAssertEqualWithAccuracy(render.contentScaleFactor, phoneScale, 0.001);
  XCTAssertTrue(CGRectEqualToRect(render.frame, host.placeholderView.bounds));
  XCTAssertEqual([host.placeholderView.subviews indexOfObject:render], 0U);
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

- (void)testPreferencesFallBackToTheBuild442KeyAndVerifyWrites {
  XCTAssertEqual(NeoExternalDisplayPreferences.mode, NeoExternalDisplayModeAutomatic);
  XCTAssertTrue(NeoExternalDisplayPreferences.enabled);
  XCTAssertTrue(NeoExternalDisplayPreferences.menuOnTV);
  NSUserDefaults* defaults = NSUserDefaults.standardUserDefaults;
  [defaults setObject:@0 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertFalse(NeoExternalDisplayPreferences.enabled, @"442 Off → disabled until the global switch is used");
  XCTAssertEqual(NeoExternalDisplayPreferences.mode, NeoExternalDisplayModeAutomatic);
  [defaults setObject:@1 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertTrue(NeoExternalDisplayPreferences.enabled);
  XCTAssertEqual(NeoExternalDisplayPreferences.mode, NeoExternalDisplayModeFit, @"442 Fit");
  [defaults setObject:@2 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertEqual(NeoExternalDisplayPreferences.mode, NeoExternalDisplayModeFill, @"442 Fill");
  __block NSUInteger notified = 0;
  id token = [NSNotificationCenter.defaultCenter addObserverForName:NeoExternalDisplayChangedNotification object:nil queue:nil usingBlock:^(NSNotification* n) { notified += 1; }];
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeOriginal]);
  XCTAssertEqual(NeoExternalDisplayPreferences.mode, NeoExternalDisplayModeOriginal, @"the global key wins once stored");
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayLegacyDolphinModeKey], @2, @"the 442 key is never rewritten");
  XCTAssertFalse([NeoExternalDisplayPreferences storeMode:(NeoExternalDisplayMode)7], @"out of range refused");
  XCTAssertEqual(NeoExternalDisplayPreferences.mode, NeoExternalDisplayModeOriginal);
  [defaults setObject:@0 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertTrue(NeoExternalDisplayPreferences.enabled, @"a stored global mode ends the 442 Off fallback");
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:NO]);
  XCTAssertFalse(NeoExternalDisplayPreferences.enabled);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMenuOnTV:NO]);
  XCTAssertFalse(NeoExternalDisplayPreferences.menuOnTV);
  [NSNotificationCenter.defaultCenter removeObserver:token];
  XCTAssertEqual(notified, 3U, @"one notification per verified write, none for the refused one");
}

- (void)testStateDictionaryAndNotificationFollowEveryChange {
  NSMutableArray<NSDictionary*>* posted = [NSMutableArray array];
  id token = [NSNotificationCenter.defaultCenter addObserverForName:NeoExternalDisplayStateChangedNotification object:nil queue:nil usingBlock:^(NSNotification* n) { [posted addObject:n.userInfo]; }];
  NSDictionary* initial = [_coordinator stateDictionary];
  XCTAssertEqualObjects(initial[@"supported"], @YES);
  XCTAssertEqualObjects(initial[@"connected"], @NO);
  XCTAssertEqualObjects(initial[@"content"], @"none");
  XCTAssertEqualObjects(initial[@"sceneRole"], @"none");
  XCTAssertEqualObjects(initial[@"menuEngine"], @"none");
  XCTAssertEqualObjects(initial[@"mode"], @0);
  XCTAssertEqualObjects(initial[@"enabled"], @YES);
  XCTAssertEqualObjects(initial[@"menuOnTV"], @YES);
  if (NSClassFromString(@"UISceneAccessory") == Nil) XCTAssertEqualObjects(initial[@"accessoryStatus"], @"unavailable", @"iOS ≤ 26: no accessory API");
  else XCTAssertTrue([initial[@"accessoryStatus"] isEqualToString:@"registered"] || [initial[@"accessoryStatus"] hasPrefix:@"failed:"]);
  [self connect];
  NSDictionary* connected = posted.lastObject;
  XCTAssertEqualObjects(connected[@"connected"], @YES);
  XCTAssertEqualObjects(connected[@"content"], @"menu");
  XCTAssertEqualObjects(connected[@"sceneRole"], @"scene");
  XCTAssertEqualObjects(connected[@"screenWidth"], @1920);
  XCTAssertEqualObjects(connected[@"screenHeight"], @1080);
  XCTAssertEqualObjects(connected[@"menuEngine"], @"attached");
  XCTAssertEqualObjects(connected[@"mirroringActive"], @NO);
  XCTAssertTrue([connected[@"screenScale"] doubleValue] >= 1);
  XCTAssertEqualObjects(_states.lastObject, connected, @"the stateChanged block sees the same state");
  const NSUInteger count = posted.count;
  [_coordinator refresh];
  XCTAssertEqual(posted.count, count, @"an unchanged state is not re-posted");
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]);
  XCTAssertEqualObjects(posted.lastObject[@"mode"], @2, @"a preference change is reported");
  [_coordinator sceneDidDisconnect:[self mainScene]];
  XCTAssertEqualObjects(posted.lastObject[@"connected"], @NO);
  XCTAssertEqualObjects(posted.lastObject[@"content"], @"none");
  XCTAssertEqualObjects(posted.lastObject[@"menuEngine"], @"destroyed");
  [NSNotificationCenter.defaultCenter removeObserver:token];
}

- (void)present:(UIViewController*)controller on:(UIViewController*)presenter {
  XCTestExpectation* done = [self expectationWithDescription:@"presented"];
  [presenter presentViewController:controller animated:NO completion:^{ [done fulfill]; }];
  [self waitForExpectations:@[done] timeout:5];
  XCTAssertEqual(presenter.presentedViewController, controller);
}
- (void)dismiss:(UIViewController*)controller completion:(dispatch_block_t)completion {
  XCTestExpectation* done = [self expectationWithDescription:@"dismissed"];
  [controller.presentingViewController dismissViewControllerAnimated:NO completion:^{
    if (completion) completion();
    [done fulfill];
  }];
  [self waitForExpectations:@[done] timeout:5];
}

/// iOS 27 regime: one accessory registration per presented controller, the
/// root always and the game controller once its bridge attached; the
/// dismissed controller's registration is released at the next pass (the
/// bridge's refresh in the dismissal completion, or a window notification)
/// with the registration object registerSceneAccessory: returned, and the
/// root's survives so the system falls back to it by itself.
- (void)testSceneAccessoryRegistrationsFollowThePresentedControllers {
  if (!InstallFakeSceneAccessoryIfNeeded()) {
    // Real iOS 27 SDK: the production API is used and only its status is observable here.
    [_coordinator refresh];
    XCTAssertTrue([_coordinator.accessoryStatus isEqualToString:@"registered"] || [_coordinator.accessoryStatus hasPrefix:@"failed:"]);
    return;
  }
  UIViewController* root = [(id)UIApplication.sharedApplication.delegate window].rootViewController;
  [_coordinator refresh];
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"registered");
  XCTAssertTrue(FakeAccessoryHolds(root), @"the application root holds a registration");
  const NSUInteger registrations = gFakeRegisterCalls;
  [_coordinator refresh];
  [NSNotificationCenter.defaultCenter postNotificationName:UIApplicationDidBecomeActiveNotification object:nil];
  XCTAssertEqual(gFakeRegisterCalls, registrations, @"a presented controller is registered once");

  // A game controller is presented and its bridge attaches: it gets its own
  // registration (the topmost, the one the system presents) and the root
  // keeps its own.
  UIViewController* game = [UIViewController new];
  game.modalPresentationStyle = UIModalPresentationFullScreen;
  [self present:game on:root];
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  XCTAssertTrue(FakeAccessoryHolds(game), @"the presented game controller holds a registration");
  XCTAssertTrue(FakeAccessoryHolds(root), @"the root keeps its registration while the game is up");
  XCTAssertEqual(gFakeUnregisterCalls, 0U);
  // A menu presented over the game is not registered by a refresh: a
  // setting changed from an in-game menu must not move the scene.
  UIViewController* menu = [UIViewController new];
  [self present:menu on:game];
  [_coordinator refresh];
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]);
  XCTAssertFalse(FakeAccessoryHolds(menu), @"a menu over the game is not registered by a refresh");
  XCTAssertTrue(FakeAccessoryHolds(game) && FakeAccessoryHolds(root), @"the registrations of the presentation chain are kept");
  [self dismiss:menu completion:nil];

  // The bridge detaches, then dismisses; the completion calls refresh (the
  // explicit hook): the dismissed controller's registration is released.
  [_coordinator detachRenderHost:host];
  XCTAssertTrue(FakeAccessoryHolds(game), @"the detach alone keeps the still-presented game controller registered");
  NeoExternalDisplayCoordinator* coordinator = _coordinator;
  [self dismiss:game completion:^{ [coordinator refresh]; }];
  XCTAssertFalse(FakeAccessoryHolds(game), @"dismissed: its registration is released");
  XCTAssertEqual(gFakeUnregisterCalls, 1U);
  XCTAssertTrue(gFakeUnregisterMatched, @"unregisterSceneAccessory: receives the registration returned by registerSceneAccessory:");
  XCTAssertTrue(FakeAccessoryHolds(root), @"the root's registration survives: the system falls back to it by itself");

  // Safety net: a dismissal nobody reported is caught by the window notifications.
  UIViewController* other = [UIViewController new];
  other.modalPresentationStyle = UIModalPresentationFullScreen;
  [self present:other on:root];
  [_coordinator attachRenderHost:host];
  XCTAssertTrue(FakeAccessoryHolds(other));
  [_coordinator detachRenderHost:host];
  [self dismiss:other completion:nil];
  // No refresh from the bridge: only a window notification can release it.
  [NSNotificationCenter.defaultCenter postNotificationName:UIWindowDidBecomeHiddenNotification object:nil];
  XCTAssertFalse(FakeAccessoryHolds(other), @"UIWindowDidBecomeHidden re-reads the presentation chain");
  XCTAssertEqual(gFakeUnregisterCalls, 2U, @"released once, with its registration");
  XCTAssertTrue(gFakeUnregisterMatched);
  [NSNotificationCenter.defaultCenter postNotificationName:UIWindowDidBecomeKeyNotification object:nil];
  XCTAssertTrue(FakeAccessoryHolds(root));
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"registered");
}
@end
'''
if platform.system() != 'Darwin':
    print('SKIP: the external display simulator harness needs macOS/Xcode; sources composed, no test executed')
    raise SystemExit(0)
ns['native']()
print('PASS: external display connection, menu/game placement in every mode, disconnection order, reconnection, mirroring fallbacks, '
      'menu engine lifecycle, legacy fallback, MTKView preservation, TV-resolution surfaces, preferences, state events and '
      'iOS 27 accessory registrations executed on the iOS Simulator')
