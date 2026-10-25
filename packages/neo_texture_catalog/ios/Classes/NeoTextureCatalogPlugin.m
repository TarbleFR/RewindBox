// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTextureCatalogPlugin.h"
#import "Public/NeoTextureCatalog.h"
#import "Public/NeoTextureHDPage.h"

static UIViewController *TopViewController(void) {
  UIWindow *keyWindow = nil;
  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class] || scene.activationState != UISceneActivationStateForegroundActive) continue;
    for (UIWindow *window in ((UIWindowScene *)scene).windows)
      if (window.isKeyWindow) { keyWindow = window; break; }
    if (keyWindow) break;
  }
  UIViewController *controller = keyWindow.rootViewController;
  while (controller.presentedViewController) controller = controller.presentedViewController;
  return controller;
}

@interface NeoTextureCatalogPlugin ()
@property(nonatomic, strong) FlutterMethodChannel *channel;
@end

@implementation NeoTextureCatalogPlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  NeoTextureCatalogPlugin *plugin = [self new];
  FlutterMethodChannel *channel = [FlutterMethodChannel methodChannelWithName:@"neostation/texture_catalog" binaryMessenger:registrar.messenger];
  plugin.channel = channel;
  [registrar addMethodCallDelegate:plugin channel:channel];
}

// Asks the app to start a game with another libretro core (Mesen for an NES
// HD pack): NeoStation's own per-game engine choice, kept by Dart. Called by
// the page off the main thread; waits for the answer (5 s at most).
- (BOOL (^)(NSString *, NSString *))coreSelector {
  __weak FlutterMethodChannel *weakChannel = self.channel;
  return ^BOOL(NSString *gameKey, NSString *core) {
    FlutterMethodChannel *channel = weakChannel;
    if (!channel || NSThread.isMainThread || !gameKey.length || !core.length) return NO;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    __block BOOL selected = NO;
    dispatch_async(dispatch_get_main_queue(), ^{
      [channel invokeMethod:@"selectLibretroCore" arguments:@{@"gameKey": gameKey, @"core": core} result:^(id answer) {
        selected = [answer isKindOfClass:NSNumber.class] && [answer boolValue];
        dispatch_semaphore_signal(done);
      }];
    });
    if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC)) != 0) return NO;
    return selected;
  };
}

- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  NSDictionary *args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  if ([call.method isEqualToString:@"open"]) {
    // Only the keys the page reads, with the types it expects (no blocks from Dart; the
    // core selector is this plugin's own call back to Dart).
    NSMutableDictionary *options = [NSMutableDictionary dictionary];
    for (NSString *key in @[@"system", @"engine", @"locale", @"title", @"gamePath", @"gameKey", @"libretroCore", @"dolphinUser", @"armsx2Data",
                            @"libretroSaves", @"libretroConfig", @"libretroSystem"])
      if ([args[key] isKindOfClass:NSString.class]) options[key] = args[key];
    if ([args[@"games"] isKindOfClass:NSArray.class]) {
      NSMutableArray *games = [NSMutableArray array];
      for (id game in args[@"games"]) {
        if (![game isKindOfClass:NSDictionary.class] || ![game[@"path"] isKindOfClass:NSString.class]) continue;
        NSMutableDictionary *entry = [@{@"path": game[@"path"]} mutableCopy];
        if ([game[@"title"] isKindOfClass:NSString.class]) entry[@"title"] = game[@"title"];
        if ([game[@"gameKey"] isKindOfClass:NSString.class]) entry[@"gameKey"] = game[@"gameKey"];
        if ([game[@"libretroCore"] isKindOfClass:NSString.class]) entry[@"libretroCore"] = game[@"libretroCore"];
        [games addObject:entry];
        if (games.count >= 3000) break;
      }
      options[@"games"] = games;
    }
    options[@"presentation"] = @"modal";
    options[@"coreSelector"] = [self coreSelector];
    UIViewController *page = [NeoTextureHDPage textureViewControllerWithOptions:options];
    UIViewController *top = TopViewController();
    if (!page || !top) { result(@NO); return; }
    [top presentViewController:page animated:YES completion:^{ result(@YES); }];
  } else if ([call.method isEqualToString:@"snapshot"]) {
    [NeoTextureCatalog.sharedCatalog loadWithCompletion:^(NSDictionary *snapshot, NSError *error) {
      NSMutableDictionary *summary = [NSMutableDictionary dictionary];
      for (NSString *key in @[@"state", @"revision", @"generated_at", @"refreshed_at", @"pack_count", @"available", @"refresh_error"])
        if (snapshot[key]) summary[key] = snapshot[key];
      result(summary);
    }];
  } else {
    result(FlutterMethodNotImplemented);
  }
}

@end
