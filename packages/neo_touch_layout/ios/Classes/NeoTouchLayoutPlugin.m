// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTouchLayoutPlugin.h"
#import "Public/NeoTouchLayout.h"

static NSArray<NSString*>* NeoTouchLayoutKeysForConsole(NSString* console) {
  if ([console isEqualToString:@"gc"]) return @[NeoTouchLayoutKeyGameCube];
  if ([console isEqualToString:@"wii"]) return @[NeoTouchLayoutKeyWii, NeoTouchLayoutKeyWiiClassic];
  if ([console isEqualToString:@"ps2"]) return @[NeoTouchLayoutKeyPlayStation2];
  if ([console isEqualToString:@"ps3"]) return @[NeoTouchLayoutKeyPlayStation3];
  return @[];
}

static UIViewController* NeoTouchLayoutTopViewController(void) {
  UIWindow* keyWindow = nil;
  for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class] ||
        scene.activationState != UISceneActivationStateForegroundActive) continue;
    for (UIWindow* window in ((UIWindowScene*)scene).windows) {
      if (window.isKeyWindow) {
        keyWindow = window;
        break;
      }
    }
    if (keyWindow) break;
  }
  UIViewController* controller = keyWindow.rootViewController;
  while (controller.presentedViewController) controller = controller.presentedViewController;
  return controller;
}

@implementation NeoTouchLayoutPlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar {
  FlutterMethodChannel* channel = [FlutterMethodChannel methodChannelWithName:@"neostation/touch_layout"
                                                              binaryMessenger:[registrar messenger]];
  NeoTouchLayoutPlugin* instance = [NeoTouchLayoutPlugin new];
  [registrar addMethodCallDelegate:instance channel:channel];
}

- (NSDictionary*)settingsForConsole:(NSString*)console {
  NSMutableArray* layouts = [NSMutableArray array];
  for (NSString* key in NeoTouchLayoutKeysForConsole(console)) {
    [layouts addObject:@{
      @"key": key,
      @"customized": @([NeoTouchLayoutStore.sharedStore hasCustomLayoutForKey:key]),
      @"editable": @([NeoTouchLayoutRegistry previewFactoryForLayoutKey:key] != nil),
    }];
  }
  return @{
    @"console": console,
    @"hideWithController": @(NeoTouchHidesControlsWithController(console)),
    @"controllerConnected": @([NeoTouchControllerMonitor compatibleControllerConnected]),
    @"layouts": layouts,
  };
}

- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {
  NSDictionary* arguments = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  NSString* console = [arguments[@"console"] isKindOfClass:NSString.class] ? arguments[@"console"] : @"";
  if ([call.method isEqualToString:@"settings"]) {
    if (NeoTouchLayoutKeysForConsole(console).count == 0) {
      result([FlutterError errorWithCode:@"invalid_console" message:@"Unknown console." details:console]);
      return;
    }
    result([self settingsForConsole:console]);
    return;
  }
  if ([call.method isEqualToString:@"setHideWithController"]) {
    if (NeoTouchLayoutKeysForConsole(console).count == 0 || ![arguments[@"hide"] isKindOfClass:NSNumber.class]) {
      result([FlutterError errorWithCode:@"invalid_arguments" message:@"Console and value required." details:nil]);
      return;
    }
    NeoTouchSetHidesControlsWithController(console, [arguments[@"hide"] boolValue]);
    result([self settingsForConsole:console]);
    return;
  }
  if ([call.method isEqualToString:@"openEditor"]) {
    NSString* layout = [arguments[@"layout"] isKindOfClass:NSString.class] ? arguments[@"layout"] : @"";
    NSString* locale = [arguments[@"locale"] isKindOfClass:NSString.class] ? arguments[@"locale"] : nil;
    NeoTouchLayoutEditorController* editor = [[NeoTouchLayoutEditorController alloc] initWithLayoutKey:layout
                                                                                                 locale:locale];
    UIViewController* presenter = NeoTouchLayoutTopViewController();
    if (!editor || !presenter) {
      result(@{@"opened": @NO, @"saved": @NO});
      return;
    }
    editor.finished = ^(BOOL saved) { result(@{@"opened": @YES, @"saved": @(saved)}); };
    [presenter presentViewController:editor animated:YES completion:nil];
    return;
  }
  result(FlutterMethodNotImplemented);
}

@end
