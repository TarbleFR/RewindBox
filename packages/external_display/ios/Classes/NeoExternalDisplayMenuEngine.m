// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoExternalDisplayMenuEngine.h"

NSString *const kNeoExternalMenuEngineGroupName = @"neostation-external";
NSString *const kNeoExternalMenuChannelName = @"neostation/external_display/menu";
NSString *const kNeoExternalMenuLocaleChannelName = @"neostation/external_display/menu_locale";
NSString *const kNeoExternalMenuLanguageArgumentPrefix = @"language=";
NSString *const kNeoExternalMenuThemeArgumentPrefix = @"theme=";

/// Lifecycle messages of the engine's lifecycle channel (SystemChannels
/// .lifecycle): a hidden engine schedules no frame.
static NSString *const kNeoExternalLifecycleResumed = @"AppLifecycleState.resumed";
static NSString *const kNeoExternalLifecycleInactive = @"AppLifecycleState.inactive";
static NSString *const kNeoExternalLifecycleHidden = @"AppLifecycleState.hidden";
/// After an activation, the FlutterViewController sends `resumed` on a later
/// turn of the run loop; the hidden state is sent again after that.
static const NSTimeInterval kNeoExternalLifecycleReassertDelay = 0.1;

/// Frozen registry of the second engine: never GeneratedPluginRegistrant,
/// whose registerWithRegistrar: calls would re-create every emulation bridge
/// (RPCS3 re-acquires the JIT escrow, Dolphin replaces a global queue). Each
/// class is resolved by name and skipped when absent from the app; a Swift
/// plugin without @objc(name) only resolves by its module-qualified runtime
/// name. Checked against the plugins the app pins (pubspec.lock, 12 October
/// 2026), extended for the display-only achievement translation plugin.
/// The TV menu needs shared_preferences (flutter_localization
/// reads the stored language there), a Swift class without @objc name
/// (shared_preferences_foundation 2.5.6). path_provider_foundation 2.6.0
/// has no native class (FFI), sqflite is not a dependency (the app uses
/// sqlite3 through FFI, and this engine never opens the database), and the
/// TV menu has no video player: the relays never send a video (images only,
/// docs § 8 bis), so video_player's native class (Swift VideoPlayerPlugin of
/// video_player_avfoundation 2.11.0) is not registered and a preview never
/// starts there. test/external_display_scope_test.py pins this list.
static NSString *const kNeoExternalMenuPlugins[] = {
  @"shared_preferences_foundation.SharedPreferencesPlugin",
  @"achievement_translation.AchievementTranslationPlugin",
};

NSArray<NSString *> *NeoExternalMenuPluginClassNames(void) {
  const size_t count = sizeof(kNeoExternalMenuPlugins) / sizeof(kNeoExternalMenuPlugins[0]);
  NSMutableArray<NSString *> *names = [NSMutableArray arrayWithCapacity:count];
  for (size_t index = 0; index < count; ++index) [names addObject:kNeoExternalMenuPlugins[index]];
  return names;
}

@interface NeoExternalDisplayMenuEngine ()
@property(nonatomic, copy, nullable) NSString *entrypoint;
@property(nonatomic, copy, nullable) NSString *libraryURI;
@property(nonatomic, copy, nullable) NSString *languageCode;
@property(nonatomic, copy, nullable) NSString *themeName;
@property(nonatomic, copy) NSString *status;
@property(nonatomic, strong, nullable) FlutterEngineGroup *group;
@property(nonatomic, strong, nullable) FlutterEngine *engine;
@property(nonatomic, strong, nullable) FlutterViewController *viewController;
@property(nonatomic, strong, nullable) FlutterBasicMessageChannel *channel;
@property(nonatomic, strong, nullable) FlutterBasicMessageChannel *localeChannel;
@property(nonatomic, copy, nullable) NSString *lastMenuState;
/// What the coordinator asked for (externalMenuSetVisible:).
@property(nonatomic, assign) BOOL menuVisible;
/// The lifecycle message last sent by this object.
@property(nonatomic, copy, nullable) NSString *lifecycleState;
@end

@implementation NeoExternalDisplayMenuEngine

+ (instancetype)shared {
  static NeoExternalDisplayMenuEngine *shared;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ shared = [[NeoExternalDisplayMenuEngine alloc] init]; });
  return shared;
}

- (instancetype)init {
  if ((self = [super init])) {
    _status = @"none";
    _menuVisible = YES;
  }
  return self;
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (void)configureWithEntrypoint:(NSString *)entrypoint
                     libraryURI:(NSString *)libraryURI
                   languageCode:(NSString *)languageCode
                      themeName:(NSString *)themeName {
  self.entrypoint = entrypoint;
  self.libraryURI = libraryURI;
  self.languageCode = languageCode.length > 0 ? languageCode : nil;
  self.themeName = themeName.length > 0 ? themeName : nil;
}

- (void)updateLanguageCode:(NSString *)languageCode themeName:(NSString *)themeName {
  if (themeName.length > 0) self.themeName = themeName;
  if (languageCode.length == 0 || [languageCode isEqualToString:self.languageCode]) return;
  self.languageCode = languageCode;
  // The running engine translates at once; a later engine starts with it.
  [self.localeChannel sendMessage:languageCode];
  NSLog(@"display.external_menu_language:%@", languageCode);
}

- (BOOL)configured { return self.entrypoint.length > 0 && self.libraryURI.length > 0; }

- (NSArray<NSString *> *)entrypointArguments {
  NSMutableArray<NSString *> *arguments = [NSMutableArray array];
  if (self.languageCode.length > 0) {
    [arguments addObject:[kNeoExternalMenuLanguageArgumentPrefix stringByAppendingString:self.languageCode]];
  }
  if (self.themeName.length > 0) {
    [arguments addObject:[kNeoExternalMenuThemeArgumentPrefix stringByAppendingString:self.themeName]];
  }
  return arguments;
}

- (void)registerPluginsOnEngine:(FlutterEngine *)engine {
  NSMutableSet<Class> *registered = [NSMutableSet set];
  for (NSString *name in NeoExternalMenuPluginClassNames()) {
    Class pluginClass = NSClassFromString(name);
    if (pluginClass == Nil || [registered containsObject:pluginClass]) continue;
    if (![pluginClass respondsToSelector:@selector(registerWithRegistrar:)]) continue;
    NSString *key = [name componentsSeparatedByString:@"."].lastObject ?: name;
    NSObject<FlutterPluginRegistrar> *registrar = [engine registrarForPlugin:key];
    if (registrar == nil) continue;
    [(Class<FlutterPlugin>)pluginClass registerWithRegistrar:registrar];
    [registered addObject:pluginClass];
    NSLog(@"display.external_menu_plugin:%@", key);
  }
}

#pragma mark NeoExternalMenuProvider

- (UIViewController *)externalMenuViewControllerCreatingIfNeeded {
  NSAssert(NSThread.isMainThread, @"The menu engine belongs to the main thread");
  if (self.viewController != nil) return self.viewController;
  if (!self.configured) return nil;
  if (self.group == nil) self.group = [[FlutterEngineGroup alloc] initWithName:kNeoExternalMenuEngineGroupName project:nil];
  // The language and the theme come from the main engine as entrypoint
  // arguments: this engine never reads the database.
  FlutterEngineGroupOptions *options = [[FlutterEngineGroupOptions alloc] init];
  options.entrypoint = self.entrypoint;
  options.libraryURI = self.libraryURI;
  options.entrypointArgs = [self entrypointArguments];
  FlutterEngine *engine = [self.group makeEngineWithOptions:options];
  if (engine == nil) {
    NSLog(@"display.external_menu_engine:failed entrypoint=%@", self.entrypoint);
    return nil;
  }
  [self registerPluginsOnEngine:engine];
  self.channel = [FlutterBasicMessageChannel messageChannelWithName:kNeoExternalMenuChannelName
                                                    binaryMessenger:engine.binaryMessenger
                                                              codec:FlutterStringCodec.sharedInstance];
  self.localeChannel = [FlutterBasicMessageChannel messageChannelWithName:kNeoExternalMenuLocaleChannelName
                                                          binaryMessenger:engine.binaryMessenger
                                                                    codec:FlutterStringCodec.sharedInstance];
  FlutterViewController *controller = [[FlutterViewController alloc] initWithEngine:engine nibName:nil bundle:nil];
  // Black until the first frame: the TV never shows the iPhone launch image.
  UIView *splash = [[UIView alloc] initWithFrame:CGRectZero];
  splash.backgroundColor = UIColor.blackColor;
  controller.splashScreenView = splash;
  controller.view.backgroundColor = UIColor.blackColor;
  self.engine = engine;
  self.viewController = controller;
  self.status = @"created";
  self.lifecycleState = nil;
  [self observeActivations];
  NSLog(@"display.external_menu_engine:created %@", [self entrypointArguments]);
  // The engine buffers the message until the Dart handler is up.
  if (self.lastMenuState != nil) [self.channel sendMessage:self.lastMenuState];
  return controller;
}

- (void)destroyExternalMenuEngineForReason:(NSString *)reason {
  NSAssert(NSThread.isMainThread, @"The menu engine belongs to the main thread");
  FlutterViewController *controller = self.viewController;
  FlutterEngine *engine = self.engine;
  if (controller == nil && engine == nil) return;
  [NSNotificationCenter.defaultCenter removeObserver:self];
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(reassertLifecycle) object:nil];
  [controller willMoveToParentViewController:nil];
  [controller.view removeFromSuperview];
  [controller removeFromParentViewController];
  self.channel = nil;
  self.localeChannel = nil;
  engine.viewController = nil;
  [engine destroyContext];
  self.viewController = nil;
  self.engine = nil;
  self.lifecycleState = nil;
  self.status = @"destroyed";
  NSLog(@"display.external_menu_engine:destroyed:%@", reason);
}

- (NSString *)externalMenuEngineStatus { return self.status; }

#pragma mark Lifecycle (hidden while a game holds the TV)

- (void)externalMenuSetVisible:(BOOL)visible {
  NSAssert(NSThread.isMainThread, @"The menu engine belongs to the main thread");
  self.menuVisible = visible;
  [self sendLifecycle];
}

/// `hidden` while the menu is not shown (the framework stops scheduling
/// frames: GIF backgrounds and timers draw nothing); on the way back,
/// `resumed` while the app is active, `inactive` otherwise. A visible engine
/// is otherwise left to its FlutterViewController.
- (void)sendLifecycle {
  FlutterEngine *engine = self.engine;
  if (engine == nil) return;
  NSString *state = kNeoExternalLifecycleHidden;
  if (self.menuVisible) {
    if (self.lifecycleState == nil || ![self.lifecycleState isEqualToString:kNeoExternalLifecycleHidden]) return;
    state = UIApplication.sharedApplication.applicationState == UIApplicationStateActive ? kNeoExternalLifecycleResumed
                                                                                         : kNeoExternalLifecycleInactive;
  } else if ([self.lifecycleState isEqualToString:kNeoExternalLifecycleHidden]) {
    return;
  }
  self.lifecycleState = state;
  [engine.lifecycleChannel sendMessage:state];
  NSLog(@"display.external_menu_lifecycle:%@", state);
}

/// The FlutterViewController sends `resumed` itself when the app or a scene
/// becomes active (on a later turn of the run loop): while the menu is
/// hidden, the hidden state is sent again shortly after.
- (void)observeActivations {
  NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
  [center removeObserver:self];
  for (NSNotificationName name in @[UIApplicationDidBecomeActiveNotification, UIApplicationWillEnterForegroundNotification,
                                    UISceneDidActivateNotification, UISceneWillEnterForegroundNotification]) {
    [center addObserver:self selector:@selector(activationObserved:) name:name object:nil];
  }
}

- (void)activationObserved:(NSNotification *)notification {
  if (self.engine == nil || self.menuVisible) return;
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(reassertLifecycle) object:nil];
  [self performSelector:@selector(reassertLifecycle) withObject:nil afterDelay:kNeoExternalLifecycleReassertDelay];
}

- (void)reassertLifecycle {
  if (self.engine == nil || self.menuVisible) return;
  self.lifecycleState = nil;
  [self sendLifecycle];
}

#pragma mark Menu state

- (void)pushMenuState:(NSString *)json {
  self.lastMenuState = json;
  [self.channel sendMessage:json];
}

- (void)destroyMenuEngineForMemory {
  [self destroyExternalMenuEngineForReason:@"memory"];
}

@end
