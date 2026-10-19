// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>
#import "NeoTextureEngine.h"

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString *const NeoTexturePackStoreErrorDomain;

/// Error codes (NSError.code); userInfo "key" holds the stable label key.
typedef NS_ENUM(NSInteger, NeoTexturePackError) {
  NeoTexturePackErrorNetwork = 1,     // download failed (resumable when resume data was kept)
  NeoTexturePackErrorChanged = 2,     // published file differs from the verified size/SHA-256
  NeoTexturePackErrorSpace = 3,       // not enough free storage
  NeoTexturePackErrorArchive = 4,     // unreadable, damaged or unsupported archive
  NeoTexturePackErrorLayout = 5,      // no usable texture for this engine/game
  NeoTexturePackErrorWrite = 6,       // could not write the engine folder
  NeoTexturePackErrorCancelled = 7,
  NeoTexturePackErrorBusy = 8,        // another operation on the same folder is running
  NeoTexturePackErrorRegion = 9,      // pack names another region: confirmation required
  NeoTexturePackErrorConflict = 10,   // another pack owns this folder: confirmation required
  NeoTexturePackErrorManual = 11,     // the author only offers a manual download
  NeoTexturePackErrorHTML = 12,       // the server answered with a web page instead of an archive
};

/// A pack installed in an engine folder, from its NeoStation-pack.json
/// (or "manual": a folder NeoStation did not install).
/// {folder, pack_id, version, title, files, bytes, installed_at, source,
///  manual: BOOL, sha256}.
typedef NSDictionary<NSString *, id> NeoTextureInstalled;

/// Downloads a catalogue pack from the author's own URL and installs it.
///
/// Download: one at a time, into Library/Caches (never backed up), resumable
/// when the server supports it. Each part is checked against the catalogue's
/// size and SHA-256 before use; an HTML page is rejected as such.
/// Install: free space is checked first; the archive is streamed (no whole
/// archive, entry or solid block in memory) into a private staging folder on
/// the engine's volume; the staged folder is validated, then replaces the
/// previous folder in one rename, with the previous one restored on failure.
/// Only the pack's own folders are ever removed: never a game, a save, a BIOS
/// or another folder of the engine.
@interface NeoTexturePackStore : NSObject
+ (instancetype)sharedStore;
/// Default Library/Caches/NeoStation/Textures/Downloads.
@property(nonatomic, copy) NSString *downloadDirectory;
/// Free bytes at a path; injectable for tests.
@property(nonatomic, copy) unsigned long long (^freeSpace)(NSString *path);
/// Injectable download transport for tests: writes the response body to
/// `destination` starting at `offset` (0 for a new download), reporting
/// progress; calls completion once with the HTTP content type.
@property(nonatomic, copy, nullable) void (^transport)(NSURL *url, NSString *destination, unsigned long long offset,
                                                        void (^progress)(unsigned long long written),
                                                        void (^completion)(NSString *_Nullable contentType, NSError *_Nullable error));

/// {state: idle|downloading|paused|verifying|installing|failed|done,
///  received, total, error (label key), resumable}.
- (NSDictionary *)jobForPack:(NSString *)packID;
- (BOOL)isBusy;

/// Downloads (or resumes) then installs. `identity` is the game the pack is
/// installed for; with `replace` NO an existing folder owned by another pack
/// fails with NeoTexturePackErrorConflict so the page can ask first.
- (void)installPack:(NSDictionary *)pack
             engine:(id<NeoTextureEngine>)engine
           identity:(nullable NSDictionary *)identity
            replace:(BOOL)replace
         completion:(void (^)(NSDictionary *_Nullable result, NSError *_Nullable error))completion;
/// `confirmed`: the user accepted the engine installer's explanation of a
/// mismatch (NeoTexturePackErrorRegion from an engine with its own installer);
/// the verified download is kept until then.
- (void)installPack:(NSDictionary *)pack
             engine:(id<NeoTextureEngine>)engine
           identity:(nullable NSDictionary *)identity
            replace:(BOOL)replace
          confirmed:(BOOL)confirmed
         completion:(void (^)(NSDictionary *_Nullable result, NSError *_Nullable error))completion;
/// Stops the download and keeps resume data when the server allows it.
- (void)pausePack:(NSString *)packID;
/// Stops and deletes the partial download.
- (void)cancelPack:(NSString *)packID;

/// Imports a folder or a ZIP/7z chosen in Files for this game (security
/// scoped). The archive layout decides the folder: the game's own ID folder,
/// the engine's region-free form, or the archive root as the game's folder.
/// A pack for another region of the same game fails with ...ErrorRegion and
/// `details` {sourceIDs} unless allowOtherRegion.
- (void)importURL:(NSURL *)url
           engine:(id<NeoTextureEngine>)engine
         identity:(NSDictionary *)identity
 allowOtherRegion:(BOOL)allowOtherRegion
          replace:(BOOL)replace
       completion:(void (^)(NSDictionary *_Nullable result, NSError *_Nullable error))completion;

/// Installed folders below the engine's root that concern this game (the
/// engine's effective folders and any NeoStation pack that declares the game).
- (NSArray<NeoTextureInstalled *> *)installedForIdentity:(NSDictionary *)identity engine:(id<NeoTextureEngine>)engine;
/// Every installed folder of the engine (bounded scan of the root's children).
- (NSArray<NeoTextureInstalled *> *)installedForEngine:(id<NeoTextureEngine>)engine;
/// Removes one installed folder (and nothing else) off the main thread.
- (void)removeInstalled:(NeoTextureInstalled *)installed
                 engine:(id<NeoTextureEngine>)engine
             completion:(void (^)(NSError *_Nullable error))completion;

/// Size and SHA-256 verification of a downloaded file, streamed.
+ (nullable NSString *)sha256OfFile:(NSString *)path size:(unsigned long long *_Nullable)size;
/// Bytes required to install: download (unless already present) + installed size + 1 GiB headroom.
+ (unsigned long long)requiredBytesForPack:(NSDictionary *)pack downloaded:(BOOL)downloaded;
@end

NS_ASSUME_NONNULL_END
