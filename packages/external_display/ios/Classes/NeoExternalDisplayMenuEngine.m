// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoExternalDisplayMenuEngine.h"

NSString *const kNeoExternalMenuEngineGroupName = @"neostation-external";
NSString *const kNeoExternalMenuChannelName = @"neostation/external_display/menu";

/// Frozen registry of the second engine: never GeneratedPluginRegistrant,
/// whose registerWithRegistrar: calls would re-create every emulation bridge
/// (RPCS3 re-acquires the JIT escrow, Dolphin replaces a global queue). Each
/// class is resolved by name and skipped when absent from the app; a Swift
/// plugin without @objc(name) is also tried by its module-qualified runtime
/// name. test/external_display_scope_test.py pins this list.
static NSString *const kNeoExternalMenuPlugins[] = {
  @"SqflitePlugin",
  @"FLTPathProviderPlugin",
  @"PathProviderPlugin",
  @"path_provider_foundation.PathProviderPlugin",
  @"FVPVideoPlayerPlugin",
  @"SharedPreferencesPlugin",
  @"shared_preferences_foundation.SharedPreferencesPlugin",
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
@property(nonatomic, copy) NSString *status;
@property(nonatomic, strong, nullable) FlutterEngineGroup *group;
@property(nonatomic, strong, nullable) FlutterEngine *engine;
@property(nonatomic, strong, nullable) FlutterViewController *viewController;
@property(nonatomic, strong, nullable) FlutterBasicMessageChannel *channel;
@property(nonatomic, copy, nullable) NSString *lastMenuState;
@end

@implementation NeoExternalDisplayMenuEngine

+ (instancetype)shared {
  static NeoExternalDisplayMenuEngine *shared;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ shared = [[NeoExternalDisplayMenuEngine alloc] init]; });
  return shared;
}

- (instancetype)init {
  if ((self = [super init])) _status = @"none";
  return self;
}

- (void)configureWithEntrypoint:(NSString *)entrypoint libraryURI:(NSString *)libraryURI {
  self.entrypoint = entrypoint;
  self.libraryURI = libraryURI;
}

- (BOOL)configured { return self.entrypoint.length > 0 && self.libraryURI.length > 0; }

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
  FlutterEngine *engine = [self.group makeEngineWithEntrypoint:self.entrypoint libraryURI:self.libraryURI];
  if (engine == nil) {
    NSLog(@"display.external_menu_engine:failed entrypoint=%@", self.entrypoint);
    return nil;
  }
  [self registerPluginsOnEngine:engine];
  self.channel = [FlutterBasicMessageChannel messageChannelWithName:kNeoExternalMenuChannelName
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
  NSLog(@"display.external_menu_engine:created");
  // The engine buffers the message until the Dart handler is up.
  if (self.lastMenuState != nil) [self.channel sendMessage:self.lastMenuState];
  return controller;
}

- (void)destroyExternalMenuEngineForReason:(NSString *)reason {
  NSAssert(NSThread.isMainThread, @"The menu engine belongs to the main thread");
  FlutterViewController *controller = self.viewController;
  FlutterEngine *engine = self.engine;
  if (controller == nil && engine == nil) return;
  [controller willMoveToParentViewController:nil];
  [controller.view removeFromSuperview];
  [controller removeFromParentViewController];
  self.channel = nil;
  engine.viewController = nil;
  [engine destroyContext];
  self.viewController = nil;
  self.engine = nil;
  self.status = @"destroyed";
  NSLog(@"display.external_menu_engine:destroyed:%@", reason);
}

- (NSString *)externalMenuEngineStatus { return self.status; }

#pragma mark Menu state

- (void)pushMenuState:(NSString *)json {
  self.lastMenuState = json;
  [self.channel sendMessage:json];
}

- (void)destroyMenuEngineForMemory {
  [self destroyExternalMenuEngineForReason:@"memory"];
}

@end
