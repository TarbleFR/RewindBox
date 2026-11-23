// The libretro JIT helper transaction, run before a launch for a core RewindBox built with its JIT interface
// (RewindBoxLibretroJit.h). The same chain as the other engines: the libretro helper extension (LibretroJitSession)
// attaches StikJIT to RewindBox's own PID, then the host itself prepares the session's code arena
// (LibretroJitArena.h) before any core code runs.
//
//   universal (iOS 26 and later): helper connected, PID attached (vAttach + qProcessInfo marker), arena mapped and
//     prepared by command 1, executable probe, command 3 (nonce + 1), command 0 (detach), helper complete, P_TRACED off;
//   classic (before iOS 26): helper connected, classic attach and detach complete, CS_DEBUGGED, arena self-mapped and
//     probed, P_TRACED off.
//
// Each of these is reported as its own fact; success requires all of them. A failure never blocks the launch: the
// core keeps its interpreter. One transaction at a time, never while a debugger is attached by another engine.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface LibretroJitBridge : NSObject

+ (instancetype)shared;

/// Main thread. `pairingFilePath`: the stored RemotePairing file; `bytes`: the core's arena (whole 16 KiB pages,
/// at most LIBRETRO_JIT_MAX_CAPACITY). `completion` runs once on the main queue with the facts: success, code,
/// message, mode, helperConnected, pidAttached, prepared, executableProbe, nonceProbe, detached, helperCompleted,
/// debugged, debuggerReleased, capacity, elapsedMs, arena (LibretroJitArenaReport).
- (void)prepareWithPairingFile:(NSString *)pairingFilePath
                         bytes:(uint64_t)bytes
                    completion:(void (^)(NSDictionary<NSString *, id> *facts))completion;

/// YES while a transaction runs.
@property(atomic, readonly) BOOL busy;

@end

NS_ASSUME_NONNULL_END
