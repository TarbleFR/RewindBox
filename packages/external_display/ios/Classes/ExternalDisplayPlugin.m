// SPDX-License-Identifier: GPL-3.0-or-later
#import "ExternalDisplayPlugin.h"

#import <UIKit/UIKit.h>

#import "NeoExternalDisplayCoordinator.h"
#import "NeoExternalDisplayMenuEngine.h"
#import "NeoExternalDisplayPreferences.h"

static NSString *const kNeoExternalDisplayChannel = @"neostation/external_display";
static NSString *const kNeoExternalDisplayEventsChannel = @"neostation/external_display/events";

/// Relays NeoStation.ExternalDisplayStateChanged to the Dart event stream.
@interface NeoExternalDisplayStateStream : NSObject <FlutterStreamHandler>
@property(nonatomic, copy, nullable) FlutterEventSink sink;
@end

@implementation NeoExternalDisplayStateStream

- (FlutterError *)onListenWithArguments:(id)arguments eventSink:(FlutterEventSink)events {
  self.sink = events;
  // One observation whatever the listen/cancel sequence (hot restart sends
  // two listens in a row): never two events per state change.
  [NSNotificationCenter.defaultCenter removeObserver:self name:NeoExternalDisplayStateChangedNotification object:nil];
  [NSNotificationCenter.defaultCenter addObserver:self
                                         selector:@selector(stateChanged:)
                                             name:NeoExternalDisplayStateChangedNotification
                                           object:nil];
  events([NeoExternalDisplayCoordinator.shared stateDictionary]);
  return nil;
}

- (FlutterError *)onCancelWithArguments:(id)arguments {
  [NSNotificationCenter.defaultCenter removeObserver:self];
  self.sink = nil;
  return nil;
}

- (void)stateChanged:(NSNotification *)notification {
  FlutterEventSink sink = self.sink;
  if (sink == nil) return;
  NSDictionary *state = notification.userInfo ?: [NeoExternalDisplayCoordinator.shared stateDictionary];
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{ sink(state); });
    return;
  }
  sink(state);
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
}

@end

@interface ExternalDisplayPlugin ()
@property(nonatomic, strong) NeoExternalDisplayStateStream *stream;
@end

@implementation ExternalDisplayPlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  FlutterMethodChannel *channel = [FlutterMethodChannel methodChannelWithName:kNeoExternalDisplayChannel
                                                              binaryMessenger:[registrar messenger]];
  ExternalDisplayPlugin *instance = [[ExternalDisplayPlugin alloc] init];
  instance.stream = [[NeoExternalDisplayStateStream alloc] init];
  FlutterEventChannel *events = [FlutterEventChannel eventChannelWithName:kNeoExternalDisplayEventsChannel
                                                          binaryMessenger:[registrar messenger]];
  [events setStreamHandler:instance.stream];
  [registrar addMethodCallDelegate:instance channel:channel];
  NeoExternalDisplayCoordinator *coordinator = NeoExternalDisplayCoordinator.shared;
  coordinator.menuProvider = NeoExternalDisplayMenuEngine.shared;
  // The Flutter view is not on screen yet: read the preferences and register
  // the iOS 27 scene accessory on the presented controller once it is.
  dispatch_async(dispatch_get_main_queue(), ^{ [coordinator refresh]; });
}

- (NSDictionary<NSString *, id> *)currentState {
  return [NeoExternalDisplayCoordinator.shared stateDictionary];
}

static FlutterError *NeoExternalBadArguments(NSString *message) {
  return [FlutterError errorWithCode:@"BAD_ARGS" message:message details:nil];
}

/// An optional string argument: absent or null is nil; any other type is
/// refused (`*refused` set).
static NSString *_Nullable NeoExternalOptionalString(NSDictionary *arguments, NSString *key, BOOL *refused) {
  id value = arguments[key];
  if (value == nil || value == NSNull.null) return nil;
  if (![value isKindOfClass:NSString.class]) {
    *refused = YES;
    return nil;
  }
  return value;
}

static FlutterError *NeoExternalSaveFailed(NSString *key) {
  return [FlutterError errorWithCode:@"SAVE_FAILED"
                             message:@"NSUserDefaults did not keep the external display preference"
                             details:key];
}

- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  NSDictionary *arguments = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  NeoExternalDisplayCoordinator *coordinator = NeoExternalDisplayCoordinator.shared;
  if ([call.method isEqualToString:@"getState"]) {
    result([self currentState]);
    return;
  }
  if ([call.method isEqualToString:@"setEnabled"]) {
    id enabled = arguments[@"enabled"];
    if (![enabled isKindOfClass:NSNumber.class]) {
      result(NeoExternalBadArguments(@"setEnabled expects {enabled: bool}"));
      return;
    }
    // The preference notification re-applies the live window synchronously.
    if (![NeoExternalDisplayPreferences storeEnabled:[enabled boolValue]]) {
      result(NeoExternalSaveFailed(NeoExternalDisplayEnabledKey));
      return;
    }
    result([self currentState]);
    return;
  }
  if ([call.method isEqualToString:@"setMode"]) {
    id mode = arguments[@"mode"];
    if (![mode isKindOfClass:NSNumber.class] || [mode integerValue] < NeoExternalDisplayModeAutomatic ||
        [mode integerValue] > NeoExternalDisplayModeOriginal) {
      result(NeoExternalBadArguments(@"setMode expects {mode: 0..3}"));
      return;
    }
    if (![NeoExternalDisplayPreferences storeMode:(NeoExternalDisplayMode)[mode integerValue]]) {
      result(NeoExternalSaveFailed(NeoExternalDisplayModeKey));
      return;
    }
    result([self currentState]);
    return;
  }
  if ([call.method isEqualToString:@"setMenuOnTV"]) {
    id enabled = arguments[@"enabled"];
    if (![enabled isKindOfClass:NSNumber.class]) {
      result(NeoExternalBadArguments(@"setMenuOnTV expects {enabled: bool}"));
      return;
    }
    if (![NeoExternalDisplayPreferences storeMenuOnTV:[enabled boolValue]]) {
      result(NeoExternalSaveFailed(NeoExternalDisplayMenuOnTVKey));
      return;
    }
    result([self currentState]);
    return;
  }
  if ([call.method isEqualToString:@"configureMenuEngine"]) {
    id entrypoint = arguments[@"entrypoint"];
    id libraryUri = arguments[@"libraryUri"];
    BOOL refused = NO;
    // The language and the theme the TV menu starts with: its engine never
    // reads the database (entrypoint arguments, NeoExternalDisplayMenuEngine).
    NSString *languageCode = NeoExternalOptionalString(arguments, @"languageCode", &refused);
    NSString *themeName = NeoExternalOptionalString(arguments, @"themeName", &refused);
    if (![entrypoint isKindOfClass:NSString.class] || [entrypoint length] == 0 ||
        ![libraryUri isKindOfClass:NSString.class] || [libraryUri length] == 0 || refused) {
      result(NeoExternalBadArguments(
          @"configureMenuEngine expects {entrypoint: String, libraryUri: String, languageCode: String?, themeName: String?}"));
      return;
    }
    [NeoExternalDisplayMenuEngine.shared configureWithEntrypoint:entrypoint
                                                      libraryURI:libraryUri
                                                    languageCode:languageCode
                                                       themeName:themeName];
    // A TV already connected gets its menu now.
    [coordinator refresh];
    result([self currentState]);
    return;
  }
  if ([call.method isEqualToString:@"updateMenuEngine"]) {
    BOOL refused = NO;
    NSString *languageCode = NeoExternalOptionalString(arguments, @"languageCode", &refused);
    NSString *themeName = NeoExternalOptionalString(arguments, @"themeName", &refused);
    if (refused) {
      result(NeoExternalBadArguments(@"updateMenuEngine expects {languageCode: String?, themeName: String?}"));
      return;
    }
    // The app language or theme changed: the copy given to the next TV
    // engine follows, and a running one translates at once.
    [NeoExternalDisplayMenuEngine.shared updateLanguageCode:languageCode themeName:themeName];
    result(@YES);
    return;
  }
  if ([call.method isEqualToString:@"pushMenuState"]) {
    id json = arguments[@"json"];
    if (![json isKindOfClass:NSString.class]) {
      result(NeoExternalBadArguments(@"pushMenuState expects {json: String}"));
      return;
    }
    [NeoExternalDisplayMenuEngine.shared pushMenuState:json];
    result(@YES);
    return;
  }
  // An engine whose bridge cannot call the coordinator
  // (docs/external-display-universal.md § 5): Flutter pairs the suspension
  // around the native session (ExternalDisplayService
  // .runUnsupportedEngineSession). Channel calls arrive on the main thread.
  if ([call.method isEqualToString:@"suspendForUnsupportedEngine"]) {
    [coordinator suspendForUnsupportedEngine];
    result(@YES);
    return;
  }
  if ([call.method isEqualToString:@"resumeAfterUnsupportedEngine"]) {
    [coordinator resumeAfterUnsupportedEngine];
    result(@YES);
    return;
  }
  result(FlutterMethodNotImplemented);
}

@end
