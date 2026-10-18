#!/usr/bin/env python3
"""Real UIKit/XCTest checks of the external_display coordinator in the iOS
Simulator (macOS CI: external-display-check).

Reuses the simulator/project harness of dolphin_account_267_test.py with the
production NeoExternalDisplayCoordinator.m, NeoExternalDisplaySceneDelegate.m
and NeoExternalDisplayPreferences.m (UIKit only: the Flutter menu engine is
replaced by a provider returning a plain controller). The external window
is injected through the windowFactory seam (scene-less, 1920×1080), the
application's own scene stands in for the external one, a second external
scene is an object answering what the coordinator reads of a scene, and the
legacy fallback runs against the legacyScreens seam. Executed: connection
mirroring the iPhone outside a game (Build 449: no menu engine is created,
a window built in its scene leaves it outside a game and comes back before
the game's render view, Apple's documented way back to mirroring), the game
in Automatic/Fit/Fill/Original, disconnection (view returned before the
window goes) and reconnection, the set of connected external scenes (a
second scene stands by, is adopted, a scene UIKit no longer lists is
dropped by a refresh), disabled/suspended/outside-a-game mirroring, a menu
controller never shown on the TV and released with its engine, RPCS3's
memory request harmless, the 1.5 s
legacy fallback and its refusal of a window in no scene, MTKView drawable
preservation, TV-resolution surfaces for a non-fixed host (the whole TV in
every format and orientation, a scale change alone announced), a call made
during a pass applied at its end, the Build 442 preference fallback and a
format choice that never turns the output on, the state notification, and
the iOS 27 scene accessory (only for an SDK 27 binary, never next to an
automatic scene; the root and the host's owning controller, never a menu
over the game; isEnabled off when there is nothing to show; released once
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
# No Dolphin menu here, hence no cheat catalogue (Build 484 harness).
ns['CATALOGUE_SOURCES'] = []

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
/// Run once, inside the coordinator's pass, when the view reaches the TV.
@property(nonatomic, copy) dispatch_block_t onActive;
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
- (void)externalDisplayDidChange:(BOOL)active {
  [self.activeChanges addObject:@(active)];
  if (active && self.onActive) {
    dispatch_block_t block = self.onActive;
    self.onActive = nil;
    block();
  }
}
@end

/// Stands in for NeoExternalDisplayMenuEngine (Flutter is not linked here).
@interface FakeMenuProvider : NSObject <NeoExternalMenuProvider>
@property(nonatomic, assign) BOOL configured;
@property(nonatomic, strong) UIViewController* controller;
@property(nonatomic, copy) NSString* status;
@property(nonatomic, assign) NSUInteger created;
@property(nonatomic, strong) NSMutableArray<NSString*>* destroyed;
/// externalMenuSetVisible: values, one entry per change.
@property(nonatomic, strong) NSMutableArray<NSNumber*>* visibility;
@end
@implementation FakeMenuProvider
- (instancetype)init {
  if ((self = [super init])) {
    _status = @"none"; _destroyed = [NSMutableArray array]; _configured = YES; _visibility = [NSMutableArray array];
  }
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
  [self.visibility removeAllObjects];
}
- (NSString*)externalMenuEngineStatus { return self.status; }
- (void)externalMenuSetVisible:(BOOL)visible {
  if (!self.controller) return;
  if (self.visibility.lastObject != nil && self.visibility.lastObject.boolValue == visible) return;
  [self.visibility addObject:@(visible)];
}
@end

/// A second external scene: UIKit cannot connect one in the simulator, so
/// an object answering what the coordinator reads of a UIWindowScene
/// (screen, activationState, delegate) stands in for it. It is not in
/// UIApplication.connectedScenes, so a refresh treats it as gone.
@interface FakeExternalScene : NSObject
@property(nonatomic, strong) UIScreen* screen;
@property(nonatomic, assign) UISceneActivationState activationState;
@property(nonatomic, strong) id delegate;
@end
@implementation FakeExternalScene
@end

/// A UISceneAccessoryRegistration with its isEnabled property.
@interface FakeSceneAccessoryRegistration : NSObject
@property(nonatomic, assign, getter=isEnabled) BOOL enabled;
@end
@implementation FakeSceneAccessoryRegistration
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
    FakeSceneAccessoryRegistration* registration = [FakeSceneAccessoryRegistration new];
    registration.enabled = YES;
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
/// The controller holds a registration and it is enabled.
static BOOL FakeAccessoryEnabled(UIViewController* controller) {
  FakeSceneAccessoryRegistration* registration = [gFakeAccessoryRegistrations objectForKey:controller];
  return registration != nil && registration.isEnabled;
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
    if ([c.sceneRole isEqualToString:@"scene"]) {
      // The scenes standing by go first, the shown one last (no adoption).
      id shown = [c valueForKey:@"scene"];
      for (UIWindowScene* scene in c.externalScenes)
        if (scene != shown) [c sceneDidDisconnect:scene];
      [c sceneDidDisconnect:shown];
    } else {
      c.legacyScreens = ^NSArray<UIScreen*>* { return @[]; };
      [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidDisconnectNotification object:nil];
    }
  }
  [c detachMenuViewController];
  // The iOS 27 regime off for the next test: no registration stays behind.
  c.buildSDKMajorVersion = ^NSInteger { return 0; };
  [c refresh];
  c.menuProvider = nil; c.windowFactory = nil; c.legacyScreens = nil; c.stateChanged = nil;
  c.buildSDKMajorVersion = nil; c.screenScaleReader = nil;
  // Private flags of the singleton, reset so each test starts from a cold app.
  [c setValue:@NO forKey:@"sceneEverConnected"];
  [c setValue:@NO forKey:@"menuSuppressed"];
  [c setValue:nil forKey:@"lastState"];
  [c setValue:[NSMutableArray array] forKey:@"connectedExternalScenes"];
  [c setValue:[NSMutableArray array] forKey:@"automaticScenes"];
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
/// What the coordinator reports for a binary of this SDK (the host's own
/// Info.plist, as NeoExternalDisplaySDKMajorVersion reads it).
- (NSInteger)hostSDKMajor {
  NSDictionary* info = NSBundle.mainBundle.infoDictionary;
  return NeoExternalDisplaySDKMajorVersion(info[@"DTPlatformVersion"], info[@"DTSDKName"]);
}


/// Build 449: outside a game the TV shows nothing of NeoStation's own and
/// iOS mirrors the iPhone, so the TV shows the NeoStation interface itself.
/// Retired contract (Build 447/448, "connect shows the menu"): the second
/// engine's TV view filled the TV at connection; it was the SecondaryScreen
/// of Android handhelds (the selected console's logo), not the interface.
- (void)testConnectMirrorsTheIPhoneThenTheGameTakesTheScreenInEachMode {
  [self connect];
  XCTAssertTrue(_coordinator.connected);
  XCTAssertEqualObjects(_coordinator.sceneRole, @"scene");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone, @"nothing of NeoStation's own outside a game");
  XCTAssertEqual(_coordinator.window, _external, @"the window comes from the factory seam");
  XCTAssertTrue(_external.hidden, @"iOS mirrors the iPhone");
  XCTAssertTrue(_coordinator.mirroringActive);
  XCTAssertFalse(_external.isKeyWindow, @"never key: the iPhone keeps the keys");
  XCTAssertTrue([(id)UIApplication.sharedApplication.delegate window].isKeyWindow);
  XCTAssertFalse(_coordinator.menuOnTV, @"the TV never shows a menu of its own");
  XCTAssertEqual(_menu.created, 0U, @"no menu engine is created for the TV");
  XCTAssertNil(_coordinator.menuViewController);
  XCTAssertEqual(_menu.visibility.count, 0U);
  XCTAssertEqualObjects(_coordinator.menuEngineStatus, @"none");
  XCTAssertTrue(CGSizeEqualToSize(_coordinator.screenPointSize, CGSizeMake(1920, 1080)));
  XCTAssertEqual(_coordinator.mode, NeoExternalDisplayModeAutomatic, @"Automatic by default");

  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  UIView* render = host.renderView;
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame);
  XCTAssertFalse(_external.hidden, @"the game takes the TV");
  XCTAssertFalse(_coordinator.mirroringActive);
  XCTAssertEqual(render.superview, [self externalRoot], @"render view on the external window");
  XCTAssertEqual(host.overlay.superview, host.placeholderView, @"controls stay on the phone");
  XCTAssertEqual(_menu.created, 0U, @"still no menu engine");
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
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone, @"the game left: iOS mirrors the iPhone again");
  XCTAssertTrue(_external.hidden);
  XCTAssertTrue(_coordinator.mirroringActive);
  XCTAssertEqual(_menu.created, 0U);

  [_coordinator sceneDidDisconnect:[self mainScene]];
  XCTAssertFalse(_coordinator.connected);
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertEqualObjects(_coordinator.sceneRole, @"none");
  XCTAssertNil(_coordinator.menuViewController);
  XCTAssertEqual(_menu.destroyed.count, 0U, @"no menu engine ever existed");
  XCTAssertTrue(_external.hidden);
  XCTAssertNil(_external.rootViewController);
  XCTAssertTrue(CGSizeEqualToSize(_coordinator.screenPointSize, CGSizeZero));
  XCTAssertEqual(_coordinator.externalScenes.count, 0U);
}

/// Build 449, Apple's documented way back to mirroring: a window of the app
/// in the external scene ends the mirroring of the iPhone, taking it out of
/// the scene (windowScene = nil) brings the mirroring back, and hiding it
/// alone does not (Apple Developer Forums thread 766398). A window built in
/// its scene, as -[UIWindow initWithWindowScene:] does on the device, leaves
/// it outside a game, comes back for the game before the render view
/// reaches it, and leaves it again for an unsupported engine, a disabled
/// output and the end of the game.
- (void)testOutsideAGameTheWindowLeavesItsSceneAndComesBackForTheGame {
  UIWindowScene* scene = [self mainScene];
  UIWindow* inScene = [[UIWindow alloc] initWithWindowScene:scene];
  inScene.frame = CGRectMake(0, 0, 1920, 1080);
  XCTAssertEqual(inScene.windowScene, scene, @"precondition: the window is built in its scene");
  __weak UIWindow* weakWindow = inScene;
  _coordinator.windowFactory = ^UIWindow*(UIWindowScene* s, UIScreen* screen) { return weakWindow; };
  [self connect];
  XCTAssertEqual(_coordinator.window, inScene);
  XCTAssertNil(inScene.windowScene, @"outside a game the window left its scene: iOS mirrors the iPhone");
  XCTAssertTrue(inScene.hidden);
  XCTAssertTrue(_coordinator.mirroringActive);
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(_coordinator.connected, @"the external scene stays known");

  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  __block UIWindowScene* sceneWhenOnTV = nil;
  host.onActive = ^{ sceneWhenOnTV = weakWindow.windowScene; };
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(sceneWhenOnTV, scene, @"the window was back in its scene before the render view reached it");
  XCTAssertEqual(inScene.windowScene, scene, @"the game brings the window back into its scene");
  XCTAssertFalse(inScene.hidden);
  XCTAssertEqual(host.renderView.superview, inScene.rootViewController.view);
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame);
  XCTAssertFalse(_coordinator.mirroringActive);

  [_coordinator suspendForUnsupportedEngine];
  XCTAssertNil(inScene.windowScene, @"Dusklight/KartPad: out of the scene, iOS mirrors the iPhone");
  XCTAssertEqual(host.renderView.superview, host.placeholderView, @"the game is drawn on the iPhone");
  [_coordinator resumeAfterUnsupportedEngine];
  XCTAssertEqual(inScene.windowScene, scene);
  XCTAssertEqual(host.renderView.superview, inScene.rootViewController.view);
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:NO]);
  XCTAssertNil(inScene.windowScene, @"output off: out of the scene");
  XCTAssertTrue(inScene.hidden);
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:YES]);
  XCTAssertEqual(inScene.windowScene, scene, @"output on again during the game: back in the scene");
  XCTAssertFalse(inScene.hidden);

  [_coordinator detachRenderHost:host];
  XCTAssertNil(inScene.windowScene, @"the game left: the window leaves its scene again");
  XCTAssertTrue(inScene.hidden);
  XCTAssertEqual(host.renderView.superview, host.placeholderView);
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO, @YES, @NO, @YES, @NO]));
  [_coordinator refresh];
  XCTAssertNil(inScene.windowScene, @"a refresh outside a game changes nothing");

  [_coordinator sceneDidDisconnect:scene];
  XCTAssertNil(_coordinator.window);
  XCTAssertNil(inScene.windowScene, @"a released window is never put back");
  XCTAssertTrue(inScene.hidden);
  XCTAssertNil(inScene.rootViewController);
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
  // The same scene delivered again changes nothing (no teardown, no second move).
  [self connect];
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);
  XCTAssertEqualObjects(host.activeChanges, @[@YES], @"a scene delivered again is not a reconnection");
  XCTAssertEqual(_coordinator.externalScenes.count, 1U);
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
  // Retired (Build 447/448): "the menu engine is created once the menu is
  // about to be shown". Build 449: the game gone, iOS mirrors the iPhone.
  XCTAssertEqual(_menu.created, 0U, @"no menu engine once the game left either");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(_external.hidden);
  [_coordinator sceneDidDisconnect:[self mainScene]];
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO, @YES, @NO]));
}

/// The set of connected external scenes (review M1): a second scene stands
/// by while the first one keeps the window and the game; when the shown
/// scene goes, the remaining one is adopted; a refresh rescans
/// UIApplication.connectedScenes and drops a tracked scene UIKit no longer
/// lists. Since Build 449 no menu engine is involved (outside a game the
/// TV mirrors the iPhone).
- (void)testASecondSceneStandsByAndIsAdoptedWhenTheShownOneDisconnects {
  UIWindow* second = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 1280, 720)];
  __weak UIWindow* weakFirst = _external;
  __weak UIWindow* weakSecond = second;
  UIWindowScene* primary = [self mainScene];
  _coordinator.windowFactory = ^UIWindow*(UIWindowScene* scene, UIScreen* screen) {
    return scene == primary ? weakFirst : weakSecond;
  };
  FakeExternalScene* standby = [FakeExternalScene new];
  standby.screen = UIScreen.mainScreen;
  standby.activationState = UISceneActivationStateForegroundInactive;
  UIWindowScene* other = (UIWindowScene*)(id)standby;

  [self connect];
  XCTAssertEqual(_menu.created, 0U, @"no menu engine for the TV (Build 449)");
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);

  [_coordinator sceneDidConnect:other];
  XCTAssertEqual(_coordinator.externalScenes.count, 2U, @"both scenes are tracked");
  XCTAssertEqual(_coordinator.window, _external, @"the shown scene keeps the window");
  XCTAssertEqual(host.renderView.superview, [self externalRoot], @"the game stays where it is");
  XCTAssertEqualObjects(host.activeChanges, @[@YES], @"no move for a scene standing by");
  XCTAssertNil(second.rootViewController, @"no window was built for the scene standing by");

  [_coordinator sceneDidDisconnect:primary];
  XCTAssertTrue(_coordinator.connected, @"a scene remains: the window moves there");
  XCTAssertEqual(_coordinator.window, second);
  XCTAssertEqualObjects(_coordinator.sceneRole, @"scene");
  XCTAssertEqual(_coordinator.externalScenes.count, 1U);
  XCTAssertEqual(host.renderView.superview, second.rootViewController.view, @"the game follows the adopted scene");
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO, @YES]), @"returned to the phone, then moved again");
  XCTAssertTrue(_external.hidden, @"the old window is released");
  XCTAssertTrue(CGSizeEqualToSize(_coordinator.screenPointSize, CGSizeMake(1280, 720)));

  // Retired (Build 447/448): "the same engine shows the menu in the adopted
  // window". Build 449: the game gone, the adopted scene mirrors the iPhone.
  [_coordinator detachRenderHost:host];
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(second.hidden, @"nothing of NeoStation's own outside a game");
  XCTAssertEqual(_menu.created, 0U);
  XCTAssertNil(_coordinator.menuViewController);

  // The stand-in is not in UIApplication.connectedScenes: a refresh treats
  // it as disconnected.
  [_coordinator refresh];
  XCTAssertFalse(_coordinator.connected, @"a scene UIKit no longer lists is dropped by the rescan");
  XCTAssertEqual(_coordinator.externalScenes.count, 0U);
  XCTAssertEqual(_menu.destroyed.count, 0U, @"no menu engine ever existed");
  XCTAssertTrue(second.hidden);
}

- (void)testDisabledSuspendedAndOutsideAGameFallBackToMirroring {
  [self connect];
  XCTAssertTrue(_external.hidden, @"outside a game: iOS mirrors the iPhone (Build 449)");
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
  XCTAssertNil(_coordinator.menuViewController);
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:YES]);
  XCTAssertFalse(_external.hidden);
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);
  XCTAssertEqualObjects(host.activeChanges, (@[@YES, @NO, @YES]));

  [_coordinator suspendForUnsupportedEngine];
  XCTAssertTrue(_coordinator.suspended);
  XCTAssertEqualObjects([_coordinator stateDictionary][@"suspended"], @YES, @"reported to Dart");
  XCTAssertTrue(_external.hidden, @"Dusklight/KartPad: window hidden, iOS resumes mirroring");
  XCTAssertEqual(host.renderView.superview, host.placeholderView);
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  [_coordinator resumeAfterUnsupportedEngine];
  XCTAssertEqualObjects([_coordinator stateDictionary][@"suspended"], @NO);
  XCTAssertFalse(_external.hidden);
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);

  // Retired (Build 447/448): the menu came back on the TV once the game left
  // and only the "menu on the TV" switch turned it off. Build 449: the game
  // gone, iOS mirrors the iPhone, and the stored switch changes nothing.
  [_coordinator detachRenderHost:host];
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(_external.hidden, @"nothing to show: iOS mirrors the iPhone");
  XCTAssertTrue([NeoExternalDisplayPreferences storeMenuOnTV:YES]);
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone, @"the stored switch of Build 447 is not read");
  XCTAssertTrue(_external.hidden);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMenuOnTV:NO]);
  XCTAssertTrue(_external.hidden);
  XCTAssertEqual(_menu.created, 0U, @"no menu engine at any point");
  XCTAssertEqual(_menu.destroyed.count, 0U);
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

/// RPCS3 still asks for the menu engine's destruction when it attaches
/// (memory). Since Build 449 there is none for the TV: the call is harmless
/// and nothing is created once the game detaches. Retired contract:
/// "recreated once the game detached".
- (void)testDestroyMenuEngineForMemoryIsHarmlessAndNoEngineComesBack {
  [self connect];
  XCTAssertEqual(_menu.created, 0U);
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  [_coordinator destroyMenuEngineForMemory];
  XCTAssertEqual(_menu.destroyed.count, 0U, @"nothing to destroy");
  XCTAssertNil(_coordinator.menuViewController);
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame, @"the game keeps the TV");
  XCTAssertEqual(host.renderView.superview, [self externalRoot]);
  [_coordinator refresh];
  [NSNotificationCenter.defaultCenter postNotificationName:UIApplicationDidBecomeActiveNotification object:nil];
  XCTAssertNil(_coordinator.menuViewController);
  [_coordinator detachRenderHost:host];
  XCTAssertEqual(_menu.created, 0U, @"no engine once the game detached");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertEqualObjects(_coordinator.menuEngineStatus, @"none");
  XCTAssertTrue(_external.hidden);
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

/// A controller attached as a menu (the second engine's, or any) is never
/// shown on the TV and is released at the next pass, with its engine.
- (void)testAMenuControllerIsNeverShownOnTheTV {
  [self connect];
  UIViewController* menu = [UIViewController new];
  _menu.controller = menu;
  _menu.status = @"created";
  [_coordinator attachMenuViewController:menu];
  XCTAssertNil(_coordinator.menuViewController, @"released at once");
  XCTAssertNil(menu.view.superview, @"never placed in the external window");
  XCTAssertEqualObjects(_menu.destroyed, @[@"menu_off"], @"its engine is released");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  XCTAssertTrue(_external.hidden, @"iOS keeps mirroring the iPhone");
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

/// A window in a scene of the target screen: the legacy fallback uses it.
- (UIWindow*)legacyWindowInTheMainScene {
  UIWindow* window = [[UIWindow alloc] initWithWindowScene:[self mainScene]];
  window.frame = CGRectMake(0, 0, 1920, 1080);
  return window;
}

- (void)testLegacyFallbackActivatesOnlyAfterTheDelayWithoutAScene {
  UIWindow* legacy = [self legacyWindowInTheMainScene];
  __weak UIWindow* weakLegacy = legacy;
  __weak UIWindow* weakExternal = _external;
  // Scene calls get the scene window, legacy calls (no scene) a window that
  // ended up in a scene of the target screen (review M2).
  _coordinator.windowFactory = ^UIWindow*(UIWindowScene* scene, UIScreen* screen) {
    return scene != nil ? weakExternal : weakLegacy;
  };
  __block NSArray<UIScreen*>* screens = @[UIScreen.mainScreen];
  _coordinator.legacyScreens = ^NSArray<UIScreen*>* { return screens; };
  XCTAssertEqual(legacy.windowScene.screen, UIScreen.mainScreen, @"precondition: the window is in a scene of the target screen");
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidConnectNotification object:nil];
  XCTAssertFalse(_coordinator.connected, @"UIKit gets 1.5 s to deliver the scene");
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.5]];
  XCTAssertFalse(_coordinator.connected, @"still waiting");
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:1.5]];
  XCTAssertTrue(_coordinator.connected, @"legacy window after the delay");
  XCTAssertEqualObjects(_coordinator.sceneRole, @"legacy");
  XCTAssertEqual(_coordinator.window, legacy, @"built through the factory seam");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone, @"outside a game nothing of NeoStation's own (Build 449)");
  XCTAssertTrue(legacy.hidden);
  XCTAssertEqual(legacy.windowScene.screen, UIScreen.mainScreen, @"a legacy window is never taken out of its scene");
  XCTAssertFalse(legacy.isKeyWindow);
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(host.renderView.superview, legacy.rootViewController.view);
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
  legacy.hidden = YES;
}

/// Review M2: in a scene-based app a window made with initWithFrame: and
/// window.screen has no scene and is never displayed. The fallback then
/// stays in mirroring and moves no render view (moving it would leave both
/// screens black).
- (void)testALegacyWindowWithoutASceneStaysInMirroringAndMovesNothing {
  UIWindow* orphan = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 1920, 1080)];
  orphan.windowScene = nil;
  XCTAssertNil(orphan.windowScene, @"precondition: a window in no scene");
  __weak UIWindow* weakOrphan = orphan;
  _coordinator.windowFactory = ^UIWindow*(UIWindowScene* scene, UIScreen* screen) { return weakOrphan; };
  _coordinator.legacyScreens = ^NSArray<UIScreen*>* { return @[UIScreen.mainScreen]; };
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenDidConnectNotification object:nil];
  [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:2]];
  XCTAssertFalse(_coordinator.connected, @"no window of ours: iOS keeps mirroring");
  XCTAssertEqualObjects(_coordinator.sceneRole, @"none");
  XCTAssertEqual(host.renderView.superview, host.placeholderView, @"the game stays on the iPhone");
  XCTAssertEqual(host.activeChanges.count, 0U, @"nothing was moved");
  XCTAssertEqual(_menu.created, 0U, @"no menu engine for a window nobody sees");
  XCTAssertTrue(orphan.hidden);
  XCTAssertNil(orphan.rootViewController);
  [_coordinator detachRenderHost:host];
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

/// Review M3: for a host whose surface follows the TV, the surface is the
/// whole TV in every format (the host keeps each game's aspect in it),
/// recomputed at every pass from the current iPhone layout: a portrait
/// phone no longer gives a pillar.
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
  // Retired 1920 × 1440 (Fill) and 1920 × 886 (Original): the surface is
  // the whole TV in every format, the host keeps the game's aspect in it.
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]);
  XCTAssertEqualWithAccuracy(render.bounds.size.height, 1080, 0.001, @"Fill: the whole TV");
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeOriginal]);
  XCTAssertEqualWithAccuracy(render.bounds.size.width, 1920, 0.001, @"Original: the whole TV");
  XCTAssertEqualWithAccuracy(render.bounds.size.height, 1080, 0.001);
  XCTAssertEqual(host.surfaces.count, 1U, @"an unchanged surface is not announced again, whatever the format");
  // The phone turns to portrait: the iPhone layout changes, the TV surface does not.
  host.placeholderView.bounds = CGRectMake(0, 0, 393, 852);
  [_coordinator refresh];
  XCTAssertTrue(CGSizeEqualToSize(render.bounds.size, CGSizeMake(1920, 1080)), @"portrait: still the whole TV, no pillar");
  XCTAssertEqualWithAccuracy(render.center.y, 540, 0.001);
  XCTAssertEqual(host.surfaces.count, 1U);
  [_coordinator detachRenderHost:host];
  XCTAssertTrue(CGSizeEqualToSize(host.surfaces.lastObject.CGSizeValue, CGSizeZero), @"CGSizeZero = back on the iPhone");
  XCTAssertEqualWithAccuracy(render.contentScaleFactor, phoneScale, 0.001);
  XCTAssertTrue(CGRectEqualToRect(render.frame, host.placeholderView.bounds));
  XCTAssertEqual([host.placeholderView.subviews indexOfObject:render], 0U);
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

/// Review m6: a mode change of the TV that keeps the points and changes the
/// scale (720p @1x to 1440p @2x) is a new drawable: the scale is re-read at
/// every pass and compared with the size.
- (void)testAScaleChangeAloneReachesTheHost {
  __block CGFloat tvScale = 1;
  _coordinator.screenScaleReader = ^CGFloat { return tvScale; };
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:NO render:nil];
  [self connect];
  [_coordinator attachRenderHost:host];
  XCTAssertEqual(host.surfaces.count, 1U);
  XCTAssertEqualWithAccuracy(host.scales.lastObject.doubleValue, 1, 0.001);
  XCTAssertEqualWithAccuracy(_coordinator.screenScale, 1, 0.001);
  tvScale = 2;
  [NSNotificationCenter.defaultCenter postNotificationName:UIScreenModeDidChangeNotification object:nil];
  XCTAssertEqual(host.surfaces.count, 2U, @"same points, new scale: announced");
  XCTAssertTrue(CGSizeEqualToSize(host.surfaces.lastObject.CGSizeValue, CGSizeMake(1920, 1080)));
  XCTAssertEqualWithAccuracy(host.scales.lastObject.doubleValue, 2, 0.001);
  XCTAssertEqualWithAccuracy(host.renderView.contentScaleFactor, 2, 0.001);
  XCTAssertEqualWithAccuracy(_coordinator.screenScale, 2, 0.001);
  XCTAssertEqualObjects([_coordinator stateDictionary][@"screenScale"], @2, @"reported to Dart");
  [_coordinator refresh];
  XCTAssertEqual(host.surfaces.count, 2U, @"nothing new: not announced again");
  [_coordinator detachRenderHost:host];
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

/// Review m5: a call made during a pass (here a preference written by a
/// host's callback while its view moves) is applied by one more pass at
/// the end, not lost.
- (void)testACallMadeDuringAPassIsAppliedAtItsEnd {
  [self connect];
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  host.onActive = ^{ XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]); };
  [_coordinator attachRenderHost:host];
  const CGSize tv = CGSizeMake(1920, 1080), phone = CGSizeMake(852, 393);
  XCTAssertEqualWithAccuracy(host.renderView.transform.a, NeoExternalDisplayScale(tv, phone, NeoExternalDisplayModeFill), 0.001,
                             @"the Fill written during the pass is placed");
  XCTAssertEqualObjects([_coordinator stateDictionary][@"mode"], @2);
  XCTAssertEqualObjects(_states.lastObject[@"mode"], @2, @"the state reported after the pass is the final one");
  XCTAssertEqualObjects(host.activeChanges, @[@YES], @"moved once");
  [_coordinator detachRenderHost:host];
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
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayEnabledKey], @YES, @"the derived switch (442 Fill: on) is persisted first");
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
  XCTAssertEqual(notified, 3U, @"one notification per verified write, none for the refused one nor the derived switch");
}

/// Review m1: a 442 user who had the Dolphin output Off (no global key yet)
/// keeps the output off when the format chip is used: the derived Enabled
/// value is persisted before the mode ends the fallback.
- (void)testChoosingAFormatNeverTurnsTheOutputOnByItself {
  NSUserDefaults* defaults = NSUserDefaults.standardUserDefaults;
  [defaults setObject:@0 forKey:NeoExternalDisplayLegacyDolphinModeKey];
  XCTAssertFalse(NeoExternalDisplayPreferences.enabled);
  __block NSUInteger notified = 0;
  id token = [NSNotificationCenter.defaultCenter addObserverForName:NeoExternalDisplayChangedNotification object:nil queue:nil usingBlock:^(NSNotification* n) { notified += 1; }];
  [self connect];
  XCTAssertTrue(_external.hidden, @"442 Off: mirroring");
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]);
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayEnabledKey], @NO, @"the Off of 442 became the global switch");
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayModeKey], @2, @"the format is stored for later");
  XCTAssertFalse(NeoExternalDisplayPreferences.enabled, @"still off after the format was chosen");
  XCTAssertEqual(NeoExternalDisplayPreferences.mode, NeoExternalDisplayModeFill);
  XCTAssertEqualObjects([defaults objectForKey:NeoExternalDisplayLegacyDolphinModeKey], @0, @"the 442 key is never rewritten");
  XCTAssertEqual(notified, 1U, @"one notification: the mode");
  XCTAssertTrue(_external.hidden, @"still mirroring");
  XCTAssertEqual(_menu.created, 0U);
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFit]);
  XCTAssertEqual(notified, 2U, @"the next mode writes the mode only");
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:YES]);
  XCTAssertTrue(_coordinator.enabled, @"the switch turns it on");
  // Retired (Build 447/448): the switch showed the menu on the TV at once.
  // Build 449: outside a game iOS keeps mirroring the iPhone; a game takes
  // the TV.
  XCTAssertTrue(_external.hidden, @"outside a game: mirroring");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone);
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator attachRenderHost:host];
  XCTAssertFalse(_external.hidden, @"the game takes the TV now that the output is on");
  XCTAssertEqual(_coordinator.content, NeoExternalContentGame);
  [_coordinator detachRenderHost:host];
  [NSNotificationCenter.defaultCenter removeObserver:token];
  [_coordinator sceneDidDisconnect:[self mainScene]];
}

- (void)testStateDictionaryAndNotificationFollowEveryChange {
  NSMutableArray<NSDictionary*>* posted = [NSMutableArray array];
  id token = [NSNotificationCenter.defaultCenter addObserverForName:NeoExternalDisplayStateChangedNotification object:nil queue:nil usingBlock:^(NSNotification* n) { [posted addObject:n.userInfo]; }];
  [_coordinator refresh];
  NSDictionary* initial = [_coordinator stateDictionary];
  XCTAssertEqualObjects(initial[@"supported"], @YES);
  XCTAssertEqualObjects(initial[@"connected"], @NO);
  XCTAssertEqualObjects(initial[@"content"], @"none");
  XCTAssertEqualObjects(initial[@"sceneRole"], @"none");
  XCTAssertEqualObjects(initial[@"menuEngine"], @"none");
  XCTAssertEqualObjects(initial[@"mode"], @0);
  XCTAssertEqualObjects(initial[@"enabled"], @YES);
  XCTAssertEqualObjects(initial[@"menuOnTV"], @NO, @"Build 449: the TV never shows a menu of its own");
  XCTAssertEqualObjects(initial[@"suspended"], @NO);
  if (NSClassFromString(@"UISceneAccessory") == Nil) XCTAssertEqualObjects(initial[@"accessoryStatus"], @"unavailable", @"iOS ≤ 26: no accessory API");
  else if ([self hostSDKMajor] < 27) XCTAssertEqualObjects(initial[@"accessoryStatus"], @"inactive:sdk", @"a binary of an SDK before 27 keeps the automatic scene");
  else XCTAssertTrue([initial[@"accessoryStatus"] isEqualToString:@"disabled"] || [initial[@"accessoryStatus"] hasPrefix:@"failed:"],
                     @"SDK 27: nothing to show outside a game, no enabled registration");
  [self connect];
  NSDictionary* connected = posted.lastObject;
  XCTAssertEqualObjects(connected[@"connected"], @YES);
  XCTAssertEqualObjects(connected[@"content"], @"none", @"outside a game the TV mirrors the iPhone");
  XCTAssertEqualObjects(connected[@"sceneRole"], @"scene");
  XCTAssertEqualObjects(connected[@"screenWidth"], @1920);
  XCTAssertEqualObjects(connected[@"screenHeight"], @1080);
  XCTAssertEqualObjects(connected[@"menuEngine"], @"none");
  XCTAssertEqualObjects(connected[@"mirroringActive"], @YES);
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
  XCTAssertEqualObjects(posted.lastObject[@"menuEngine"], @"none", @"no menu engine ever existed");
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

/// Review M1: the accessory path is taken only by a binary built with the
/// iOS 27 SDK (this one is built with an earlier SDK, whose external scene
/// iOS 27 still connects by itself), and never while a scene the system
/// offered by itself is connected.
- (void)testTheAccessoryRegimeNeedsTheIOS27SDKAndNoAutomaticScene {
  if (!InstallFakeSceneAccessoryIfNeeded()) {
    // Real iOS 27 SDK: the production API is used and only its status is observable here.
    [_coordinator refresh];
    XCTAssertTrue([_coordinator.accessoryStatus isEqualToString:@"registered"] || [_coordinator.accessoryStatus isEqualToString:@"disabled"] ||
                  [_coordinator.accessoryStatus hasPrefix:@"failed:"]);
    return;
  }
  UIViewController* root = [(id)UIApplication.sharedApplication.delegate window].rootViewController;
  __block NSInteger sdk = 26;
  _coordinator.buildSDKMajorVersion = ^NSInteger { return sdk; };
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [_coordinator refresh];
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"inactive:sdk");
  XCTAssertFalse(FakeAccessoryHolds(root), @"an SDK 26 binary registers nothing (iOS connects its scene by itself)");
  sdk = 27;
  [_coordinator refresh];
  // Retired (Build 447/448): "an SDK 27 binary registers the application
  // root" at once, to show the menu on the TV. Build 449: outside a game
  // nothing of NeoStation's own is shown, so no registration is made and
  // the system mirrors the iPhone.
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"disabled");
  XCTAssertFalse(FakeAccessoryHolds(root), @"no registration only to be turned off");
  [_coordinator attachRenderHost:host];
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"registered");
  XCTAssertTrue(FakeAccessoryEnabled(root), @"an SDK 27 binary registers the application root for a game");
  [_coordinator detachRenderHost:host];
  XCTAssertTrue(FakeAccessoryHolds(root) && !FakeAccessoryEnabled(root), @"the game left: turned off, the system mirrors the iPhone");
  // Back to no registration, then a scene arrives without one of ours: the
  // system offered it by itself, so the regime stays off while it is there.
  sdk = 26;
  [_coordinator refresh];
  XCTAssertFalse(FakeAccessoryHolds(root));
  sdk = 27;
  [self connect];
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"inactive:automatic_scene");
  XCTAssertFalse(FakeAccessoryHolds(root), @"no registration next to an automatic scene");
  XCTAssertEqual(_coordinator.content, NeoExternalContentNone, @"the automatic scene mirrors the iPhone outside a game, as on iOS 26");
  [_coordinator sceneDidDisconnect:[self mainScene]];
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"disabled", @"the automatic scene gone, the SDK 27 path resumes (nothing to show yet)");
  [_coordinator attachRenderHost:host];
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"registered");
  XCTAssertTrue(FakeAccessoryEnabled(root));
  [_coordinator detachRenderHost:host];
}

/// iOS 27 regime (SDK 27 binary): the application root and the presented
/// controller that owns the attached render host hold the registrations,
/// never a menu presented over the game (review m10: RPCS3 and ARMSX2
/// attach again from a still-presented menu after a failed stop); each is
/// enabled only while it has something to show; a dismissed controller's
/// registration is released at the next pass (the bridge's refresh in the
/// dismissal completion, or a window notification) with the registration
/// object registerSceneAccessory: returned.
- (void)testSceneAccessoryRegistrationsFollowThePresentedControllers {
  if (!InstallFakeSceneAccessoryIfNeeded()) {
    // Real iOS 27 SDK: the production API is used and only its status is observable here.
    [_coordinator refresh];
    XCTAssertTrue([_coordinator.accessoryStatus isEqualToString:@"registered"] || [_coordinator.accessoryStatus hasPrefix:@"failed:"] ||
                  [_coordinator.accessoryStatus isEqualToString:@"disabled"] || [_coordinator.accessoryStatus hasPrefix:@"inactive:"]);
    return;
  }
  _coordinator.buildSDKMajorVersion = ^NSInteger { return 27; };
  UIViewController* root = [(id)UIApplication.sharedApplication.delegate window].rootViewController;
  [_coordinator refresh];
  // Retired (Build 447/448): "the application root holds an enabled
  // registration" outside a game, for the menu on the TV. Build 449:
  // nothing of NeoStation's own is shown outside a game, so nothing is
  // registered and the system mirrors the iPhone.
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"disabled");
  XCTAssertFalse(FakeAccessoryHolds(root), @"outside a game no registration is made");
  const NSUInteger registrations = gFakeRegisterCalls;
  const NSUInteger unregistrations = gFakeUnregisterCalls;

  // A game controller is presented and its bridge attaches a host whose
  // placeholder lives in that controller's view: the controller gets its own
  // registration (the topmost, the one the system presents) and the root
  // one too.
  UIViewController* game = [UIViewController new];
  game.modalPresentationStyle = UIModalPresentationFullScreen;
  [self present:game on:root];
  FakeRenderHost* host = [[FakeRenderHost alloc] initFixed:YES render:nil];
  [game.view addSubview:host.placeholderView];
  [_coordinator attachRenderHost:host];
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"registered");
  XCTAssertTrue(FakeAccessoryEnabled(game), @"the controller owning the host holds an enabled registration");
  XCTAssertTrue(FakeAccessoryEnabled(root), @"the root holds one while the game is up");
  XCTAssertEqual(gFakeRegisterCalls, registrations + 2);
  [_coordinator refresh];
  [NSNotificationCenter.defaultCenter postNotificationName:UIApplicationDidBecomeActiveNotification object:nil];
  XCTAssertEqual(gFakeRegisterCalls, registrations + 2, @"a presented controller is registered once");

  // Nothing to show: the registrations are turned off (isEnabled), not removed.
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:NO]);
  XCTAssertTrue(FakeAccessoryHolds(root) && !FakeAccessoryEnabled(root), @"output off: the root's registration is disabled");
  XCTAssertTrue(FakeAccessoryHolds(game) && !FakeAccessoryEnabled(game), @"and the game's");
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"disabled");
  XCTAssertTrue([NeoExternalDisplayPreferences storeEnabled:YES]);
  XCTAssertTrue(FakeAccessoryEnabled(root) && FakeAccessoryEnabled(game));
  [_coordinator suspendForUnsupportedEngine];
  XCTAssertFalse(FakeAccessoryEnabled(root), @"suspended (Dusklight, KartPad): off");
  [_coordinator resumeAfterUnsupportedEngine];
  XCTAssertTrue(FakeAccessoryEnabled(root));
  XCTAssertTrue([NeoExternalDisplayPreferences storeMenuOnTV:NO]);
  XCTAssertTrue(FakeAccessoryEnabled(root), @"the stored menu switch of Build 447 is not read");
  XCTAssertTrue([NeoExternalDisplayPreferences storeMenuOnTV:YES]);
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"registered");
  XCTAssertEqual(gFakeRegisterCalls, registrations + 2, @"turned off and on again, never registered twice");
  XCTAssertEqual(gFakeUnregisterCalls, unregistrations);

  // A menu presented over the game is never registered, by a refresh or a
  // setting changed from it.
  UIViewController* menu = [UIViewController new];
  [self present:menu on:game];
  [_coordinator refresh];
  XCTAssertTrue([NeoExternalDisplayPreferences storeMode:NeoExternalDisplayModeFill]);
  XCTAssertFalse(FakeAccessoryHolds(menu), @"a menu over the game is not registered by a refresh");
  XCTAssertTrue(FakeAccessoryEnabled(game) && FakeAccessoryEnabled(root), @"the registrations of the presentation chain are kept");
  // Review m10: a failed stop detaches, then the bridge attaches again while
  // its menu is still presented over the game: the owner of the host, not
  // the topmost controller, holds the registration.
  [_coordinator detachRenderHost:host];
  XCTAssertTrue(FakeAccessoryHolds(game) && !FakeAccessoryEnabled(game), @"detached: the game's registration shows nothing, turned off");
  XCTAssertTrue(FakeAccessoryHolds(root) && !FakeAccessoryEnabled(root), @"and the root's: outside a game the system mirrors the iPhone");
  [_coordinator attachRenderHost:host];
  XCTAssertTrue(FakeAccessoryEnabled(game), @"attached again from the menu: the game controller's registration, enabled again");
  XCTAssertTrue(FakeAccessoryEnabled(root));
  XCTAssertFalse(FakeAccessoryHolds(menu), @"never the menu presented over the game");
  [self dismiss:menu completion:nil];

  // The bridge detaches, then dismisses; the completion calls refresh (the
  // explicit hook): the dismissed controller's registration is released.
  [_coordinator detachRenderHost:host];
  XCTAssertTrue(FakeAccessoryHolds(game), @"the detach alone keeps the still-presented game controller registered (turned off)");
  NeoExternalDisplayCoordinator* coordinator = _coordinator;
  [self dismiss:game completion:^{ [coordinator refresh]; }];
  XCTAssertFalse(FakeAccessoryHolds(game), @"dismissed: its registration is released");
  XCTAssertEqual(gFakeUnregisterCalls, unregistrations + 1);
  XCTAssertTrue(gFakeUnregisterMatched, @"unregisterSceneAccessory: receives the registration returned by registerSceneAccessory:");
  XCTAssertTrue(FakeAccessoryHolds(root) && !FakeAccessoryEnabled(root),
                @"the root keeps its registration, turned off: outside a game the system mirrors the iPhone");
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"disabled");

  // Safety net: a dismissal nobody reported is caught by the window notifications.
  UIViewController* other = [UIViewController new];
  other.modalPresentationStyle = UIModalPresentationFullScreen;
  [self present:other on:root];
  [other.view addSubview:host.placeholderView];
  [_coordinator attachRenderHost:host];
  XCTAssertTrue(FakeAccessoryEnabled(other));
  XCTAssertTrue(FakeAccessoryEnabled(root), @"the root's registration is enabled again for the game");
  [_coordinator detachRenderHost:host];
  [self dismiss:other completion:nil];
  // No refresh from the bridge: only a window notification can release it.
  [NSNotificationCenter.defaultCenter postNotificationName:UIWindowDidBecomeHiddenNotification object:nil];
  XCTAssertFalse(FakeAccessoryHolds(other), @"UIWindowDidBecomeHidden re-reads the presentation chain");
  XCTAssertEqual(gFakeUnregisterCalls, unregistrations + 2, @"released once, with its registration");
  XCTAssertTrue(gFakeUnregisterMatched);
  [NSNotificationCenter.defaultCenter postNotificationName:UIWindowDidBecomeKeyNotification object:nil];
  XCTAssertTrue(FakeAccessoryHolds(root) && !FakeAccessoryEnabled(root));
  XCTAssertEqualObjects(_coordinator.accessoryStatus, @"disabled");
}
@end
'''
if platform.system() != 'Darwin':
    print('SKIP: the external display simulator harness needs macOS/Xcode; sources composed, no test executed')
    raise SystemExit(0)
ns['native']()
print('PASS: external display connection mirroring the iPhone outside a game (window out of its scene, back for the game), '
      'game placement in every mode, disconnection order, reconnection, scene set and adoption, mirroring fallbacks, no menu '
      'on the TV, legacy fallback and its refusal without a scene, '
      'MTKView preservation, TV-resolution surfaces (whole TV, scale changes), reapplied passes, preferences, state events and '
      'iOS 27 accessory regime and registrations executed on the iOS Simulator')
