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

static NSDictionary *RBRADecodeCredentials(NSData *data) {
  if (![data isKindOfClass:NSData.class]) return nil;
  id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  if (![decoded isKindOfClass:NSDictionary.class] || !RBRAString(decoded[@"username"]).length || !RBRAString(decoded[@"token"]).length) {
    return nil;
  }
  NSMutableDictionary *credentials = [@{ @"username": decoded[@"username"], @"token": decoded[@"token"] } mutableCopy];
  NSDictionary *policy = [decoded[@"migrationPolicy"] isKindOfClass:NSDictionary.class] ? decoded[@"migrationPolicy"] : nil;
  if ([policy[@"enabled"] isKindOfClass:NSNumber.class] && [policy[@"hardcore"] isKindOfClass:NSNumber.class]) {
    credentials[@"migrationPolicy"] = @{@"enabled": @(RBRABool(policy[@"enabled"])), @"hardcore": @(RBRABool(policy[@"hardcore"]))};
  }
  return [credentials copy];
}

static NSDictionary *RBRAReadCredentials(NSString *suffix, OSStatus *status) {
  NSMutableDictionary *query = RBRAKeychainQuery(suffix);
  query[(__bridge id)kSecReturnData] = @YES;
  query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
  CFTypeRef value = NULL;
  OSStatus result = SecItemCopyMatching((__bridge CFDictionaryRef)query, &value);
  if (status) *status = result;
  if (result != errSecSuccess) return nil;
  NSDictionary *credentials = RBRADecodeCredentials(CFBridgingRelease(value));
  if (!credentials && status) *status = errSecDecode;
  return credentials;
}

// Second copy of the central account (username + Connect token, never the
// password) in the application's private Application Support folder: never
// in Documents (visible in Files), excluded from backups, readable only after
// the first unlock. Some installations do not get their Keychain item back at
// the next launch (2 November 2026 recording: signed in, then "password
// required" after every restart while the Web API key, also in the Keychain,
// survived). RetroArch, Dolphin and PCSX2 keep the same token in their own
// configuration files.
static NSURL *RBRAFallbackURL(void) {
  NSURL *support = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory
                                                       inDomains:NSUserDomainMask].firstObject;
  if (!support) return nil;
  return [[support URLByAppendingPathComponent:@"RetroAchievements" isDirectory:YES]
          URLByAppendingPathComponent:@"central-session.json" isDirectory:NO];
}

static NSDictionary *RBRAReadFallback(void) {
  NSURL *url = RBRAFallbackURL();
  if (!url) return nil;
  NSData *data = [NSData dataWithContentsOfURL:url options:0 error:nil];
  return data ? RBRADecodeCredentials(data) : nil;
}

static BOOL RBRAWriteFallback(NSData *data) {
  NSURL *url = RBRAFallbackURL();
  if (!url || !data) return NO;
  NSFileManager *files = NSFileManager.defaultManager;
  NSURL *folder = url.URLByDeletingLastPathComponent;
  if (![files createDirectoryAtURL:folder withIntermediateDirectories:YES
        attributes:@{NSFilePosixPermissions: @0700} error:nil]) return NO;
  [folder setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
  if (![data writeToURL:url options:NSDataWritingAtomic |
        NSDataWritingFileProtectionCompleteUntilFirstUserAuthentication error:nil]) return NO;
  [files setAttributes:@{NSFilePosixPermissions: @0600} ofItemAtPath:url.path error:nil];
  [url setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
  return YES;
}

static void RBRADeleteFallback(void) {
  NSURL *url = RBRAFallbackURL();
  if (url) [NSFileManager.defaultManager removeItemAtURL:url error:nil];
}

static OSStatus RBRAWriteKeychain(NSData *data) {
  NSMutableDictionary *query = RBRAKeychainQuery(@".retroachievements");
  NSDictionary *update = @{(__bridge id)kSecValueData: data,
      (__bridge id)kSecAttrAccessible: (__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly};
  OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)update);
  if (status == errSecItemNotFound) {
    [query addEntriesFromDictionary:update];
    status = SecItemAdd((__bridge CFDictionaryRef)query, NULL);
  }
  return status;
}

/// Saves the central account in the Keychain and in the private fallback
/// file. Succeeds when at least one copy was written.
static OSStatus RBRAWriteCredentials(NSDictionary *credentials) {
  NSData *data = [NSJSONSerialization dataWithJSONObject:credentials options:0 error:nil];
  if (!data) return errSecParam;
  OSStatus keychain = RBRAWriteKeychain(data);
  BOOL file = RBRAWriteFallback(data);
  // Codes only: never the username or the token.
  NSLog(@"[RetroAchievements] central account saved: keychain=%d file=%@", (int)keychain, file ? @"yes" : @"no");
  return keychain == errSecSuccess || file ? errSecSuccess : keychain;
}

/// The central account: the Keychain item, else the private fallback copy
/// (which then restores the Keychain item). [source] is "keychain", "file"
/// or "none"; [keychainStatus] the Keychain read result, for diagnostics.
static NSDictionary *RBRALoadCentral(OSStatus *status, NSString **source, OSStatus *keychainStatus) {
  OSStatus keychain = errSecSuccess;
  NSDictionary *credentials = RBRAReadCredentials(@".retroachievements", &keychain);
  if (keychainStatus) *keychainStatus = keychain;
  if (credentials) {
    // Accounts saved before the private copy existed get it; a stale copy
    // (another account) follows the Keychain.
    if (![RBRAReadFallback() isEqualToDictionary:credentials]) {
      NSData *data = [NSJSONSerialization dataWithJSONObject:credentials options:0 error:nil];
      RBRAWriteFallback(data);
    }
    if (status) *status = errSecSuccess;
    if (source) *source = @"keychain";
    return credentials;
  }
  NSDictionary *fallback = RBRAReadFallback();
  if (fallback) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:fallback options:0 error:nil];
    OSStatus restored = data ? RBRAWriteKeychain(data) : errSecParam;
    NSLog(@"[RetroAchievements] central account read from the private copy (keychain=%d, restored=%d)",
          (int)keychain, (int)restored);
    if (status) *status = errSecSuccess;
    if (source) *source = @"file";
    return fallback;
  }
  if (status) *status = keychain;
  if (source) *source = @"none";
  return nil;
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
// In-game status notices for the current launch only (guarded by lock).
@property(nonatomic, copy, nullable) RBRAStatusPresenter statusPresenter;
@property(nonatomic, copy) NSString *statusSessionId;
@property(nonatomic, copy) NSString *statusAnnounced;
@property(nonatomic) NSUInteger statusCount;
@property(nonatomic) BOOL statusReady;
@property(nonatomic) BOOL statusTimedOut;
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
    hub.statusSessionId = @"";
    hub.statusAnnounced = @"";
  });
  return hub;
}

- (NSDictionary *)publicState:(NSDictionary *)configuration {
  NSMutableDictionary *state = [NSMutableDictionary dictionary];
  for (NSString *key in @[@"sessionId", @"engine", @"system", @"core", @"generation",
                          @"enabled", @"supported", @"hardcore", @"notifications", @"capability",
                          @"requested"]) {
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
    NSDictionary *central = RBRALoadCentral(&status, NULL, NULL);
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
    NSDictionary *central = RBRALoadCentral(&status, NULL, NULL);
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
    NSString *source = @"none";
    OSStatus keychain = errSecSuccess;
    NSDictionary *credentials = RBRALoadCentral(&status, &source, &keychain);
    NSLog(@"[RetroAchievements] central account read: source=%@ keychain=%d", source, (int)keychain);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    [self.lock lock]; NSDictionary *state = self.lastState; [self.lock unlock];
    // storage/keychainStatus: diagnostics only (no account data).
    // A real boolean: @(credentials != nil) boxes a C int, which the Flutter
    // codec sends as 1, and Dart's `== true` read it as signed out at every
    // launch (the 2 November 2026 report: "password required" after each
    // restart while the Keychain item was found).
    result(@{@"available": @YES, @"authenticated": credentials ? @YES : @NO,
             @"username": credentials[@"username"] ?: @"", @"session": state,
             @"storage": source, @"keychainStatus": @((int)keychain)});
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
        // Only codes and the HTTP status are logged: never the request,
        // response body, username, password or token.
        void (^fail)(NSString *) = ^(NSString *code) {
          NSLog(@"[RetroAchievements] central sign-in failed: %@ (HTTP %ld)", code, (long)status);
          result(RBRAError(code));
        };
        // No answer at all (offline, DNS, TLS, timeout): a network problem.
        if (error || status == 0) { fail(@"RA_NETWORK_UNAVAILABLE"); return; }
        if (status == 429) { fail(@"RA_RATE_LIMITED"); return; }
        if (status >= 500) { fail(@"RA_SERVER_ERROR"); return; }
        id payload = data.length <= 1024 * 1024 ? [NSJSONSerialization JSONObjectWithData:data ?: NSData.data options:0 error:nil] : nil;
        if (![payload isKindOfClass:NSDictionary.class]) {
          // An HTML page (captive portal, proxy, maintenance) is not a refusal
          // of the player's password; only 401/403 without JSON are.
          fail(status == 401 || status == 403 ? @"RA_AUTHENTICATION_FAILED" : @"RA_SERVER_ERROR");
          return;
        }
        BOOL success = [payload[@"Success"] isKindOfClass:NSNumber.class] && [payload[@"Success"] boolValue];
        if (!success || status != 200) {
          // RetroAchievements explicitly refused the sign-in (for example
          // invalid_credentials or access_denied).
          fail(@"RA_AUTHENTICATION_FAILED"); return;
        }
        if (!RBRAString(payload[@"User"]).length || !RBRAString(payload[@"Token"]).length) {
          fail(@"RA_SERVER_ERROR"); return;
        }
        NSDictionary *credentials = @{@"username": payload[@"User"], @"token": payload[@"Token"]};
        if (RBRAWriteCredentials(credentials) != errSecSuccess) { fail(@"RA_STORAGE_UNAVAILABLE"); return; }
        NSLog(@"[RetroAchievements] central sign-in succeeded (HTTP %ld)", (long)status);
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
    // The private copy goes first: a sign-out never comes back at the next launch.
    RBRADeleteFallback();
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
    NSDictionary *credentials = RBRALoadCentral(&status, NULL, NULL);
    if (status != errSecSuccess && status != errSecItemNotFound) { result(RBRAError(@"RA_STORAGE_UNAVAILABLE")); return; }
    // RPCS3 (PS3) has its own rcheevos client; MeloNX has no integration.
    BOOL supported = RBRABool(args[@"supported"]) && ![@[@"melonx"] containsObject:engine];
    BOOL enabled = RBRABool(args[@"enabled"]) && supported && credentials != nil;
    // The player's own RA choice (even without a usable account) drives the
    // display-only launch status; it never enables anything by itself.
    BOOL requested = RBRABool(args[@"requested"]) || enabled;
    // Localized, non-secret status labels from the app catalogs (bounded).
    NSMutableDictionary<NSString *, NSString *> *statusText = [NSMutableDictionary dictionary];
    NSDictionary *texts = [args[@"statusText"] isKindOfClass:NSDictionary.class] ? args[@"statusText"] : @{};
    for (id key in texts) {
      if (statusText.count >= 64) break;
      if ([key isKindOfClass:NSString.class] && [key length] <= 64 &&
          [texts[key] isKindOfClass:NSString.class] && [texts[key] length] <= 512) {
        statusText[key] = [texts[key] copy];
      }
    }
    NSString *identifier = NSUUID.UUID.UUIDString;
    NSDictionary *snapshot = @{@"sessionId": identifier, @"engine": engine,
      @"system": RBRAString(args[@"system"]), @"core": RBRAString(args[@"core"]),
      @"language": RBRAString(args[@"language"]),
      @"capability": RBRAString(args[@"capability"]),
      @"enabled": @(enabled), @"supported": @(supported), @"requested": @(requested),
      @"hardcore": (enabled && RBRABool(args[@"hardcore"])) ? @YES : @NO, @"notifications": @(enabled),
      @"username": enabled ? credentials[@"username"] : @"", @"token": enabled ? credentials[@"token"] : @"",
      @"statusText": [statusText copy],
      @"generation": [args[@"generation"] isKindOfClass:NSNumber.class] ? args[@"generation"] : @0,
      @"expires": [NSDate dateWithTimeIntervalSinceNow:600]};
    NSLog(@"[RetroAchievements] launch prepared: engine=%@ supported=%d requested=%d enabled=%d hardcore=%d account=%d",
          engine, supported, requested, enabled, enabled && RBRABool(args[@"hardcore"]), credentials != nil);
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

#pragma mark - In-game launch status (display only)

static const NSTimeInterval RBRAStatusInitialDelay = 3.0;  // game view visible
static const NSTimeInterval RBRAStatusTimeout = 40.0;      // still unconfirmed
static const NSUInteger RBRAStatusMaxNotices = 4;

// Engine error codes that end the launch status; anything else (empty,
// cleanup_pending, RA_SYNC_PENDING, RA_SERVER_ERROR, hardcore_inactive,
// state_unavailable) is transient and keeps the status pending.
static NSString *RBRAStatusKeyForCode(NSString *code) {
  static NSDictionary<NSString *, NSString *> *keys;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    keys = @{
      // rcheevos RC_ACCESS_DENIED -33, RC_INVALID_CREDENTIALS -34, RC_EXPIRED_TOKEN -35.
      @"RA_AUTHENTICATION_FAILED": @"authRejected", @"login_failed_-33": @"authRejected",
      @"login_failed_-34": @"authRejected", @"login_failed_-35": @"authRejected",
      // RC_NO_RESPONSE -32 (no answer), RC_INVALID_JSON -26 (not a RA answer).
      @"RA_NETWORK_UNAVAILABLE": @"network", @"login_failed_-32": @"network",
      @"login_failed_-26": @"network",
      @"RA_LOGIN_FAILED": @"loginFailed",
      @"RA_LOGIN_REQUIRED": @"signIn", @"RA_CREDENTIALS_MISSING": @"signIn",
      @"RA_GAME_NOT_RECOGNIZED": @"unknownGame",
      @"RA_NO_ACHIEVEMENTS": @"noAchievements",
      @"RA_ACHIEVEMENTS_UNSUPPORTED": @"setUnsupported",
      @"RA_UNSUPPORTED": @"unsupported", @"RA_CORE_UNSUPPORTED": @"unsupported",
      @"RA_MEMORY_UNAVAILABLE": @"unsupported",
      @"RA_HARDCORE_OPTIONS": @"hardcoreOptions", @"RA_HARDCORE_RESET_REQUIRED": @"hardcoreOptions",
      @"RA_GAME_LOAD_FAILED": @"loadFailed",
      @"configuration_failed": @"unavailable", @"RA_CLIENT_UNAVAILABLE": @"unavailable",
      @"RA_SESSION_ERROR": @"unavailable", @"RA_UNAVAILABLE": @"unavailable",
    };
  });
  NSString *key = keys[code];
  if (!key && [code hasPrefix:@"login_failed_"]) key = @"loginFailed";
  return key;
}

static NSString *RBRAStatusFallback(NSString *key) {
  static NSDictionary<NSString *, NSString *> *english;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    english = @{
      @"active": @"Achievements active",
      @"progress": @"{unlocked}/{total} unlocked",
      @"hardcoreOn": @"Hardcore on", @"hardcoreOff": @"Hardcore off",
      @"hardcoreNotApplied": @"Hardcore not applied",
      @"signingIn": @"Signing in to RetroAchievements…",
      @"identifying": @"Signed in · identifying the game…",
      @"noAchievements": @"Game recognized, but it has no achievements to track.",
      @"setUnsupported": @"Game recognized, but its achievements are not supported by this emulator.",
      @"unknownGame": @"Game not recognized by RetroAchievements (unlisted version or dump).",
      @"unsupported": @"RetroAchievements is not available for this game or emulator core.",
      @"signIn": @"Sign-in required: open the RetroAchievements tab.",
      @"authRejected": @"RetroAchievements refused the sign-in. Sign in again from the RetroAchievements tab.",
      @"network": @"RetroAchievements is unreachable: achievements are not active.",
      @"loginFailed": @"Could not sign in to RetroAchievements: achievements are not active.",
      @"hardcoreOptions": @"Achievements off: some emulator options are incompatible with Hardcore mode.",
      @"loadFailed": @"Could not load this game's achievements from RetroAchievements.",
      @"unavailable": @"RetroAchievements could not start for this game.",
      @"unconfirmed": @"Achievement tracking not confirmed: game not recognized or server unreachable.",
    };
  });
  return english[key] ?: @"";
}

NSString *RBRAPointsText(NSDictionary *configuration, NSUInteger points) {
  NSDictionary *texts = [configuration isKindOfClass:NSDictionary.class] &&
      [configuration[@"statusText"] isKindOfClass:NSDictionary.class] ? configuration[@"statusText"] : @{};
  NSString *unit = RBRAString(texts[@"points"]);
  return [NSString stringWithFormat:@"%lu %@", (unsigned long)points, unit.length ? unit : @"points"];
}

NSDictionary<NSString *, id> *RBRAStatusForState(NSDictionary *configuration, NSDictionary *state, BOOL timedOut) {
  if (![configuration isKindOfClass:NSDictionary.class]) return nil;
  if (![state isKindOfClass:NSDictionary.class]) state = @{};
  const BOOL enabled = RBRABool(configuration[@"enabled"]);
  // Players who switched RA off are never notified in game.
  if (!enabled && !RBRABool(configuration[@"requested"])) return nil;
  NSDictionary *texts = [configuration[@"statusText"] isKindOfClass:NSDictionary.class]
      ? configuration[@"statusText"] : @{};
  NSString *(^text)(NSString *) = ^NSString *(NSString *key) {
    NSString *value = RBRAString(texts[key]);
    return value.length ? value : RBRAStatusFallback(key);
  };
  NSDictionary *(^notice)(NSString *, NSString *, BOOL) = ^NSDictionary *(NSString *key, NSString *message, BOOL final) {
    return @{@"key": key, @"message": message ?: @"", @"final": @(final)};
  };
  if (!RBRABool(configuration[@"supported"])) return notice(@"unsupported", text(@"unsupported"), YES);
  if (!enabled) return notice(@"signIn", text(@"signIn"), YES);
  if (RBRABool(state[@"active"])) {
    // "Active" requires the engine's own confirmation: signed in, game
    // identified and a usable achievement set being evaluated.
    NSMutableArray<NSString *> *parts = [NSMutableArray arrayWithObject:text(@"active")];
    NSString *username = RBRAString(configuration[@"username"]);
    if (username.length) [parts addObject:username];
    const NSUInteger total = [state[@"totalCount"] isKindOfClass:NSNumber.class]
        ? [state[@"totalCount"] unsignedIntegerValue] : 0;
    const NSUInteger unlocked = [state[@"unlockedCount"] isKindOfClass:NSNumber.class]
        ? [state[@"unlockedCount"] unsignedIntegerValue] : 0;
    if (total > 0) {
      NSString *progress = [text(@"progress") stringByReplacingOccurrencesOfString:@"{unlocked}"
                                                                        withString:@(MIN(unlocked, total)).stringValue];
      [parts addObject:[progress stringByReplacingOccurrencesOfString:@"{total}" withString:@(total).stringValue]];
    }
    // Only the Hardcore state the engine actually applied is displayed.
    const BOOL hardcoreActive = RBRABool(state[@"hardcoreActive"]);
    [parts addObject:hardcoreActive ? text(@"hardcoreOn")
        : RBRABool(configuration[@"hardcore"]) ? text(@"hardcoreNotApplied") : text(@"hardcoreOff")];
    return notice(hardcoreActive ? @"activeHardcore" : @"active", [parts componentsJoinedByString:@" · "], YES);
  }
  NSString *key = RBRAStatusKeyForCode(RBRAString(state[@"errorCode"]));
  if (key) return notice(key, text(key), YES);
  if (timedOut) return notice(@"unconfirmed", text(@"unconfirmed"), YES);
  const BOOL signedIn = RBRABool(state[@"loggedIn"]) || RBRABool(state[@"gameLoaded"]);
  return notice(@"pending", text(signedIn ? @"identifying" : @"signingIn"), NO);
}

// Main queue only. Announces the current launch status when it changed: the
// pending notice once (if nothing is known after the initial delay), then each
// distinct final status once, at most RBRAStatusMaxNotices per launch.
static void RBRAEvaluateStatus(NSString *identifier) {
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock];
  RBRAStatusPresenter presenter = hub.statusPresenter;
  NSDictionary *snapshot = hub.active[identifier];
  if (!presenter || !hub.statusReady || !snapshot || ![identifier isEqualToString:hub.statusSessionId] ||
      ![identifier isEqualToString:hub.currentSessionId] || hub.statusCount >= RBRAStatusMaxNotices) {
    [hub.lock unlock];
    return;
  }
  NSDictionary *status = RBRAStatusForState(snapshot, hub.lastState, hub.statusTimedOut);
  NSString *key = RBRAString(status[@"key"]);
  const BOOL final = RBRABool(status[@"final"]);
  const BOOL announce = key.length > 0 && ![key isEqualToString:hub.statusAnnounced] &&
      (final || hub.statusAnnounced.length == 0);
  if (!announce) {
    [hub.lock unlock];
    return;
  }
  hub.statusAnnounced = key;
  hub.statusCount += 1;
  [hub.lock unlock];
  presenter(key, @"RetroAchievements", RBRAString(status[@"message"]), final ? 5.0 : 3.0);
}

void RBRASetStatusPresenter(NSDictionary *configuration, RBRAStatusPresenter presenter) {
  if (![configuration isKindOfClass:NSDictionary.class]) return;
  NSString *identifier = RBRAString(configuration[@"sessionId"]);
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock];
  // Only the exact snapshot of the current launch may present its status.
  if (!identifier.length || hub.active[identifier] != configuration ||
      ![identifier isEqualToString:hub.currentSessionId]) {
    [hub.lock unlock];
    return;
  }
  hub.statusPresenter = presenter;
  hub.statusSessionId = presenter ? identifier : @"";
  hub.statusAnnounced = @"";
  hub.statusCount = 0;
  hub.statusReady = NO;
  hub.statusTimedOut = NO;
  [hub.lock unlock];
  if (!presenter) return;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(RBRAStatusInitialDelay * NSEC_PER_SEC)),
                 dispatch_get_main_queue(), ^{
    [hub.lock lock];
    const BOOL current = [identifier isEqualToString:hub.statusSessionId];
    if (current) hub.statusReady = YES;
    [hub.lock unlock];
    if (current) RBRAEvaluateStatus(identifier);
  });
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(RBRAStatusTimeout * NSEC_PER_SEC)),
                 dispatch_get_main_queue(), ^{
    [hub.lock lock];
    const BOOL current = [identifier isEqualToString:hub.statusSessionId];
    if (current) {
      hub.statusReady = YES;
      hub.statusTimedOut = YES;
    }
    [hub.lock unlock];
    if (current) RBRAEvaluateStatus(identifier);
  });
}

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
  // A previous launch can never present its status over this one.
  hub.statusPresenter = nil;
  hub.statusSessionId = @"";
  hub.statusAnnounced = @"";
  hub.statusCount = 0;
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
  for (NSString *key in @[@"active", @"gameLoaded", @"hardcoreActive", @"gameId", @"totalCount",
                          @"unlockedCount", @"loggedIn"]) {
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
  const BOOL announces = [identifier isEqualToString:hub.statusSessionId];
  [hub.lock unlock];
  [hub emit:published];
  if (announces) dispatch_async(dispatch_get_main_queue(), ^{ RBRAEvaluateStatus(identifier); });
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
  if ([identifier isEqualToString:hub.statusSessionId]) {
    // No status toast survives its game.
    hub.statusPresenter = nil;
    hub.statusSessionId = @"";
  }
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
