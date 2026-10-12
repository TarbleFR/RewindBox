#import "UiRefreshRatePlugin.h"

#import <UIKit/UIKit.h>

#import "UiRefreshRateEngineHook.h"

static NSString *const kUiRefreshRateChannel = @"neostation/ui_refresh_rate";

@interface UiRefreshRatePlugin ()
@property(nonatomic, weak, nullable) NSObject<FlutterPluginRegistrar> *registrar;
@end

@implementation UiRefreshRatePlugin

+ (void)load {
  // Runs before main(): the Flutter view's Metal layer, the vsync waiter and
  // the touch-rate link read the rate while the first view is built, before
  // any plugin is registered. GeneratedPluginRegistrant references this class,
  // so its object file is always linked into the Runner executable.
  NeoUiRefreshInstallEngineHook();
}

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  FlutterMethodChannel *channel =
      [FlutterMethodChannel methodChannelWithName:kUiRefreshRateChannel
                                  binaryMessenger:[registrar messenger]];
  UiRefreshRatePlugin *instance = [[UiRefreshRatePlugin alloc] init];
  instance.registrar = registrar;
  [registrar addMethodCallDelegate:instance channel:channel];
}

/// The screen showing NeoStation; read directly, never through the hook.
- (UIScreen *)currentScreen {
  UIViewController *controller = self.registrar.viewController;
  UIWindowScene *scene = controller.viewIfLoaded.window.windowScene;
  if (scene != nil) return scene.screen;
  // Only the iPhone's own scene: an external display scene (external_display
  // plugin) reports the TV's rate, not the interface's.
  for (UIScene *connected in UIApplication.sharedApplication.connectedScenes) {
    if ([connected isKindOfClass:UIWindowScene.class] &&
        [connected.session.role isEqualToString:UIWindowSceneSessionRoleApplication]) {
      return ((UIWindowScene *)connected).screen;
    }
  }
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
  return UIScreen.mainScreen;
#pragma clang diagnostic pop
}

- (NSDictionary<NSString *, id> *)currentState {
  NSProcessInfo *process = NSProcessInfo.processInfo;
  return @{
    @"hookStatus" : NeoUiRefreshHookStatusName(NeoUiRefreshCurrentHookStatus()),
    @"storedEnabled" : @(NeoUiRefreshStoredEnabled()),
    @"activeEnabled" : @(NeoUiRefreshActiveEnabled()),
    @"screenMaxHz" : @([self currentScreen].maximumFramesPerSecond),
    @"engineTargetHz" : @(NeoUiRefreshEngineTargetHz()),
    @"cappedHz" : @(NeoUiRefreshCappedHz),
    @"lowPowerMode" : @(process.lowPowerModeEnabled),
    @"thermalState" : @((NSInteger)process.thermalState),
  };
}

- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  if ([call.method isEqualToString:@"getState"]) {
    result([self currentState]);
    return;
  }
  if ([call.method isEqualToString:@"setEnabled"]) {
    NSDictionary *arguments = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : nil;
    id enabled = arguments[@"enabled"];
    if (![enabled isKindOfClass:NSNumber.class]) {
      result([FlutterError errorWithCode:@"BAD_ARGS"
                                 message:@"setEnabled expects {enabled: bool}"
                                 details:nil]);
      return;
    }
    // Stored only: the running engine keeps the rate it started with until
    // NeoStation is opened again.
    if (!NeoUiRefreshStoreEnabled([enabled boolValue])) {
      result([FlutterError errorWithCode:@"SAVE_FAILED"
                                 message:@"NSUserDefaults did not keep the 120 Hz interface preference"
                                 details:NeoUiRefreshPreferenceKey]);
      return;
    }
    result([self currentState]);
    return;
  }
  result(FlutterMethodNotImplemented);
}

@end
