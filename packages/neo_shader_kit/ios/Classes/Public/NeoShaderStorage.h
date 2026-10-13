// SPDX-License-Identifier: GPL-3.0-or-later
// Installed shaders of one engine: verified downloads from a bundled
// catalog, favourites, profiles and the storage report. Everything lives
// below one root directory per engine:
//
//   files/<revision>/<repository path>   files of installed presets, shared
//                                         by every preset of that revision
//   installed.json                        installed presets and their files
//   favorites.json, profiles.json         the user's choices
//   previews/<sha256>.png                 cached catalog previews
//   staging/                              downloads not yet verified
//
// A preset is installed only when every file it needs has the size and
// SHA-256 its catalog records; files are moved into place after all of
// them are verified, so an interrupted or refused download leaves nothing
// behind but the staging folder (emptied at the next start). Removing a
// preset deletes only the files no other installed preset uses.
#import <Foundation/Foundation.h>

#import "NeoShaderCatalog.h"
#import "NeoShaderEngine.h"

NS_ASSUME_NONNULL_BEGIN

@interface NeoShaderInstallation : NSObject
/// Catalog identifier ("crt/crt-royale.slangp").
@property(nonatomic, copy, readonly) NSString *identifier;
/// Repository revision of its files (the catalog's sourceRevision).
@property(nonatomic, copy, readonly) NSString *revision;
/// Repository-relative paths of every file it uses.
@property(nonatomic, copy, readonly) NSArray<NSString *> *files;
@property(nonatomic, readonly) unsigned long long bytes;
@property(nonatomic, strong, readonly) NSDate *installedAt;
@end

/// A named shader with its parameter values, applicable to any game.
@interface NeoShaderProfile : NSObject
@property(nonatomic, copy, readonly) NSString *identifier;
@property(nonatomic, copy, readonly) NSString *name;
/// The engine's shader identifier ("slang:crt/crt-royale.slangp" or a
/// built-in preset).
@property(nonatomic, copy, readonly) NSString *shader;
@property(nonatomic, copy, readonly) NSDictionary<NSString *, NSNumber *> *parameters;
@property(nonatomic, strong, readonly) NSDate *createdAt;
@end

/// Stable reason codes of NeoShaderResult failures (translated by the host).
FOUNDATION_EXPORT NSString *const NeoShaderErrorEntryInvalid;      // ENTRY_INVALID
FOUNDATION_EXPORT NSString *const NeoShaderErrorEntryTooLarge;     // ENTRY_TOO_LARGE
FOUNDATION_EXPORT NSString *const NeoShaderErrorNoDownloadURL;     // DOWNLOAD_URL
FOUNDATION_EXPORT NSString *const NeoShaderErrorNetwork;           // DOWNLOAD_NETWORK
FOUNDATION_EXPORT NSString *const NeoShaderErrorHTTPStatus;        // DOWNLOAD_HTTP
FOUNDATION_EXPORT NSString *const NeoShaderErrorSizeMismatch;      // DOWNLOAD_SIZE
FOUNDATION_EXPORT NSString *const NeoShaderErrorHashMismatch;      // DOWNLOAD_HASH
FOUNDATION_EXPORT NSString *const NeoShaderErrorCancelled;         // DOWNLOAD_CANCELLED
FOUNDATION_EXPORT NSString *const NeoShaderErrorStorageSpace;      // STORAGE_SPACE
FOUNDATION_EXPORT NSString *const NeoShaderErrorStorageWrite;      // STORAGE_WRITE
FOUNDATION_EXPORT NSString *const NeoShaderErrorBusy;              // DOWNLOAD_BUSY
FOUNDATION_EXPORT NSString *const NeoShaderErrorProfileName;       // PROFILE_NAME
FOUNDATION_EXPORT NSString *const NeoShaderErrorProfileLimit;      // PROFILE_LIMIT

/// Loads the bytes of one https URL. The default uses an ephemeral
/// NSURLSession (no cookies, no cache); tests serve files from disk.
/// `status` is the HTTP status (0 when unknown).
typedef void (^NeoShaderDataLoader)(NSURL *url,
                                    void (^completion)(NSData *_Nullable data, NSInteger status,
                                                       NSError *_Nullable error));

@interface NeoShaderStorage : NSObject

/// The one storage of `root` in this process (the in-game menus and the
/// maintenance tools share it, so a download in progress is never mistaken
/// for a leftover). `engine` is "libretro" or "dolphin".
+ (instancetype)sharedStorageWithRoot:(NSString *)root engine:(NSString *)engine;
/// `root` is created when missing; leftovers of interrupted downloads are
/// removed. Use sharedStorageWithRoot:engine: outside tests.
- (instancetype)initWithRoot:(NSString *)root engine:(NSString *)engine;
@property(nonatomic, copy, readonly) NSString *root;
@property(nonatomic, copy, readonly) NSString *engine;

/// Directory a preset of `revision` is compiled from (files/<revision>).
- (NSString *)filesDirectoryForRevision:(NSString *)revision;

#pragma mark Installed presets

- (NSArray<NeoShaderInstallation *> *)installations;
- (nullable NeoShaderInstallation *)installationWithIdentifier:(NSString *)identifier;
/// Every file of the installation is present with a regular file of the
/// size its catalog recorded (no hashing: cheap enough for list rows).
- (BOOL)installationIsComplete:(NeoShaderInstallation *)installation;
/// Downloads (only the files missing or different), verifies and installs
/// `entry` of `catalog`. `progress` (bytes received, bytes to receive) and
/// `completion` run on the main queue; one installation at a time per
/// identifier (DOWNLOAD_BUSY otherwise).
- (void)installEntry:(NeoShaderCatalogEntry *)entry
             catalog:(NeoShaderCatalog *)catalog
            progress:(nullable void (^)(unsigned long long received, unsigned long long expected))progress
          completion:(void (^)(NeoShaderResult *result))completion;
- (void)cancelInstallationOfIdentifier:(NSString *)identifier;
- (BOOL)isInstallingIdentifier:(NSString *)identifier;
/// Removes the installation and deletes the files no other installation
/// of the same revision uses. Profiles and favourites are kept.
- (BOOL)removeInstallationWithIdentifier:(NSString *)identifier error:(NSError *_Nullable *_Nullable)error;

#pragma mark Previews

/// PNG bytes of a catalog preview: from the cache when its SHA-256
/// matches, else downloaded, verified and cached. Completion on the main
/// queue; nil on failure.
- (void)previewDataForFile:(NeoShaderCatalogFile *)file
                   catalog:(NeoShaderCatalog *)catalog
                completion:(void (^)(NSData *_Nullable data))completion;

#pragma mark Favourites and profiles

- (NSArray<NSString *> *)favorites;
- (BOOL)isFavorite:(NSString *)identifier;
- (void)setFavorite:(BOOL)favorite identifier:(NSString *)identifier;

- (NSArray<NeoShaderProfile *> *)profiles;
/// Name: 1 to 64 characters after trimming (PROFILE_NAME); at most 200
/// profiles (PROFILE_LIMIT). A profile with the same name is replaced.
- (nullable NeoShaderProfile *)saveProfileWithName:(NSString *)name
                                            shader:(NSString *)shader
                                        parameters:(NSDictionary<NSString *, NSNumber *> *)parameters
                                             error:(NSError *_Nullable *_Nullable)error;
- (BOOL)removeProfileWithIdentifier:(NSString *)identifier;

#pragma mark Storage

/// {"engine", "installed", "installedBytes", "orphanFiles", "orphanBytes",
///  "staleDownloads", "staleBytes", "previewBytes"}: what the storage holds
/// and what can be removed without touching an installed preset, a profile
/// or a favourite.
- (NSDictionary<NSString *, id> *)storageReport;
/// Removes only what storageReport lists as removable (orphan files,
/// interrupted downloads, cached previews); returns the bytes freed.
- (unsigned long long)cleanCaches;

/// Test seam: replaces the network.
@property(nonatomic, copy, nullable) NeoShaderDataLoader dataLoader;
/// Largest download of one entry (default 64 MiB).
@property(nonatomic, assign) unsigned long long maximumEntryBytes;

@end

NS_ASSUME_NONNULL_END
