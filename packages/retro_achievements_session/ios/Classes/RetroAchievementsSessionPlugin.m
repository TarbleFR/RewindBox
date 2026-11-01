#import "Public/RetroAchievementsSessionPlugin.h"
#import "Public/RBRASession.h"
#import "RBRALegacyMigration.h"
#import <Security/Security.h>

static NSString *RBRAString(id value) {
  return [value isKindOfClass:NSString.class] ? [value copy] : @"";
}

static BOOL RBRABool(id value) {
  return [value isKindOfClass:NSNumber.class] && [value boolValue];
}

static NSDictionary *RBRADisabled(void) {
  return @{@"sessionId": @"", @"enabled": @NO, @"supported": @NO,
           @"hardcore": @NO, @"notifications": @NO, @"username": @"", @"token": @"", @"generation": @0};
}

static NSMutableDictionary *RBRAKeychainQuery(NSString *suffix) {
  NSString *bundle = NSBundle.mainBundle.bundleIdentifier ?: @"com.neogamelab.neostation";
  return [@{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
            (__bridge id)kSecAttrService: [bundle stringByAppendingString:suffix],
            (__bridge id)kSecAttrAccount: @"emulator-player"} mutableCopy];
}

static NSDictionary *RBRAReadCredentials(NSString *suffix, OSStatus *status) {
  NSMutableDictionary *query = RBRAKeychainQuery(suffix);
  query[(__bridge id)kSecReturnData] = @YES;
  query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
  CFTypeRef value = NULL;
  OSStatus result = SecItemCopyMatching((__bridge CFDictionaryRef)query, &value);
  if (status) *status = result;
  if (result != errSecSuccess) return nil;
  NSData *data = CFBridgingRelease(value);
  if (![data isKindOfClass:NSData.class]) { if (status) *status = errSecDecode; return nil; }
  id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  if (![decoded isKindOfClass:NSDictionary.class] || !RBRAString(decoded[@"username"]).length || !RBRAString(decoded[@"token"]).length) {
    if (status) *status = errSecDecode;
    return nil;
  }
  NSMutableDictionary *credentials = [@{ @"username": decoded[@"username"], @"token": decoded[@"token"] } mutableCopy];
  NSDictionary *policy = [decoded[@"migrationPolicy"] isKindOfClass:NSDictionary.class] ? decoded[@"migrationPolicy"] : nil;
  if ([policy[@"enabled"] isKindOfClass:NSNumber.class] && [policy[@"hardcore"] isKindOfClass:NSNumber.class]) {
    credentials[@"migrationPolicy"] = @{@"enabled": @(RBRABool(policy[@"enabled"])), @"hardcore": @(RBRABool(policy[@"hardcore"]))};
  }
  return [credentials copy];
}

static OSStatus RBRAWriteCredentials(NSDictionary *credentials) {
  NSData *data = [NSJSONSerialization dataWithJSONObject:credentials options:0 error:nil];
  if (!data) return errSecParam;
  NSMutableDictionary *query = RBRAKeychainQuery(@".retroachievements");
  NSDictionary *update = @{(__bridge id)kSecValueData: data,
      (__bridge id)kSecAttrAccessible: (__bridge id)kSecAttrAccessibleWhenUnlockedThisDeviceOnly};
  OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)update);
  if (status == errSecItemNotFound) {
    [query addEntriesFromDictionary:update];
    status = SecItemAdd((__bridge CFDictionaryRef)query, NULL);
  }
  return status;
}

static FlutterError *RBRAError(NSString *code) {
  // Never include the request, response, password or token in Flutter errors.
  return [FlutterError errorWithCode:code message:code details:nil];
}

// Engine diagnostics crossing the Flutter boundary are codes, never raw
// service responses or arbitrary strings which could contain credentials.
static NSString *RBRAPublicErrorCode(id value) {
  if (![value isKindOfClass:NSString.class]) return @"";
  NSString *code = [value copy];
  static NSSet<NSString *> *allowed;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    allowed = [NSSet setWithArray:@[@"", @"state_unavailable", @"configuration_failed",
      @"hardcore_inactive", @"cleanup_pending", @"RA_UNAVAILABLE", @"RA_UNSUPPORTED",
      @"RA_NETWORK_UNAVAILABLE", @"RA_LOGIN_REQUIRED", @"RA_LOGIN_FAILED",
      @"RA_AUTHENTICATION_FAILED", @"RA_RATE_LIMITED", @"RA_STORAGE_UNAVAILABLE",
      @"RA_CREDENTIALS_MISSING", @"RA_CLIENT_UNAVAILABLE", @"RA_CORE_UNSUPPORTED",
      @"RA_MEMORY_UNAVAILABLE", @"RA_GAME_LOAD_FAILED", @"RA_GAME_NOT_RECOGNIZED",
      @"RA_NO_ACHIEVEMENTS", @"RA_ACHIEVEMENTS_UNSUPPORTED", @"RA_SERVER_ERROR",
      @"RA_SYNC_PENDING", @"RA_HARDCORE_OPTIONS", @"RA_HARDCORE_RESET_REQUIRED",
      @"RA_CANCELLED", @"RA_MIGRATION_EXPIRED", @"RA_SESSION_ERROR"]];
  });
  if ([allowed containsObject:code]) return code;
  // Dolphin preserves its signed integer rcheevos error without response text.
  if (code.length <= 24) {
    NSRange match = [code rangeOfString:@"^login_failed_-?[0-9]{1,10}$" options:NSRegularExpressionSearch];
    if (match.location == 0 && match.length == code.length) return code;
  }
  return @"RA_SESSION_ERROR";
}

@interface RBRANoRedirectDelegate : NSObject <NSURLSessionTaskDelegate>
@end
@implementation RBRANoRedirectDelegate
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
    willPerformHTTPRedirection:(NSHTTPURLResponse *)response newRequest:(NSURLRequest *)request
    completionHandler:(void (^)(NSURLRequest * _Nullable))completionHandler {
  completionHandler(nil);
}
@end

@interface RBRASessionHub : NSObject
@property(nonatomic, strong) NSLock *lock;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSDictionary *> *pending;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSDictionary *> *active;
@property(nonatomic, copy) NSDictionary<NSString *, NSDictionary *> *legacyCandidates;
@property(nonatomic, strong) NSHashTable<FlutterMethodChannel *> *channels;
@property(nonatomic, copy) NSDictionary *lastState;
@property(nonatomic, copy) NSString *currentSessionId;
@property(nonatomic, strong) NSURLSessionDataTask *authTask;
@property(nonatomic) NSUInteger authGeneration;
@property(nonatomic) NSUInteger stateRevision;
+ (instancetype)shared;
- (NSDictionary *)publicState:(NSDictionary *)configuration;
- (void)emit:(NSDictionary *)state;
- (void)handle:(FlutterMethodCall *)call result:(FlutterResult)result;
@end

@implementation RBRASessionHub
+ (instancetype)shared {
  static RBRASessionHub *hub;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    hub = [RBRASessionHub new];
    hub.lock = [NSLock new];
    hub.pending = [NSMutableDictionary dictionary];
    hub.active = [NSMutableDictionary dictionary];
    hub.legacyCandidates = @{};
    hub.channels = [NSHashTable weakObjectsHashTable];
    hub.lastState = @{};
    hub.currentSessionId = @"";
  });
  return hub;
}

- (NSDictionary *)publicState:(NSDictionary *)configuration {
  NSMutableDictionary *state = [NSMutableDictionary dictionary];
  for (NSString *key in @[@"sessionId", @"engine", @"system", @"core", @"generation",
                          @"enabled", @"supported", @"hardcore", @"notifications", @"capability"]) {
    if (configuration[key]) state[key] = configuration[key];
  }
  state[@"active"] = @NO;
  state[@"gameLoaded"] = @NO;
  state[@"hardcoreActive"] = @NO;
  state[@"ended"] = @NO;
  return state;
}

- (void)emit:(NSDictionary *)state {
  // Engine callbacks may arrive on any queue. Channel calls always use main.
  dispatch_async(dispatch_get_main_queue(), ^{
    [self.lock lock];
    BOOL current = [RBRAString(state[@"sessionId"]) isEqualToString:self.currentSessionId] &&
      [state[@"stateRevision"] isEqual:self.lastState[@"stateRevision"]];
    NSArray *channels = self.channels.allObjects;
    [self.lock unlock];
    if (!current) return;
    for (FlutterMethodChannel *channel in channels) [channel invokeMethod:@"sessionChanged" arguments:state];
  });
}

- (void)handle:(FlutterMethodCall *)call result:(FlutterResult)result {
  NSAssert(NSThread.isMainThread, @"Flutter account operations must be serialized on main");
  NSDictionary *args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  if ([call.method isEqualToString:@"inspectLegacy"]) {
    OSStatus status;
    NSDictionary *central = RBRAReadCredentials(@".retroachievements", &status);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    if (central) {
      // An interrupted DB write resumes the same import. Never overwrite a
      // confirmed central account with credentials rediscovered in old files.
      self.legacyCandidates = @{};
      result(@{@"central": @YES, @"authenticated": @YES, @"username": central[@"username"],
               @"policy": central[@"migrationPolicy"] ?: @{}, @"candidates": @[]});
      return;
    }
    NSDictionary *libretro = RBRAReadCredentials(@".libretro.retroachievements", &status);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    NSDictionary *dolphin = RBRAReadCredentials(@".dolphin.retroachievements", &status);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject;
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    if (!support.length || !documents.length) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    NSError *error = nil;
    NSDictionary *dolphinValues = [RBRALegacyMigration achievementValuesAtPath:
      [support stringByAppendingPathComponent:@"NeoStation/Dolphin/User/Config/RetroAchievements.ini"] error:&error];
    if (!dolphinValues) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    NSDictionary *armsx2Values = [RBRALegacyMigration achievementValuesAtPath:
      [documents stringByAppendingPathComponent:@"ARMSX2/inis/PCSX2.ini"] error:&error];
    if (!armsx2Values) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    NSDictionary *armsx2Secrets = [RBRALegacyMigration achievementValuesAtPath:
      [documents stringByAppendingPathComponent:@"ARMSX2/inis/secrets.ini"] error:&error];
    if (!armsx2Secrets) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    NSArray *candidates = [RBRALegacyMigration candidatesWithLibretro:libretro
      libretroEnabled:[NSUserDefaults.standardUserDefaults objectForKey:@"libretro.achievements.enabled"]
      dolphin:dolphin dolphinValues:dolphinValues armsx2Values:armsx2Values armsx2Secrets:armsx2Secrets];
    NSMutableDictionary *privateCandidates = [NSMutableDictionary dictionary];
    NSMutableArray *publicCandidates = [NSMutableArray array];
    for (NSDictionary *candidate in candidates) {
      NSString *identifier = NSUUID.UUID.UUIDString;
      privateCandidates[identifier] = candidate;
      [publicCandidates addObject:@{@"id": identifier, @"username": candidate[@"username"],
        @"sources": candidate[@"sources"], @"enabled": candidate[@"enabled"], @"hardcore": candidate[@"hardcore"]}];
    }
    self.legacyCandidates = [privateCandidates copy];
    result(@{@"central": @NO, @"candidates": publicCandidates});
    return;
  }
  if ([call.method isEqualToString:@"importLegacy"]) {
    NSDictionary *candidate = self.legacyCandidates[RBRAString(args[@"id"])];
    if (!candidate) { result(RBRAError(@"RA_MIGRATION_EXPIRED")); return; }
    OSStatus status;
    NSDictionary *central = RBRAReadCredentials(@".retroachievements", &status);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    if (central && [central[@"username"] caseInsensitiveCompare:candidate[@"username"]] != NSOrderedSame) {
      result(RBRAError(@"RA_MIGRATION_EXPIRED")); return;
    }
    if (!central) {
      central = @{@"username": candidate[@"username"], @"token": candidate[@"token"],
        @"migrationPolicy": @{@"enabled": candidate[@"enabled"], @"hardcore": candidate[@"hardcore"]}};
      if (RBRAWriteCredentials(central) != errSecSuccess) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    }
    result(@{@"authenticated": @YES, @"username": central[@"username"], @"policy": central[@"migrationPolicy"] ?: @{}});
    return;
  }
  if ([call.method isEqualToString:@"completeLegacy"]) {
    // Dart calls only after the existing SQLite preference transaction commits.
    // The legacy files/Keychain items remain intact but are never consulted again.
    self.legacyCandidates = @{};
    result(@{}); return;
  }
  if ([call.method isEqualToString:@"account"]) {
    OSStatus status;
    NSDictionary *credentials = RBRAReadCredentials(@".retroachievements", &status);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    [self.lock lock]; NSDictionary *state = self.lastState; [self.lock unlock];
    result(@{@"available": @YES, @"authenticated": @(credentials != nil),
             @"username": credentials[@"username"] ?: @"", @"session": state});
    return;
  }
  if ([call.method isEqualToString:@"login"]) {
    NSString *username = [RBRAString(args[@"username"]) stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSString *password = RBRAString(args[@"password"]);
    if (!username.length || !password.length) { result(RBRAError(@"RA_LOGIN_REQUIRED")); return; }
    self.legacyCandidates = @{};
    [self.authTask cancel];
    NSUInteger generation = ++self.authGeneration;
    NSMutableCharacterSet *allowed = [NSCharacterSet.alphanumericCharacterSet mutableCopy];
    [allowed addCharactersInString:@"-._~"];
    NSString *body = [NSString stringWithFormat:@"r=login2&u=%@&p=%@",
      [username stringByAddingPercentEncodingWithAllowedCharacters:allowed],
      [password stringByAddingPercentEncodingWithAllowedCharacters:allowed]];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:@"https://retroachievements.org/dorequest.php"]];
    request.HTTPMethod = @"POST";
    request.HTTPBody = [body dataUsingEncoding:NSUTF8StringEncoding];
    request.timeoutInterval = 25;
    [request setValue:@"application/x-www-form-urlencoded" forHTTPHeaderField:@"Content-Type"];
    [request setValue:@"RewindBox/0.0.8 (iOS; central account)" forHTTPHeaderField:@"User-Agent"];
    NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    configuration.HTTPCookieStorage = nil;
    configuration.URLCache = nil;
    NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration delegate:[RBRANoRedirectDelegate new] delegateQueue:nil];
    self.authTask = [session dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
      [session finishTasksAndInvalidate];
      dispatch_async(dispatch_get_main_queue(), ^{
        if (generation != self.authGeneration) { result(RBRAError(@"RA_CANCELLED")); return; }
        self.authTask = nil;
        NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class] ? ((NSHTTPURLResponse *)response).statusCode : 0;
        if (error || status == 0 || status >= 500) { result(RBRAError(@"RA_NETWORK_UNAVAILABLE")); return; }
        if (status == 429) { result(RBRAError(@"RA_RATE_LIMITED")); return; }
        id payload = data.length <= 1024 * 1024 ? [NSJSONSerialization JSONObjectWithData:data ?: NSData.data options:0 error:nil] : nil;
        if (status != 200 || ![payload isKindOfClass:NSDictionary.class] ||
            ![payload[@"Success"] isKindOfClass:NSNumber.class] || ![payload[@"Success"] boolValue] ||
            !RBRAString(payload[@"User"]).length || !RBRAString(payload[@"Token"]).length) {
          result(RBRAError(@"RA_AUTHENTICATION_FAILED")); return;
        }
        NSDictionary *credentials = @{@"username": payload[@"User"], @"token": payload[@"Token"]};
        if (RBRAWriteCredentials(credentials) != errSecSuccess) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
        result(@{@"authenticated": @YES, @"username": credentials[@"username"]});
      });
    }];
    [self.authTask resume];
    return;
  }
  if ([call.method isEqualToString:@"logout"]) {
    self.authGeneration++;
    [self.authTask cancel]; self.authTask = nil;
    OSStatus status = SecItemDelete((__bridge CFDictionaryRef)RBRAKeychainQuery(@".retroachievements"));
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    // Active snapshots retain their own credentials until their game ends.
    self.legacyCandidates = @{};
    [self.lock lock]; [self.pending removeAllObjects]; [self.lock unlock];
    result(@{@"authenticated": @NO, @"username": @""});
    return;
  }
  if ([call.method isEqualToString:@"prepareSession"]) {
    NSString *engine = RBRAString(args[@"engine"]);
    if (![@[@"dolphin", @"armsx2", @"libretro", @"rpcs3", @"melonx"] containsObject:engine]) {
      result(RBRAError(@"RA_UNSUPPORTED")); return;
    }
    OSStatus status;
    NSDictionary *credentials = RBRAReadCredentials(@".retroachievements", &status);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    BOOL supported = RBRABool(args[@"supported"]) && ![@[@"rpcs3", @"melonx"] containsObject:engine];
    BOOL enabled = RBRABool(args[@"enabled"]) && supported && credentials != nil;
    NSString *identifier = NSUUID.UUID.UUIDString;
    NSDictionary *snapshot = @{@"sessionId": identifier, @"engine": engine,
      @"system": RBRAString(args[@"system"]), @"core": RBRAString(args[@"core"]),
      @"language": RBRAString(args[@"language"]),
      @"capability": RBRAString(args[@"capability"]),
      @"enabled": @(enabled), @"supported": @(supported),
      @"hardcore": @(enabled && RBRABool(args[@"hardcore"])), @"notifications": @(enabled),
      @"username": enabled ? credentials[@"username"] : @"", @"token": enabled ? credentials[@"token"] : @"",
      @"generation": [args[@"generation"] isKindOfClass:NSNumber.class] ? args[@"generation"] : @0,
      @"expires": [NSDate dateWithTimeIntervalSinceNow:600]};
    [self.lock lock];
    for (NSString *key in self.pending.allKeys) {
      if ([self.pending[key][@"expires"] timeIntervalSinceNow] <= 0) [self.pending removeObjectForKey:key];
    }
    if (self.pending.count >= 8) [self.pending removeAllObjects];
    self.pending[identifier] = snapshot;
    [self.lock unlock];
    result(@{@"raSessionId": identifier, @"enabled": @(enabled), @"supported": @(supported),
      @"hardcore": snapshot[@"hardcore"], @"capability": snapshot[@"capability"]});
    return;
  }
  if ([call.method isEqualToString:@"finishSession"]) {
    NSString *identifier = RBRAString(args[@"sessionId"]);
    [self.lock lock];
    NSDictionary *snapshot = self.active[identifier];
    [self.pending removeObjectForKey:identifier];
    [self.lock unlock];
    if (snapshot) RBRAEndSession(snapshot);
    result(@{}); return;
  }
  result(FlutterMethodNotImplemented);
}
@end

NSDictionary *RBRATakeLaunchConfiguration(NSDictionary *arguments, NSString *engine) {
  if (![arguments isKindOfClass:NSDictionary.class]) return RBRADisabled();
  NSString *identifier = RBRAString(arguments[@"raSessionId"]);
  if (!identifier.length) return RBRADisabled();
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock];
  NSDictionary *snapshot = hub.pending[identifier];
  if (snapshot && [snapshot[@"expires"] timeIntervalSinceNow] <= 0) {
    [hub.pending removeObjectForKey:identifier];
    [hub.lock unlock]; return RBRADisabled();
  }
  if (!snapshot || ![snapshot[@"engine"] isEqualToString:engine]) {
    [hub.lock unlock]; return RBRADisabled();
  }
  [hub.pending removeObjectForKey:identifier];
  NSMutableDictionary *owned = [snapshot mutableCopy];
  [owned removeObjectForKey:@"expires"];
  snapshot = [owned copy];
  hub.active[identifier] = snapshot;
  hub.currentSessionId = identifier;
  NSMutableDictionary *initialState = [[hub publicState:snapshot] mutableCopy];
  initialState[@"stateRevision"] = @(++hub.stateRevision);
  NSDictionary *state = [initialState copy];
  hub.lastState = state;
  [hub.lock unlock];
  [hub emit:state];
  return snapshot;
}

void RBRAPublishSessionState(NSDictionary *configuration, NSDictionary *state) {
  if (![configuration isKindOfClass:NSDictionary.class] || ![state isKindOfClass:NSDictionary.class]) return;
  NSString *identifier = RBRAString(configuration[@"sessionId"]);
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock];
  NSDictionary *snapshot = hub.active[identifier];
  if (snapshot != configuration || ![identifier isEqualToString:hub.currentSessionId]) {
    [hub.lock unlock]; return;
  }
  NSMutableDictionary *next = [hub.lastState mutableCopy];
  for (NSString *key in @[@"active", @"gameLoaded", @"hardcoreActive", @"gameId", @"totalCount", @"unlockedCount"]) {
    if ([state[key] isKindOfClass:NSNumber.class]) next[key] = state[key];
  }
  if ([state[@"errorCode"] isKindOfClass:NSString.class]) next[@"errorCode"] = RBRAPublicErrorCode(state[@"errorCode"]);
  // An engine cannot announce active RA for an unsupported/disabled snapshot.
  if (![snapshot[@"enabled"] boolValue] || ![next[@"gameLoaded"] boolValue]) {
    next[@"active"] = @NO; next[@"hardcoreActive"] = @NO;
  }
  if (![snapshot[@"hardcore"] boolValue] || ![next[@"active"] boolValue]) next[@"hardcoreActive"] = @NO;
  next[@"stateRevision"] = @(++hub.stateRevision);
  hub.lastState = [next copy];
  NSDictionary *published = hub.lastState;
  [hub.lock unlock];
  [hub emit:published];
}

void RBRAEndSession(NSDictionary *configuration) {
  if (![configuration isKindOfClass:NSDictionary.class]) return;
  NSString *identifier = RBRAString(configuration[@"sessionId"]);
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock];
  // Public session IDs are metadata. Only the exact launch snapshot owns its
  // native session; an already-ended snapshot cannot emit another end event.
  if (hub.active[identifier] != configuration) { [hub.lock unlock]; return; }
  [hub.active removeObjectForKey:identifier];
  BOOL current = identifier.length && [identifier isEqualToString:hub.currentSessionId];
  NSDictionary *state = nil;
  if (current) {
    NSMutableDictionary *ended = [hub.lastState mutableCopy];
    ended[@"ended"] = @YES; ended[@"active"] = @NO; ended[@"hardcoreActive"] = @NO;
    ended[@"stateRevision"] = @(++hub.stateRevision);
    hub.lastState = [ended copy]; state = hub.lastState;
  }
  [hub.lock unlock];
  if (state) [hub emit:state];
}

@interface RetroAchievementsSessionPlugin ()
@property(nonatomic, strong) FlutterMethodChannel *channel;
@end
@implementation RetroAchievementsSessionPlugin
+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  RetroAchievementsSessionPlugin *plugin = [RetroAchievementsSessionPlugin new];
  plugin.channel = [FlutterMethodChannel methodChannelWithName:@"rewindbox/retro_achievements_session" binaryMessenger:registrar.messenger];
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock]; [hub.channels addObject:plugin.channel]; [hub.lock unlock];
  [registrar addMethodCallDelegate:plugin channel:plugin.channel];
}
- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  [RBRASessionHub.shared handle:call result:result];
}
@end
