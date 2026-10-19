// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString *const NeoTextureCatalogErrorDomain;
/// Posted on main whenever the index, a download or an installation changes.
/// userInfo may hold "pack" (a pack ID) or "catalogue" (@YES).
FOUNDATION_EXPORT NSNotificationName const NeoTextureCatalogDidChangeNotification;

/// Injected transports call completion once, on any queue, and respect
/// maximumBytes; the catalogue checks size and content again.
typedef void (^NeoTextureFetch)(NSURL *url, NSUInteger maximumBytes,
                                void (^completion)(NSData *_Nullable data, NSError *_Nullable error));

/// The unified HD texture pack index. It only stores metadata: the author's
/// official download URL, sizes, SHA-256, target game IDs, layout, credits
/// and terms. Texture files are fetched by NeoTexturePackStore when a pack is
/// chosen; nothing here downloads a pack or writes an engine folder.
///
/// Index sources, in order: the last validated remote index
/// (`storageDirectory/manifest.json`), the index bundled with the app, then
/// the remote index. A refresh that fails never replaces a valid index.
@interface NeoTextureCatalog : NSObject
+ (instancetype)sharedCatalog;
/// Default: Claude/native/textures/catalogue/manifest.json.gz of TarbleFR/neostation-ios.
@property(nonatomic, strong) NSURL *manifestURL;
/// Folder holding the bundled manifest.json(.gz); found in the pod resources.
@property(nonatomic, copy, nullable) NSString *bundledDirectory;
/// Default: Library/Application Support/NeoStation/Textures/Catalogue.
@property(nonatomic, copy) NSString *storageDirectory;
@property(nonatomic, copy, nullable) NeoTextureFetch fetch;

/// state: missing|bundled|downloaded; refreshing; revision; generated_at;
/// refreshed_at (last successful refresh, seconds since 1970); refresh_error
/// (last failed attempt, kept until a refresh succeeds); pack_count;
/// systems {system: count}; sources [...].
- (NSDictionary *)snapshot;
/// Reads the local or bundled index; never touches the network.
- (void)loadWithCompletion:(void (^)(NSDictionary *snapshot, NSError *_Nullable error))completion;
/// "Download the HD catalogues": fetches the unified index, validates it and
/// keeps it for offline use. On failure the previous index stays in effect
/// and the error is recorded in the snapshot.
- (void)refreshWithCompletion:(void (^)(NSDictionary *snapshot, NSError *_Nullable error))completion;

/// Packs for one console and engine, sorted by game title then pack title.
- (NSArray<NSDictionary *> *)packsForSystem:(NSString *)system engine:(NSString *)engine;
/// Packs that declare this game. Rows are copies of the pack with "match":
/// exact (same typed ID, compatible region/revision) or candidate (same title
/// family or region-free ID, to be confirmed by the user). Conflicts are absent.
- (NSArray<NSDictionary *> *)packsForIdentity:(NSDictionary *)identity engine:(NSString *)engine;
- (nullable NSDictionary *)packWithID:(NSString *)packID;

/// exact, candidate or nil. identity: {system, title, regions, revision,
/// identities:[{type,scheme,value}]}. A title alone is never exact; a known
/// different region or revision is a conflict (nil), never a candidate.
+ (nullable NSString *)matchPack:(NSDictionary *)pack identity:(NSDictionary *)identity;
/// A copy of the pack with the verdict of packsForIdentity: for this game in
/// "match" (absent when it does not match), for a pack that reaches the page or
/// the store without one (reopened from its installed row, chosen from a
/// console's list). An identifier read from a file name ("uncertain") never
/// makes a pack exact.
+ (NSDictionary *)pack:(NSDictionary *)pack matchedTo:(nullable NSDictionary *)identity;
/// Validates an index (JSON or gzip). Invalid packs are dropped and counted
/// in "rejected_packs"; an index without schema 1 is refused.
+ (nullable NSDictionary *)validatedIndex:(NSData *)data error:(NSError **)error;
@end

NS_ASSUME_NONNULL_END
