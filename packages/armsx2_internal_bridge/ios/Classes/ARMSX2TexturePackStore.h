// SPDX-License-Identifier: GPL-3.0-or-later
// HD texture packs of the embedded ARMSX2 engine (Build 485): the store used by
// the library (no ARMSX2Core loaded) and by the in-game menu. Files live in
// <ARMSX2 data>/textures/<SERIAL>/replacements, NeoStation's per-game choices and
// the serials the engine read in <ARMSX2 data>/inis/NeoStation-textures.json.
// Every method blocks: call it off the main thread.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Expands a .tar.zst pack into [destination] with the engine's decoder
/// (ARMSX2Core ABI 8, in a game only). Returns nil on success or an error key.
typedef NSString* _Nullable (^ARMSX2TextureExpander)(NSString* archive, NSString* destination,
                                                      uint64_t available, const volatile int* cancel,
                                                      volatile uint64_t* consumed);
/// fraction in [0, 1] or -1 when unknown; phase "expanding" or "installing".
typedef void (^ARMSX2TextureProgress)(double fraction, NSString* phase);

@interface ARMSX2TexturePackStore : NSObject
+ (NSString*)texturesRootForDataPath:(NSString*)dataPath;
/// serial, version, crc, title, source ("session", "disc", "name", "none") and region.
+ (NSDictionary<NSString*, id>*)identifyGameAtPath:(NSString*)gamePath dataPath:(NSString*)dataPath;
/// Records what the engine read for a game it booted (serial, crc, version, title).
+ (void)recordIdentity:(NSDictionary<NSString*, id>*)identity
           forGamePath:(NSString*)gamePath
              dataPath:(NSString*)dataPath;
/// Installed pack (manifest, or a scan for a pack copied without NeoStation),
/// NeoStation's choice ("enabled": NSNumber or NSNull), the game's INI value when
/// its CRC is known ("iniEnabled") and the global default ("globalEnabled").
+ (NSDictionary<NSString*, id>*)statusForSerial:(NSString*)serial
                                            crc:(nullable NSString*)crc
                                       dataPath:(NSString*)dataPath;
+ (BOOL)setEnabled:(BOOL)enabled serial:(NSString*)serial dataPath:(NSString*)dataPath;
/// Moves the pack aside and turns the game's choice off. "removingPath" is
/// deleted with -discardPath: once the engine (if running) reloaded its map.
+ (NSDictionary<NSString*, id>*)removeSerial:(NSString*)serial dataPath:(NSString*)dataPath;
/// {"games":{"<serial>":bool}} for ARMSX2Core set_texture_boot_preferences.
+ (NSString*)bootPreferencesJSONForDataPath:(NSString*)dataPath;
/// GPU capabilities the engine's Metal device reports for replacement formats.
+ (NSDictionary<NSString*, id>*)deviceFormats;
+ (void)discardPath:(nullable NSString*)path;
/// Leftovers of an interrupted import. Never while an import or a game runs.
+ (void)sweepLeftoversInDataPath:(NSString*)dataPath;
@end

/// One import, from the Files choice to its installation or abandonment.
@interface ARMSX2TextureImport : NSObject
@property(nonatomic, readonly) NSString* token;
@property(nonatomic, readonly, copy) NSString* serial;
/// ARMSX2's data folder the pack is installed under.
@property(nonatomic, readonly, copy) NSString* dataPath;
- (instancetype)initWithURL:(NSURL*)url
                   dataPath:(NSString*)dataPath
                       game:(NSDictionary<NSString*, id>*)game
                   expander:(nullable ARMSX2TextureExpander)expander;
- (instancetype)init NS_UNAVAILABLE;
/// Lists and checks the pack without writing it (a .tar.zst is first expanded).
- (NSDictionary<NSString*, id>*)inspectWithProgress:(nullable ARMSX2TextureProgress)progress;
/// Installs the inspected pack for the game. A verdict needing confirmation
/// is refused unless [allow] (the user confirmed the explanation).
- (NSDictionary<NSString*, id>*)installAllowingMismatch:(BOOL)allow progress:(nullable ARMSX2TextureProgress)progress;
- (void)cancel;
/// Releases the security scope and deletes any temporary expansion.
- (void)close;
@end

NS_ASSUME_NONNULL_END
