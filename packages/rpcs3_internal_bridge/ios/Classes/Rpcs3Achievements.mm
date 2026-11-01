#import "Rpcs3Achievements.h"

#import <achievement_translation/RBAchievementTranslation.h>
#import <retro_achievements_session/RBRASession.h>

#include <dlfcn.h>
#include <string.h>
#include <sys/stat.h>

#include <atomic>
#include <mutex>
#include <string>

#include "Rpcs3AchievementsPolicy.h"
#include "rc_api_request.h"
#include "rc_client.h"
#include "rc_consoles.h"
#include "rc_error.h"
#include "rc_hash.h"

static NSString* Rpcs3RAString(const char* text) {
  if (text == NULL) return @"";
  return [NSString stringWithUTF8String:text] ?: @"";
}

static bool Rpcs3RAFileExists(const std::string& path) {
  struct stat info = {};
  return stat(path.c_str(), &info) == 0 && S_ISREG(info.st_mode);
}

@interface Rpcs3Achievements ()
- (void)processFrame;
- (void)publishState;
- (void)failWithCode:(NSString*)code;
- (void)refreshSummaryLocked;
- (void)note:(NSString*)event detail:(NSString*)detail;
@end

@implementation Rpcs3Achievements {
  NSDictionary* _configuration;  // the exact snapshot returned by RBRATakeLaunchConfiguration
  rpcs3_ios_ra_api _api;
  dispatch_queue_t _queue;
  dispatch_source_t _idleTimer;  // queue only
  std::mutex _clientMutex;       // guards _client and every rcheevos call
  std::mutex _hookMutex;         // orders frame-hook registration against shutdown
  rc_client_t* _client;
  NSLock* _responseLock;         // guards _urlSession
  NSURLSession* _urlSession;
  NSString* _userAgent;
  NSString* _errorCode;   // queue only
  NSString* _hashPath;    // queue only
  BOOL _started;          // queue only
  BOOL _active;           // queue only
  BOOL _loadStarted;      // queue only
  uint64_t _idleFramesSeen;  // queue only
  std::atomic<bool> _shutdown;
  std::atomic<bool> _failed;
  std::atomic<bool> _suspended;
  std::atomic<bool> _gameReady;
  std::atomic<bool> _evaluated;
  std::atomic<bool> _loggedIn;
  std::atomic<bool> _hardcoreActive;
  std::atomic<bool> _restrictions;
  std::atomic<bool> _hookRegistered;  // this object is the Core's frame callback context
  std::atomic<bool> _presentationSignalled;
  std::atomic<uint64_t> _generation;
  std::atomic<unsigned> _total;
  std::atomic<unsigned> _unlockedCount;
  // RetroAchievements id of the loaded game, published so the library can
  // remember that this title is recognized (NEOSTATION_RA_IDENTIFICATION_V1).
  std::atomic<unsigned> _gameId;
  std::atomic<uint64_t> _framesProcessed;
  std::atomic<uint64_t> _framesSkipped;
}

#pragma mark - Core and rcheevos callbacks

// RSX VBlank thread (60 Hz while the game runs). Never blocks the emulator.
static void Rpcs3RAFrame(void* context, uint64_t frame) {
  (void)frame;
  @autoreleasepool {
    [(__bridge Rpcs3Achievements*)context processFrame];
  }
}

static uint32_t Rpcs3RAReadMemory(uint32_t address, uint8_t* buffer, uint32_t count, rc_client_t* client) {
  Rpcs3Achievements* achievements = (__bridge Rpcs3Achievements*)rc_client_get_userdata(client);
  if (achievements == nil || buffer == NULL || count == 0 || achievements->_api.read_memory == NULL) return 0;
  // RetroAchievements addresses of the PS3 map are guest virtual addresses
  // (rc_memory_regions_playstation3: real_address == start_address).
  uint32_t mapped = 0;
  const rpcs3_ios_status status = achievements->_api.read_memory(address, buffer, count, &mapped);
  if (status != RPCS3_IOS_RA_STATUS_OK) memset(buffer, 0, count);
  return rpcs3_ra::reported_bytes(status, count);
}

static void Rpcs3RAServerCall(const rc_api_request_t* request, rc_client_server_callback_t callback,
                              void* callbackData, rc_client_t* client) {
  Rpcs3Achievements* achievements = (__bridge Rpcs3Achievements*)rc_client_get_userdata(client);
  NSURL* url = request->url != NULL ? [NSURL URLWithString:Rpcs3RAString(request->url)] : nil;
  if (achievements == nil || url == nil) {
    rc_api_server_response_t failure = {NULL, 0, RC_API_SERVER_RESPONSE_CLIENT_ERROR};
    callback(&failure, callbackData);
    return;
  }
  const uint64_t generation = achievements->_generation.load();
  NSMutableURLRequest* urlRequest = [NSMutableURLRequest requestWithURL:url];
  [urlRequest setValue:achievements->_userAgent forHTTPHeaderField:@"User-Agent"];
  if (request->post_data != NULL) {
    urlRequest.HTTPMethod = @"POST";
    urlRequest.HTTPBody = [NSData dataWithBytes:request->post_data length:strlen(request->post_data)];
    NSString* type = request->content_type != NULL ? Rpcs3RAString(request->content_type)
                                                   : @"application/x-www-form-urlencoded";
    [urlRequest setValue:type forHTTPHeaderField:@"Content-Type"];
  }
  [achievements->_responseLock lock];
  NSURLSession* session = achievements->_shutdown.load() ? nil : achievements->_urlSession;
  if (session == nil) {
    [achievements->_responseLock unlock];
    rc_api_server_response_t failure = {NULL, 0, RC_API_SERVER_RESPONSE_CLIENT_ERROR};
    callback(&failure, callbackData);
    return;
  }
  // The URL and body carry the account token: never logged.
  NSURLSessionDataTask* task = [session dataTaskWithRequest:urlRequest
                                          completionHandler:^(NSData* data, NSURLResponse* response, NSError* error) {
    NSData* body = [data copy];
    const NSInteger status = error != nil ? RC_API_SERVER_RESPONSE_RETRYABLE_CLIENT_ERROR
        : [response isKindOfClass:NSHTTPURLResponse.class] ? ((NSHTTPURLResponse*)response).statusCode
                                                           : RC_API_SERVER_RESPONSE_CLIENT_ERROR;
    // Answers are fed to rcheevos on the client queue, never racing a frame
    // (the frame skips while the client is busy) or the client destruction.
    dispatch_async(achievements->_queue, ^{
      if (achievements->_shutdown.load() || generation != achievements->_generation.load()) return;
      std::lock_guard<std::mutex> lock(achievements->_clientMutex);
      if (achievements->_client == NULL) return;
      rc_api_server_response_t serverResponse = {(const char*)body.bytes, body.length, (int)status};
      callback(&serverResponse, callbackData);
    });
  }];
  [task resume];
  [achievements->_responseLock unlock];
}

// Runs inside rcheevos (frame thread or client queue, client lock held):
// copies what it needs and defers the rest to the client queue.
static void Rpcs3RAEvent(const rc_client_event_t* event, rc_client_t* client) {
  Rpcs3Achievements* achievements = (__bridge Rpcs3Achievements*)rc_client_get_userdata(client);
  if (achievements == nil || event == NULL || achievements->_shutdown.load()) return;
  const uint64_t generation = achievements->_generation.load();
  switch (event->type) {
    case RC_CLIENT_EVENT_ACHIEVEMENT_TRIGGERED: {
      if (event->achievement == NULL) return;
      const NSUInteger achievementID = event->achievement->id;
      NSString* title = Rpcs3RAString(event->achievement->title);
      NSString* description = Rpcs3RAString(event->achievement->description);
      const NSUInteger points = event->achievement->points;
      dispatch_async(achievements->_queue, ^{
        if (achievements->_shutdown.load() || generation != achievements->_generation.load()) return;
        {
          std::lock_guard<std::mutex> lock(achievements->_clientMutex);
          if (achievements->_client != NULL) [achievements refreshSummaryLocked];
        }
        [achievements note:@"ra.unlock" detail:[NSString stringWithFormat:@"id=%lu unlocked=%u total=%u",
            (unsigned long)achievementID, achievements->_unlockedCount.load(), achievements->_total.load()]];
        [achievements publishState];
      });
      // Presentation only; the award itself is already committed by rcheevos.
      if (![achievements->_configuration[@"notifications"] boolValue]) return;
      dispatch_async(dispatch_get_main_queue(), ^{
        if (achievements->_shutdown.load() || generation != achievements->_generation.load()) return;
        if (achievements.unlocked != nil) achievements.unlocked(achievementID, title, description, points);
      });
      return;
    }
    case RC_CLIENT_EVENT_SERVER_ERROR:
    case RC_CLIENT_EVENT_DISCONNECTED:
    case RC_CLIENT_EVENT_RECONNECTED: {
      // rcheevos keeps its own award retry and synchronization.
      NSString* code = event->type == RC_CLIENT_EVENT_SERVER_ERROR ? @"RA_SERVER_ERROR"
          : event->type == RC_CLIENT_EVENT_DISCONNECTED ? @"RA_SYNC_PENDING" : @"";
      dispatch_async(achievements->_queue, ^{
        if (achievements->_shutdown.load() || generation != achievements->_generation.load() ||
            achievements->_failed.load()) return;
        achievements->_errorCode = code;
        [achievements publishState];
      });
      return;
    }
    case RC_CLIENT_EVENT_RESET: {
      // Hardcore is chosen before loading and never switched on mid-game. If
      // rcheevos still asks for a reset, fail closed rather than reset the
      // player's game or evaluate an unreset one.
      dispatch_async(achievements->_queue, ^{
        if (achievements->_shutdown.load() || generation != achievements->_generation.load()) return;
        [achievements failWithCode:@"RA_HARDCORE_RESET_REQUIRED"];
      });
      return;
    }
    default:
      return;
  }
}

static void Rpcs3RAGameLoaded(int result, const char* message, rc_client_t* client, void* userdata) {
  (void)message;
  Rpcs3Achievements* achievements = (__bridge Rpcs3Achievements*)rc_client_get_userdata(client);
  if (achievements == nil || achievements->_shutdown.load() || achievements->_failed.load() ||
      (uint64_t)(uintptr_t)userdata != achievements->_generation.load()) return;
  achievements->_loadStarted = NO;
  if (result != RC_OK) {
    [achievements note:@"ra.game" detail:[NSString stringWithFormat:@"load_failed result=%d", result]];
    // RC_NO_GAME_LOADED: unknown hash. RC_INVALID_STATE: the files could not be
    // hashed as a PS3 title. RC_NO_RESPONSE: no answer from the server.
    [achievements failWithCode:result == RC_NO_GAME_LOADED || result == RC_INVALID_STATE ? @"RA_GAME_NOT_RECOGNIZED"
                             : result == RC_NO_RESPONSE ? @"RA_NETWORK_UNAVAILABLE" : @"RA_GAME_LOAD_FAILED"];
    return;
  }
  const rc_client_game_t* game = rc_client_get_game_info(client);
  if (game == NULL || game->id == 0 || !rc_client_is_game_loaded(client)) {
    [achievements failWithCode:@"RA_GAME_NOT_RECOGNIZED"];
    return;
  }
  achievements->_gameId.store(game->id);
  achievements->_gameReady.store(true);
  achievements->_evaluated.store(false);
  achievements->_errorCode = @"";
  [achievements refreshSummaryLocked];
  [achievements note:@"ra.game" detail:[NSString stringWithFormat:@"loaded id=%u achievements=%u hardcore=%d",
      game->id, achievements->_total.load(), rc_client_get_hardcore_enabled(client)]];
  // Source texts for the display-only translation cache; never rcheevos pointers.
  rc_client_achievement_list_t* list = rc_client_create_achievement_list(client,
      RC_CLIENT_ACHIEVEMENT_CATEGORY_CORE_AND_UNOFFICIAL, RC_CLIENT_ACHIEVEMENT_LIST_GROUPING_LOCK_STATE);
  NSMutableArray* sources = [NSMutableArray array];
  if (list != NULL) {
    for (uint32_t b = 0; b < list->num_buckets; ++b) {
      const rc_client_achievement_bucket_t* bucket = &list->buckets[b];
      for (uint32_t i = 0; i < bucket->num_achievements; ++i) {
        const rc_client_achievement_t* item = bucket->achievements[i];
        if (item == NULL) continue;
        [sources addObject:@{@"id": @(item->id), @"title": Rpcs3RAString(item->title),
                             @"description": Rpcs3RAString(item->description)}];
      }
    }
    rc_client_destroy_achievement_list(list);
  }
  RBAchievementPrefetch(sources);
  [achievements publishState];
}

static void Rpcs3RATokenLogin(int result, const char* message, rc_client_t* client, void* userdata) {
  (void)message;
  Rpcs3Achievements* achievements = (__bridge Rpcs3Achievements*)rc_client_get_userdata(client);
  if (achievements == nil || achievements->_shutdown.load() || achievements->_failed.load() ||
      (uint64_t)(uintptr_t)userdata != achievements->_generation.load()) return;
  if (result == RC_OK && rc_client_get_user_info(client) != NULL) {
    achievements->_loggedIn.store(true);
    [achievements note:@"ra.login" detail:@"result=0"];
    [achievements publishState];
    // Identification hashes synchronously: start it after this callback returns.
    dispatch_async(achievements->_queue, ^{ [achievements beginIdentify]; });
    return;
  }
  [achievements note:@"ra.login" detail:[NSString stringWithFormat:@"result=%d", result]];
  // An explicit refusal of the stored token asks for a new sign-in in the RA
  // tab; no answer is a network problem.
  const bool refused = result == RC_INVALID_CREDENTIALS || result == RC_EXPIRED_TOKEN || result == RC_ACCESS_DENIED;
  const bool unreachable = result == RC_NO_RESPONSE || result == RC_INVALID_JSON;
  [achievements failWithCode:refused ? @"RA_AUTHENTICATION_FAILED"
                           : unreachable ? @"RA_NETWORK_UNAVAILABLE" : @"RA_LOGIN_FAILED"];
}

#pragma mark - Lifecycle

+ (BOOL)resolveCoreAPI:(void*)handle api:(rpcs3_ios_ra_api*)api {
  if (api != NULL) memset(api, 0, sizeof(*api));
  if (handle == NULL || api == NULL) return NO;
  auto version = reinterpret_cast<rpcs3_ios_ra_api_version_function>(dlsym(handle, "rpcs3_ios_ra_api_version"));
  if (version == NULL || version() != RPCS3_IOS_RA_API_VERSION) return NO;
  rpcs3_ios_ra_api resolved = {};
  resolved.set_frame_callback = reinterpret_cast<rpcs3_ios_ra_set_frame_callback_function>(
      dlsym(handle, "rpcs3_ios_ra_set_frame_callback"));
  resolved.read_memory = reinterpret_cast<rpcs3_ios_ra_read_memory_function>(
      dlsym(handle, "rpcs3_ios_ra_read_memory"));
  resolved.get_session_info = reinterpret_cast<rpcs3_ios_ra_get_session_info_function>(
      dlsym(handle, "rpcs3_ios_ra_get_session_info"));
  if (resolved.set_frame_callback == NULL || resolved.read_memory == NULL || resolved.get_session_info == NULL)
    return NO;
  *api = resolved;
  return YES;
}

- (instancetype)initWithConfiguration:(NSDictionary*)configuration api:(rpcs3_ios_ra_api)api {
  self = [super init];
  if (self) {
    // Kept as is: the hub accepts state only for the exact snapshot it issued.
    _configuration = [configuration isKindOfClass:NSDictionary.class] ? configuration : @{};
    _api = api;
    _errorCode = @"";
    _responseLock = [NSLock new];
    _queue = dispatch_queue_create("com.neogamelab.neostation.rpcs3.retroachievements", DISPATCH_QUEUE_SERIAL);
    NSNumber* generation = [_configuration[@"generation"] isKindOfClass:NSNumber.class] ? _configuration[@"generation"] : nil;
    _generation.store(generation.unsignedLongLongValue);
  }
  return self;
}

- (void)dealloc {
  // Normally already shut down by the bridge. Blocks queued on _queue retain
  // self, so nothing else can still use the client here.
  if (!_shutdown.exchange(true)) {
    {
      std::lock_guard<std::mutex> hook(_hookMutex);
      if (_hookRegistered.exchange(false) && _api.set_frame_callback != NULL) _api.set_frame_callback(NULL, NULL);
    }
    [_urlSession invalidateAndCancel];
    if (_idleTimer != nil) dispatch_source_cancel(_idleTimer);
    std::lock_guard<std::mutex> lock(_clientMutex);
    if (_client != NULL) rc_client_destroy(_client);
    _client = NULL;
  }
}

- (void)signalPresentationReady {
  if (_presentationSignalled.exchange(true)) return;
  dispatch_block_t ready = self.presentationReady;
  if (ready != nil) dispatch_async(dispatch_get_main_queue(), ready);
}

- (void)note:(NSString*)event detail:(NSString*)detail {
  void (^journal)(NSString*, NSString*) = self.journal;
  if (journal != nil) journal(event, detail ?: @"");
}

- (BOOL)hardcoreRestrictionsActive {
  return _restrictions.load() && !_failed.load() && !_shutdown.load();
}

- (void)publishState {
  if (_shutdown.load()) return;
  // Observed facts only (no account data): the hub derives the in-game status
  // and the RetroAchievements tab state from them.
  RBRAPublishSessionState(_configuration, @{
    @"active": @(_active),
    @"loggedIn": @(_loggedIn.load()),
    @"gameLoaded": @(_gameReady.load()),
    @"hardcoreActive": @(_hardcoreActive.load()),
    @"totalCount": @(_total.load()),
    @"unlockedCount": @(_unlockedCount.load()),
    @"gameId": @(_gameReady.load() ? _gameId.load() : 0u),
    @"errorCode": _errorCode ?: @""
  });
}

// Client queue (rcheevos callbacks included).
- (void)failWithCode:(NSString*)code {
  _failed.store(true);
  _active = NO;
  _errorCode = [code copy] ?: @"";
  _gameReady.store(false);
  _hardcoreActive.store(false);
  // Nothing can become active after a terminal failure: ordinary gameplay
  // (savestates, cheats) is no longer restricted.
  _restrictions.store(false);
  [self note:@"ra.failed" detail:_errorCode];
  [self publishState];
  // Without the frame hook no VBlank will announce the running game.
  if (!_hookRegistered.load()) [self signalPresentationReady];
}

// Client queue with the client lock held.
- (void)refreshSummaryLocked {
  if (_client == NULL) return;
  rc_client_user_game_summary_t summary;
  memset(&summary, 0, sizeof(summary));
  rc_client_get_user_game_summary(_client, &summary);
  _total.store(summary.num_core_achievements);
  _unlockedCount.store(summary.num_unlocked_achievements);
  const bool evaluated = _evaluated.load();
  // Active only after an evaluated frame of a set with a supported achievement.
  _active = evaluated && _gameReady.load() && summary.num_core_achievements > summary.num_unsupported_achievements;
  _hardcoreActive.store(_active && rc_client_get_hardcore_enabled(_client));
  if (evaluated && summary.num_core_achievements == 0) _errorCode = @"RA_NO_ACHIEVEMENTS";
  else if (evaluated && summary.num_core_achievements <= summary.num_unsupported_achievements)
    _errorCode = @"RA_ACHIEVEMENTS_UNSUPPORTED";
  if (evaluated && !_active) {
    // A recognized game without a usable set is not an active session: no
    // restriction remains and frames stop being evaluated.
    _failed.store(true);
    _restrictions.store(false);
  }
}

- (void)startWithSavestateBoot:(BOOL)savestateBoot cheatsEnabled:(BOOL)cheatsEnabled {
  dispatch_async(_queue, ^{ [self startOnQueueWithSavestateBoot:savestateBoot cheatsEnabled:cheatsEnabled]; });
}

- (void)startOnQueueWithSavestateBoot:(BOOL)savestateBoot cheatsEnabled:(BOOL)cheatsEnabled {
  if (_started || _shutdown.load()) return;
  _started = YES;
  NSString* sessionID = [_configuration[@"sessionId"] isKindOfClass:NSString.class] ? _configuration[@"sessionId"] : nil;
  if (![_configuration[@"enabled"] boolValue] || sessionID.length == 0) {
    [self signalPresentationReady];  // the hub reports from the snapshot
    return;
  }
  if (![_configuration[@"supported"] boolValue]) { [self failWithCode:@"RA_UNSUPPORTED"]; return; }
  if (_api.set_frame_callback == NULL || _api.read_memory == NULL || _api.get_session_info == NULL) {
    [self failWithCode:@"RA_CORE_UNSUPPORTED"];
    return;
  }
  NSString* username = [_configuration[@"username"] isKindOfClass:NSString.class] ? _configuration[@"username"] : nil;
  NSString* token = [_configuration[@"token"] isKindOfClass:NSString.class] ? _configuration[@"token"] : nil;
  if (username.length == 0 || token.length == 0) { [self failWithCode:@"RA_CREDENTIALS_MISSING"]; return; }

  rpcs3_ios_ra_session_info info;
  memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  if (_api.get_session_info(&info) != RPCS3_IOS_RA_STATUS_OK) {
    [self note:@"ra.content" detail:@"session_info_unavailable"];
    [self failWithCode:@"RA_GAME_LOAD_FAILED"];
    return;
  }
  info.title_id[sizeof(info.title_id) - 1] = '\0';
  info.content_path[sizeof(info.content_path) - 1] = '\0';
  const std::string hashPath = rpcs3_ra::hash_source(info.content_path, Rpcs3RAFileExists);
  if (hashPath.empty()) {
    // No PARAM.SFO + EBOOT.BIN layout rcheevos can hash: nothing to identify.
    [self note:@"ra.content" detail:[NSString stringWithFormat:@"hash_source=missing title=%s", info.title_id]];
    [self failWithCode:@"RA_GAME_NOT_RECOGNIZED"];
    return;
  }
  _hashPath = [NSString stringWithUTF8String:hashPath.c_str()];
  if (_hashPath.length == 0) { [self failWithCode:@"RA_GAME_NOT_RECOGNIZED"]; return; }

  const BOOL requested = [_configuration[@"hardcore"] boolValue];
  const rpcs3_ra::hardcore_decision decision =
      rpcs3_ra::decide_hardcore(requested, savestateBoot, cheatsEnabled, info.hardcore_compatible != 0);
  _restrictions.store(decision.applied);
  [self note:@"ra.hardcore" detail:[NSString stringWithFormat:
      @"requested=%d applied=%d blocks=%s vblank=%u clocks=%u frame_limit_unbounded=%u",
      requested, decision.applied, rpcs3_ra::block_text(decision.blocks).c_str(),
      info.vblank_rate, info.clocks_scale, info.frame_limit_unbounded]];

  static dispatch_once_t cdreader;
  dispatch_once(&cdreader, ^{ rc_hash_init_default_cdreader(); });
  rc_client_t* client = rc_client_create(Rpcs3RAReadMemory, Rpcs3RAServerCall);
  if (client == NULL) { [self failWithCode:@"RA_CLIENT_UNAVAILABLE"]; return; }
  rc_client_set_userdata(client, (__bridge void*)self);
  rc_client_set_event_handler(client, Rpcs3RAEvent);
  rc_client_set_allow_background_memory_reads(client, 0);
  rc_client_set_hardcore_enabled(client, decision.applied ? 1 : 0);
  char clause[128] = {0};
  rc_client_get_user_agent_clause(client, clause, sizeof(clause));
  NSString* version = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"0";
  _userAgent = [NSString stringWithFormat:@"NeoStation/%@ %s", version, clause];
  NSURLSessionConfiguration* network = NSURLSessionConfiguration.ephemeralSessionConfiguration;
  network.timeoutIntervalForRequest = 30;
  [_responseLock lock];
  _urlSession = [NSURLSession sessionWithConfiguration:network];
  [_responseLock unlock];
  {
    std::lock_guard<std::mutex> lock(_clientMutex);
    _client = client;
  }
  {
    // From now on every VBlank may evaluate a frame (once the game is loaded).
    // Under the hook lock: a shutdown that already began never sees a hook
    // registered after its detach (the queued destruction follows).
    std::lock_guard<std::mutex> hook(_hookMutex);
    if (_shutdown.load()) return;
    _hookRegistered.store(true);
    _api.set_frame_callback(Rpcs3RAFrame, (__bridge void*)self);
  }
  [self startIdleTimer];
  [self publishState];
  const uint64_t generation = _generation.load();
  std::lock_guard<std::mutex> lock(_clientMutex);
  rc_client_begin_login_with_token(_client, username.UTF8String, token.UTF8String, Rpcs3RATokenLogin,
                                   (void*)(uintptr_t)generation);
}

- (void)beginIdentify {
  if (_shutdown.load() || _failed.load() || _loadStarted || _gameReady.load() || _hashPath.length == 0) return;
  _loadStarted = YES;
  // Only the kind of source is journaled, never the player's file path.
  NSString* source = [_hashPath.pathExtension.lowercaseString isEqualToString:@"iso"] ? @"iso" : @"eboot";
  [self note:@"ra.identify" detail:[@"source=" stringByAppendingString:source]];
  const uint64_t generation = _generation.load();
  // rcheevos hashes PARAM.SFO + EBOOT.BIN synchronously here (never the
  // emulated memory); frames are skipped meanwhile, no game is loaded yet.
  std::lock_guard<std::mutex> lock(_clientMutex);
  if (_client == NULL) return;
  rc_client_begin_identify_and_load_game(_client, RC_CONSOLE_PLAYSTATION_3, _hashPath.fileSystemRepresentation,
                                         NULL, 0, Rpcs3RAGameLoaded, (void*)(uintptr_t)generation);
}

- (void)processFrame {
  if (!_presentationSignalled.load()) [self signalPresentationReady];
  if (_shutdown.load() || _suspended.load() || _failed.load() || !_gameReady.load()) return;
  std::unique_lock<std::mutex> lock(_clientMutex, std::try_to_lock);
  if (!lock.owns_lock()) {
    _framesSkipped.fetch_add(1);
    return;
  }
  if (_client == NULL) return;
  rc_client_do_frame(_client);
  _framesProcessed.fetch_add(1);
  lock.unlock();
  if (!_evaluated.exchange(true)) {
    const uint64_t generation = _generation.load();
    dispatch_async(_queue, ^{
      if (self->_shutdown.load() || generation != self->_generation.load() || self->_failed.load()) return;
      {
        std::lock_guard<std::mutex> clientLock(self->_clientMutex);
        if (self->_client == NULL) return;
        [self refreshSummaryLocked];
      }
      [self note:@"ra.active" detail:[NSString stringWithFormat:@"active=%d total=%u unlocked=%u hardcore=%d",
          self->_active, self->_total.load(), self->_unlockedCount.load(), self->_hardcoreActive.load()]];
      [self publishState];
    });
  }
}

- (void)startIdleTimer {
  if (_idleTimer != nil) return;
  _idleTimer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, _queue);
  dispatch_source_set_timer(_idleTimer, dispatch_time(DISPATCH_TIME_NOW, (int64_t)NSEC_PER_SEC),
                            NSEC_PER_SEC, NSEC_PER_SEC / 4);
  __weak Rpcs3Achievements* weakSelf = self;
  dispatch_source_set_event_handler(_idleTimer, ^{ [weakSelf idleTick]; });
  dispatch_resume(_idleTimer);
}

// Client queue, once per second: rcheevos pings and retries while no frame is
// evaluated (sign-in, identification, pause, menu, restart).
- (void)idleTick {
  if (_shutdown.load() || _failed.load()) return;
  const uint64_t frames = _framesProcessed.load();
  if (frames != _idleFramesSeen) {
    _idleFramesSeen = frames;
    return;
  }
  std::lock_guard<std::mutex> lock(_clientMutex);
  if (_client != NULL) rc_client_idle(_client);
}

- (void)suspendForRestart {
  _suspended.store(true);
}

- (void)resumeWithoutRestart {
  if (!_shutdown.load()) _suspended.store(false);
}

- (void)resumeAfterRestart:(BOOL)booted savestateBoot:(BOOL)savestateBoot cheatsEnabled:(BOOL)cheatsEnabled {
  dispatch_async(_queue, ^{
    if (self->_shutdown.load()) return;
    if (!booted) {
      [self note:@"ra.restart" detail:@"boot_failed"];
      return;  // still suspended: the bridge closes the game
    }
    rpcs3_ios_ra_session_info info;
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    const bool speedCompatible = self->_api.get_session_info != NULL &&
        self->_api.get_session_info(&info) == RPCS3_IOS_RA_STATUS_OK && info.hardcore_compatible != 0;
    {
      std::lock_guard<std::mutex> lock(self->_clientMutex);
      if (self->_client != NULL) {
        if (rc_client_get_hardcore_enabled(self->_client)) {
          const rpcs3_ra::hardcore_decision decision =
              rpcs3_ra::decide_hardcore(true, savestateBoot, cheatsEnabled, speedCompatible);
          if (!decision.applied) {
            // Disabling Hardcore needs no reset; it is never re-enabled.
            rc_client_set_hardcore_enabled(self->_client, 0);
            self->_restrictions.store(false);
            [self note:@"ra.hardcore" detail:[NSString stringWithFormat:@"ended blocks=%s",
                rpcs3_ra::block_text(decision.blocks).c_str()]];
          }
        }
        // The title booted again: forget the hit counts of the previous run.
        if (self->_gameReady.load()) rc_client_reset(self->_client);
        if (self->_gameReady.load() && !self->_failed.load()) [self refreshSummaryLocked];
      }
    }
    self->_suspended.store(false);
    [self note:@"ra.restart" detail:@"reset"];
    [self publishState];
  });
}

- (void)shutdown {
  if (_shutdown.exchange(true)) return;
  _generation.fetch_add(1);
  _restrictions.store(false);
  // Returns after an in-flight frame finished: no frame uses the client later.
  // Only the registering session detaches (never a later launch's hook).
  {
    std::lock_guard<std::mutex> hook(_hookMutex);
    if (_hookRegistered.exchange(false) && _api.set_frame_callback != NULL) _api.set_frame_callback(NULL, NULL);
  }
  [_responseLock lock];
  [_urlSession invalidateAndCancel];
  _urlSession = nil;
  [_responseLock unlock];
  [self note:@"ra.session_end" detail:[NSString stringWithFormat:@"frames=%llu skipped=%llu",
      (unsigned long long)_framesProcessed.load(), (unsigned long long)_framesSkipped.load()]];
  _gameReady.store(false);
  _loggedIn.store(false);
  _hardcoreActive.store(false);
  // After queued work (a running identification hashes files, never memory).
  dispatch_async(_queue, ^{
    if (self->_idleTimer != nil) {
      dispatch_source_cancel(self->_idleTimer);
      self->_idleTimer = nil;
    }
    {
      std::lock_guard<std::mutex> lock(self->_clientMutex);
      if (self->_client != NULL) rc_client_destroy(self->_client);
      self->_client = NULL;
    }
    // A start that was already running may have opened a session afterwards.
    [self->_responseLock lock];
    [self->_urlSession invalidateAndCancel];
    self->_urlSession = nil;
    [self->_responseLock unlock];
  });
}

@end
