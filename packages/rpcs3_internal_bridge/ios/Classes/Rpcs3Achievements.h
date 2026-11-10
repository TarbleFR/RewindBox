#import <Foundation/Foundation.h>

#include "Rpcs3AchievementsABI.h"

NS_ASSUME_NONNULL_BEGIN

/// NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1: one RetroAchievements client
/// (rcheevos, PlayStation 3) for one immutable central launch snapshot.
///
/// - Frames are evaluated on the Core's VBlank thread, which only exists while
///   the game runs and is joined before the guest memory is released. A frame
///   never waits: if the client is busy (sign-in, hashing, a server answer) the
///   frame is skipped.
/// - Sign-in, identification (the synchronous rcheevos hash), server answers,
///   idle pings and destruction run on a private serial queue.
/// - The account is the central session's (Keychain token) for this launch
///   only; no engine-local account or preference exists. Logs carry codes only.
@interface Rpcs3Achievements : NSObject

- (instancetype)initWithConfiguration:(NSDictionary *)configuration api:(rpcs3_ios_ra_api)api;
- (instancetype)init NS_UNAVAILABLE;

/// Resolves the optional Core exports (all or nothing). Returns NO for a Core
/// built without NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1.
+ (BOOL)resolveCoreAPI:(void *)handle api:(rpcs3_ios_ra_api *)api;

/// Main queue, display only: an unlock committed by rcheevos.
@property(nonatomic, copy, nullable) void (^unlocked)(NSUInteger achievementID, NSString *title,
                                                       NSString *description, NSUInteger points);
/// Host journal (event, detail). Codes and counters only, never account data.
@property(nonatomic, copy, nullable) void (^journal)(NSString *event, NSString *detail);
/// Main queue, once: the game is running (first emulated VBlank, which only
/// follows RSX initialization, after the PPU compilation of a first boot) or
/// the client ended before the frame hook was attached. The in-game status is
/// presented from then on, never over a long compilation.
@property(atomic, copy, nullable) dispatch_block_t presentationReady;

/// YES while Hardcore is applied, or still pending sign-in/identification, for
/// this session: loading a savestate and enabling cheats must be refused.
@property(readonly) BOOL hardcoreRestrictionsActive;

/// After the Core accepted the boot of the launched title. Idempotent.
- (void)startWithSavestateBoot:(BOOL)savestateBoot cheatsEnabled:(BOOL)cheatsEnabled;
/// Before a host-initiated stop of the emulation (quit, settings, state).
- (void)suspendForRestart;
/// The stop was refused and the same run goes on: evaluate frames again.
- (void)resumeWithoutRestart;
/// After that boot: the game restarted, so rcheevos is reset before frames are
/// evaluated again. A savestate boot or changed speed settings end Hardcore.
- (void)resumeAfterRestart:(BOOL)booted savestateBoot:(BOOL)savestateBoot cheatsEnabled:(BOOL)cheatsEnabled;
/// Detaches the frame hook (waits for an in-flight frame), cancels requests and
/// destroys the client. Call before the emulation stops. Idempotent.
- (void)shutdown;

@end

NS_ASSUME_NONNULL_END
