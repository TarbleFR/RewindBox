// See LibretroJitBridge.h. Timeouts are RPCS3's (Rpcs3JitBridgePlugin.mm): 30 s for the helper to connect, 600 s to
// attach (the first use may download or mount a Developer Disk Image), 120 s for the helper to complete after the
// detach. The host issues the universal commands itself and only then waits for the helper: waiting for completion
// before command 0 would deadlock the host and the helper (RPCS3's old 90 s failure).
#import "LibretroJitBridge.h"

#import "LibretroJit.h"
#import "LibretroJitArena.h"
#import "LibretroJitSession.h"

#include <unistd.h>

static const NSTimeInterval kLibretroJitConnectTimeout = 30.0;
static const NSTimeInterval kLibretroJitAttachTimeout = 600.0;
static const NSTimeInterval kLibretroJitCompleteTimeout = 120.0;

@interface LibretroJitBridge ()
@property(atomic, readwrite) BOOL busy;
@end

@implementation LibretroJitBridge {
  dispatch_queue_t _queue;
}

+ (instancetype)shared {
  static LibretroJitBridge *bridge;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    bridge = [[LibretroJitBridge alloc] init];
  });
  return bridge;
}

- (instancetype)init {
  self = [super init];
  if (self == nil) return nil;
  _queue = dispatch_queue_create("com.neogamelab.neostation.libretro.jit",
                                 dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL,
                                                                         QOS_CLASS_USER_INITIATED, 0));
  return self;
}

static NSMutableDictionary<NSString *, id> *LibretroJitFacts(BOOL universal) {
  return [@{
    @"success" : @NO,
    @"pid" : @(getpid()),
    @"mode" : universal ? @"universal" : @"classic",
    @"helperConnected" : @NO,
    @"pidAttached" : @NO,
    @"prepared" : @NO,
    @"executableProbe" : @NO,
    @"nonceProbe" : @NO,
    @"detached" : @NO,
    @"helperCompleted" : @NO,
    @"debugged" : @NO,
    @"debuggerReleased" : @NO,
    @"capacity" : @0,
  } mutableCopy];
}

- (void)prepareWithPairingFile:(NSString *)pairingFilePath
                         bytes:(uint64_t)bytes
                    completion:(void (^)(NSDictionary<NSString *, id> *facts))completion {
  void (^done)(NSDictionary<NSString *, id> *) = [completion copy];
  const BOOL universal = LibretroJitRequiresCoreHandshake();
  NSMutableDictionary<NSString *, id> *facts = LibretroJitFacts(universal);
  void (^refuse)(NSString *, NSString *) = ^(NSString *code, NSString *message) {
    facts[@"code"] = code;
    facts[@"message"] = message;
    facts[@"arena"] = LibretroJitArenaReport();
    dispatch_async(dispatch_get_main_queue(), ^{
      done(facts);
    });
  };
  if (@available(iOS 17.4, *)) {
  } else {
    refuse(@"LIBRETRO_JIT_OS", @"The libretro JIT helper requires iOS 17.4 or newer.");
    return;
  }
  if (!LibretroJitHostHasGetTaskAllow()) {
    refuse(@"LIBRETRO_JIT_ENTITLEMENT", @"This RewindBox installation does not preserve get-task-allow.");
    return;
  }
  if (pairingFilePath.length == 0 || ![NSFileManager.defaultManager isReadableFileAtPath:pairingFilePath]) {
    refuse(@"LIBRETRO_JIT_PAIRING", @"Import a readable pairing file before enabling JIT.");
    return;
  }
  if (bytes == 0 || bytes > LIBRETRO_JIT_MAX_CAPACITY) {
    refuse(@"LIBRETRO_JIT_CAPACITY", @"The requested code arena size is not supported.");
    return;
  }
  if (LibretroJitHostHasLiveDebugger()) {
    // Another engine's helper (or an external debugger) is attached: never attach over it.
    refuse(@"LIBRETRO_JIT_DEBUGGER_BUSY", @"Another debugger is attached to RewindBox.");
    return;
  }
  @synchronized(self) {
    if (self.busy) {
      refuse(@"LIBRETRO_JIT_BUSY", @"A libretro JIT transaction is already running.");
      return;
    }
    self.busy = YES;
  }
  // A stale arena of an earlier launch is never handed to this one.
  libretro_jit_arena_release();

  dispatch_async(_queue, ^{
    const NSTimeInterval started = NSProcessInfo.processInfo.systemUptime;
    __block LibretroJitSession *session = nil;
    void (^finish)(NSString *, NSString *) = ^(NSString *code, NSString *message) {
      const BOOL success = code == nil;
      if (!success) libretro_jit_arena_release();  // never a half-proven arena
      facts[@"success"] = @(success);
      if (code != nil) facts[@"code"] = code;
      facts[@"message"] = message ?: @"";
      facts[@"debugged"] = @(LibretroHostIsDebugged());
      facts[@"debuggerReleased"] = @(!LibretroJitHostHasLiveDebugger());
      facts[@"elapsedMs"] = @((NSProcessInfo.processInfo.systemUptime - started) * 1000.0);
      facts[@"arena"] = LibretroJitArenaReport();
      LibretroJitArenaStats stats;
      libretro_jit_arena_stats(&stats);
      facts[@"capacity"] = @(success ? stats.capacity : 0);
      [session close];
      self.busy = NO;
      dispatch_async(dispatch_get_main_queue(), ^{
        done(facts);
      });
    };

    NSData *pairingData = [[NSData alloc] initWithContentsOfFile:pairingFilePath
                                                         options:NSDataReadingMappedIfSafe
                                                           error:nil];
    if (pairingData.length == 0) {
      finish(@"LIBRETRO_JIT_PAIRING", @"The stored pairing file could not be read.");
      return;
    }
    NSError *error = nil;
    session = [[LibretroJitSession alloc] initWithError:&error];
    if (session == nil) {
      finish(@"LIBRETRO_JIT_HELPER", error.localizedDescription ?: @"Could not prepare the libretro JIT helper.");
      return;
    }
    session.requiresCoreHandshake = universal;
    [session startReader];
    if (![session launchHelperWithPairingData:pairingData error:&error]) {
      finish(@"LIBRETRO_JIT_HELPER", error.localizedDescription ?: @"Could not launch the libretro JIT helper.");
      return;
    }
    if (![session waitUntilConnected:kLibretroJitConnectTimeout]) {
      finish(@"LIBRETRO_JIT_HELPER_CONNECT",
             session.finalMessage.length > 0 ? session.finalMessage : @"The libretro JIT helper did not connect.");
      return;
    }
    facts[@"helperConnected"] = @YES;
    if (![session waitUntilAttached:kLibretroJitAttachTimeout]) {
      finish(@"LIBRETRO_JIT_ATTACH",
             session.finalMessage.length > 0 ? session.finalMessage : @"StikJIT did not attach to RewindBox.");
      return;
    }
    facts[@"pidAttached"] = @YES;

    if (universal) {
      // The debugger is attached and waits for commands: the arena, the nonce, then the single detach, always
      // issued (a failed preparation must not leave RewindBox stopped at the next trap).
      const BOOL prepared = libretro_jit_arena_prepare(bytes, 1) == 0;
      const uint64_t nonce = session.probeNonce;
      const BOOL nonceProbe = libretro_jit_arena_probe(nonce) == nonce + 1;
      const BOOL detached = libretro_jit_arena_detach() == 1;
      LibretroJitArenaStats stats;
      libretro_jit_arena_stats(&stats);
      facts[@"prepared"] = @(prepared);
      facts[@"executableProbe"] = @(stats.executableProbe != 0);
      facts[@"nonceProbe"] = @(nonceProbe);
      facts[@"detached"] = @(detached);
      const BOOL completed = [session waitUntilFinished:kLibretroJitCompleteTimeout] && session.success;
      facts[@"helperCompleted"] = @(completed);
      if (!prepared) {
        finish(@"LIBRETRO_JIT_PREPARE", @"The code arena could not be prepared.");
      } else if (!nonceProbe) {
        finish(@"LIBRETRO_JIT_NONCE", @"The helper did not answer the session's nonce.");
      } else if (!detached || !completed) {
        finish(@"LIBRETRO_JIT_DETACH", session.finalMessage.length > 0 ? session.finalMessage
                                                                        : @"The helper did not complete after the detach.");
      } else if (LibretroJitHostHasLiveDebugger()) {
        finish(@"LIBRETRO_JIT_DEBUGGER_LEFT", @"A debugger is still attached after the detach.");
      } else if (!libretro_jit_arena_ready()) {
        finish(@"LIBRETRO_JIT_PREPARE", @"The code arena is not ready.");
      } else {
        finish(nil, @"JIT ready for the libretro core.");
      }
      return;
    }

    // Classic: the helper attached and detached by itself; the process maps its own executable pages now.
    const BOOL completed = [session waitUntilFinished:kLibretroJitCompleteTimeout] && session.success;
    facts[@"helperCompleted"] = @(completed);
    if (!completed) {
      finish(@"LIBRETRO_JIT_ATTACH",
             session.finalMessage.length > 0 ? session.finalMessage : @"StikJIT did not complete the classic attach.");
      return;
    }
    if (!LibretroHostIsDebugged()) {
      finish(@"LIBRETRO_JIT_NOT_DEBUGGED", @"StikJIT detached without leaving RewindBox JIT-enabled.");
      return;
    }
    const BOOL prepared = libretro_jit_arena_prepare(bytes, 0) == 0;
    facts[@"prepared"] = @(prepared);
    LibretroJitArenaStats stats;
    libretro_jit_arena_stats(&stats);
    facts[@"executableProbe"] = @(stats.executableProbe != 0);
    if (!prepared || !libretro_jit_arena_ready()) {
      finish(@"LIBRETRO_JIT_PREPARE", @"The code arena could not be prepared.");
    } else if (LibretroJitHostHasLiveDebugger()) {
      finish(@"LIBRETRO_JIT_DEBUGGER_LEFT", @"A debugger is still attached after the classic attach.");
    } else {
      finish(nil, @"JIT ready for the libretro core.");
    }
  });
}

@end
