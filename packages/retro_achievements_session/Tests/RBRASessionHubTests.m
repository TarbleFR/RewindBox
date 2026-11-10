#import <XCTest/XCTest.h>
#import <Flutter/Flutter.h>
#import <Security/Security.h>
#import <objc/runtime.h>
#import "RBRASession.h"
#import "RetroAchievementsSessionPlugin.h"

// Private test declarations only. Production does not expose test/reset,
// credential-injection, clock-injection or alternative endpoint APIs.
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
@end

@interface RBRANoRedirectDelegate : NSObject <NSURLSessionTaskDelegate>
@end

static NSString *const RBRAFixtureToken = @"fixture-token-never-public-8a64";
static NSString *const RBRAFixturePassword = @"fixture-password-never-public-4f19";

static void RBRAOnMain(dispatch_block_t block) {
  if (NSThread.isMainThread) block();
  else dispatch_sync(dispatch_get_main_queue(), block);
}

static NSMutableDictionary *RBRATestKeychainQueryForSuffix(NSString *suffix) {
  // The simulator test host has a separate bundle ID and no shared access group.
  // Never query the installed application's service. Fail before any mutation.
  NSString *bundle = NSBundle.mainBundle.bundleIdentifier;
  if (![bundle isEqualToString:@"org.rewindbox.tests.ra-session.host"])
    @throw [NSException exceptionWithName:NSInternalInconsistencyException reason:@"Wrong Keychain test host" userInfo:nil];
  return [@{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
    (__bridge id)kSecAttrService: [bundle stringByAppendingString:suffix],
    (__bridge id)kSecAttrAccount: @"emulator-player"} mutableCopy];
}
static NSMutableDictionary *RBRATestKeychainQuery(void) { return RBRATestKeychainQueryForSuffix(@".retroachievements"); }
static NSDictionary<NSString *, NSString *> *RBRATestLegacyPaths(void) {
  NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject;
  NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  return @{@"dolphin": [support stringByAppendingPathComponent:@"NeoStation/Dolphin/User/Config/RetroAchievements.ini"],
    @"armsx2": [documents stringByAppendingPathComponent:@"ARMSX2/inis/PCSX2.ini"],
    @"secrets": [documents stringByAppendingPathComponent:@"ARMSX2/inis/secrets.ini"]};
}

// Private copy of the central account (RBRAFallbackURL), in the test host's
// own container.
static NSString *RBRATestFallbackPath(void) {
  NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject;
  return [support stringByAppendingPathComponent:@"RetroAchievements/central-session.json"];
}

static NSDictionary *RBRATestForm(NSURLRequest *request) {
  NSData *data = request.HTTPBody;
  if (!data && request.HTTPBodyStream) {
    NSMutableData *buffer = [NSMutableData data];
    NSInputStream *stream = request.HTTPBodyStream;
    [stream open];
    uint8_t bytes[1024]; NSInteger size;
    while ((size = [stream read:bytes maxLength:sizeof(bytes)]) > 0)
      [buffer appendBytes:bytes length:(NSUInteger)size];
    [stream close]; data = buffer;
  }
  NSString *body = [[NSString alloc] initWithData:data ?: NSData.data encoding:NSUTF8StringEncoding];
  NSMutableDictionary *fields = [NSMutableDictionary dictionary];
  for (NSString *pair in [body componentsSeparatedByString:@"&"]) {
    NSRange separator = [pair rangeOfString:@"="];
    if (separator.location == NSNotFound) continue;
    NSString *key = [[pair substringToIndex:separator.location] stringByRemovingPercentEncoding];
    NSString *value = [[pair substringFromIndex:separator.location + 1] stringByRemovingPercentEncoding];
    if (key && value) fields[key] = value;
  }
  return fields;
}

// The real FlutterMethodChannel and StandardMethodCodec encode these events.
// Only the transport endpoint is recorded; no Flutter engine or Dart VM runs.
@interface RBRATestMessenger : NSObject <FlutterBinaryMessenger>
@property(nonatomic, strong) NSLock *lock;
@property(nonatomic, strong) NSMutableArray<FlutterMethodCall *> *calls;
@property(nonatomic) BOOL everySendWasOnMain;
- (NSArray<FlutterMethodCall *> *)recordedCalls;
- (void)clear;
@end
@implementation RBRATestMessenger
- (instancetype)init {
  if ((self = [super init])) { _lock = [NSLock new]; _calls = [NSMutableArray array]; _everySendWasOnMain = YES; }
  return self;
}
- (void)sendOnChannel:(NSString *)channel message:(NSData *)message {
  FlutterMethodCall *call = message ? [FlutterStandardMethodCodec.sharedInstance decodeMethodCall:message] : nil;
  [self.lock lock];
  self.everySendWasOnMain = self.everySendWasOnMain && NSThread.isMainThread;
  if (call) [self.calls addObject:call];
  [self.lock unlock];
}
- (void)sendOnChannel:(NSString *)channel message:(NSData *)message binaryReply:(FlutterBinaryReply)reply {
  [self sendOnChannel:channel message:message]; if (reply) reply(nil);
}
- (FlutterBinaryMessengerConnection)setMessageHandlerOnChannel:(NSString *)channel
    binaryMessageHandler:(FlutterBinaryMessageHandler)handler { return 1; }
- (void)cleanUpConnection:(FlutterBinaryMessengerConnection)connection {}
- (NSArray<FlutterMethodCall *> *)recordedCalls {
  [self.lock lock]; NSArray *result = [self.calls copy]; [self.lock unlock]; return result;
}
- (void)clear { [self.lock lock]; [self.calls removeAllObjects]; [self.lock unlock]; }
@end

typedef NSDictionary *(^RBRATestResponse)(NSURLRequest *request);
static NSLock *RBRAProtocolLock;
static RBRATestResponse RBRAProtocolResponse;

// Intercepts all requests in the test session. No fixture request can reach the
// network, including requests to an unexpected host. Production still creates
// its actual NSURLSession, request, redirect delegate and completion handler.
@interface RBRATestURLProtocol : NSURLProtocol
@property(nonatomic, strong) NSLock *stateLock;
@property(nonatomic) BOOL stopped;
+ (void)setResponse:(RBRATestResponse)response;
@end
@implementation RBRATestURLProtocol
+ (void)initialize {
  if (self == RBRATestURLProtocol.class) RBRAProtocolLock = [NSLock new];
}
+ (void)setResponse:(RBRATestResponse)response {
  [RBRAProtocolLock lock]; RBRAProtocolResponse = [response copy]; [RBRAProtocolLock unlock];
}
+ (BOOL)canInitWithRequest:(NSURLRequest *)request { return YES; }
+ (NSURLRequest *)canonicalRequestForRequest:(NSURLRequest *)request { return request; }
- (void)startLoading {
  self.stateLock = [NSLock new];
  [RBRAProtocolLock lock]; RBRATestResponse response = RBRAProtocolResponse; [RBRAProtocolLock unlock];
  NSDictionary *fixture = response ? response(self.request) : @{ @"status": @599 };
  // Cancellation tests hold the request until NSURLSession cancels it, rather
  // than depending on a timing window on a busy simulator.
  if ([fixture[@"hold"] boolValue]) return;
  NSTimeInterval delay = [fixture[@"delay"] doubleValue];
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)),
      dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    [self.stateLock lock]; BOOL stopped = self.stopped; [self.stateLock unlock];
    if (stopped) return;
    if ([fixture[@"error"] isKindOfClass:NSError.class]) {
      [self.client URLProtocol:self didFailWithError:fixture[@"error"]]; return;
    }
    NSInteger status = [fixture[@"status"] integerValue];
    NSHTTPURLResponse *reply = [[NSHTTPURLResponse alloc] initWithURL:self.request.URL
      statusCode:status HTTPVersion:@"HTTP/1.1" headerFields:@{@"Content-Type": @"application/json"}];
    NSData *body = fixture[@"data"];
    if (!body) body = [NSJSONSerialization dataWithJSONObject:fixture[@"json"] ?: @{} options:0 error:nil];
    [self.client URLProtocol:self didReceiveResponse:reply cacheStoragePolicy:NSURLCacheStorageNotAllowed];
    [self.client URLProtocol:self didLoadData:body];
    [self.client URLProtocolDidFinishLoading:self];
  });
}
- (void)stopLoading { [self.stateLock lock]; self.stopped = YES; [self.stateLock unlock]; }
@end

@interface NSURLSessionConfiguration (RBRATestTransport)
+ (instancetype)rbra_testEphemeralConfiguration;
@end
@implementation NSURLSessionConfiguration (RBRATestTransport)
+ (instancetype)rbra_testEphemeralConfiguration {
  // After method exchange this invokes the original Foundation factory.
  NSURLSessionConfiguration *configuration = [self rbra_testEphemeralConfiguration];
  configuration.protocolClasses = @[RBRATestURLProtocol.class];
  return configuration;
}
@end

@interface RBRASessionHubTests : XCTestCase
@property(nonatomic, strong) RetroAchievementsSessionPlugin *plugin;
@property(nonatomic, strong) RBRATestMessenger *messenger;
@property(nonatomic, strong) FlutterMethodChannel *channel;
@end

@implementation RBRASessionHubTests
+ (void)setUp {
  [super setUp];
  Method original = class_getClassMethod(NSURLSessionConfiguration.class, @selector(ephemeralSessionConfiguration));
  Method fixture = class_getClassMethod(NSURLSessionConfiguration.class, @selector(rbra_testEphemeralConfiguration));
  method_exchangeImplementations(original, fixture);
}
+ (void)tearDown {
  Method original = class_getClassMethod(NSURLSessionConfiguration.class, @selector(ephemeralSessionConfiguration));
  Method fixture = class_getClassMethod(NSURLSessionConfiguration.class, @selector(rbra_testEphemeralConfiguration));
  method_exchangeImplementations(original, fixture);
  [super tearDown];
}
- (void)resetHub {
  RBRAOnMain(^{
    RBRASessionHub *hub = RBRASessionHub.shared;
    ++hub.authGeneration; [hub.authTask cancel]; hub.authTask = nil;
    [hub.lock lock];
    [hub.pending removeAllObjects]; [hub.active removeAllObjects]; [hub.channels removeAllObjects];
    hub.legacyCandidates = @{};
    hub.currentSessionId = @""; hub.lastState = @{}; ++hub.stateRevision;
    [hub.lock unlock];
  });
}
- (void)setUp {
  [super setUp];
  XCTAssertTrue([NSBundle.mainBundle.bundleIdentifier hasPrefix:@"org.rewindbox.tests.ra-session."]);
  [self resetHub];
  for (NSString *suffix in @[@".retroachievements", @".libretro.retroachievements", @".dolphin.retroachievements"]) {
    OSStatus status = SecItemDelete((__bridge CFDictionaryRef)RBRATestKeychainQueryForSuffix(suffix));
    XCTAssertTrue(status == errSecSuccess || status == errSecItemNotFound);
  }
  [NSUserDefaults.standardUserDefaults removeObjectForKey:@"libretro.achievements.enabled"];
  for (NSString *path in [RBRATestLegacyPaths().allValues arrayByAddingObject:RBRATestFallbackPath()])
    if ([NSFileManager.defaultManager fileExistsAtPath:path])
      XCTAssertTrue([NSFileManager.defaultManager removeItemAtPath:path error:nil]);
  self.plugin = [RetroAchievementsSessionPlugin new];
  self.messenger = [RBRATestMessenger new];
  self.channel = [FlutterMethodChannel methodChannelWithName:@"rewindbox/retro_achievements_session" binaryMessenger:self.messenger];
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock]; [hub.channels addObject:self.channel]; [hub.lock unlock];
  [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) { return @{ @"status": @599 }; }];
}
- (void)tearDown {
  [self resetHub];
  [RBRATestURLProtocol setResponse:nil];
  for (NSString *suffix in @[@".retroachievements", @".libretro.retroachievements", @".dolphin.retroachievements"]) {
    OSStatus status = SecItemDelete((__bridge CFDictionaryRef)RBRATestKeychainQueryForSuffix(suffix));
    XCTAssertTrue(status == errSecSuccess || status == errSecItemNotFound);
  }
  [NSUserDefaults.standardUserDefaults removeObjectForKey:@"libretro.achievements.enabled"];
  for (NSString *path in [RBRATestLegacyPaths().allValues arrayByAddingObject:RBRATestFallbackPath()])
    if ([NSFileManager.defaultManager fileExistsAtPath:path])
      XCTAssertTrue([NSFileManager.defaultManager removeItemAtPath:path error:nil]);
  [super tearDown];
}
- (void)waitFor:(NSArray<XCTestExpectation *> *)expectations {
  XCTAssertEqual([XCTWaiter waitForExpectations:expectations timeout:8], XCTWaiterResultCompleted);
}
- (void)drainMain {
  XCTestExpectation *done = [self expectationWithDescription:@"main event queue drained"];
  dispatch_async(dispatch_get_main_queue(), ^{ [done fulfill]; });
  [self waitFor:@[done]];
}
- (id)call:(NSString *)method arguments:(id)arguments {
  XCTestExpectation *done = [self expectationWithDescription:method];
  __block id answer;
  RBRAOnMain(^{
    [self.plugin handleMethodCall:[FlutterMethodCall methodCallWithMethodName:method arguments:arguments]
      result:^(id value) { answer = value; [done fulfill]; }];
  });
  [self waitFor:@[done]];
  return answer;
}
- (void)writeRawKeychain:(NSData *)data {
  NSMutableDictionary *query = RBRATestKeychainQuery();
  OSStatus removed = SecItemDelete((__bridge CFDictionaryRef)query);
  XCTAssertTrue(removed == errSecSuccess || removed == errSecItemNotFound);
  query[(__bridge id)kSecValueData] = data;
  query[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleWhenUnlockedThisDeviceOnly;
  XCTAssertEqual(SecItemAdd((__bridge CFDictionaryRef)query, NULL), errSecSuccess);
}
- (void)seedAccount:(NSString *)username token:(NSString *)token {
  [self writeRawKeychain:[NSJSONSerialization dataWithJSONObject:@{@"username": username, @"token": token} options:0 error:nil]];
}
- (void)seedLegacySuffix:(NSString *)suffix username:(NSString *)username token:(NSString *)token {
  NSMutableDictionary *query = RBRATestKeychainQueryForSuffix(suffix);
  query[(__bridge id)kSecValueData] = [NSJSONSerialization dataWithJSONObject:@{@"username": username, @"token": token} options:0 error:nil];
  query[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleWhenUnlockedThisDeviceOnly;
  XCTAssertEqual(SecItemAdd((__bridge CFDictionaryRef)query, NULL), errSecSuccess);
}
- (void)writeLegacy:(NSString *)name contents:(NSString *)contents {
  NSString *path = RBRATestLegacyPaths()[name];
  NSError *error = nil;
  XCTAssertTrue([NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
    withIntermediateDirectories:YES attributes:nil error:&error]);
  XCTAssertNil(error);
  XCTAssertTrue([contents writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:&error]);
  XCTAssertNil(error);
}
- (NSDictionary *)prepare:(NSDictionary *)overrides {
  NSMutableDictionary *arguments = [@{@"engine": @"armsx2", @"system": @"ps2", @"core": @"armsx2",
    @"language": @"fr", @"capability": @"supported", @"enabled": @YES,
    @"supported": @YES, @"hardcore": @YES, @"generation": @42,
    @"notifications": @NO} mutableCopy];
  [arguments addEntriesFromDictionary:overrides];
  id response = [self call:@"prepareSession" arguments:arguments];
  XCTAssertTrue([response isKindOfClass:NSDictionary.class]);
  return [response isKindOfClass:NSDictionary.class] ? response : @{};
}
- (NSDictionary *)start:(NSDictionary *)overrides {
  NSDictionary *prepared = [self prepare:overrides];
  NSDictionary *snapshot = RBRATakeLaunchConfiguration(prepared, overrides[@"engine"] ?: @"armsx2");
  XCTAssertTrue([snapshot[@"sessionId"] length] > 0);
  return snapshot;
}
- (NSDictionary *)lastState {
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock]; NSDictionary *state = hub.lastState; [hub.lock unlock]; return state;
}
- (void)assertRedacted:(id)value {
  if ([value isKindOfClass:FlutterError.class]) {
    FlutterError *error = value;
    [self assertRedacted:error.code]; [self assertRedacted:error.message]; [self assertRedacted:error.details];
  } else if ([value isKindOfClass:NSDictionary.class]) {
    for (id key in value) {
      if ([key isKindOfClass:NSString.class]) {
        XCTAssertNotEqualObjects([key lowercaseString], @"token");
        XCTAssertNotEqualObjects([key lowercaseString], @"password");
      }
      [self assertRedacted:value[key]];
    }
  } else if ([value isKindOfClass:NSArray.class]) {
    for (id child in value) [self assertRedacted:child];
  } else if ([value isKindOfClass:NSString.class]) {
    XCTAssertFalse([value containsString:RBRAFixtureToken]);
    XCTAssertFalse([value containsString:RBRAFixturePassword]);
  }
}
/// What Dart receives: the answer through the real Flutter standard codec.
/// @(a != b) boxes a C int that arrives as 1, which Dart's `== true` reads
/// as false (every launch looked signed out until 2 November 2026).
- (void)assertFlagsSurviveTheCodec:(NSDictionary *)answer {
  FlutterStandardMethodCodec *codec = [FlutterStandardMethodCodec sharedInstance];
  NSDictionary *decoded = [codec decodeEnvelope:[codec encodeSuccessEnvelope:answer]];
  for (NSString *key in @[@"available", @"authenticated", @"central"]) {
    if (!decoded[key]) continue;
    XCTAssertEqual(CFGetTypeID((__bridge CFTypeRef)decoded[key]), CFBooleanGetTypeID(), @"%@", key);
  }
}
- (void)assertEventsRedacted {
  [self drainMain];
  for (FlutterMethodCall *event in self.messenger.recordedCalls) {
    XCTAssertEqualObjects(event.method, @"sessionChanged");
    [self assertRedacted:event.arguments];
  }
  XCTAssertTrue(self.messenger.everySendWasOnMain);
}

- (void)testMissingMalformedAndUnknownHandlesDisableRA {
  for (id arguments in @[(id)NSNull.null, @{}, @{@"raSessionId": @7}, @{@"raSessionId": @"unknown"}]) {
    NSDictionary *snapshot = RBRATakeLaunchConfiguration((NSDictionary *)arguments, @"armsx2");
    XCTAssertEqualObjects(snapshot[@"enabled"], @NO);
    XCTAssertEqualObjects(snapshot[@"hardcore"], @NO);
    XCTAssertEqualObjects(snapshot[@"notifications"], @NO);
    XCTAssertEqualObjects(snapshot[@"token"], @"");
  }
}
- (void)testHandleIsOneShotAndBoundToItsEngine {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *prepared = [self prepare:@{}];
  XCTAssertEqualObjects(RBRATakeLaunchConfiguration(prepared, @"dolphin")[@"enabled"], @NO);
  NSDictionary *snapshot = RBRATakeLaunchConfiguration(prepared, @"armsx2");
  XCTAssertEqualObjects(snapshot[@"enabled"], @YES);
  XCTAssertEqualObjects(snapshot[@"token"], RBRAFixtureToken);
  XCTAssertEqualObjects(RBRATakeLaunchConfiguration(prepared, @"armsx2")[@"enabled"], @NO);
}
- (void)testConcurrentTakeOnlyGrantsOneSnapshot {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *prepared = [self prepare:@{}];
  NSLock *counterLock = [NSLock new]; __block NSUInteger granted = 0;
  dispatch_group_t group = dispatch_group_create();
  for (NSUInteger i = 0; i < 32; ++i) dispatch_group_async(group, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSDictionary *snapshot = RBRATakeLaunchConfiguration(prepared, @"armsx2");
    [counterLock lock]; if ([snapshot[@"enabled"] boolValue]) ++granted; [counterLock unlock];
  });
  XCTestExpectation *done = [self expectationWithDescription:@"concurrent consumes"];
  dispatch_group_notify(group, dispatch_get_main_queue(), ^{ [done fulfill]; });
  [self waitFor:@[done]]; XCTAssertEqual(granted, 1u);
}
- (void)testExpiredHandleCannotLaunchAndReleasesPendingCredentials {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *prepared = [self prepare:@{}]; NSString *identifier = prepared[@"raSessionId"];
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock];
  NSMutableDictionary *expired = [hub.pending[identifier] mutableCopy];
  expired[@"expires"] = [NSDate dateWithTimeIntervalSinceNow:-1];
  hub.pending[identifier] = [expired copy];
  [hub.lock unlock];
  XCTAssertEqualObjects(RBRATakeLaunchConfiguration(prepared, @"armsx2")[@"enabled"], @NO);
  [hub.lock lock]; BOOL removed = hub.pending[identifier] == nil; [hub.lock unlock];
  XCTAssertTrue(removed);
}
- (void)testNotificationsFollowActivationAndSnapshotsCopyMutableInputs {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSMutableString *system = [@"ps2" mutableCopy], *language = [@"fr" mutableCopy];
  NSDictionary *prepared = [self prepare:@{@"system": system, @"language": language, @"notifications": @NO}];
  [system appendString:@"-changed"]; [language setString:@"ja"];
  NSDictionary *snapshot = RBRATakeLaunchConfiguration(prepared, @"armsx2");
  XCTAssertEqualObjects(snapshot[@"system"], @"ps2"); XCTAssertEqualObjects(snapshot[@"language"], @"fr");
  XCTAssertEqualObjects(snapshot[@"notifications"], @YES);
  XCTAssertThrowsSpecificNamed([(NSMutableDictionary *)snapshot setObject:@NO forKey:@"enabled"], NSException, NSInvalidArgumentException);
  XCTAssertEqualObjects(snapshot, [snapshot copy]);
  XCTAssertTrue(snapshot == [snapshot copy]);
  RBRAEndSession(snapshot);
  NSDictionary *disabled = [self start:@{@"enabled": @NO}];
  XCTAssertEqualObjects(disabled[@"notifications"], @NO); XCTAssertEqualObjects(disabled[@"token"], @"");
}
- (void)testUnsupportedEnginesAndMissingCredentialsCannotBecomeActive {
  NSDictionary *missing = [self start:@{}];
  XCTAssertEqualObjects(missing[@"enabled"], @NO);
  [self seedAccount:@"player" token:RBRAFixtureToken];
  for (NSString *engine in @[@"melonx"]) {
    NSDictionary *snapshot = [self start:@{@"engine": engine, @"supported": @YES}];
    XCTAssertEqualObjects(snapshot[@"supported"], @NO);
    XCTAssertEqualObjects(snapshot[@"enabled"], @NO);
    RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES, @"hardcoreActive": @YES});
    XCTAssertEqualObjects(self.lastState[@"active"], @NO);
    XCTAssertEqualObjects(self.lastState[@"hardcoreActive"], @NO);
  }
  // NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1: RPCS3 (PS3) owns an rcheevos client.
  NSDictionary *ps3 = [self start:@{@"engine": @"rpcs3", @"system": @"ps3", @"core": @"rpcs3", @"supported": @YES}];
  XCTAssertEqualObjects(ps3[@"supported"], @YES);
  XCTAssertEqualObjects(ps3[@"enabled"], @YES);
  RBRAPublishSessionState(ps3, @{@"active": @YES, @"gameLoaded": @YES, @"hardcoreActive": @NO});
  XCTAssertEqualObjects(self.lastState[@"active"], @YES);
  RBRAEndSession(ps3);
  id invalid = [self call:@"prepareSession" arguments:@{@"engine": @"invented"}];
  XCTAssertTrue([invalid isKindOfClass:FlutterError.class]);
  XCTAssertEqualObjects(((FlutterError *)invalid).code, @"RA_UNSUPPORTED");
}
- (void)testPendingHandleCapacityIsBounded {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *first = [self prepare:@{}], *last;
  for (NSUInteger i = 0; i < 12; ++i) last = [self prepare:@{}];
  RBRASessionHub *hub = RBRASessionHub.shared;
  [hub.lock lock]; NSUInteger count = hub.pending.count; [hub.lock unlock];
  XCTAssertLessThanOrEqual(count, 8u);
  XCTAssertEqualObjects(RBRATakeLaunchConfiguration(first, @"armsx2")[@"enabled"], @NO);
  XCTAssertEqualObjects(RBRATakeLaunchConfiguration(last, @"armsx2")[@"enabled"], @YES);
}
- (void)testLogoutKeepsTheRunningSnapshotAndInvalidatesPendingLaunches {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *running = [self start:@{}], *pending = [self prepare:@{}];
  RBRAPublishSessionState(running, @{@"active": @YES, @"gameLoaded": @YES, @"hardcoreActive": @YES});
  id response = [self call:@"logout" arguments:nil]; [self assertRedacted:response];
  XCTAssertEqualObjects(response[@"authenticated"], @NO);
  XCTAssertEqualObjects(running[@"token"], RBRAFixtureToken);
  XCTAssertEqualObjects(self.lastState[@"active"], @YES);
  XCTAssertEqualObjects(RBRATakeLaunchConfiguration(pending, @"armsx2")[@"enabled"], @NO);
  XCTAssertEqualObjects([self call:@"account" arguments:nil][@"authenticated"], @NO);
  NSDictionary *next = [self prepare:@{}]; XCTAssertEqualObjects(next[@"enabled"], @NO);
  RBRAEndSession(running); XCTAssertEqualObjects(self.lastState[@"ended"], @YES);
  [self assertEventsRedacted];
}
- (void)testAccountReplacementOnlyChangesTheNextLaunch {
  [self seedAccount:@"first" token:RBRAFixtureToken]; NSDictionary *running = [self start:@{}];
  [self seedAccount:@"second" token:@"next-fixture-token"];
  NSDictionary *prepared = [self prepare:@{@"hardcore": @NO}];
  XCTAssertEqualObjects(running[@"username"], @"first"); XCTAssertEqualObjects(running[@"token"], RBRAFixtureToken);
  NSDictionary *next = RBRATakeLaunchConfiguration(prepared, @"armsx2");
  XCTAssertEqualObjects(next[@"username"], @"second"); XCTAssertEqualObjects(next[@"token"], @"next-fixture-token");
  XCTAssertEqualObjects(next[@"hardcore"], @NO);
  RBRAPublishSessionState(next, @{@"active": @YES, @"gameLoaded": @YES, @"hardcoreActive": @YES});
  XCTAssertEqualObjects(self.lastState[@"hardcoreActive"], @NO);
}
- (void)testPublicSessionIdCannotForgePublishOrEndAuthority {
  [self seedAccount:@"player" token:RBRAFixtureToken]; NSDictionary *snapshot = [self start:@{}];
  NSDictionary *initial = self.lastState;
  NSDictionary *forged = @{ @"sessionId": snapshot[@"sessionId"] };
  RBRAPublishSessionState(forged, @{@"active": @YES, @"gameLoaded": @YES, @"hardcoreActive": @YES});
  RBRAEndSession(forged); XCTAssertEqualObjects(self.lastState, initial);
  NSMutableDictionary *equalCopy = [snapshot mutableCopy];
  RBRAPublishSessionState(equalCopy, @{@"active": @YES, @"gameLoaded": @YES});
  RBRAEndSession(equalCopy); XCTAssertEqualObjects(self.lastState, initial);
  RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES});
  XCTAssertEqualObjects(self.lastState[@"active"], @YES);
}
- (void)testPublishOnlyEmitsKnownCodesAndNonsecretFields {
  [self seedAccount:@"player" token:RBRAFixtureToken]; NSDictionary *snapshot = [self start:@{}];
  RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES, @"hardcoreActive": @YES,
    @"gameId": @17, @"totalCount": @10, @"unlockedCount": @3,
    @"username": @"must-not-enter-session-event", @"token": RBRAFixtureToken,
    @"password": RBRAFixturePassword, @"errorCode": [@"raw-server-message " stringByAppendingString:RBRAFixtureToken]});
  XCTAssertEqualObjects(self.lastState[@"gameId"], @17);
  XCTAssertEqualObjects(self.lastState[@"totalCount"], @10);
  XCTAssertEqualObjects(self.lastState[@"unlockedCount"], @3);
  XCTAssertNil(self.lastState[@"username"]);
  XCTAssertEqualObjects(self.lastState[@"errorCode"], @"RA_SESSION_ERROR");
  for (NSString *code in @[@"RA_LOGIN_FAILED", @"RA_NETWORK_UNAVAILABLE", @"hardcore_inactive", @"cleanup_pending", @"login_failed_-3", @""]) {
    RBRAPublishSessionState(snapshot, @{@"errorCode": code});
    XCTAssertEqualObjects(self.lastState[@"errorCode"], code);
  }
  NSMutableString *code = [@"RA_SYNC_PENDING" mutableCopy];
  RBRAPublishSessionState(snapshot, @{@"errorCode": code}); [code appendString:RBRAFixturePassword];
  XCTAssertEqualObjects(self.lastState[@"errorCode"], @"RA_SYNC_PENDING");
  [self assertRedacted:[self call:@"account" arguments:nil]];
  [self assertEventsRedacted];
}
- (void)testActivityRequiresALoadedGameAndMalformedStateCannotInjectFields {
  [self seedAccount:@"player" token:RBRAFixtureToken]; NSDictionary *snapshot = [self start:@{}];
  RBRAPublishSessionState(snapshot, @{@"active": @YES, @"hardcoreActive": @YES});
  XCTAssertEqualObjects(self.lastState[@"active"], @NO);
  XCTAssertEqualObjects(self.lastState[@"hardcoreActive"], @NO);
  NSDictionary *before = self.lastState;
  RBRAPublishSessionState((NSDictionary *)NSNull.null, @{});
  RBRAPublishSessionState(snapshot, (NSDictionary *)NSNull.null);
  RBRAEndSession((NSDictionary *)NSNull.null);
  XCTAssertEqualObjects(self.lastState, before);
  RBRAPublishSessionState(snapshot, @{@"active": RBRAFixtureToken, @"gameId": RBRAFixturePassword});
  XCTAssertEqualObjects(self.lastState[@"active"], @NO); XCTAssertNil(self.lastState[@"gameId"]);
  [self assertEventsRedacted];
}
- (void)testNewSessionDiscardsQueuedEventsAndLateCallbacksFromTheOldSession {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *oldPrepared = [self prepare:@{}], *newPrepared = [self prepare:@{@"engine": @"dolphin"}];
  __block NSDictionary *old, *current;
  RBRAOnMain(^{
    old = RBRATakeLaunchConfiguration(oldPrepared, @"armsx2");
    RBRAPublishSessionState(old, @{@"active": @YES, @"gameLoaded": @YES});
    current = RBRATakeLaunchConfiguration(newPrepared, @"dolphin");
    RBRAPublishSessionState(current, @{@"active": @YES, @"gameLoaded": @YES, @"gameId": @99});
    RBRAPublishSessionState(old, @{@"active": @NO, @"gameId": @1}); RBRAEndSession(old);
  });
  [self drainMain];
  XCTAssertEqualObjects(self.lastState[@"sessionId"], current[@"sessionId"]);
  XCTAssertEqualObjects(self.lastState[@"gameId"], @99); XCTAssertEqualObjects(self.lastState[@"ended"], @NO);
  XCTAssertEqual(self.messenger.recordedCalls.count, 1u);
  XCTAssertEqualObjects(self.messenger.recordedCalls.firstObject.arguments[@"sessionId"], current[@"sessionId"]);
}
- (void)testEndIsIdempotentAndInvalidatesQueuedActiveUpdates {
  [self seedAccount:@"player" token:RBRAFixtureToken]; NSDictionary *snapshot = [self start:@{}];
  [self drainMain]; [self.messenger clear];
  RBRAOnMain(^{
    RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES});
    RBRAEndSession(snapshot);
    NSDictionary *ended = self.lastState;
    RBRAEndSession(snapshot);
    RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES});
    XCTAssertEqualObjects(self.lastState, ended);
  });
  [self drainMain];
  XCTAssertEqual(self.messenger.recordedCalls.count, 1u);
  XCTAssertEqualObjects(self.lastState[@"ended"], @YES); XCTAssertEqualObjects(self.lastState[@"active"], @NO);
}
- (void)testConcurrentEngineUpdatesAreSerializedAndDeliveredOnMain {
  [self seedAccount:@"player" token:RBRAFixtureToken]; NSDictionary *snapshot = [self start:@{}];
  [self drainMain]; [self.messenger clear];
  NSUInteger initial = [self.lastState[@"stateRevision"] unsignedIntegerValue];
  dispatch_group_t group = dispatch_group_create();
  for (NSUInteger i = 0; i < 64; ++i) dispatch_group_async(group, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES, @"unlockedCount": @(i)});
  });
  XCTestExpectation *done = [self expectationWithDescription:@"concurrent native states"];
  dispatch_group_notify(group, dispatch_get_main_queue(), ^{ [done fulfill]; });
  [self waitFor:@[done]]; [self drainMain];
  XCTAssertEqual([self.lastState[@"stateRevision"] unsignedIntegerValue], initial + 64);
  NSUInteger previous = initial;
  for (FlutterMethodCall *event in self.messenger.recordedCalls) {
    NSUInteger revision = [event.arguments[@"stateRevision"] unsignedIntegerValue];
    XCTAssertGreaterThan(revision, previous); previous = revision;
  }
  XCTAssertEqual(previous, [self.lastState[@"stateRevision"] unsignedIntegerValue]);
  XCTAssertTrue(self.messenger.everySendWasOnMain);
}
- (void)testFinishSessionUsesOwnedSnapshotAndCancelsUnusedHandles {
  [self seedAccount:@"player" token:RBRAFixtureToken]; NSDictionary *running = [self start:@{}];
  NSDictionary *pending = [self prepare:@{}];
  [self call:@"finishSession" arguments:@{@"sessionId": pending[@"raSessionId"]}];
  XCTAssertEqualObjects(RBRATakeLaunchConfiguration(pending, @"armsx2")[@"enabled"], @NO);
  [self call:@"finishSession" arguments:@{@"sessionId": running[@"sessionId"]}];
  XCTAssertEqualObjects(self.lastState[@"ended"], @YES);
}
- (void)testRealLoginRequestAndKeychainSuccessNeverReturnTheToken {
  NSString *username = @"pláyer +&=?";
  NSString *password = [RBRAFixturePassword stringByAppendingString:@" é+&=?"];
  NSLock *requestLock = [NSLock new]; __block NSDictionary *observed;
  [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) {
    [requestLock lock]; observed = @{ @"url": request.URL.absoluteString, @"method": request.HTTPMethod,
      @"fields": RBRATestForm(request) }; [requestLock unlock];
    return @{@"status": @200, @"json": @{@"Success": @YES, @"User": username, @"Token": RBRAFixtureToken}};
  }];
  id response = [self call:@"login" arguments:@{@"username": [@"  " stringByAppendingString:username], @"password": password}];
  XCTAssertTrue([response isKindOfClass:NSDictionary.class]);
  XCTAssertEqualObjects(response[@"authenticated"], @YES); [self assertRedacted:response];
  [requestLock lock]; NSDictionary *request = observed; [requestLock unlock];
  XCTAssertEqualObjects(request[@"url"], @"https://retroachievements.org/dorequest.php");
  XCTAssertEqualObjects(request[@"method"], @"POST");
  XCTAssertEqualObjects(request[@"fields"][@"r"], @"login2");
  XCTAssertEqualObjects(request[@"fields"][@"u"], username); XCTAssertEqualObjects(request[@"fields"][@"p"], password);
  id account = [self call:@"account" arguments:nil]; [self assertRedacted:account];
  XCTAssertEqualObjects(account[@"authenticated"], @YES); XCTAssertEqualObjects(account[@"username"], username);
  [self assertFlagsSurviveTheCodec:account];
  NSDictionary *snapshot = [self start:@{}]; XCTAssertEqualObjects(snapshot[@"token"], RBRAFixtureToken);
  [self assertEventsRedacted];
}
- (void)testAuthenticationErrorsDiscardRawResponseAndLeaveStorageEmpty {
  [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) {
    return @{@"status": @200, @"json": @{@"Success": @NO,
      @"Error": RBRAFixturePassword, @"Token": RBRAFixtureToken}};
  }];
  id response = [self call:@"login" arguments:@{@"username": @"player", @"password": RBRAFixturePassword}];
  XCTAssertTrue([response isKindOfClass:FlutterError.class]);
  XCTAssertEqualObjects(((FlutterError *)response).code, @"RA_AUTHENTICATION_FAILED");
  [self assertRedacted:response];
  XCTAssertEqualObjects([self call:@"account" arguments:nil][@"authenticated"], @NO);
}
- (void)testLogoutCancelsPendingLoginWithoutRepopulatingKeychain {
  XCTestExpectation *started = [self expectationWithDescription:@"request started"];
  [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) {
    [started fulfill];
    return @{@"status": @200, @"hold": @YES, @"json": @{@"Success": @YES, @"User": @"late", @"Token": RBRAFixtureToken}};
  }];
  XCTestExpectation *completed = [self expectationWithDescription:@"cancelled login answered"];
  __block id loginResponse;
  RBRAOnMain(^{ [self.plugin handleMethodCall:[FlutterMethodCall methodCallWithMethodName:@"login"
    arguments:@{@"username": @"late", @"password": RBRAFixturePassword}]
    result:^(id value) { loginResponse = value; [completed fulfill]; }]; });
  [self waitFor:@[started]];
  [self call:@"logout" arguments:nil]; [self waitFor:@[completed]];
  XCTAssertTrue([loginResponse isKindOfClass:FlutterError.class]);
  XCTAssertEqualObjects(((FlutterError *)loginResponse).code, @"RA_CANCELLED");
  [self assertRedacted:loginResponse];
  XCTAssertEqualObjects([self call:@"account" arguments:nil][@"authenticated"], @NO);
}
- (void)testSupersededLoginCannotReplaceNewerAccount {
  XCTestExpectation *started = [self expectationWithDescription:@"first login started"];
  [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) {
    NSString *username = RBRATestForm(request)[@"u"];
    if ([username isEqualToString:@"first"]) [started fulfill];
    return @{@"status": @200, @"hold": @([username isEqualToString:@"first"]),
      @"json": @{@"Success": @YES, @"User": username, @"Token": RBRAFixtureToken}};
  }];
  XCTestExpectation *completed = [self expectationWithDescription:@"first login cancelled"];
  __block id first;
  RBRAOnMain(^{ [self.plugin handleMethodCall:[FlutterMethodCall methodCallWithMethodName:@"login"
    arguments:@{@"username": @"first", @"password": RBRAFixturePassword}]
    result:^(id value) { first = value; [completed fulfill]; }]; });
  [self waitFor:@[started]];
  id second = [self call:@"login" arguments:@{@"username": @"second", @"password": RBRAFixturePassword}];
  [self waitFor:@[completed]];
  XCTAssertEqualObjects(((FlutterError *)first).code, @"RA_CANCELLED");
  XCTAssertEqualObjects(second[@"username"], @"second");
  XCTAssertEqualObjects([self call:@"account" arguments:nil][@"username"], @"second");
  [self assertRedacted:first]; [self assertRedacted:second];
}
- (void)testSignInSurvivesALostKeychainItemAndSignOutRemovesBothCopies {
  [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) {
    return @{@"status": @200, @"json": @{@"Success": @YES, @"User": @"player", @"Token": RBRAFixtureToken}};
  }];
  id response = [self call:@"login" arguments:@{@"username": @"player", @"password": RBRAFixturePassword}];
  XCTAssertEqualObjects(response[@"authenticated"], @YES);
  XCTAssertTrue([NSFileManager.defaultManager fileExistsAtPath:RBRATestFallbackPath()]);
  NSNumber *excluded = nil;
  [[NSURL fileURLWithPath:RBRATestFallbackPath()] getResourceValue:&excluded forKey:NSURLIsExcludedFromBackupKey error:nil];
  XCTAssertEqualObjects(excluded, @YES);
  // The 2 November 2026 recording: the Keychain item is gone at the next launch.
  OSStatus removed = SecItemDelete((__bridge CFDictionaryRef)RBRATestKeychainQuery());
  XCTAssertEqual(removed, errSecSuccess);
  id account = [self call:@"account" arguments:nil]; [self assertRedacted:account];
  XCTAssertEqualObjects(account[@"authenticated"], @YES);
  [self assertFlagsSurviveTheCodec:account];
  XCTAssertEqualObjects(account[@"username"], @"player");
  XCTAssertEqualObjects(account[@"storage"], @"file");
  XCTAssertEqualObjects(account[@"keychainStatus"], @((int)errSecItemNotFound));
  // The Keychain item is restored and the next launch can use the token.
  XCTAssertEqualObjects([self call:@"account" arguments:nil][@"storage"], @"keychain");
  NSDictionary *snapshot = [self start:@{}]; XCTAssertEqualObjects(snapshot[@"token"], RBRAFixtureToken);
  [self call:@"logout" arguments:nil];
  XCTAssertFalse([NSFileManager.defaultManager fileExistsAtPath:RBRATestFallbackPath()]);
  id signedOut = [self call:@"account" arguments:nil];
  XCTAssertEqualObjects(signedOut[@"authenticated"], @NO);
  [self assertFlagsSurviveTheCodec:signedOut];
  XCTAssertEqualObjects(signedOut[@"storage"], @"none");
}
- (void)testInvalidKeychainDataFailsClosedWithoutEchoingContents {
  [self writeRawKeychain:[RBRAFixtureToken dataUsingEncoding:NSUTF8StringEncoding]];
  for (NSString *method in @[@"account", @"prepareSession"]) {
    id response = [self call:method arguments:@{@"engine": @"armsx2", @"enabled": @YES, @"supported": @YES}];
    XCTAssertTrue([response isKindOfClass:FlutterError.class]);
    XCTAssertEqualObjects(((FlutterError *)response).code, @"RA_STORAGE_UNAVAILABLE");
    [self assertRedacted:response];
  }
}
- (void)testRedirectDelegateNeverForwardsCredentials {
  RBRANoRedirectDelegate *delegate = [RBRANoRedirectDelegate new];
  NSURLRequest *redirect = [NSURLRequest requestWithURL:[NSURL URLWithString:@"https://unexpected.example.invalid/"]];
  NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:[NSURL URLWithString:@"https://retroachievements.org/dorequest.php"]
    statusCode:307 HTTPVersion:@"HTTP/1.1" headerFields:@{}];
  __block BOOL answered = NO;
  NSURLSession *session = [NSURLSession sessionWithConfiguration:NSURLSessionConfiguration.ephemeralSessionConfiguration];
  NSURLSessionDataTask *task = [session dataTaskWithRequest:redirect];
  [delegate URLSession:session task:task willPerformHTTPRedirection:response
    newRequest:redirect completionHandler:^(NSURLRequest *request) { answered = YES; XCTAssertNil(request); }];
  [session invalidateAndCancel];
  XCTAssertTrue(answered);
}
- (void)testLegacyMigrationImportAndInterruptedDBRetryKeepSourcesIntact {
  [self writeLegacy:@"armsx2" contents:@"[Achievements]\nUsername=legacy-player\nEnabled=true\nChallengeMode=true\nToken=old-base-token\n"];
  [self writeLegacy:@"secrets" contents:[NSString stringWithFormat:@"[Achievements]\nToken=%@\n", RBRAFixtureToken]];
  NSString *iniPath = RBRATestLegacyPaths()[@"armsx2"], *secretsPath = RBRATestLegacyPaths()[@"secrets"];
  NSData *iniBefore = [NSData dataWithContentsOfFile:iniPath], *secretsBefore = [NSData dataWithContentsOfFile:secretsPath];
  NSDictionary *inspection = [self call:@"inspectLegacy" arguments:nil]; [self assertRedacted:inspection];
  XCTAssertEqualObjects(inspection[@"central"], @NO); XCTAssertEqual([inspection[@"candidates"] count], 1u);
  NSDictionary *candidate = [inspection[@"candidates"] firstObject];
  XCTAssertEqualObjects(candidate[@"username"], @"legacy-player");
  XCTAssertEqualObjects(candidate[@"enabled"], @YES); XCTAssertEqualObjects(candidate[@"hardcore"], @YES);
  id imported = [self call:@"importLegacy" arguments:@{@"id": candidate[@"id"]}]; [self assertRedacted:imported];
  XCTAssertEqualObjects(imported[@"authenticated"], @YES);
  XCTAssertEqualObjects(imported[@"policy"], (@{@"enabled": @YES, @"hardcore": @YES}));
  // The app's SQLite transaction has not completed yet. Re-inspection must
  // recover the same policy saved alongside the central Keychain credential.
  NSDictionary *resumed = [self call:@"inspectLegacy" arguments:nil]; [self assertRedacted:resumed];
  XCTAssertEqualObjects(resumed[@"central"], @YES);
  XCTAssertEqualObjects(resumed[@"policy"], imported[@"policy"]);
  XCTAssertEqual([resumed[@"candidates"] count], 0u);
  NSDictionary *snapshot = [self start:@{}]; XCTAssertEqualObjects(snapshot[@"token"], RBRAFixtureToken);
  [self call:@"completeLegacy" arguments:nil];
  id stale = [self call:@"importLegacy" arguments:@{@"id": candidate[@"id"]}];
  XCTAssertTrue([stale isKindOfClass:FlutterError.class]);
  XCTAssertEqualObjects(((FlutterError *)stale).code, @"RA_MIGRATION_EXPIRED");
  XCTAssertEqualObjects([NSData dataWithContentsOfFile:iniPath], iniBefore);
  XCTAssertEqualObjects([NSData dataWithContentsOfFile:secretsPath], secretsBefore);
  [self assertEventsRedacted];
}
- (void)testAbsentNSUserDefaultDoesNotMigrateLibretroAsEnabled {
  [self seedLegacySuffix:@".libretro.retroachievements" username:@"legacy" token:RBRAFixtureToken];
  XCTAssertNil([NSUserDefaults.standardUserDefaults objectForKey:@"libretro.achievements.enabled"]);
  NSDictionary *inspection = [self call:@"inspectLegacy" arguments:nil]; [self assertRedacted:inspection];
  XCTAssertEqual([inspection[@"candidates"] count], 1u);
  NSDictionary *candidate = [inspection[@"candidates"] firstObject];
  XCTAssertEqualObjects(candidate[@"enabled"], @NO); XCTAssertEqualObjects(candidate[@"hardcore"], @NO);
  id imported = [self call:@"importLegacy" arguments:@{@"id": candidate[@"id"]}];
  XCTAssertEqualObjects(imported[@"policy"][@"enabled"], @NO);
  NSMutableDictionary *legacy = RBRATestKeychainQueryForSuffix(@".libretro.retroachievements");
  XCTAssertEqual(SecItemCopyMatching((__bridge CFDictionaryRef)legacy, NULL), errSecSuccess);
}
- (void)testLogoutAndExplicitLoginInvalidateLegacySelectionHandles {
  [self seedLegacySuffix:@".libretro.retroachievements" username:@"legacy" token:RBRAFixtureToken];
  NSDictionary *inspection = [self call:@"inspectLegacy" arguments:nil];
  NSString *oldID = [inspection[@"candidates"] firstObject][@"id"];
  [self call:@"logout" arguments:nil];
  id afterLogout = [self call:@"importLegacy" arguments:@{@"id": oldID}];
  XCTAssertTrue([afterLogout isKindOfClass:FlutterError.class]);
  XCTAssertEqualObjects(((FlutterError *)afterLogout).code, @"RA_MIGRATION_EXPIRED");
  inspection = [self call:@"inspectLegacy" arguments:nil];
  NSString *beforeLogin = [inspection[@"candidates"] firstObject][@"id"];
  [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) {
    return @{@"status": @200, @"json": @{@"Success": @NO}};
  }];
  [self call:@"login" arguments:@{@"username": @"new-account", @"password": RBRAFixturePassword}];
  id afterLogin = [self call:@"importLegacy" arguments:@{@"id": beforeLogin}];
  XCTAssertTrue([afterLogin isKindOfClass:FlutterError.class]);
  XCTAssertEqualObjects(((FlutterError *)afterLogin).code, @"RA_MIGRATION_EXPIRED");
  XCTAssertEqualObjects([self call:@"account" arguments:nil][@"authenticated"], @NO);
  [self assertRedacted:afterLogout]; [self assertRedacted:afterLogin];
}
- (void)testRestrictionLabelsUseAllTwelveExplicitAppLanguages {
  for (NSString *locale in @[@"en", @"es", @"ru", @"zh", @"zh_Hant", @"pt", @"fr", @"de", @"it", @"id", @"ja", @"ko"])
    for (NSString *key in @[@"hardcoreBlocked", @"hardcorePause", @"managedInTab"])
      XCTAssertGreaterThan(RBRALocalizedText(key, locale).length, 0u);
  XCTAssertEqualObjects(RBRALocalizedText(@"hardcoreBlocked", @"fr-CA"), @"Indisponible en mode Hardcore");
  XCTAssertEqualObjects(RBRALocalizedText(@"hardcoreBlocked", @"zh-Hant-TW"), RBRALocalizedText(@"hardcoreBlocked", @"zh_Hant"));
  XCTAssertEqualObjects(RBRALocalizedText(@"hardcoreBlocked", @"zh-HK"), RBRALocalizedText(@"hardcoreBlocked", @"zh_Hant"));
  XCTAssertNotEqualObjects(RBRALocalizedText(@"hardcoreBlocked", @"zh"), RBRALocalizedText(@"hardcoreBlocked", @"zh_Hant"));
}
// Build 609 follow-up: launch status classification, sign-in error classes and
// the display-only presenter lifecycle.
- (void)testStatusClassificationUsesObservedEngineStateOnly {
  NSDictionary *texts = @{@"active": @"Succès actifs", @"progress": @"{unlocked}/{total} débloqués",
    @"hardcoreOn": @"Hardcore activé", @"hardcoreOff": @"Hardcore désactivé",
    @"hardcoreNotApplied": @"Hardcore non appliqué", @"unknownGame": @"Jeu non reconnu"};
  NSDictionary *base = @{@"sessionId": @"s", @"enabled": @YES, @"supported": @YES, @"requested": @YES,
    @"hardcore": @YES, @"username": @"player", @"token": RBRAFixtureToken, @"statusText": texts};
  // Switched off by the player: never any in-game notice.
  XCTAssertNil(RBRAStatusForState(@{@"enabled": @NO, @"requested": @NO, @"supported": @YES}, @{}, NO));
  XCTAssertEqualObjects(RBRAStatusForState(@{@"enabled": @NO, @"requested": @YES, @"supported": @NO}, @{}, NO)[@"key"], @"unsupported");
  XCTAssertEqualObjects(RBRAStatusForState(@{@"enabled": @NO, @"requested": @YES, @"supported": @YES}, @{}, NO)[@"key"], @"signIn");
  // A signed-in account alone is pending, not active.
  NSDictionary *pending = RBRAStatusForState(base, @{@"loggedIn": @YES}, NO);
  XCTAssertEqualObjects(pending[@"key"], @"pending"); XCTAssertEqualObjects(pending[@"final"], @NO);
  NSDictionary *active = RBRAStatusForState(base, @{@"active": @YES, @"gameLoaded": @YES,
    @"hardcoreActive": @YES, @"totalCount": @10, @"unlockedCount": @3}, NO);
  XCTAssertEqualObjects(active[@"key"], @"activeHardcore");
  XCTAssertEqualObjects(active[@"message"], @"Succès actifs · player · 3/10 débloqués · Hardcore activé");
  NSDictionary *notApplied = RBRAStatusForState(base, @{@"active": @YES, @"gameLoaded": @YES}, NO);
  XCTAssertEqualObjects(notApplied[@"key"], @"active");
  XCTAssertTrue([notApplied[@"message"] hasSuffix:@"Hardcore non appliqué"]);
  NSDictionary *codes = @{@"login_failed_-34": @"authRejected", @"login_failed_-35": @"authRejected",
    @"RA_AUTHENTICATION_FAILED": @"authRejected", @"login_failed_-32": @"network",
    @"RA_NETWORK_UNAVAILABLE": @"network", @"login_failed_-1": @"loginFailed",
    @"RA_GAME_NOT_RECOGNIZED": @"unknownGame", @"RA_GAME_HASH_FAILED": @"hashFailed",
    @"RA_NO_ACHIEVEMENTS": @"noAchievements",
    @"RA_ACHIEVEMENTS_UNSUPPORTED": @"setUnsupported", @"RA_HARDCORE_OPTIONS": @"hardcoreOptions",
    @"RA_GAME_LOAD_FAILED": @"loadFailed", @"configuration_failed": @"unavailable",
    @"RA_SYNC_PENDING": @"pending", @"cleanup_pending": @"pending", @"": @"pending"};
  for (NSString *code in codes)
    XCTAssertEqualObjects(RBRAStatusForState(base, @{@"errorCode": code}, NO)[@"key"], codes[code], @"%@", code);
  XCTAssertEqualObjects(RBRAStatusForState(base, @{@"errorCode": @"RA_GAME_NOT_RECOGNIZED"}, NO)[@"message"], @"Jeu non reconnu");
  // PS3 (2 November 2026): RetroAchievements links almost no PS3 disc yet, so
  // an unknown hash there is not blamed on the player's dump.
  NSMutableDictionary *ps3 = [base mutableCopy];
  ps3[@"engine"] = @"rpcs3";
  NSDictionary *ps3Unknown = RBRAStatusForState(ps3, @{@"errorCode": @"RA_GAME_NOT_RECOGNIZED"}, NO);
  XCTAssertEqualObjects(ps3Unknown[@"key"], @"unknownGamePs3");
  XCTAssertEqualObjects(ps3Unknown[@"message"],
    @"This PS3 game is not (yet) listed by RetroAchievements: no achievements to track.");
  XCTAssertEqualObjects(RBRAStatusForState(ps3, @{@"errorCode": @"RA_GAME_HASH_FAILED"}, NO)[@"key"], @"hashFailed");
  ps3[@"engine"] = @"dolphin";
  XCTAssertEqualObjects(RBRAStatusForState(ps3, @{@"errorCode": @"RA_GAME_NOT_RECOGNIZED"}, NO)[@"key"], @"unknownGame");
  XCTAssertEqualObjects(RBRAStatusForState(base, @{}, YES)[@"key"], @"unconfirmed");
  for (NSDictionary *state in @[@{}, @{@"active": @YES, @"gameLoaded": @YES}, @{@"errorCode": @"RA_LOGIN_FAILED"}])
    [self assertRedacted:RBRAStatusForState(base, state, NO)];
}
- (void)testSignInSeparatesRefusalNetworkAndUnexpectedServerAnswers {
  NSArray *cases = @[
    @[@{@"status": @200, @"data": [@"<html>portal</html>" dataUsingEncoding:NSUTF8StringEncoding]}, @"RA_SERVER_ERROR"],
    @[@{@"status": @503, @"json": @{}}, @"RA_SERVER_ERROR"],
    @[@{@"status": @429, @"json": @{}}, @"RA_RATE_LIMITED"],
    @[@{@"status": @401, @"json": @{@"Success": @NO, @"Code": @"invalid_credentials"}}, @"RA_AUTHENTICATION_FAILED"],
    @[@{@"error": [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorNotConnectedToInternet userInfo:nil]}, @"RA_NETWORK_UNAVAILABLE"],
    @[@{@"status": @200, @"json": @{@"Success": @YES, @"User": @"player"}}, @"RA_SERVER_ERROR"],
  ];
  for (NSArray *entry in cases) {
    [RBRATestURLProtocol setResponse:^NSDictionary *(NSURLRequest *request) { return entry[0]; }];
    id response = [self call:@"login" arguments:@{@"username": @"player", @"password": RBRAFixturePassword}];
    XCTAssertTrue([response isKindOfClass:FlutterError.class]);
    XCTAssertEqualObjects(((FlutterError *)response).code, entry[1]);
    [self assertRedacted:response];
    XCTAssertEqualObjects([self call:@"account" arguments:nil][@"authenticated"], @NO);
  }
}
- (void)testStatusPresenterAnnouncesOnceAndNeverOutlivesItsLaunch {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *snapshot = [self start:@{@"requested": @YES,
    @"statusText": @{@"active": @"Succès actifs", @"token": RBRAFixtureToken}}];
  NSMutableArray<NSString *> *keys = [NSMutableArray array];
  NSMutableArray<NSString *> *messages = [NSMutableArray array];
  XCTestExpectation *announced = [self expectationWithDescription:@"active status"];
  RBRASetStatusPresenter(snapshot, ^(NSString *key, NSString *title, NSString *message, NSTimeInterval duration) {
    XCTAssertTrue(NSThread.isMainThread);
    XCTAssertEqualObjects(title, @"RetroAchievements");
    XCTAssertGreaterThan(duration, 0);
    [keys addObject:key]; [messages addObject:message];
    if ([key hasPrefix:@"active"]) [announced fulfill];
  });
  RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES, @"loggedIn": @YES,
    @"totalCount": @4, @"unlockedCount": @1});
  [self waitFor:@[announced]];
  // The same state published again is not announced twice.
  RBRAPublishSessionState(snapshot, @{@"active": @YES, @"gameLoaded": @YES});
  [self drainMain];
  // Hardcore was requested but the engine did not report it applied, and the
  // final state was known before the initial delay: no pending notice.
  XCTAssertEqualObjects(keys, (@[@"active"]));
  XCTAssertTrue([messages.firstObject hasPrefix:@"Succès actifs · player · 1/4"]);
  XCTAssertEqualObjects(self.lastState[@"loggedIn"], @YES);
  for (NSString *message in messages) XCTAssertFalse([message containsString:RBRAFixtureToken]);
  // After the game ends (or a new launch), the old presenter is never called.
  RBRAEndSession(snapshot);
  NSUInteger before = keys.count;
  RBRAPublishSessionState(snapshot, @{@"errorCode": @"RA_LOGIN_FAILED"});
  [self drainMain];
  XCTAssertEqual(keys.count, before);
  [self assertEventsRedacted];
}
- (void)testPresenterCannotAttachToAStaleOrForgedSnapshot {
  [self seedAccount:@"player" token:RBRAFixtureToken];
  NSDictionary *old = [self start:@{}];
  NSDictionary *current = [self start:@{}];
  __block NSUInteger calls = 0;
  RBRAStatusPresenter presenter = ^(NSString *key, NSString *title, NSString *message, NSTimeInterval duration) { calls++; };
  RBRASetStatusPresenter(old, presenter);
  RBRASetStatusPresenter([current mutableCopy], presenter);
  RBRASetStatusPresenter((NSDictionary *)NSNull.null, presenter);
  RBRAPublishSessionState(current, @{@"errorCode": @"RA_LOGIN_FAILED"});
  [self drainMain];
  XCTAssertEqual(calls, 0u);
}
@end
