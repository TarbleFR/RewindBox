// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Where and how one embedded engine loads replacement textures, and the
/// engine's own switch for them. One adapter per engine; each is configured
/// with the directories NeoStation actually gives that engine (from the Dart
/// launch services or the running session), never with a container path.
///
/// Identity dictionaries: {system, title, regions, revision, path,
/// identities:[{type, scheme, value}], crc (PS2 executable CRC, 8 hex),
/// gameKey (libretro "<system>/<rom file>")}.
///
/// Every method may read or write files: call them off the main thread.
@protocol NeoTextureEngine <NSObject>
/// dolphin, armsx2, ppsspp or azahar.
@property(nonatomic, copy, readonly) NSString *engineID;
/// Folder whose children are the per-game texture folders the engine reads.
@property(nonatomic, copy, readonly) NSString *texturesRoot;
- (BOOL)supportsSystem:(NSString *)system;
/// The game's own folder name below texturesRoot (for instance SLUS-21050/replacements,
/// GZ2E01, ULUS10041 or 0004000000033500); nil when the identity has no usable ID.
- (nullable NSString *)folderForIdentity:(NSDictionary *)identity;
/// Folders below texturesRoot the engine would actually read for this game,
/// in the engine's order (Dolphin falls back to the region-free folder).
- (NSArray<NSString *> *)effectiveFoldersForIdentity:(NSDictionary *)identity;
/// Whether a file at this path (relative to a pack folder) may be installed.
- (BOOL)acceptsFile:(NSString *)relativePath;
/// Checks a staged pack folder before it replaces anything. Returns nil when
/// the folder is usable, else an error key (noTextures, missingIni, ...).
- (nullable NSString *)problemWithStagedFolder:(NSString *)folder pack:(nullable NSDictionary *)pack;

/// {known: whether the engine's setting can be read and written for this game,
/// enabled, scope: game|default, appliesAt: next-launch|live, reason: when unknown,
/// setting: human-readable engine key}.
- (NSDictionary *)activationForIdentity:(NSDictionary *)identity;
- (BOOL)setActivation:(BOOL)enabled identity:(NSDictionary *)identity error:(NSError **)error;

@optional
/// Engines that already have their own pack installer (ARMSX2 and its
/// Build 485 store): NeoTexturePackStore downloads and verifies the author's
/// archive, then hands it over instead of writing the engine folder itself.
- (BOOL)installsPacks;
/// Name prefix of the folder, directly below texturesRoot, where the store
/// expands an archive the engine cannot read as is (7z, a subtree of a
/// repository archive); the engine's own leftover sweep removes such folders.
- (NSString *)expansionPrefix;
/// YES when the engine reads this download format itself (zip, tar).
- (BOOL)readsArchiveFormat:(NSString *)format;
/// Installs `source` (the verified archive, or a folder the store expanded at
/// -expansionPathForToken:) for the game. `pack`: the catalogue entry (its
/// "match" exact means the author lists this game), nil for an import.
/// `confirmed`: the user accepted the explanation of a mismatch. Returns
/// {success, error (label key), needsConfirmation, match, packSerial,
/// regionConflict, crcConflict, uncertain, files, bytes, replaced}.
- (NSDictionary *)installSource:(NSString *)source
                       expanded:(BOOL)expanded
                           pack:(nullable NSDictionary *)pack
                       identity:(NSDictionary *)identity
                      confirmed:(BOOL)confirmed
                       progress:(void (^)(double fraction))progress
                      cancelled:(BOOL (^)(void))cancelled;
/// Imports a folder or an archive chosen in Files (security scoped URL).
- (NSDictionary *)importURL:(NSURL *)url
                   identity:(NSDictionary *)identity
                  confirmed:(BOOL)confirmed
                   progress:(void (^)(double fraction))progress
                  cancelled:(BOOL (^)(void))cancelled;
/// Packs installed for this game / for every game, as NeoTextureInstalled rows.
- (NSArray<NSDictionary *> *)installedPacksForIdentity:(NSDictionary *)identity;
- (NSArray<NSDictionary *> *)installedPacks;
/// Removes one installed pack (and nothing else): {success, error}.
- (NSDictionary *)removeInstalledPack:(NSDictionary *)installed;
/// A page with the engine's own details for this game (live engine state),
/// pushed from the unified page; nil when the engine has none.
- (nullable id)detailsViewControllerWithLocale:(NSString *)locale;
/// What the engine itself recorded for a game file at an earlier boot (its
/// identity in the unified form, with "identity_source": session, disc or
/// name; "name" means read from the file name, to be confirmed). nil if none.
- (nullable NSDictionary *)recordedIdentityForGamePath:(NSString *)path;
@end

/// Engine adapters built into this pod. Each class documents the engine
/// sources it mirrors. The libretro adapters may be given session hooks so a
/// change during a game goes through the running core's option store.
@interface NeoTextureEngines : NSObject
/// Dolphin user directory (<AppSupport>/NeoStation/Dolphin/User).
+ (id<NeoTextureEngine>)dolphinWithUserDirectory:(NSString *)userDirectory;
/// ARMSX2 data root (<Documents>/ARMSX2). The pack files, NeoStation's
/// per-game choice and the installer are those of the ARMSX2 bridge
/// (ARMSX2TexturePackStore, Build 485), reached at run time. `gamePath`: the
/// game image (its identity as the engine recorded it). `host`: the running
/// game's ARMSX2TextureHost (live switch, reload), nil in the library.
+ (id<NeoTextureEngine>)armsx2WithDataDirectory:(NSString *)dataDirectory
                                       gamePath:(nullable NSString *)gamePath
                                           host:(nullable id)host;
/// PPSSPP memory stick root = the libretro save directory of the core
/// (<Documents>/Libretro/Saves/PPSSPP); config = <Documents>/Libretro/Config.
+ (id<NeoTextureEngine>)ppssppWithSaveDirectory:(NSString *)saveDirectory configDirectory:(NSString *)configDirectory;
/// Azahar user directory (<Documents>/Libretro/Saves/Azahar/Azahar).
+ (id<NeoTextureEngine>)azaharWithUserDirectory:(NSString *)userDirectory configDirectory:(NSString *)configDirectory;
/// Optional session hooks for libretro adapters: read (key, gameKey) -> value
/// and write (key, value, gameKey) -> success. Used while that game runs.
+ (void)setLibretroSessionReader:(nullable NSString *_Nullable (^)(NSString *key, NSString *gameKey))reader
                          writer:(nullable BOOL (^)(NSString *key, NSString *value, NSString *gameKey))writer
                       forEngine:(id<NeoTextureEngine>)engine;
/// The option keys the libretro adapters write.
+ (NSString *)ppssppOptionKey;
+ (NSString *)azaharOptionKey;
@end

/// INI helpers of the Dolphin adapter: one key in one section, every other
/// line kept byte for byte.
FOUNDATION_EXPORT NSString *_Nullable NeoTextureINIValue(NSString *text, NSString *section, NSString *key);
FOUNDATION_EXPORT NSString *NeoTextureINISet(NSString *text, NSString *section, NSString *key, NSString *value);

NS_ASSUME_NONNULL_END
