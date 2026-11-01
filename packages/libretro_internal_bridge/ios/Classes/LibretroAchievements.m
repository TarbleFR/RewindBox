#import <achievement_translation/RBAchievementTranslation.h>
#import <retro_achievements_session/RBRASession.h>
#import "LibretroAchievements.h"

#import "LibretroCoreHost.h"

#include <stdatomic.h>

#include "rc_api_request.h"
#include "rc_client.h"
#include "rc_hash.h"
#include "rc_libretro.h"

/// rc_libretro's memory-info callback carries no context pointer. Only the
/// emulation thread initializes/reads these maps, for its current core.
static __unsafe_unretained LibretroCoreHost *gAchievementHost = nil;

@implementation LibretroAchievements {
  rc_client_t *_client;
  rc_libretro_memory_regions_t _regions;
  BOOL _regionsReady;
  unsigned _consoleId;
  LibretroCoreHost *_host;
  NSDictionary *_configuration;
  NSURLSession *_urlSession;
  NSString *_userAgent;
  NSString *_contentPath;
  NSString *_errorCode;
  NSLock *_responseLock;
  NSLock *_lifecycleLock;
  NSMutableArray<dispatch_block_t> *_responses;
  BOOL _startRequested;
  BOOL _loadStarted;
  BOOL _failed;
  BOOL _evaluated;
  BOOL _active;
  _Atomic bool _gameReady;
  _Atomic bool _loggedIn;
  _Atomic bool _hardcoreActive;
  _Atomic bool _shutdown;
  _Atomic bool _identifying;
  _Atomic uint64_t _callbackGeneration;
  _Atomic unsigned _totalAchievements;
  _Atomic unsigned _unlockedAchievements;
}

// Removed with the in-game account page in step 3. A legacy menu cannot
// alter the immutable launch snapshot or restore an old account.
+ (BOOL)enabled { return NO; }
+ (void)setEnabled:(BOOL)enabled { (void)enabled; }
+ (BOOL)hasStoredLogin { return NO; }
- (void)loginWithUsername:(NSString *)username password:(NSString *)password completion:(void (^)(BOOL))completion {
  (void)username; (void)password;
  if (completion != nil) completion(NO);
}
- (void)logout {}

+ (BOOL)isHardcoreOptionAllowedForLibrary:(NSString *)library consoleId:(unsigned)consoleId
                                     key:(NSString *)key value:(NSString *)value {
  const rc_disallowed_setting_t *core = rc_libretro_get_disallowed_settings(library.UTF8String);
  const rc_disallowed_setting_t *system =
      rc_libretro_get_disallowed_settings_for_system(library.UTF8String, consoleId);
  // The shipped GX Wide adapter also exposes the original genesis_plus_gx_
  // keys (the packaged-core option contract records that prefix). Apply the
  // existing GX restrictions to those keys as well; no extra rule is invented.
  const rc_disallowed_setting_t *baseGX = [library isEqualToString:@"Genesis Plus GX Wide"]
      ? rc_libretro_get_disallowed_settings("Genesis Plus GX") : NULL;
  return (baseGX == NULL || rc_libretro_is_setting_allowed(baseGX, key.UTF8String, value.UTF8String)) &&
         (core == NULL || rc_libretro_is_setting_allowed(core, key.UTF8String, value.UTF8String)) &&
         (system == NULL || rc_libretro_is_setting_allowed(system, key.UTF8String, value.UTF8String));
}

#pragma mark - rcheevos callbacks

static void CoreMemoryInfo(uint32_t identifier, rc_libretro_core_memory_info_t *info) {
  size_t size = 0;
  info->data = (uint8_t *)[gAchievementHost memoryDataForIdentifier:identifier size:&size];
  info->size = info->data != NULL ? size : 0;
}

static uint32_t ReadMemory(uint32_t address, uint8_t *buffer, uint32_t count, rc_client_t *client) {
  LibretroAchievements *achievements = (__bridge LibretroAchievements *)rc_client_get_userdata(client);
  if (achievements == nil || atomic_load(&achievements->_shutdown) || !achievements->_regionsReady) return 0;
  return rc_libretro_memory_read(&achievements->_regions, address, buffer, count);
}

static void ServerCall(const rc_api_request_t *request, rc_client_server_callback_t callback, void *callbackData,
                       rc_client_t *client) {
  LibretroAchievements *achievements = (__bridge LibretroAchievements *)rc_client_get_userdata(client);
  NSURL *url = request->url != NULL ? [NSURL URLWithString:[NSString stringWithUTF8String:request->url]] : nil;
  if (achievements == nil || url == nil) {
    rc_api_server_response_t failure = {NULL, 0, RC_API_SERVER_RESPONSE_CLIENT_ERROR};
    callback(&failure, callbackData);
    return;
  }
  const uint64_t generation = atomic_load(&achievements->_callbackGeneration);
  NSMutableURLRequest *urlRequest = [NSMutableURLRequest requestWithURL:url];
  [urlRequest setValue:achievements->_userAgent forHTTPHeaderField:@"User-Agent"];
  if (request->post_data != NULL) {
    urlRequest.HTTPMethod = @"POST";
    urlRequest.HTTPBody = [NSData dataWithBytes:request->post_data length:strlen(request->post_data)];
    NSString *type = request->content_type != NULL ? [NSString stringWithUTF8String:request->content_type]
                                                   : @"application/x-www-form-urlencoded";
    [urlRequest setValue:type forHTTPHeaderField:@"Content-Type"];
  }
  // A background hash may finish after the game has closed. Do not start a
  // request on an invalidated NSURLSession, or deliver it to another launch.
  [achievements->_responseLock lock];
  if (atomic_load(&achievements->_shutdown)) {
    [achievements->_responseLock unlock];
    rc_api_server_response_t failure = {NULL, 0, RC_API_SERVER_RESPONSE_CLIENT_ERROR};
    callback(&failure, callbackData);
    return;
  }
  NSURLSessionDataTask *task = [achievements->_urlSession
      dataTaskWithRequest:urlRequest
        completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
          // Copy and retain the bytes, then let the emulation thread feed the
          // response to rcheevos. Never race do_frame or client destruction.
          [achievements->_responseLock lock];
          if (!atomic_load(&achievements->_shutdown) &&
              generation == atomic_load(&achievements->_callbackGeneration)) {
            NSData *body = [data copy];
            NSInteger status = error != nil ? RC_API_SERVER_RESPONSE_RETRYABLE_CLIENT_ERROR
                : [response isKindOfClass:NSHTTPURLResponse.class]
                    ? ((NSHTTPURLResponse *)response).statusCode : RC_API_SERVER_RESPONSE_CLIENT_ERROR;
            [achievements->_responses addObject:[^{
              if (atomic_load(&achievements->_shutdown) ||
                  generation != atomic_load(&achievements->_callbackGeneration)) return;
              rc_api_server_response_t serverResponse = {body.bytes, body.length, (int)status};
              callback(&serverResponse, callbackData);
            } copy]];
          }
          [achievements->_responseLock unlock];
        }];
  [task resume];
  [achievements->_responseLock unlock];
}

static void EventHandler(const rc_client_event_t *event, rc_client_t *client) {
  LibretroAchievements *achievements = (__bridge LibretroAchievements *)rc_client_get_userdata(client);
  if (achievements == nil || event == NULL || atomic_load(&achievements->_shutdown) || achievements->_failed) return;
  if (event->type == RC_CLIENT_EVENT_ACHIEVEMENT_TRIGGERED && event->achievement != NULL) {
    NSString *title = event->achievement->title != NULL ? [NSString stringWithUTF8String:event->achievement->title] : @"";
    NSUInteger achievementID = event->achievement->id;
    NSString *description = event->achievement->description != NULL
        ? [NSString stringWithUTF8String:event->achievement->description] : @"";
    [achievements refreshSummary];
    [achievements publishState];
    // Presentation only: the rcheevos event/award path above is never gated or
    // delayed by notifications or translation. This launch owns the preference.
    if (![achievements->_configuration[@"notifications"] boolValue]) return;
    const uint64_t generation = atomic_load(&achievements->_callbackGeneration);
    dispatch_async(dispatch_get_main_queue(), ^{
      if (atomic_load(&achievements->_shutdown) ||
          generation != atomic_load(&achievements->_callbackGeneration)) return;
      if (achievements.unlocked != nil) achievements.unlocked(achievementID, title ?: @"", description ?: @"");
    });
  } else if (event->type == RC_CLIENT_EVENT_SERVER_ERROR) {
    // rcheevos retains its own award/retry/synchronization behavior.
    achievements->_errorCode = @"RA_SERVER_ERROR";
    [achievements publishState];
  } else if (event->type == RC_CLIENT_EVENT_DISCONNECTED) {
    achievements->_errorCode = @"RA_SYNC_PENDING";
    [achievements publishState];
  } else if (event->type == RC_CLIENT_EVENT_RECONNECTED) {
    achievements->_errorCode = @"";
    [achievements publishState];
  } else if (event->type == RC_CLIENT_EVENT_RESET) {
    // Hardcore is set only before loading, never toggled on mid-game. If a
    // future caller violates that rule, fail closed rather than evaluate an
    // unreset game or reset the player's game behind their back.
    [achievements failWithCode:@"RA_HARDCORE_RESET_REQUIRED"];
  }
}

static void GameLoaded(int result, const char *message, rc_client_t *client, void *userdata) {
  (void)message;
  LibretroAchievements *achievements = (__bridge LibretroAchievements *)rc_client_get_userdata(client);
  if (achievements == nil || atomic_load(&achievements->_shutdown) || achievements->_failed ||
      (uint64_t)(uintptr_t)userdata != atomic_load(&achievements->_callbackGeneration)) return;
  achievements->_loadStarted = NO;
  const rc_client_game_t *game = result == RC_OK ? rc_client_get_game_info(client) : NULL;
  if (result != RC_OK) {
    [achievements->_host appendLog:[NSString stringWithFormat:@"[HOST] RA game load failed (%d)", result]];
    [achievements failWithCode:@"RA_GAME_LOAD_FAILED"];
    return;
  }
  // rc_client_get_game_info can return a dummy record for an unknown hash.
  if (game == NULL || game->id == 0 || !rc_client_is_game_loaded(client)) {
    [achievements failWithCode:@"RA_GAME_NOT_RECOGNIZED"];
    return;
  }
  atomic_store(&achievements->_gameReady, true);
  achievements->_evaluated = NO;
  achievements->_errorCode = @"";
  [achievements refreshSummary];
  // Copy source metadata on the client thread; never retain rcheevos pointers.
  rc_client_achievement_list_t *list = rc_client_create_achievement_list(client,
      RC_CLIENT_ACHIEVEMENT_CATEGORY_CORE_AND_UNOFFICIAL, RC_CLIENT_ACHIEVEMENT_LIST_GROUPING_LOCK_STATE);
  NSMutableArray *sources = [NSMutableArray array];
  if (list != NULL) {
    for (uint32_t b = 0; b < list->num_buckets; ++b) {
      const rc_client_achievement_bucket_t *bucket = &list->buckets[b];
      for (uint32_t i = 0; i < bucket->num_achievements; ++i) {
        const rc_client_achievement_t *item = bucket->achievements[i];
        if (item == NULL) continue;
        [sources addObject:@{@"id": @(item->id),
            @"title": item->title ? ([NSString stringWithUTF8String:item->title] ?: @"") : @"",
            @"description": item->description ? ([NSString stringWithUTF8String:item->description] ?: @"") : @""}];
      }
    }
    rc_client_destroy_achievement_list(list);
  }
  RBAchievementPrefetch(sources);
  [achievements publishState];
}

static void TokenLogin(int result, const char *message, rc_client_t *client, void *userdata) {
  (void)message;
  LibretroAchievements *achievements = (__bridge LibretroAchievements *)rc_client_get_userdata(client);
  if (achievements == nil || atomic_load(&achievements->_shutdown) || achievements->_failed ||
      (uint64_t)(uintptr_t)userdata != atomic_load(&achievements->_callbackGeneration)) return;
  if (result == RC_OK && rc_client_get_user_info(client) != NULL) {
    atomic_store(&achievements->_loggedIn, true);
    [achievements loadGame];
  } else {
    [achievements->_host appendLog:[NSString stringWithFormat:@"[HOST] RA token login failed (%d)", result]];
    [achievements failWithCode:@"RA_LOGIN_FAILED"];
  }
  [achievements publishState];
}

#pragma mark - Lifecycle

- (instancetype)initWithConsoleId:(unsigned)consoleId
                            host:(LibretroCoreHost *)host
                   configuration:(NSDictionary *)configuration {
  self = [super init];
  if (self) {
    _consoleId = consoleId;
    _host = host;
    _configuration = [configuration copy] ?: @{};
    _errorCode = @"";
    _responseLock = [NSLock new];
    _lifecycleLock = [NSLock new];
    _responses = [NSMutableArray array];
    NSNumber *generation = [_configuration[@"generation"] isKindOfClass:NSNumber.class] ? _configuration[@"generation"] : nil;
    atomic_store(&_callbackGeneration, generation.unsignedLongLongValue);
  }
  return self;
}

- (void)dealloc {
  [self shutdown];
}

- (void)drainResponses {
  [_responseLock lock];
  NSUInteger available = _responses.count;
  [_responseLock unlock];
  for (NSUInteger index = 0; index < available; ++index) {
    // TokenLogin can start background identification. Leave the remaining
    // callbacks queued until that exclusive client operation has returned.
    if (atomic_load(&_shutdown) || atomic_load(&_identifying)) break;
    [_responseLock lock];
    dispatch_block_t response = _responses.firstObject;
    if (response != nil) [_responses removeObjectAtIndex:0];
    [_responseLock unlock];
    if (response == nil) break;
    response();
  }
}

- (void)publishState {
  if (atomic_load(&_shutdown)) return;
  RBRAPublishSessionState(_configuration, @{
    @"active": @(_active),
    @"gameLoaded": @(atomic_load(&_gameReady)),
    @"hardcoreActive": @(atomic_load(&_hardcoreActive)),
    @"errorCode": _errorCode ?: @""
  });
  const uint64_t generation = atomic_load(&_callbackGeneration);
  dispatch_async(dispatch_get_main_queue(), ^{
    if (atomic_load(&self->_shutdown) || generation != atomic_load(&self->_callbackGeneration)) return;
    if (self.stateChanged != nil) self.stateChanged();
  });
}

- (void)failWithCode:(NSString *)code {
  _failed = YES;
  _active = NO;
  _errorCode = [code copy];
  atomic_store(&_gameReady, false);
  atomic_store(&_hardcoreActive, false);
  // No client can later become active after a terminal preflight/login/load
  // failure. Release the pending-Hardcore barriers for ordinary gameplay.
  _host.hardcoreRestrictionsEnabled = NO;
  [self publishState];
}

- (void)refreshSummary {
  if (_client == NULL) return;
  rc_client_user_game_summary_t summary;
  memset(&summary, 0, sizeof(summary));
  rc_client_get_user_game_summary(_client, &summary);
  atomic_store(&_totalAchievements, summary.num_core_achievements);
  atomic_store(&_unlockedAchievements, summary.num_unlocked_achievements);
  // Background reads are disabled. Wait for the first evaluated frame before
  // claiming that the loaded set has at least one supported achievement.
  _active = _evaluated && atomic_load(&_gameReady) &&
      summary.num_core_achievements > summary.num_unsupported_achievements;
  atomic_store(&_hardcoreActive, _active && rc_client_get_hardcore_enabled(_client));
  if (_evaluated && summary.num_core_achievements == 0) _errorCode = @"RA_NO_ACHIEVEMENTS";
  else if (_evaluated && summary.num_core_achievements <= summary.num_unsupported_achievements)
    _errorCode = @"RA_ACHIEVEMENTS_UNSUPPORTED";
  if (_evaluated && !_active) {
    // A recognized game without a usable set is not an active RA session.
    // Do not retain gameplay restrictions for it or silently use Softcore.
    _failed = YES;
    _host.hardcoreRestrictionsEnabled = NO;
  }
}

- (BOOL)loggedIn { return atomic_load(&_loggedIn); }
- (NSString *)username {
  return [_configuration[@"username"] isKindOfClass:NSString.class] ? _configuration[@"username"] : nil;
}
- (BOOL)gameLoaded { return atomic_load(&_gameReady); }
- (BOOL)hardcoreActive { return atomic_load(&_hardcoreActive); }
- (unsigned)totalCount { return atomic_load(&_totalAchievements); }
- (unsigned)unlockedCount { return atomic_load(&_unlockedAchievements); }

- (BOOL)prepareMemory {
  if (_regionsReady) return YES;
  unsigned count = 0;
  const struct retro_memory_descriptor *descriptors = [_host memoryDescriptors:&count];
  struct retro_memory_map map = {descriptors, count};
  gAchievementHost = _host;
  _regionsReady = rc_libretro_memory_init(&_regions, count > 0 ? &map : NULL, CoreMemoryInfo, _consoleId) != 0;
  return _regionsReady;
}

- (void)startWithContentPath:(NSString *)path {
  if (_startRequested || atomic_load(&_shutdown)) return;
  _startRequested = YES;
  _contentPath = [(_host.loadedContentPath ?: path) copy];
  NSString *sessionID = [_configuration[@"sessionId"] isKindOfClass:NSString.class] ? _configuration[@"sessionId"] : nil;
  if (![_configuration[@"enabled"] boolValue] || sessionID.length == 0) {
    _host.hardcoreRestrictionsEnabled = NO;
    [self publishState];
    return;
  }
  if (![_configuration[@"supported"] boolValue] || _consoleId == 0) {
    [self failWithCode:@"RA_UNSUPPORTED"];
    return;
  }
  if (!_host.supportsAchievements ||
      !rc_libretro_is_system_allowed(_host.libraryName.UTF8String, _consoleId)) {
    [self failWithCode:@"RA_CORE_UNSUPPORTED"];
    return;
  }
  NSError *optionError = nil;
  if ([_configuration[@"hardcore"] boolValue] && ![_host validateHardcoreOptions:&optionError]) {
    [_host appendLog:optionError.localizedDescription ?: @"[HOST] incompatible Hardcore options"];
    [self failWithCode:@"RA_HARDCORE_OPTIONS"];
    return;
  }
  if (![self prepareMemory]) {
    [self failWithCode:@"RA_MEMORY_UNAVAILABLE"];
    return;
  }
  NSString *username = [_configuration[@"username"] isKindOfClass:NSString.class] ? _configuration[@"username"] : nil;
  NSString *token = [_configuration[@"token"] isKindOfClass:NSString.class] ? _configuration[@"token"] : nil;
  if (username.length == 0 || token.length == 0) {
    [self failWithCode:@"RA_CREDENTIALS_MISSING"];
    return;
  }
  static dispatch_once_t once;
  dispatch_once(&once, ^{ rc_hash_init_default_cdreader(); });
  _client = rc_client_create(ReadMemory, ServerCall);
  if (_client == NULL) {
    [self failWithCode:@"RA_CLIENT_UNAVAILABLE"];
    return;
  }
  rc_client_set_userdata(_client, (__bridge void *)self);
  rc_client_set_event_handler(_client, EventHandler);
  rc_client_set_allow_background_memory_reads(_client, 0);
  rc_client_set_hardcore_enabled(_client, [_configuration[@"hardcore"] boolValue] ? 1 : 0);
  char clause[128] = {0};
  rc_client_get_user_agent_clause(_client, clause, sizeof(clause));
  NSString *version = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"0";
  _userAgent = [NSString stringWithFormat:@"NeoStation/%@ %s", version, clause];
  NSURLSessionConfiguration *network = NSURLSessionConfiguration.ephemeralSessionConfiguration;
  network.timeoutIntervalForRequest = 30;
  _urlSession = [NSURLSession sessionWithConfiguration:network];
  const uint64_t generation = atomic_load(&_callbackGeneration);
  [self publishState];
  rc_client_begin_login_with_token(_client, username.UTF8String, token.UTF8String, TokenLogin,
                                  (void *)(uintptr_t)generation);
}

- (void)loadGame {
  if (_client == NULL || _failed || _contentPath.length == 0 || _loadStarted || atomic_load(&_gameReady)) return;
  _loadStarted = YES;
  const uint64_t generation = atomic_load(&_callbackGeneration);
  rc_client_t *client = _client;
  NSString *path = [_contentPath copy];
  atomic_store(&_identifying, true);
  // This API hashes synchronously in rcheevos v12.5.0. Keep that same hashing
  // implementation off the frame thread. Until it returns, doFrame/idle never
  // touch the client or drain responses. Background memory reads are disabled.
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
    if (!atomic_load(&self->_shutdown) && generation == atomic_load(&self->_callbackGeneration)) {
      rc_client_begin_identify_and_load_game(client, self->_consoleId, path.fileSystemRepresentation,
          NULL, 0, GameLoaded, (void *)(uintptr_t)generation);
    }
    [self->_lifecycleLock lock];
    atomic_store(&self->_identifying, false);
    if (atomic_load(&self->_shutdown) && self->_client == client) {
      rc_client_destroy(client);
      self->_client = NULL;
    }
    [self->_lifecycleLock unlock];
  });
}

- (void)doFrame {
  if (atomic_load(&_shutdown) || atomic_load(&_identifying)) return;
  [self drainResponses];
  if (atomic_load(&_identifying) || _client == NULL || _failed || !atomic_load(&_gameReady)) return;
  if ([_configuration[@"hardcore"] boolValue] &&
      (!_host.hardcoreRestrictionsEnabled || ![_host validateHardcoreOptions:nil])) {
    [self failWithCode:@"RA_HARDCORE_OPTIONS"];
    return;
  }
  rc_client_do_frame(_client);
  if (!_evaluated) {
    _evaluated = YES;
    [self refreshSummary];
    [self publishState];
  }
}

- (void)idle {
  if (atomic_load(&_shutdown) || atomic_load(&_identifying)) return;
  [self drainResponses];
  if (!atomic_load(&_identifying) && _client != NULL && !_failed) rc_client_idle(_client);
}

- (BOOL)canPause {
  if (atomic_load(&_shutdown) || atomic_load(&_identifying)) return YES;
  return _client == NULL || _failed || !atomic_load(&_gameReady) || rc_client_can_pause(_client, NULL) != 0;
}

- (void)resetGame {
  if (atomic_load(&_shutdown) || atomic_load(&_identifying)) return;
  if (_client != NULL && !_failed && atomic_load(&_gameReady)) rc_client_reset(_client);
}

- (void)shutdown {
  if (atomic_exchange(&_shutdown, true)) return;
  atomic_fetch_add(&_callbackGeneration, 1);
  [_responseLock lock];
  [_responses removeAllObjects];
  [_urlSession invalidateAndCancel];
  [_responseLock unlock];
  // Closing does not wait for a large CD/PSP hash. Its task retains this old
  // client and destroys it on return, after generation invalidation. The core
  // can unload immediately: hashing never reads the emulated memory maps.
  [_lifecycleLock lock];
  if (_client != NULL && !atomic_load(&_identifying)) {
    rc_client_destroy(_client);
    _client = NULL;
  }
  [_lifecycleLock unlock];
  rc_libretro_memory_destroy(&_regions);
  _regionsReady = NO;
  atomic_store(&_gameReady, false);
  atomic_store(&_loggedIn, false);
  atomic_store(&_hardcoreActive, false);
  if (gAchievementHost == _host) gAchievementHost = nil;
}

@end
