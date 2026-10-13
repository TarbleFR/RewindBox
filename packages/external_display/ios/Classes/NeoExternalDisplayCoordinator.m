// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoExternalDisplayCoordinator.h"

#import <MetalKit/MetalKit.h>
#import <objc/message.h>

#import "NeoExternalDisplayPreferences.h"

NSString *const NeoExternalDisplayStateChangedNotification = @"NeoStation.ExternalDisplayStateChanged";

/// Names shared with build-utils/configure_external_display_ios.py (Info.plist
/// scene configuration) and NeoExternalDisplaySceneDelegate.
static NSString *const kNeoExternalSceneConfigurationName = @"neostation-external-display";
static NSString *const kNeoExternalSceneDelegateClassName = @"NeoExternalDisplaySceneDelegate";
/// The legacy fallback waits this long for a scene after a screen connects.
static const NSTimeInterval kNeoExternalLegacyDelaySeconds = 1.5;
/// A pass asked again by calls made during it runs at most this many times
/// in a row (a host callback that keeps re-applying cannot loop forever).
static const NSUInteger kNeoExternalMaxApplyPasses = 4;

static NSString *const kNeoExternalRoleScene = @"scene";
static NSString *const kNeoExternalRoleLegacy = @"legacy";
static NSString *const kNeoExternalRoleNone = @"none";

#pragma mark - Black host of the external window

/// Black, non-rotating root of the external window (DOLExternalDisplayViewController).
@interface NeoExternalDisplayViewController : UIViewController
@end

@implementation NeoExternalDisplayViewController
- (void)loadView {
  UIView *view = [[UIView alloc] initWithFrame:CGRectZero];
  view.backgroundColor = UIColor.blackColor;
  self.view = view;
}
- (BOOL)prefersStatusBarHidden { return YES; }
- (BOOL)prefersHomeIndicatorAutoHidden { return YES; }
@end

#pragma mark - iOS 27 scene accessory (selectors only)

/// In an app built with the iOS 27 SDK, the external non-interactive scene
/// is delivered only while a view controller the app presents holds an
/// enabled UISceneAccessory registration; the system presents the
/// registration of the topmost, most recently presented controller and
/// disconnects the scene when that controller is dismissed ("Presenting
/// content on a connected display", Apple, read on 12 October 2026; release
/// note 177015874). An app built with an earlier SDK keeps the automatic
/// connection on iOS 27, which is why the coordinator only takes this path
/// for a binary built with SDK 27 or later (NeoExternalDisplaySDKMajorVersion)
/// and never while a scene the system offered by itself is connected: the
/// two regimes mixed would move the scene at every game start and stop. The
/// API is iOS 27.0 and the CI SDK is iOS 26, so everything is resolved at
/// run time by name; without the class this is a no-op.
///
/// Registrations: the application root (the menu, and the scene a game
/// falls back to), and the presented controller that owns the attached
/// render host (found from the host's placeholder view), never the topmost
/// controller as such, which can be a menu presented over the game. Each is
/// enabled only while it has something to show (isEnabled through
/// -setEnabled:, or an unregistration when the registration has no
/// setter); the registrations of dismissed controllers are released at the
/// next pass (the bridge's refresh after the dismissal, a window
/// notification, the next attach).

/// A controller and the UISceneAccessoryRegistration it holds.
@interface NeoExternalAccessoryRegistration : NSObject
@property(nonatomic, weak, nullable) UIViewController *controller;
@property(nonatomic, strong) id registration;
/// The value last given to the registration (YES at creation).
@property(nonatomic, assign) BOOL enabled;
@end

@implementation NeoExternalAccessoryRegistration
@end

/// `controller` or one of its ancestors is in the presentation chain.
static BOOL NeoExternalControllerIsLive(UIViewController *controller, NSArray<UIViewController *> *chain) {
  UIViewController *node = controller;
  while (node != nil) {
    if ([chain containsObject:node]) return YES;
    node = node.parentViewController;
  }
  return NO;
}

/// The view controller whose view hierarchy holds `view` (responder chain).
static UIViewController *_Nullable NeoExternalOwningController(UIView *_Nullable view) {
  UIResponder *responder = view;
  while (responder != nil) {
    if ([responder isKindOfClass:UIViewController.class]) return (UIViewController *)responder;
    responder = responder.nextResponder;
  }
  return nil;
}

@interface NeoExternalDisplaySceneAccessory : NSObject
+ (NSString *)registerOnViewController:(UIViewController *_Nullable)controller enabled:(BOOL)enabled;
+ (void)releaseRegistrationsOutside:(NSArray<UIViewController *> *)chain;
+ (void)disableRegistrationsExcept:(NSArray<UIViewController *> *)kept;
+ (void)releaseAllRegistrations;
+ (BOOL)hasEnabledRegistration;
@end

@implementation NeoExternalDisplaySceneAccessory

static NSMutableArray<NeoExternalAccessoryRegistration *> *gNeoExternalRegistrations;

/// The documented Objective-C factory of UISceneAccessory first; the
/// spelling of docs/external-display-universal.md § 3.3 is kept as a
/// fallback until the first iOS 27 device run settles it.
static NSString *const kNeoExternalAccessoryFactorySelectors[] = {
  @"externalNonInteractiveSceneAccessoryWithConfiguration:",
  @"externalNonInteractiveWithSceneConfiguration:",
};

+ (SEL)factorySelectorOfClass:(Class)accessoryClass {
  const size_t count = sizeof(kNeoExternalAccessoryFactorySelectors) / sizeof(kNeoExternalAccessoryFactorySelectors[0]);
  for (size_t index = 0; index < count; ++index) {
    SEL factory = NSSelectorFromString(kNeoExternalAccessoryFactorySelectors[index]);
    if ([accessoryClass respondsToSelector:factory]) return factory;
  }
  return NULL;
}

+ (NeoExternalAccessoryRegistration *_Nullable)entryForViewController:(UIViewController *)controller {
  for (NeoExternalAccessoryRegistration *entry in gNeoExternalRegistrations) {
    if (entry.controller == controller) return entry;
  }
  return nil;
}

/// unregisterSceneAccessory: with the registration registerSceneAccessory:
/// returned.
+ (void)unregisterEntry:(NeoExternalAccessoryRegistration *)entry {
  SEL unregisterSelector = NSSelectorFromString(@"unregisterSceneAccessory:");
  UIViewController *controller = entry.controller;
  if (controller != nil && entry.registration != nil && [controller respondsToSelector:unregisterSelector]) {
    ((void (*)(id, SEL, id))objc_msgSend)(controller, unregisterSelector, entry.registration);
  }
}

/// isEnabled of the registration, through its setter; NO when the
/// registration has none (the caller unregisters instead).
+ (BOOL)setRegistration:(id)registration enabled:(BOOL)enabled {
  SEL setter = NSSelectorFromString(@"setEnabled:");
  if (registration == nil || ![registration respondsToSelector:setter]) return NO;
  ((void (*)(id, SEL, BOOL))objc_msgSend)(registration, setter, enabled);
  return YES;
}

/// Turns `entry` off: isEnabled = NO, or an unregistration (the entry is
/// then dropped). Returns NO when the entry was dropped.
+ (BOOL)disableEntry:(NeoExternalAccessoryRegistration *)entry {
  if (!entry.enabled) return YES;
  if ([self setRegistration:entry.registration enabled:NO]) {
    entry.enabled = NO;
    return YES;
  }
  [self unregisterEntry:entry];
  [gNeoExternalRegistrations removeObject:entry];
  return NO;
}

+ (NSString *)registerOnViewController:(UIViewController *_Nullable)controller enabled:(BOOL)enabled {
  Class accessoryClass = NSClassFromString(@"UISceneAccessory");
  if (accessoryClass == Nil) return @"unavailable";
  if (controller == nil) return @"failed:no_controller";
  NeoExternalAccessoryRegistration *existing = [self entryForViewController:controller];
  if (existing != nil) {
    if (!enabled) {
      [self disableEntry:existing];
      return @"disabled";
    }
    if (!existing.enabled && [self setRegistration:existing.registration enabled:YES]) existing.enabled = YES;
    return existing.enabled ? @"registered" : @"disabled";
  }
  // Nothing to show through this controller: no registration is made only
  // to be turned off.
  if (!enabled) return @"disabled";
  SEL factory = [self factorySelectorOfClass:accessoryClass];
  SEL registerSelector = NSSelectorFromString(@"registerSceneAccessory:");
  if (factory == NULL) return @"failed:factory_missing";
  if (![controller respondsToSelector:registerSelector]) return @"failed:register_missing";
  UISceneConfiguration *configuration =
      [UISceneConfiguration configurationWithName:kNeoExternalSceneConfigurationName
                                      sessionRole:UIWindowSceneSessionRoleExternalDisplayNonInteractive];
  configuration.sceneClass = UIWindowScene.class;
  configuration.delegateClass = NSClassFromString(kNeoExternalSceneDelegateClassName);
  id accessory = ((id (*)(Class, SEL, id))objc_msgSend)(accessoryClass, factory, configuration);
  if (accessory == nil) return @"failed:accessory_nil";
  // registerSceneAccessory: answers the UISceneAccessoryRegistration that
  // unregisterSceneAccessory: takes; it is kept with its controller.
  id registration = ((id (*)(id, SEL, id))objc_msgSend)(controller, registerSelector, accessory);
  if (registration == nil) return @"failed:registration_nil";
  NeoExternalAccessoryRegistration *entry = [NeoExternalAccessoryRegistration new];
  entry.controller = controller;
  entry.registration = registration;
  entry.enabled = YES;
  if (gNeoExternalRegistrations == nil) gNeoExternalRegistrations = [NSMutableArray array];
  [gNeoExternalRegistrations addObject:entry];
  return @"registered";
}

/// Unregisters the controllers that left the presentation chain (dismissed
/// game controllers) or were released; the ones still presented keep their
/// registration so the system never runs out of one.
+ (void)releaseRegistrationsOutside:(NSArray<UIViewController *> *)chain {
  if (gNeoExternalRegistrations.count == 0) return;
  NSMutableArray<NeoExternalAccessoryRegistration *> *kept = [NSMutableArray array];
  for (NeoExternalAccessoryRegistration *entry in gNeoExternalRegistrations) {
    UIViewController *controller = entry.controller;
    if (controller != nil && NeoExternalControllerIsLive(controller, chain)) {
      [kept addObject:entry];
      continue;
    }
    [self unregisterEntry:entry];
  }
  gNeoExternalRegistrations = kept;
}

/// Turns off every registration but those of `kept` (a controller that no
/// longer owns the render host shows nothing).
+ (void)disableRegistrationsExcept:(NSArray<UIViewController *> *)kept {
  for (NeoExternalAccessoryRegistration *entry in [gNeoExternalRegistrations copy]) {
    UIViewController *controller = entry.controller;
    if (controller != nil && [kept containsObject:controller]) continue;
    [self disableEntry:entry];
  }
}

/// The regime is off: no registration stays behind.
+ (void)releaseAllRegistrations {
  for (NeoExternalAccessoryRegistration *entry in gNeoExternalRegistrations) [self unregisterEntry:entry];
  [gNeoExternalRegistrations removeAllObjects];
}

+ (BOOL)hasEnabledRegistration {
  for (NeoExternalAccessoryRegistration *entry in gNeoExternalRegistrations) {
    if (entry.enabled && entry.controller != nil) return YES;
  }
  return NO;
}

@end

/// The presentation chain of the application scene (never the external
/// one), root first: the Flutter menu, then each controller presented over
/// it (a game controller, a menu over the game).
static NSArray<UIViewController *> *NeoExternalApplicationPresentationChain(void) {
  UIWindow *keyWindow = nil;
  UIWindow *visibleWindow = nil;
  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class]) continue;
    if (![scene.session.role isEqualToString:UIWindowSceneSessionRoleApplication]) continue;
    for (UIWindow *window in ((UIWindowScene *)scene).windows) {
      if (window.isKeyWindow) {
        keyWindow = window;
        break;
      }
      if (visibleWindow == nil && !window.hidden) visibleWindow = window;
    }
    if (keyWindow != nil) break;
  }
  NSMutableArray<UIViewController *> *chain = [NSMutableArray array];
  UIViewController *controller = (keyWindow ?: visibleWindow).rootViewController;
  while (controller != nil && ![chain containsObject:controller]) {
    [chain addObject:controller];
    controller = controller.presentedViewController;
  }
  return chain;
}

/// A connected scene of the external role on `screen` (one UIKit connected
/// without the delegate hearing of it), or nil.
static UIWindowScene *_Nullable NeoExternalConnectedSceneOnScreen(UIScreen *screen) {
  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class]) continue;
    if (![scene.session.role isEqualToString:UIWindowSceneSessionRoleExternalDisplayNonInteractive]) continue;
    if (scene.activationState == UISceneActivationStateUnattached) continue;
    if (((UIWindowScene *)scene).screen == screen) return (UIWindowScene *)scene;
  }
  return nil;
}

static NSString *NeoExternalContentName(NeoExternalContentKind content) {
  switch (content) {
    case NeoExternalContentMenu: return @"menu";
    case NeoExternalContentGame: return @"game";
    case NeoExternalContentNone: break;
  }
  return @"none";
}

/// One status for the root and the host owner's registrations: a failure
/// first, then an enabled registration, else the root's own (disabled,
/// unavailable).
static NSString *NeoExternalCombinedAccessoryStatus(NSString *root, NSString *_Nullable owner) {
  if ([root hasPrefix:@"failed:"]) return root;
  if ([owner hasPrefix:@"failed:"]) return owner;
  if ([root isEqualToString:@"registered"] || [owner isEqualToString:@"registered"]) return @"registered";
  return root;
}

#pragma mark - Coordinator

@interface NeoExternalDisplayCoordinator ()
@property(nonatomic, strong, nullable) UIWindow *window;
/// The scene holding the window (scene role).
@property(nonatomic, strong, nullable) UIWindowScene *scene;
/// The window was taken out of `scene` so that iOS mirrors the iPhone
/// (placeWindowInScene:); it goes back there when a game takes the TV.
@property(nonatomic, assign) BOOL windowLeftScene;
/// The coordinator built the window itself (-[UIWindow
/// initWithWindowScene:], not the factory seam): back in its scene it takes
/// the scene's bounds.
@property(nonatomic, assign) BOOL windowFollowsScene;
/// The window's frame when it left its scene (restored on its return for a
/// window the factory seam built).
@property(nonatomic, assign) CGRect frameBeforeLeavingScene;
/// Every external scene UIKit connected and has not disconnected, in
/// connection order.
@property(nonatomic, strong) NSMutableArray<UIWindowScene *> *connectedExternalScenes;
/// Those that connected while no accessory registration of ours was
/// enabled: offered by the system on its own.
@property(nonatomic, strong) NSMutableArray<UIWindowScene *> *automaticScenes;
/// The scene being connected right now, never dropped by a rescan.
@property(nonatomic, weak, nullable) UIWindowScene *connectingScene;
@property(nonatomic, strong, nullable) UIScreen *legacyScreen;
@property(nonatomic, copy) NSString *sceneRole;
@property(nonatomic, assign) BOOL sceneEverConnected;
@property(nonatomic, strong, nullable) NSTimer *legacyTimer;
@property(nonatomic, strong, nullable) id<NeoExternalRenderHost> renderHost;
/// The render view is in the external window right now.
@property(nonatomic, assign) BOOL renderPlaced;
/// The surface last announced to a non-fixed host, and its scale.
@property(nonatomic, assign) CGSize lastSurface;
@property(nonatomic, assign) CGFloat lastSurfaceScale;
@property(nonatomic, strong, nullable) UIViewController *menuViewController;
/// destroyMenuEngineForMemory until the game's host detaches.
@property(nonatomic, assign) BOOL menuSuppressed;
@property(nonatomic, assign) BOOL suspended;
@property(nonatomic, assign) NeoExternalContentKind content;
@property(nonatomic, assign) CGFloat screenScale;
@property(nonatomic, copy) NSString *accessoryStatus;
@property(nonatomic, copy, nullable) NSDictionary<NSString *, id> *lastState;
@property(nonatomic, assign) BOOL applying;
/// A call made during a pass: the pass runs once more at its end.
@property(nonatomic, assign) BOOL needsReapply;
/// A refresh asked during a pass: the scenes are rescanned between passes.
@property(nonatomic, assign) BOOL needsRescan;
// The render view's iPhone configuration, restored on return.
@property(nonatomic, assign) BOOL savedAutoResizeDrawable;
@property(nonatomic, assign) CGFloat savedContentScale;
@property(nonatomic, assign) UIViewAutoresizing savedAutoresizing;
@property(nonatomic, assign) CGRect savedBounds;
@end

@implementation NeoExternalDisplayCoordinator

+ (instancetype)shared {
  static NeoExternalDisplayCoordinator *shared;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ shared = [[NeoExternalDisplayCoordinator alloc] init]; });
  return shared;
}

- (instancetype)init {
  if ((self = [super init])) {
    _sceneRole = kNeoExternalRoleNone;
    _accessoryStatus = @"unavailable";
    _content = NeoExternalContentNone;
    _connectedExternalScenes = [NSMutableArray array];
    _automaticScenes = [NSMutableArray array];
    NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
    [center addObserver:self selector:@selector(environmentChanged:)
                   name:UIApplicationDidBecomeActiveNotification object:nil];
    [center addObserver:self selector:@selector(environmentChanged:)
                   name:NeoExternalDisplayChangedNotification object:nil];
    // Safety net of the iOS 27 accessory: a window of the application
    // scene changing (SDL window of an unsupported engine, overlay) is a
    // presentation change nobody reported; the pass re-reads the chain.
    [center addObserver:self selector:@selector(windowDidChange:)
                   name:UIWindowDidBecomeKeyNotification object:nil];
    [center addObserver:self selector:@selector(windowDidChange:)
                   name:UIWindowDidBecomeHiddenNotification object:nil];
    [self observeScreenNotifications];
  }
  return self;
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

/// The UIScreen notifications are deprecated since iOS 16 in favour of
/// scenes; they remain the only signal of the legacy fallback (connect,
/// disconnect) and of a mode change of the external screen.
- (void)observeScreenNotifications {
  NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
  [center addObserver:self selector:@selector(screenDidConnect:) name:UIScreenDidConnectNotification object:nil];
  [center addObserver:self selector:@selector(screenDidDisconnect:) name:UIScreenDidDisconnectNotification object:nil];
  [center addObserver:self selector:@selector(environmentChanged:) name:UIScreenModeDidChangeNotification object:nil];
#pragma clang diagnostic pop
}

#pragma mark State

- (BOOL)connected { return self.window != nil; }

- (CGSize)screenPointSize { return self.window != nil ? self.window.bounds.size : CGSizeZero; }

- (NeoExternalDisplayMode)mode { return NeoExternalDisplayPreferences.mode; }

- (BOOL)enabled { return NeoExternalDisplayPreferences.enabled; }

/// Never (Build 449): outside a game the TV mirrors the iPhone, so it shows
/// the NeoStation interface itself. The second engine's TV view (the
/// SecondaryScreen of Android handhelds: the selected console's logo) is
/// not shown any more, and the stored "menu on the TV" preference of Build
/// 447 is no longer read.
- (BOOL)menuOnTV { return NO; }

- (BOOL)mirroringActive { return self.window != nil && self.window.hidden; }

- (NSArray<UIWindowScene *> *)externalScenes { return [self.connectedExternalScenes copy]; }

- (NSString *)menuEngineStatus {
  id<NeoExternalMenuProvider> provider = self.menuProvider;
  NSString *status = provider != nil ? [provider externalMenuEngineStatus] : @"none";
  if ([status isEqualToString:@"created"] && self.menuViewController != nil && self.window != nil) return @"attached";
  return status;
}

- (NSDictionary<NSString *, id> *)stateDictionary {
  const CGSize size = self.screenPointSize;
  return @{
    @"supported" : @YES,
    @"connected" : @(self.connected),
    @"content" : NeoExternalContentName(self.content),
    @"screenWidth" : @(size.width),
    @"screenHeight" : @(size.height),
    @"screenScale" : @(self.window != nil ? self.screenScale : 0),
    @"mode" : @((NSInteger)self.mode),
    @"enabled" : @(self.enabled),
    @"menuOnTV" : @(self.menuOnTV),
    @"suspended" : @(self.suspended),
    @"mirroringActive" : @(self.mirroringActive),
    @"accessoryStatus" : self.accessoryStatus,
    @"sceneRole" : self.sceneRole,
    @"menuEngine" : self.menuEngineStatus,
  };
}

- (void)notifyIfChanged {
  NSDictionary<NSString *, id> *state = [self stateDictionary];
  if (self.lastState != nil && [self.lastState isEqualToDictionary:state]) return;
  self.lastState = state;
  if (self.stateChanged) self.stateChanged();
  [NSNotificationCenter.defaultCenter postNotificationName:NeoExternalDisplayStateChangedNotification
                                                    object:self
                                                  userInfo:state];
}

/// The SDK major the app binary was built with (read once from the main
/// bundle), or the test seam.
- (NSInteger)buildSDKMajor {
  if (self.buildSDKMajorVersion != nil) return self.buildSDKMajorVersion();
  static NSInteger major;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    NSDictionary<NSString *, id> *info = NSBundle.mainBundle.infoDictionary;
    id platform = info[@"DTPlatformVersion"];
    id sdk = info[@"DTSDKName"];
    major = NeoExternalDisplaySDKMajorVersion([platform isKindOfClass:NSString.class] ? platform : nil,
                                              [sdk isKindOfClass:NSString.class] ? sdk : nil);
    NSLog(@"display.external_build_sdk %ld (%@, %@)", (long)major, platform, sdk);
  });
  return major;
}

/// The external screen's scale now (a mode change of the TV can change it
/// alone); the last one when the screen does not tell.
- (CGFloat)currentScreenScale {
  if (self.window == nil) return 0;
  CGFloat scale = 0;
  if (self.screenScaleReader != nil) {
    scale = self.screenScaleReader();
  } else {
    UIScreen *screen = self.scene != nil ? self.scene.screen : self.legacyScreen;
    scale = screen.scale;
  }
  return isfinite(scale) && scale > 0 ? scale : self.screenScale;
}

#pragma mark Notifications

- (void)environmentChanged:(NSNotification *)notification {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self environmentChanged:notification]; });
    return;
  }
  [self refresh];
}

/// The external window's own hidden/visible changes come from applyState
/// and are not a presentation change of the iPhone.
- (void)windowDidChange:(NSNotification *)notification {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self windowDidChange:notification]; });
    return;
  }
  if (notification.object != nil && notification.object == self.window) return;
  [self refresh];
}

- (void)screenDidConnect:(NSNotification *)notification {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self screenDidConnect:notification]; });
    return;
  }
  // The scene regime is proven once a scene connected: the next one will
  // come by itself. Otherwise give UIKit the delay, then fall back.
  if (self.window != nil || self.sceneEverConnected) return;
  [self.legacyTimer invalidate];
  self.legacyTimer = [NSTimer scheduledTimerWithTimeInterval:kNeoExternalLegacyDelaySeconds
                                                      target:self
                                                    selector:@selector(legacyTimerFired:)
                                                    userInfo:nil
                                                     repeats:NO];
}

- (void)legacyTimerFired:(NSTimer *)timer {
  [self activateLegacyIfNeeded];
}

- (void)screenDidDisconnect:(NSNotification *)notification {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ [self screenDidDisconnect:notification]; });
    return;
  }
  [self.legacyTimer invalidate];
  self.legacyTimer = nil;
  if (![self.sceneRole isEqualToString:kNeoExternalRoleLegacy]) return;  // a scene disconnects itself
  if (self.legacyScreens != nil && self.legacyScreen != nil && [self.legacyScreens() containsObject:self.legacyScreen]) return;
  [self disconnectWindow];
}

#pragma mark Scene and legacy windows

- (void)sceneDidConnect:(UIWindowScene *)scene {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (scene == nil) return;
  [self.legacyTimer invalidate];
  self.legacyTimer = nil;
  self.sceneEverConnected = YES;
  if (![self.connectedExternalScenes containsObject:scene]) {
    [self.connectedExternalScenes addObject:scene];
    // No registration of ours asked for it: the system offered it by itself
    // (every SDK before 27, or an SDK 27 binary before its first
    // registration); the accessory regime stays off while it is there.
    if (![NeoExternalDisplaySceneAccessory hasEnabledRegistration]) [self.automaticScenes addObject:scene];
  }
  if (self.window != nil && self.scene == scene) {
    [self applyState];
    return;
  }
  if (self.window != nil && [self.sceneRole isEqualToString:kNeoExternalRoleLegacy]) {
    // A legacy window gives way to the scene of the same screen; the menu
    // engine moves with the window content.
    [self releaseWindowKeepingMenuEngine:YES];
  }
  if (self.window != nil) {
    // Another scene still shows NeoStation's window: it keeps it, its menu
    // engine and the game stay where they are; this one is adopted if that
    // scene goes away (sceneDidDisconnect:).
    NSLog(@"display.external_scene_standby %lu scene(s)", (unsigned long)self.connectedExternalScenes.count);
    [self applyState];
    return;
  }
  [self showWindowInScene:scene];
}

/// The coordinator's window in `scene` (windowFactory seam or
/// -[UIWindow initWithWindowScene:]), given to the scene's delegate when it
/// is ours.
- (void)showWindowInScene:(UIWindowScene *)scene {
  self.connectingScene = scene;
  UIWindow *window = self.windowFactory ? self.windowFactory(scene, scene.screen) : nil;
  // A window the factory seam built keeps its own frame (the test host's
  // stand-in scene is the iPhone's, not the TV's); the coordinator's own
  // window follows the scene's bounds when it comes back into the scene.
  self.windowFollowsScene = window == nil;
  if (window == nil) window = [[UIWindow alloc] initWithWindowScene:scene];
  self.scene = scene;
  self.screenScale = scene.screen.scale;
  [self giveWindow:window toDelegateOfScene:scene];
  NSLog(@"display.external_scene_connected %@ @%.0fx", NSStringFromCGSize(window.bounds.size), self.screenScale);
  [self connectWindow:window role:kNeoExternalRoleScene];
  self.connectingScene = nil;
}

/// NeoExternalDisplaySceneDelegate keeps a reference to the window of its
/// own scene only (never another scene's, never another delegate class).
- (void)giveWindow:(UIWindow *_Nullable)window toDelegateOfScene:(UIWindowScene *_Nullable)scene {
  id<UISceneDelegate> delegate = scene.delegate;
  Class ours = NSClassFromString(kNeoExternalSceneDelegateClassName);
  if (delegate == nil || ours == Nil || ![delegate isKindOfClass:ours]) return;
  ((id<UIWindowSceneDelegate>)delegate).window = window;
}

- (void)sceneDidDisconnect:(UIWindowScene *)scene {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (scene == nil) return;
  [self.connectedExternalScenes removeObject:scene];
  [self.automaticScenes removeObject:scene];
  if (self.window == nil || self.scene != scene || ![self.sceneRole isEqualToString:kNeoExternalRoleScene]) {
    // A standing-by scene went away (or nothing of ours was there): the
    // regime and the accessory are re-read.
    [self applyState];
    return;
  }
  UIWindowScene *next = [self adoptableExternalScene];
  if (next == nil) {
    [self disconnectWindow];
    return;
  }
  // A scene remains: the window moves there. The render view and the menu
  // leave the old window first; the menu engine is kept (no disconnection
  // of the TV as far as the user is concerned).
  NSLog(@"display.external_scene_adopted %lu scene(s)", (unsigned long)self.connectedExternalScenes.count);
  [self giveWindow:nil toDelegateOfScene:scene];
  [self releaseWindowKeepingMenuEngine:YES];
  [self showWindowInScene:next];
}

/// The most recently connected external scene still attached, or nil.
- (UIWindowScene *_Nullable)adoptableExternalScene {
  for (UIWindowScene *candidate in self.connectedExternalScenes.reverseObjectEnumerator) {
    if (candidate.activationState != UISceneActivationStateUnattached) return candidate;
  }
  return nil;
}

/// UIKit's own list of connected scenes is the reference: a tracked scene
/// that left it is handled as a disconnection, and a connected external
/// scene whose delegate never told us (its delegate absent or ours) is
/// adopted.
- (void)rescanExternalScenes {
  NSSet<UIScene *> *connected = UIApplication.sharedApplication.connectedScenes;
  for (UIWindowScene *tracked in [self.connectedExternalScenes copy]) {
    if (tracked == self.connectingScene || [connected containsObject:tracked]) continue;
    NSLog(@"display.external_scene_lost");
    [self sceneDidDisconnect:tracked];
  }
  Class ours = NSClassFromString(kNeoExternalSceneDelegateClassName);
  for (UIScene *candidate in connected) {
    if (![candidate isKindOfClass:UIWindowScene.class]) continue;
    if (![candidate.session.role isEqualToString:UIWindowSceneSessionRoleExternalDisplayNonInteractive]) continue;
    if ([self.connectedExternalScenes containsObject:(UIWindowScene *)candidate]) continue;
    if (candidate.activationState == UISceneActivationStateUnattached) continue;
    id<UISceneDelegate> delegate = candidate.delegate;
    if (delegate != nil && (ours == Nil || ![delegate isKindOfClass:ours])) continue;
    NSLog(@"display.external_scene_found");
    [self sceneDidConnect:(UIWindowScene *)candidate];
  }
}

/// Build 442 path, kept only for a system that never delivers the external
/// scene: `UIScreen.screens` and `UIWindow.screen` are deprecated since iOS
/// 16 and used nowhere else. Runs 1.5 s after UIScreenDidConnectNotification
/// when no scene arrived and none ever did. In a scene-based app a window
/// without a scene is never displayed: a connected external scene of that
/// screen is adopted instead, and a window is only used once it ended up in
/// a scene of that screen; otherwise iOS keeps mirroring and no render view
/// moves (both screens would be black).
- (void)activateLegacyIfNeeded {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  self.legacyTimer = nil;
  if (self.window != nil || self.sceneEverConnected) return;
  NSArray<UIScreen *> *screens = nil;
  UIWindow *window = nil;
  UIWindowScene *existing = nil;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
  if (self.legacyScreens != nil) {
    screens = self.legacyScreens() ?: @[];
  } else {
    NSMutableArray<UIScreen *> *found = [NSMutableArray array];
    for (UIScreen *candidate in UIScreen.screens) {
      if (candidate != UIScreen.mainScreen) [found addObject:candidate];
    }
    screens = found;
  }
  UIScreen *screen = screens.firstObject;
  if (screen != nil) existing = NeoExternalConnectedSceneOnScreen(screen);
  if (screen != nil && existing == nil) {
    window = self.windowFactory ? self.windowFactory(nil, screen) : nil;
    if (window == nil) {
      window = [[UIWindow alloc] initWithFrame:screen.bounds];
      window.screen = screen;
    }
  }
#pragma clang diagnostic pop
  if (screen == nil) return;
  if (existing != nil) {
    NSLog(@"display.external_legacy_scene (a connected external scene of the screen is adopted)");
    [self sceneDidConnect:existing];
    return;
  }
  UIWindowScene *windowScene = window.windowScene;
  if (windowScene == nil || windowScene.screen != screen) {
    NSLog(@"display.legacy_unavailable %@ (the window is in no scene of that screen: iOS keeps mirroring the iPhone)",
          NSStringFromCGSize(screen.bounds.size));
    window.hidden = YES;
    return;
  }
  self.legacyScreen = screen;
  self.screenScale = screen.scale;
  NSLog(@"display.external_legacy %@ @%.0fx (no scene delivered after %.1f s)", NSStringFromCGSize(window.bounds.size),
        self.screenScale, kNeoExternalLegacyDelaySeconds);
  [self connectWindow:window role:kNeoExternalRoleLegacy];
}

/// Never makeKeyAndVisible: the window is shown, the iPhone keeps the keys.
- (void)connectWindow:(UIWindow *)window role:(NSString *)role {
  window.backgroundColor = UIColor.blackColor;
  window.windowLevel = UIWindowLevelNormal;
  if (window.rootViewController == nil) window.rootViewController = [NeoExternalDisplayViewController new];
  self.window = window;
  self.sceneRole = role;
  window.hidden = NO;
  [self applyState];
}

/// A window of the app in the external scene ends the mirroring of the
/// iPhone; the documented way back is taking it out of the scene, not
/// hiding it ("To make it go back to mirroring, simply remove your UIWindow
/// from the scene through use of the windowScene property (just set it to
/// nil)", Apple Frameworks Engineer, Apple Developer Forums thread 766398,
/// read on 12 October 2026). Outside a game the window leaves its
/// scene, and goes back to the same scene, before the render view moves in,
/// when a game takes the TV. A window that was never in a scene (legacy
/// screen, test seam) is left as it is.
- (void)placeWindowInScene:(BOOL)inScene {
  UIWindow *window = self.window;
  UIWindowScene *scene = self.scene;
  if (window == nil || scene == nil || ![self.sceneRole isEqualToString:kNeoExternalRoleScene]) return;
  if (inScene) {
    if (!self.windowLeftScene) return;
    self.windowLeftScene = NO;
    window.windowScene = scene;
    // The TV's mode may have changed while the iPhone was mirrored: the
    // coordinator's own window takes the scene's bounds; a window the
    // factory seam built gets back its own frame, whatever UIKit did.
    const CGRect bounds = scene.coordinateSpace.bounds;
    if (self.windowFollowsScene && NeoExternalDisplayUsableSize(bounds.size)) {
      window.frame = bounds;
    } else if (!self.windowFollowsScene && NeoExternalDisplayUsableSize(self.frameBeforeLeavingScene.size)) {
      window.frame = self.frameBeforeLeavingScene;
    }
    [self giveWindow:window toDelegateOfScene:scene];
    NSLog(@"display.external_window_back_in_scene");
    return;
  }
  if (self.windowLeftScene || window.windowScene != scene) return;
  self.windowLeftScene = YES;
  self.frameBeforeLeavingScene = window.frame;
  [self giveWindow:nil toDelegateOfScene:scene];
  window.windowScene = nil;
  NSLog(@"display.external_mirroring (the window left its scene: iOS mirrors the iPhone)");
}

/// The render view goes back to the iPhone first, then the window is
/// released; the menu engine is destroyed (recreated at the next
/// connection) unless another external scene takes the window over at once.
- (void)releaseWindowKeepingMenuEngine:(BOOL)keepMenuEngine {
  UIWindow *window = self.window;
  if (window == nil) return;
  [self returnRenderViewToPlaceholder];
  [self detachMenuViewControllerInternal];
  if (!keepMenuEngine) [self.menuProvider destroyExternalMenuEngineForReason:@"disconnect"];
  // Hidden while it is still the coordinator's: its own
  // UIWindowDidBecomeHidden is not taken for a presentation change.
  window.hidden = YES;
  self.window = nil;
  self.scene = nil;
  self.windowLeftScene = NO;
  self.windowFollowsScene = NO;
  self.frameBeforeLeavingScene = CGRectZero;
  self.legacyScreen = nil;
  self.screenScale = 0;
  self.sceneRole = kNeoExternalRoleNone;
  window.rootViewController = nil;
}

- (void)disconnectWindow {
  if (self.window == nil) return;
  [self releaseWindowKeepingMenuEngine:NO];
  [self applyState];
}

#pragma mark Render hosts

- (void)attachRenderHost:(id<NeoExternalRenderHost>)host {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (host == nil) return;
  if (self.renderHost != nil && self.renderHost != host) [self detachRenderHost:self.renderHost];
  self.renderHost = host;
  [self applyState];
}

- (void)detachRenderHost:(id<NeoExternalRenderHost>)host {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (host == nil || self.renderHost != host) return;
  [self returnRenderViewToPlaceholder];
  self.renderHost = nil;
  self.menuSuppressed = NO;
  [self applyState];
}

- (void)moveRenderViewToWindow {
  id<NeoExternalRenderHost> host = self.renderHost;
  UIView *render = host.renderView;
  UIWindow *window = self.window;
  if (render == nil || window == nil || self.renderPlaced) return;
  // The engines with a fixed drawable sized it for the iPhone and never
  // re-read it: the view keeps those bounds and that scale, and only a
  // transform maps it to the TV (Build 442 guarantees).
  self.savedContentScale = render.contentScaleFactor;
  self.savedAutoresizing = render.autoresizingMask;
  self.savedBounds = render.bounds;
  if (host.fixedDrawable && [render isKindOfClass:MTKView.class]) {
    self.savedAutoResizeDrawable = ((MTKView *)render).autoResizeDrawable;
    ((MTKView *)render).autoResizeDrawable = NO;
  }
  [render removeFromSuperview];
  render.autoresizingMask = UIViewAutoresizingNone;
  [window.rootViewController.view addSubview:render];
  if (host.fixedDrawable) {
    render.bounds = self.savedBounds;
    render.contentScaleFactor = self.savedContentScale;
  }
  self.renderPlaced = YES;
  self.lastSurface = CGSizeZero;
  self.lastSurfaceScale = 0;
  [self placeRenderView];
  NSLog(@"display.external_attached:%@ %@", NSStringFromClass([host class]), NSStringFromCGSize(window.bounds.size));
  if ([host respondsToSelector:@selector(externalDisplayDidChange:)]) [host externalDisplayDidChange:YES];
}

- (void)placeRenderView {
  id<NeoExternalRenderHost> host = self.renderHost;
  UIView *render = host.renderView;
  UIWindow *window = self.window;
  if (render == nil || window == nil || !self.renderPlaced) return;
  UIView *hostView = window.rootViewController.view;
  hostView.frame = window.bounds;
  const CGSize screen = hostView.bounds.size;
  const NeoExternalDisplayMode mode = NeoExternalDisplayEffectiveMode(self.mode, NeoExternalContentGame);
  if (host.fixedDrawable) {
    const CGSize source = render.bounds.size;
    const CGFloat scale = NeoExternalDisplayScale(screen, source, mode);
    render.transform = CGAffineTransformIdentity;
    render.bounds = CGRectMake(0, 0, source.width, source.height);
    render.center = CGPointMake(screen.width / 2, screen.height / 2);
    render.transform = CGAffineTransformMakeScale(scale, scale);
    return;
  }
  // The surface follows the TV: the whole screen in every mode, at the TV's
  // scale re-read by this pass; the host places each game's picture in it
  // at the game's own aspect and rebuilds its drawable from it. Recomputed
  // at every pass from the iPhone layout the host draws from now (its
  // placeholder, rotated or not), never from the bounds of the move.
  CGSize source = host.placeholderView.bounds.size;
  if (!NeoExternalDisplayUsableSize(source)) source = self.savedBounds.size;
  CGSize surface = NeoExternalDisplaySurfaceSize(screen, source, mode);
  if (!NeoExternalDisplayUsableSize(surface)) surface = screen;
  const CGFloat scale = self.screenScale > 0 ? self.screenScale : render.contentScaleFactor;
  render.transform = CGAffineTransformIdentity;
  render.bounds = CGRectMake(0, 0, surface.width, surface.height);
  render.center = CGPointMake(screen.width / 2, screen.height / 2);
  render.contentScaleFactor = scale;
  // Size and scale together: a mode change of the TV (720p @1x to the same
  // points @2x) is a new drawable too.
  if (CGSizeEqualToSize(surface, self.lastSurface) && scale == self.lastSurfaceScale) return;
  self.lastSurface = surface;
  self.lastSurfaceScale = scale;
  if ([host respondsToSelector:@selector(externalSurfaceDidChange:scale:)]) [host externalSurfaceDidChange:surface scale:scale];
}

/// Index 0 of the placeholder, iPhone configuration restored; always before
/// a bridge stops its core and before the window is released.
- (void)returnRenderViewToPlaceholder {
  id<NeoExternalRenderHost> host = self.renderHost;
  UIView *render = host.renderView;
  if (render == nil || !self.renderPlaced) return;
  [render removeFromSuperview];
  render.transform = CGAffineTransformIdentity;
  UIView *placeholder = host.placeholderView;
  if (placeholder != nil) {
    render.frame = placeholder.bounds;
    [placeholder insertSubview:render atIndex:0];
  }
  render.autoresizingMask = self.savedAutoresizing;
  render.contentScaleFactor = self.savedContentScale;
  if (host.fixedDrawable && [render isKindOfClass:MTKView.class]) {
    ((MTKView *)render).autoResizeDrawable = self.savedAutoResizeDrawable;
  }
  self.renderPlaced = NO;
  self.lastSurface = CGSizeZero;
  self.lastSurfaceScale = 0;
  NSLog(@"display.external_detached:%@", NSStringFromClass([host class]));
  if (!host.fixedDrawable && [host respondsToSelector:@selector(externalSurfaceDidChange:scale:)]) {
    [host externalSurfaceDidChange:CGSizeZero scale:0];
  }
  if ([host respondsToSelector:@selector(externalDisplayDidChange:)]) [host externalDisplayDidChange:NO];
}

#pragma mark Unsupported engines

- (void)suspendForUnsupportedEngine {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  self.suspended = YES;
  [self applyState];
}

- (void)resumeAfterUnsupportedEngine {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  self.suspended = NO;
  [self applyState];
}

#pragma mark Menu

- (void)attachMenuViewController:(UIViewController *)controller {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (controller == nil || self.menuViewController == controller) return;
  [self detachMenuViewControllerInternal];
  self.menuViewController = controller;
  [self applyState];
}

- (void)detachMenuViewController {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  [self detachMenuViewControllerInternal];
  [self applyState];
}

- (void)detachMenuViewControllerInternal {
  UIViewController *menu = self.menuViewController;
  if (menu == nil) return;
  [menu willMoveToParentViewController:nil];
  [menu.view removeFromSuperview];
  [menu removeFromParentViewController];
  self.menuViewController = nil;
}

- (void)destroyMenuEngineForMemory {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  self.menuSuppressed = YES;
  [self detachMenuViewControllerInternal];
  [self.menuProvider destroyExternalMenuEngineForReason:@"memory"];
  [self applyState];
}

#pragma mark Apply

- (void)refresh {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (self.applying) {
    // Asked by a callback of the running pass: the scenes are rescanned
    // between passes, never in the middle of one.
    self.needsRescan = YES;
    self.needsReapply = YES;
    return;
  }
  [self rescanExternalScenes];
  [self applyState];
}

/// Every pass: the registrations of dismissed controllers are released, the
/// application root holds one while there is something to show (a game on
/// the TV: outside a game nothing of NeoStation's own is shown and the
/// system mirrors the iPhone), and the presented controller that owns the
/// attached render host holds its own (enabled while the output is
/// usable). A menu presented over the game is
/// never registered: the owner is found from the host's placeholder view,
/// not from the top of the presentation chain, so a bridge that attaches
/// again from a still-presented menu (RPCS3, ARMSX2 after a failed stop)
/// keeps the scene on its game controller. Off entirely (all registrations
/// released) for a binary built with an SDK before 27 and while a scene
/// the system offered by itself is connected.
- (void)registerAccessory {
  NSString *status = nil;
  if (NSClassFromString(@"UISceneAccessory") == Nil) {
    status = @"unavailable";
  } else if ([self buildSDKMajor] < NeoExternalDisplayAccessorySDKMajor) {
    [NeoExternalDisplaySceneAccessory releaseAllRegistrations];
    status = @"inactive:sdk";
  } else if (self.automaticScenes.count > 0) {
    [NeoExternalDisplaySceneAccessory releaseAllRegistrations];
    status = @"inactive:automatic_scene";
  } else {
    NSArray<UIViewController *> *chain = NeoExternalApplicationPresentationChain();
    [NeoExternalDisplaySceneAccessory releaseRegistrationsOutside:chain];
    UIViewController *root = chain.firstObject;
    UIViewController *owner = [self presentedOwnerOfRenderHostInChain:chain];
    if (owner == root) owner = nil;
    NSMutableArray<UIViewController *> *kept = [NSMutableArray array];
    if (root != nil) [kept addObject:root];
    if (owner != nil) [kept addObject:owner];
    [NeoExternalDisplaySceneAccessory disableRegistrationsExcept:kept];
    const BOOL usable = self.enabled && !self.suspended;
    NSString *rootStatus =
        [NeoExternalDisplaySceneAccessory registerOnViewController:root
                                                           enabled:usable && self.renderHost != nil];
    NSString *ownerStatus =
        owner != nil ? [NeoExternalDisplaySceneAccessory registerOnViewController:owner enabled:usable] : nil;
    status = NeoExternalCombinedAccessoryStatus(rootStatus, ownerStatus);
  }
  if ([status isEqualToString:self.accessoryStatus]) return;
  self.accessoryStatus = status;
  NSLog(@"display.external_accessory:%@", status);
}

/// The controller of the presentation chain that holds the attached host's
/// placeholder view (the game controller, or the presented container of
/// it), or nil without a host or before it is presented.
- (UIViewController *_Nullable)presentedOwnerOfRenderHostInChain:(NSArray<UIViewController *> *)chain {
  id<NeoExternalRenderHost> host = self.renderHost;
  if (host == nil) return nil;
  UIViewController *node = NeoExternalOwningController(host.placeholderView);
  while (node != nil) {
    if ([chain containsObject:node]) return node;
    node = node.parentViewController;
  }
  return nil;
}

/// Single placement policy, run in passes: a call made during a pass (a
/// host's or the provider's callback, a preference written from one) asks
/// for one more pass at its end instead of being lost.
- (void)applyState {
  if (self.applying) {
    self.needsReapply = YES;
    return;
  }
  self.applying = YES;
  NSUInteger passes = 0;
  do {
    self.needsReapply = NO;
    if (self.needsRescan) {
      self.needsRescan = NO;
      [self rescanExternalScenes];
    }
    [self applyStatePass];
    passes += 1;
  } while (self.needsReapply && passes < kNeoExternalMaxApplyPasses);
  if (self.needsReapply) NSLog(@"display.external_apply_passes:%lu (stopped)", (unsigned long)passes);
  self.needsReapply = NO;
  self.needsRescan = NO;
  self.applying = NO;
  [self notifyIfChanged];
}

/// The game when a host is attached and the output is usable, else nothing
/// of NeoStation's own: the window is hidden and leaves its scene, and iOS
/// mirrors the iPhone, so the TV shows the NeoStation interface itself
/// (menus, library, covers, settings, animations). Build 449: the menu of
/// the second Flutter engine is never placed on the TV any more (it showed
/// the SecondaryScreen of Android handhelds, the selected console's logo,
/// instead of the interface); a controller or an engine an earlier state
/// left is released. A game going to the TV first brings the window back
/// into its scene, so the render view moves into a window that is shown.
- (void)applyStatePass {
  self.screenScale = [self currentScreenScale];
  UIWindow *window = self.window;
  const BOOL enabled = self.enabled;
  const BOOL usable = window != nil && enabled && !self.suspended;
  if (usable && self.renderHost != nil) [self placeWindowInScene:YES];
  if (self.renderHost != nil) {
    if (usable && !self.renderPlaced) [self moveRenderViewToWindow];
    else if (!usable && self.renderPlaced) [self returnRenderViewToPlaceholder];
    else if (usable) [self placeRenderView];
  }
  const BOOL gameShown = self.renderHost != nil && self.renderPlaced;
  id<NeoExternalMenuProvider> provider = self.menuProvider;
  const BOOL engineAlive =
      self.menuViewController != nil || [[provider externalMenuEngineStatus] isEqualToString:@"created"];
  if (self.menuViewController != nil) [self detachMenuViewControllerInternal];
  if (engineAlive) [provider destroyExternalMenuEngineForReason:enabled ? @"menu_off" : @"disabled"];
  self.content = gameShown ? NeoExternalContentGame : NeoExternalContentNone;
  const BOOL shown = usable && gameShown;
  if (window != nil) window.hidden = !shown;
  if (!shown) [self placeWindowInScene:NO];
  [self registerAccessory];
}

@end
