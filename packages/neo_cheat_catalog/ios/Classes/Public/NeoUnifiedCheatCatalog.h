// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString *const NeoUnifiedCheatCatalogErrorDomain;
/// Posted on main after a bulk installation, including partial success.
FOUNDATION_EXPORT NSNotificationName const NeoUnifiedCheatCatalogDidInstallNotification;
/// Shared installation state/progress, posted on main for every console menu.
FOUNDATION_EXPORT NSNotificationName const NeoUnifiedCheatCatalogProgressNotification;

/// Injected transports must invoke completion once, on any queue, and respect
/// maximumBytes. The manager independently verifies size and SHA-256 as well.
typedef void (^NeoUnifiedCheatFetch)(NSURL *url, NSUInteger maximumBytes,
                                    void (^completion)(NSData *_Nullable, NSError *_Nullable));

/// Shared data service only. It never activates cheats or writes engine files.
/// Configure before use; callbacks and progress arrive on the main queue.
@interface NeoUnifiedCheatCatalog : NSObject
+ (instancetype)sharedCatalog;
@property(nonatomic, strong) NSURL *manifestURL;
/// Optional local source folder containing manifest.json, packs/ and games/.
@property(nonatomic, copy, nullable) NSString *bundledDirectory;
/// Defaults to Documents/NeoStation/Cheats/Unified. Injectable for host tests.
@property(nonatomic, copy) NSString *storageDirectory;
@property(nonatomic, copy, nullable) NeoUnifiedCheatFetch fetch;

/// Reads a validated disk/bundle index; fetches only if no local index exists.
/// Snapshot installation_state: missing/partial/installing/complete. Counts
/// reflect the one shared on-disk installation, including interrupted installs.
- (void)loadWithCompletion:(void (^)(NSDictionary *_Nullable, NSError *_Nullable))completion;
/// Refreshes the index, then installs every eligible pack. At most two fetches
/// are active. Good packs survive failures; another call retries missing ones.
/// Progress: total_packs/completed_packs/failed_packs/total_bytes/completed_bytes.
/// Result additionally contains installed_games, failed_packs and errors.
/// Partial success returns a result AND an error, never discards good files.
- (void)installAllWithProgress:(void (^_Nullable)(NSDictionary *progress))progress
                   completion:(void (^)(NSDictionary *_Nullable, NSError *_Nullable))completion;
/// In-game download: use the validated local/bundled index immediately and
/// prioritize this game's packs. Existing verified files work without network.
/// A completed installation is a no-op; a partial installation schedules only
/// missing packs. Concurrent callers join the same installation.
/// The separate update action above still refreshes the remote index.
- (void)installAllForIdentity:(NSDictionary *)identity
                    progress:(void (^_Nullable)(NSDictionary *progress))progress
                  completion:(void (^)(NSDictionary *_Nullable, NSError *_Nullable))completion;

/// identity: {system,title,regions,languages,revision,identities:[{type,value,scheme}]}
/// Returned rows add match (exact/candidate) and installed. A title alone is
/// never an exact match. Conflicting regions/languages/revisions are excluded.
/// A known typed identifier limits discovery to that identifier's compatible
/// rows; title-only fallback remains available to explicit searchGames calls.
- (void)gamesForIdentity:(NSDictionary *)identity
             completion:(void (^)(NSArray<NSDictionary *> *, NSError *_Nullable))completion;
- (void)searchGames:(NSString *)query system:(NSString *)system
        completion:(void (^)(NSArray<NSDictionary *> *, NSError *_Nullable))completion;
/// Reads only the requested verified chunk, installing its pack if needed.
/// All returned rows have enabled:false. Callers must gate dialect, status,
/// parameters and dependencies against their actual engine capabilities.
- (void)cheatsForGame:(NSDictionary *)game
          completion:(void (^)(NSArray<NSDictionary *> *, NSError *_Nullable))completion;

/// Boot-time native adapters: exact typed identities and verified installed
/// chunks only. Disk reads, no fetch or main-queue callbacks. Off-main only.
- (NSArray<NSDictionary *> *)installedProgramsForIdentity:(NSDictionary *)identity;

/// nil means no match; exact requires compatible source-specific strong IDs.
/// Bare serial/game ID without a known matching revision remains candidate.
+ (nullable NSString *)matchGame:(NSDictionary *)game identity:(NSDictionary *)identity;
/// YES only for known contradictory systems, regions, languages, revisions or
/// comparable typed identities. Missing identifiers/title matches are not a
/// conflict; callers may confirm candidates but must never override a conflict.
+ (BOOL)gameHasConflict:(NSDictionary *)game identity:(NSDictionary *)identity;
@end

NS_ASSUME_NONNULL_END
