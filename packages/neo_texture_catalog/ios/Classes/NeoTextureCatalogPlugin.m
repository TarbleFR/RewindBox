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

@implementation NeoTextureCatalogPlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  NeoTextureCatalogPlugin *plugin = [self new];
  FlutterMethodChannel *channel = [FlutterMethodChannel methodChannelWithName:@"neostation/texture_catalog" binaryMessenger:registrar.messenger];
  [registrar addMethodCallDelegate:plugin channel:channel];
}

- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  NSDictionary *args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  if ([call.method isEqualToString:@"open"]) {
    // Only the keys the page reads, with the types it expects (no blocks from Dart).
    NSMutableDictionary *options = [NSMutableDictionary dictionary];
    for (NSString *key in @[@"system", @"engine", @"locale", @"title", @"gamePath", @"gameKey", @"dolphinUser", @"armsx2Data",
                            @"libretroSaves", @"libretroConfig", @"libretroSystem"])
      if ([args[key] isKindOfClass:NSString.class]) options[key] = args[key];
    if ([args[@"games"] isKindOfClass:NSArray.class]) {
      NSMutableArray *games = [NSMutableArray array];
      for (id game in args[@"games"]) {
        if (![game isKindOfClass:NSDictionary.class] || ![game[@"path"] isKindOfClass:NSString.class]) continue;
        NSMutableDictionary *entry = [@{@"path": game[@"path"]} mutableCopy];
        if ([game[@"title"] isKindOfClass:NSString.class]) entry[@"title"] = game[@"title"];
        if ([game[@"gameKey"] isKindOfClass:NSString.class]) entry[@"gameKey"] = game[@"gameKey"];
        [games addObject:entry];
        if (games.count >= 3000) break;
      }
      options[@"games"] = games;
    }
    options[@"presentation"] = @"modal";
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
