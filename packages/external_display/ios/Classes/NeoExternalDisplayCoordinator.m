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

/// From iOS 27 the external non-interactive scene is delivered only while a
/// view controller the app presents holds an enabled UISceneAccessory
/// registration. When several controllers hold one, the system presents the
/// registration of the topmost, most recently presented controller, and it
/// disconnects the scene when that controller is dismissed ("Presenting
/// content on a connected display", Apple, read on 12 October 2026). The API
/// is iOS 27.0 and the CI SDK is iOS 26, so everything is resolved at run
/// time by name; on earlier systems the class is absent and this is a no-op
/// (the scene connects by itself).
///
/// One registration per controller, kept while the controller is still in
/// the application's presentation chain: the Flutter root keeps its own
/// while a game controller is presented over it, so the dismissal of the
/// game controller hands the scene back to the root without any call from
/// the bridge. The registrations of dismissed controllers are released at
/// the next pass (the bridge's refresh after the dismissal, a window
/// notification, the next attach).

/// A controller and the UISceneAccessoryRegistration it holds.
@interface NeoExternalAccessoryRegistration : NSObject
@property(nonatomic, weak, nullable) UIViewController *controller;
@property(nonatomic, strong) id registration;
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

@interface NeoExternalDisplaySceneAccessory : NSObject
+ (NSString *)registerOnViewController:(UIViewController *_Nullable)controller;
+ (void)releaseRegistrationsOutside:(NSArray<UIViewController *> *)chain;
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

+ (NSString *)registerOnViewController:(UIViewController *_Nullable)controller {
  Class accessoryClass = NSClassFromString(@"UISceneAccessory");
  if (accessoryClass == Nil) return @"unavailable";
  if (controller == nil) return @"failed:no_controller";
  if ([self entryForViewController:controller] != nil) return @"registered";
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
  if (gNeoExternalRegistrations == nil) gNeoExternalRegistrations = [NSMutableArray array];
  [gNeoExternalRegistrations addObject:entry];
  return @"registered";
}

/// Unregisters the controllers that left the presentation chain (dismissed
/// game controllers) or were released; the ones still presented keep their
/// registration so the system never runs out of one.
+ (void)releaseRegistrationsOutside:(NSArray<UIViewController *> *)chain {
  if (gNeoExternalRegistrations.count == 0) return;
  SEL unregisterSelector = NSSelectorFromString(@"unregisterSceneAccessory:");
  NSMutableArray<NeoExternalAccessoryRegistration *> *kept = [NSMutableArray array];
  for (NeoExternalAccessoryRegistration *entry in gNeoExternalRegistrations) {
    UIViewController *controller = entry.controller;
    if (controller != nil && NeoExternalControllerIsLive(controller, chain)) {
      [kept addObject:entry];
      continue;
    }
    if (controller != nil && entry.registration != nil && [controller respondsToSelector:unregisterSelector]) {
      ((void (*)(id, SEL, id))objc_msgSend)(controller, unregisterSelector, entry.registration);
    }
  }
  gNeoExternalRegistrations = kept;
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

static NSString *NeoExternalContentName(NeoExternalContentKind content) {
  switch (content) {
    case NeoExternalContentMenu: return @"menu";
    case NeoExternalContentGame: return @"game";
    case NeoExternalContentNone: break;
  }
  return @"none";
}

#pragma mark - Coordinator

@interface NeoExternalDisplayCoordinator ()
@property(nonatomic, strong, nullable) UIWindow *window;
@property(nonatomic, strong, nullable) UIWindowScene *scene;
@property(nonatomic, strong, nullable) UIScreen *legacyScreen;
@property(nonatomic, copy) NSString *sceneRole;
@property(nonatomic, assign) BOOL sceneEverConnected;
@property(nonatomic, strong, nullable) NSTimer *legacyTimer;
@property(nonatomic, strong, nullable) id<NeoExternalRenderHost> renderHost;
/// The render view is in the external window right now.
@property(nonatomic, assign) BOOL renderPlaced;
@property(nonatomic, assign) CGSize lastSurface;
@property(nonatomic, strong, nullable) UIViewController *menuViewController;
/// destroyMenuEngineForMemory until the game's host detaches.
@property(nonatomic, assign) BOOL menuSuppressed;
@property(nonatomic, assign) BOOL suspended;
@property(nonatomic, assign) NeoExternalContentKind content;
@property(nonatomic, assign) CGFloat screenScale;
@property(nonatomic, copy) NSString *accessoryStatus;
/// attachRenderHost: a bridge presented a game controller; the next pass
/// registers the iOS 27 accessory on it too (the root keeps its own).
@property(nonatomic, assign) BOOL registerPresentedController;
@property(nonatomic, copy, nullable) NSDictionary<NSString *, id> *lastState;
@property(nonatomic, assign) BOOL applying;
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

- (BOOL)menuOnTV { return NeoExternalDisplayPreferences.menuOnTV; }

- (BOOL)mirroringActive { return self.window != nil && self.window.hidden; }

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
  [self.legacyTimer invalidate];
  self.legacyTimer = nil;
  self.sceneEverConnected = YES;
  if (self.window != nil) [self disconnectWindow];  // a legacy window gives way to the scene
  UIWindow *window = self.windowFactory ? self.windowFactory(scene, scene.screen) : nil;
  if (window == nil) window = [[UIWindow alloc] initWithWindowScene:scene];
  self.scene = scene;
  self.screenScale = scene.screen.scale;
  NSLog(@"display.external_scene_connected %@ @%.0fx", NSStringFromCGSize(window.bounds.size), self.screenScale);
  [self connectWindow:window role:kNeoExternalRoleScene];
}

- (void)sceneDidDisconnect:(UIWindowScene *)scene {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (self.window == nil || ![self.sceneRole isEqualToString:kNeoExternalRoleScene]) return;
  if (self.scene != nil && scene != nil && self.scene != scene) return;
  [self disconnectWindow];
}

/// Build 442 path, kept only for a system that never delivers the external
/// scene: `UIScreen.screens` and `UIWindow.screen` are deprecated since iOS
/// 16 and used nowhere else. Runs 1.5 s after UIScreenDidConnectNotification
/// when no scene arrived and none ever did.
- (void)activateLegacyIfNeeded {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  self.legacyTimer = nil;
  if (self.window != nil || self.sceneEverConnected) return;
  NSArray<UIScreen *> *screens = nil;
  UIWindow *window = nil;
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
  if (screen == nil) return;
  window = self.windowFactory ? self.windowFactory(nil, screen) : nil;
  if (window == nil) {
    window = [[UIWindow alloc] initWithFrame:screen.bounds];
    window.screen = screen;
  }
#pragma clang diagnostic pop
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

/// The render view goes back to the iPhone first, then the window is
/// released; the menu engine is destroyed (recreated at the next connection).
- (void)disconnectWindow {
  UIWindow *window = self.window;
  if (window == nil) return;
  [self returnRenderViewToPlaceholder];
  [self detachMenuViewControllerInternal];
  [self.menuProvider destroyExternalMenuEngineForReason:@"disconnect"];
  self.window = nil;
  self.scene = nil;
  self.legacyScreen = nil;
  self.screenScale = 0;
  self.sceneRole = kNeoExternalRoleNone;
  window.hidden = YES;
  window.rootViewController = nil;
  [self applyState];
}

#pragma mark Render hosts

- (void)attachRenderHost:(id<NeoExternalRenderHost>)host {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  if (host == nil) return;
  if (self.renderHost != nil && self.renderHost != host) [self detachRenderHost:self.renderHost];
  self.renderHost = host;
  self.registerPresentedController = YES;
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
  // The surface follows the TV: the view takes the surface size in points
  // at the TV's scale and the host rebuilds its drawable from it.
  CGSize source = self.savedBounds.size;
  if (!NeoExternalDisplayUsableSize(source)) source = host.placeholderView.bounds.size;
  const CGSize surface = NeoExternalDisplaySurfaceSize(screen, source, mode);
  const CGFloat scale = self.screenScale > 0 ? self.screenScale : render.contentScaleFactor;
  render.transform = CGAffineTransformIdentity;
  render.bounds = CGRectMake(0, 0, surface.width, surface.height);
  render.center = CGPointMake(screen.width / 2, screen.height / 2);
  render.contentScaleFactor = scale;
  if (CGSizeEqualToSize(surface, self.lastSurface)) return;
  self.lastSurface = surface;
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

/// The menu view fills the window below the render view; hidden while the
/// game is on the TV, never released here.
- (void)placeMenuViewControllerShown:(BOOL)shown {
  UIViewController *menu = self.menuViewController;
  UIWindow *window = self.window;
  if (menu == nil || window == nil) return;
  UIViewController *root = window.rootViewController;
  root.view.frame = window.bounds;
  if (menu.parentViewController != root) {
    [root addChildViewController:menu];
    menu.view.frame = root.view.bounds;
    menu.view.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    menu.view.backgroundColor = UIColor.blackColor;
    [root.view insertSubview:menu.view atIndex:0];
    [menu didMoveToParentViewController:root];
  } else {
    menu.view.frame = root.view.bounds;
  }
  menu.view.hidden = !shown;
}

#pragma mark Apply

- (void)refresh {
  NSAssert(NSThread.isMainThread, @"External display belongs to the main thread");
  [self applyState];
}

/// Every pass: the registrations of dismissed controllers are released and
/// the root of the application scene holds one. After attachRenderHost:,
/// the presented game controller gets its own as well (the topmost
/// registration is the one the system presents); menus presented over a
/// game are never registered by a plain refresh, so a setting changed from
/// an in-game menu does not move the scene.
- (void)registerAccessoryIncludingPresented:(BOOL)includePresented {
  NSArray<UIViewController *> *chain = NeoExternalApplicationPresentationChain();
  [NeoExternalDisplaySceneAccessory releaseRegistrationsOutside:chain];
  NSString *status = [NeoExternalDisplaySceneAccessory registerOnViewController:chain.firstObject];
  if (includePresented && chain.count > 1 && [status isEqualToString:@"registered"]) {
    status = [NeoExternalDisplaySceneAccessory registerOnViewController:chain.lastObject];
  }
  if ([status isEqualToString:self.accessoryStatus]) return;
  self.accessoryStatus = status;
  NSLog(@"display.external_accessory:%@", status);
}

- (void)registerAccessory {
  const BOOL includePresented = self.registerPresentedController;
  self.registerPresentedController = NO;
  [self registerAccessoryIncludingPresented:includePresented];
}

/// Single placement policy: the game when a host is attached, else the menu
/// when wanted, else nothing (window hidden so iOS mirrors the iPhone). The
/// menu engine is only created when it is about to be shown: never while a
/// game holds the TV (an engine that already exists is hidden, not released).
- (void)applyState {
  if (self.applying) return;
  self.applying = YES;
  UIWindow *window = self.window;
  const BOOL usable = window != nil && self.enabled && !self.suspended;
  if (self.renderHost != nil) {
    if (usable && !self.renderPlaced) [self moveRenderViewToWindow];
    else if (!usable && self.renderPlaced) [self returnRenderViewToPlaceholder];
    else if (usable) [self placeRenderView];
  }
  const BOOL gameShown = self.renderHost != nil && self.renderPlaced;
  const BOOL menuOnTV = self.menuOnTV;
  id<NeoExternalMenuProvider> provider = self.menuProvider;
  if (usable && menuOnTV && !gameShown && !self.menuSuppressed && self.menuViewController == nil && provider != nil) {
    UIViewController *controller = [provider externalMenuViewControllerCreatingIfNeeded];
    if (controller != nil) self.menuViewController = controller;
  }
  if (!menuOnTV && self.menuViewController != nil) {
    [self detachMenuViewControllerInternal];
    [provider destroyExternalMenuEngineForReason:@"menu_off"];
  }
  const BOOL menuShown = usable && self.menuViewController != nil && !gameShown;
  [self placeMenuViewControllerShown:menuShown];
  self.content = gameShown ? NeoExternalContentGame : menuShown ? NeoExternalContentMenu : NeoExternalContentNone;
  if (window != nil) window.hidden = !(usable && self.content != NeoExternalContentNone);
  [self registerAccessory];
  self.applying = NO;
  [self notifyIfChanged];
}

@end
