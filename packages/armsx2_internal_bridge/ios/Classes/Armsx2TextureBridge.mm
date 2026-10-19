// SPDX-License-Identifier: GPL-3.0-or-later
// HD texture packs of the embedded ARMSX2 engine (Build 485). See the header.
#import "Armsx2TextureBridge.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

#include <string>

static NSString* TextValue(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }

static UIViewController* TextureRootViewController(void) {
  UIWindow* keyWindow = nil;
  for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class] ||
        scene.activationState != UISceneActivationStateForegroundActive) continue;
    for (UIWindow* window in ((UIWindowScene*)scene).windows)
      if (window.isKeyWindow) { keyWindow = window; break; }
    if (keyWindow) break;
  }
  UIViewController* controller = keyWindow.rootViewController;
  while (controller.presentedViewController) controller = controller.presentedViewController;
  return controller;
}

static NSArray<UTType*>* ArchiveTypes(BOOL withZstd) {
  NSMutableArray<UTType*>* types = [@[UTTypeZIP, UTTypeArchive] mutableCopy];
  for (NSString* extension in withZstd ? @[@"tar", @"zst", @"tzst"] : @[@"tar"]) {
    UTType* type = [UTType typeWithFilenameExtension:extension];
    if (type) [types addObject:type];
  }
  return types;
}

// Engine state of the running game (ABI 8), or nil.
static NSDictionary* EngineState(const NeoARMSX2API* api) {
  if (!api || !api->get_texture_replacements_json) return nil;
  char json[4096] = {};
  if (!api->get_texture_replacements_json(json, sizeof(json))) return nil;
  id decoded = [NSJSONSerialization JSONObjectWithData:[NSData dataWithBytes:json length:strlen(json)] options:0 error:nil];
  return [decoded isKindOfClass:NSDictionary.class] ? decoded : nil;
}

@interface Armsx2TexturePicker : NSObject <UIDocumentPickerDelegate>
@property(nonatomic, copy) void (^completion)(NSURL* _Nullable url);
@property(nonatomic, strong) Armsx2TexturePicker* retainedSelf;
@end

@implementation Armsx2TexturePicker
- (void)documentPicker:(UIDocumentPickerViewController*)controller didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
  void (^completion)(NSURL*) = self.completion;
  self.completion = nil;
  self.retainedSelf = nil;
  if (completion) completion(urls.firstObject);
}
- (void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller {
  void (^completion)(NSURL*) = self.completion;
  self.completion = nil;
  self.retainedSelf = nil;
  if (completion) completion(nil);
}
@end

@interface Armsx2TextureBridge ()
@property(nonatomic, strong) FlutterMethodChannel* channel;
@property(nonatomic, copy) BOOL (^sessionActive)(void);
@property(nonatomic, strong) NSMutableDictionary<NSString*, ARMSX2TextureImport*>* imports;
@property(nonatomic, assign) BOOL swept;
@end

@interface Armsx2TextureSessionHost : NSObject <ARMSX2TextureHost>
@property(nonatomic, weak) Armsx2TextureBridge* bridge;
@property(nonatomic, assign) const NeoARMSX2API* api;
@property(nonatomic, copy) NSString* gamePath;
@property(nonatomic, copy) NSString* dataPath;
@property(nonatomic, copy) BOOL (^alive)(void);
@property(atomic, strong) ARMSX2TextureImport* inspecting;
@end

@implementation Armsx2TextureBridge {
  dispatch_queue_t _queue;
}

- (instancetype)initWithChannel:(FlutterMethodChannel*)channel sessionActive:(BOOL (^)(void))sessionActive {
  self = [super init];
  if (self) {
    _channel = channel;
    _sessionActive = [sessionActive copy];
    _imports = [NSMutableDictionary dictionary];
    _queue = dispatch_queue_create("com.neogamelab.neostation.armsx2.textures", DISPATCH_QUEUE_SERIAL);
  }
  return self;
}

- (dispatch_queue_t)queue { return _queue; }

- (void)keep:(ARMSX2TextureImport*)import {
  @synchronized(self.imports) { self.imports[import.token] = import; }
}
- (ARMSX2TextureImport*)importFor:(NSString*)token {
  @synchronized(self.imports) { return token.length ? self.imports[token] : nil; }
}
- (void)discard:(NSString*)token {
  ARMSX2TextureImport* import = nil;
  @synchronized(self.imports) {
    import = self.imports[token];
    if (token.length) [self.imports removeObjectForKey:token];
  }
  [import cancel];
  // After any running inspection or installation of this import finishes.
  dispatch_async(_queue, ^{ [import close]; });
}
- (BOOL)importing {
  @synchronized(self.imports) { return self.imports.count > 0; }
}

- (ARMSX2TextureProgress)progressFor:(NSString*)token {
  __block double last = -2;
  __block CFAbsoluteTime when = 0;
  FlutterMethodChannel* channel = self.channel;
  return ^(double fraction, NSString* phase) {
    const CFAbsoluteTime now = CFAbsoluteTimeGetCurrent();
    if (fabs(fraction - last) < 0.01 && now - when < 0.25) return;
    last = fraction; when = now;
    dispatch_async(dispatch_get_main_queue(), ^{
      [channel invokeMethod:@"textureProgress" arguments:@{@"token": token, @"fraction": @(fraction), @"phase": phase ?: @""}];
    });
  };
}

- (NSString*)bootPreferencesJSONForDataPath:(NSString*)dataPath {
  return [ARMSX2TexturePackStore bootPreferencesJSONForDataPath:dataPath];
}

- (void)recordBootForAPI:(const NeoARMSX2API*)api gamePath:(NSString*)gamePath dataPath:(NSString*)dataPath {
  dispatch_async(_queue, ^{
    NSDictionary* engine = EngineState(api);
    if ([engine[@"available"] boolValue])
      [ARMSX2TexturePackStore recordIdentity:engine forGamePath:gamePath dataPath:dataPath];
  });
}

- (id<ARMSX2TextureHost>)sessionHostForAPI:(const NeoARMSX2API*)api gamePath:(NSString*)gamePath
                                  dataPath:(NSString*)dataPath alive:(BOOL (^)(void))alive {
  Armsx2TextureSessionHost* host = [Armsx2TextureSessionHost new];
  host.bridge = self;
  host.api = api;
  host.gamePath = gamePath;
  host.dataPath = dataPath;
  host.alive = alive;
  return host;
}

static void Reply(FlutterResult result, id value) {
  dispatch_async(dispatch_get_main_queue(), ^{ result(value); });
}

- (BOOL)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {
  static NSSet* methods = [NSSet setWithArray:@[@"textureStatus", @"texturePick", @"textureInstall", @"textureCancel",
                                                @"textureDiscard", @"textureSetEnabled", @"textureRemove"]];
  if (![methods containsObject:call.method]) return NO;
  NSDictionary* args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  NSString* gamePath = TextValue(args[@"gamePath"]);
  NSString* dataPath = TextValue(args[@"dataPath"]);
  NSString* token = TextValue(args[@"token"]);
  NSString* method = call.method;

  if ([method isEqual:@"textureCancel"]) { [[self importFor:token] cancel]; result(@{@"success": @YES}); return YES; }
  if ([method isEqual:@"textureDiscard"]) { [self discard:token]; result(@{@"success": @YES}); return YES; }

  if ([method isEqual:@"textureInstall"]) {
    ARMSX2TextureImport* import = [self importFor:token];
    if (!import) { result(@{@"success": @NO, @"error": @"failed"}); return YES; }
    if (self.sessionActive()) { result(@{@"success": @NO, @"error": @"sessionActive"}); return YES; }
    const BOOL allow = [args[@"allowMismatch"] boolValue];
    ARMSX2TextureProgress progress = [self progressFor:token];
    dispatch_async(_queue, ^{
      NSMutableDictionary* outcome = [[import installAllowingMismatch:allow progress:progress] mutableCopy];
      [ARMSX2TexturePackStore discardPath:outcome[@"previousPath"]];  // no engine holds it in the library
      outcome[@"live"] = @NO;
      // The channel's install call names only the token: the import knows its data folder.
      NSDictionary* status = [ARMSX2TexturePackStore statusForSerial:import.serial crc:nil dataPath:import.dataPath];
      id enabled = status[@"enabled"];
      outcome[@"enabled"] = [enabled isKindOfClass:NSNumber.class] ? enabled : @NO;
      Reply(result, outcome);
    });
    return YES;
  }

  if (![gamePath hasPrefix:@"/"] || ![dataPath hasPrefix:@"/"]) {
    result(@{@"success": @NO, @"error": @"failed"});
    return YES;
  }
  if (![method isEqual:@"textureStatus"] && self.sessionActive()) {
    result(@{@"success": @NO, @"error": @"sessionActive"});
    return YES;
  }

  if ([method isEqual:@"textureStatus"]) {
    const BOOL active = self.sessionActive();
    dispatch_async(_queue, ^{
      // Leftovers of an interrupted import, never while one runs or a game plays.
      if (!self.swept && !active && !self.importing) {
        [ARMSX2TexturePackStore sweepLeftoversInDataPath:dataPath];
        self.swept = YES;
      }
      NSDictionary* game = [ARMSX2TexturePackStore identifyGameAtPath:gamePath dataPath:dataPath];
      NSDictionary* pack = [ARMSX2TexturePackStore statusForSerial:game[@"serial"] crc:game[@"crc"] dataPath:dataPath];
      Reply(result, @{@"success": @YES, @"game": game, @"pack": pack, @"formats": [ARMSX2TexturePackStore deviceFormats],
                      @"sessionActive": @(active)});
    });
    return YES;
  }

  if ([method isEqual:@"textureSetEnabled"] || [method isEqual:@"textureRemove"]) {
    const BOOL enabled = [args[@"enabled"] boolValue];
    dispatch_async(_queue, ^{
      NSString* serial = [ARMSX2TexturePackStore identifyGameAtPath:gamePath dataPath:dataPath][@"serial"];
      if (!TextValue(serial).length) { Reply(result, @{@"success": @NO, @"error": @"gameUnknown"}); return; }
      if ([method isEqual:@"textureRemove"]) {
        NSDictionary* removal = [ARMSX2TexturePackStore removeSerial:serial dataPath:dataPath];
        [ARMSX2TexturePackStore discardPath:removal[@"removingPath"]];
        Reply(result, @{@"success": removal[@"success"] ?: @NO, @"error": removal[@"error"] ?: @"", @"serial": serial});
        return;
      }
      const BOOL saved = [ARMSX2TexturePackStore setEnabled:enabled serial:serial dataPath:dataPath];
      Reply(result, saved ? @{@"success": @YES, @"message": enabled ? @"enabledNext" : @"disabledNext"}
                          : @{@"success": @NO, @"error": @"write"});
    });
    return YES;
  }

  // texturePick: Files, then the inspection of the chosen pack.
  const BOOL folder = [TextValue(args[@"kind"]) isEqual:@"folder"];
  dispatch_async(dispatch_get_main_queue(), ^{
    UIViewController* root = TextureRootViewController();
    if (!root) { result(@{@"success": @NO, @"error": @"failed"}); return; }
    Armsx2TexturePicker* delegate = [Armsx2TexturePicker new];
    delegate.retainedSelf = delegate;
    __weak Armsx2TextureBridge* weakSelf = self;
    delegate.completion = ^(NSURL* url) {
      Armsx2TextureBridge* bridge = weakSelf;
      if (!url || !bridge) { result(@{@"success": @NO, @"cancelled": @YES}); return; }
      if (bridge.sessionActive()) { result(@{@"success": @NO, @"error": @"sessionActive"}); return; }
      dispatch_async(bridge->_queue, ^{
        NSDictionary* game = [ARMSX2TexturePackStore identifyGameAtPath:gamePath dataPath:dataPath];
        ARMSX2TextureImport* import = [[ARMSX2TextureImport alloc] initWithURL:url dataPath:dataPath game:game expander:nil];
        [bridge keep:import];
        NSMutableDictionary* inspection = [[import inspectWithProgress:[bridge progressFor:import.token]] mutableCopy];
        inspection[@"token"] = import.token;
        if (![inspection[@"success"] boolValue]) [bridge discard:import.token];
        Reply(result, inspection);
      });
    };
    UIDocumentPickerViewController* picker = [[UIDocumentPickerViewController alloc]
        initForOpeningContentTypes:folder ? @[UTTypeFolder] : ArchiveTypes(NO) asCopy:NO];
    picker.delegate = delegate;
    picker.allowsMultipleSelection = NO;
    [root presentViewController:picker animated:YES completion:nil];
  });
  return YES;
}

@end

@implementation Armsx2TextureSessionHost

- (BOOL)textureLive { return YES; }

- (dispatch_queue_t)queue { return [self.bridge queue]; }

static void Main(dispatch_block_t block) { dispatch_async(dispatch_get_main_queue(), block); }

// What the engine read for the running disc, as the store's identity.
- (NSDictionary*)gameFrom:(NSDictionary*)engine {
  if ([engine[@"available"] boolValue] && TextValue(engine[@"serial"]).length) {
    NSString* serial = engine[@"serial"];
    NSDictionary* identified = [ARMSX2TexturePackStore identifyGameAtPath:self.gamePath dataPath:self.dataPath];
    return @{@"serial": serial, @"crc": TextValue(engine[@"crc"]), @"version": TextValue(engine[@"version"]),
             @"title": TextValue(engine[@"title"]), @"source": @"session",
             @"region": [identified[@"serial"] isEqual:serial] ? identified[@"region"] : @""};
  }
  return [ARMSX2TexturePackStore identifyGameAtPath:self.gamePath dataPath:self.dataPath];
}

- (void)textureReadState:(void (^)(NSDictionary*))completion {
  if (!self.bridge) { completion(nil); return; }
  dispatch_async(self.queue, ^{
    if (!self.alive()) { Main(^{ completion(nil); }); return; }
    NSDictionary* engine = EngineState(self.api);
    NSDictionary* game = [self gameFrom:engine];
    NSDictionary* pack = [ARMSX2TexturePackStore statusForSerial:game[@"serial"] crc:game[@"crc"] dataPath:self.dataPath];
    NSMutableDictionary* state = [@{@"game": game, @"pack": pack, @"formats": [ARMSX2TexturePackStore deviceFormats]} mutableCopy];
    if (engine) state[@"engine"] = engine;
    Main(^{ completion(state); });
  });
}

- (void)textureInspectURL:(NSURL*)url progress:(ARMSX2TextureProgress)progress completion:(void (^)(NSDictionary*))completion {
  Armsx2TextureBridge* bridge = self.bridge;
  if (!bridge) { completion(@{@"success": @NO, @"error": @"failed"}); return; }
  dispatch_async(self.queue, ^{
    if (!self.alive()) { Main(^{ completion(@{@"success": @NO, @"error": @"failed"}); }); return; }
    NSDictionary* game = [self gameFrom:EngineState(self.api)];
    const NeoARMSX2API* api = self.api;
    BOOL (^alive)(void) = self.alive;
    // .tar.zst packs: the engine's own decoder, only while this game runs.
    ARMSX2TextureExpander expander = ^NSString*(NSString* archive, NSString* destination, uint64_t available,
                                                const volatile int* cancel, volatile uint64_t* consumed) {
      if (!alive()) return @"failed";
      char error[128] = {};
      if (api->expand_texture_archive(archive.fileSystemRepresentation, destination.fileSystemRepresentation,
                                      available, cancel, consumed, error, sizeof(error)))
        return nil;
      return error[0] ? [NSString stringWithUTF8String:error] : @"invalid";
    };
    ARMSX2TextureImport* import = [[ARMSX2TextureImport alloc] initWithURL:url dataPath:self.dataPath game:game expander:expander];
    [bridge keep:import];
    self.inspecting = import;
    NSDictionary* inspection = [import inspectWithProgress:^(double fraction, NSString* phase) {
      Main(^{ progress(fraction, phase); });
    }];
    self.inspecting = nil;
    if (![inspection[@"success"] boolValue]) [bridge discard:import.token];
    NSMutableDictionary* answer = [inspection mutableCopy];
    answer[@"token"] = import.token;
    Main(^{ completion(answer); });
  });
}

- (void)textureInstall:(NSString*)token allowMismatch:(BOOL)allow progress:(ARMSX2TextureProgress)progress
            completion:(void (^)(NSDictionary*))completion {
  ARMSX2TextureImport* import = [self.bridge importFor:token];
  if (!import) { completion(@{@"success": @NO, @"error": @"failed"}); return; }
  dispatch_async(self.queue, ^{
    if (!self.alive()) { Main(^{ completion(@{@"success": @NO, @"error": @"failed"}); }); return; }
    NSMutableDictionary* outcome = [[import installAllowingMismatch:allow progress:^(double fraction, NSString* phase) {
      Main(^{ progress(fraction, phase); });
    }] mutableCopy];
    if ([outcome[@"success"] boolValue] && self.alive()) {
      NSDictionary* engine = EngineState(self.api);
      const BOOL running = [TextValue(engine[@"serial"]) isEqual:import.serial];
      id choice = [ARMSX2TexturePackStore statusForSerial:import.serial crc:nil dataPath:self.dataPath][@"enabled"];
      char error[128] = {};
      if (running && [choice isKindOfClass:NSNumber.class] && [choice boolValue] && ![engine[@"effective"] boolValue])
        self.api->set_texture_replacements(1, error, sizeof(error));  // a first pack turns the game's textures on
      else if (running)
        self.api->reload_texture_replacements(error, sizeof(error));  // the engine re-reads the new files
      NSDictionary* after = EngineState(self.api);
      outcome[@"enabled"] = @([after[@"effective"] boolValue]);
      outcome[@"live"] = @(running);
    }
    // The previous files go only once the engine re-indexed the new ones.
    [ARMSX2TexturePackStore discardPath:outcome[@"previousPath"]];
    Main(^{ completion(outcome); });
  });
}

- (void)textureCancel:(NSString*)token { [[self.bridge importFor:token] cancel]; }
- (void)textureCancelInspection { [self.inspecting cancel]; }
- (void)textureDiscard:(NSString*)token { [self.bridge discard:token]; }

- (void)textureSetEnabled:(BOOL)enabled completion:(void (^)(NSDictionary*))completion {
  dispatch_async(self.queue, ^{
    if (!self.alive()) { Main(^{ completion(@{@"success": @NO, @"error": @"failed"}); }); return; }
    char error[128] = {};
    const BOOL applied = self.api->set_texture_replacements(enabled ? 1 : 0, error, sizeof(error)) != 0;
    NSDictionary* engine = EngineState(self.api);
    if (applied) [ARMSX2TexturePackStore setEnabled:enabled serial:TextValue(engine[@"serial"]) dataPath:self.dataPath];
    NSDictionary* answer = applied ? @{@"success": @YES, @"message": enabled ? @"enabledLive" : @"disabledLive"}
                                   : @{@"success": @NO, @"error": error[0] ? [NSString stringWithUTF8String:error] : @"failed"};
    Main(^{ completion(answer); });
  });
}

- (void)textureRemove:(void (^)(NSDictionary*))completion {
  dispatch_async(self.queue, ^{
    if (!self.alive()) { Main(^{ completion(@{@"success": @NO, @"error": @"failed"}); }); return; }
    NSDictionary* engine = EngineState(self.api);
    NSString* serial = [self gameFrom:engine][@"serial"];
    NSDictionary* removal = [ARMSX2TexturePackStore removeSerial:serial dataPath:self.dataPath];
    if ([removal[@"success"] boolValue] && [TextValue(engine[@"serial"]) isEqual:serial]) {
      char error[128] = {};
      // The pack is gone: the game's switch goes off with it, and the engine
      // forgets the moved files before they are deleted.
      if ([engine[@"effective"] boolValue]) self.api->set_texture_replacements(0, error, sizeof(error));
      self.api->reload_texture_replacements(error, sizeof(error));
    }
    [ARMSX2TexturePackStore discardPath:removal[@"removingPath"]];
    Main(^{ completion(removal); });
  });
}

@end
