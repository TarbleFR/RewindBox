#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
/// Shared, bounded catalogue parsers and per-core native-code adapters. No code is
/// enabled by parsing, downloading, importing or restoring saved preferences.
@interface LibretroCheats : NSObject
+ (nullable NSArray<NSDictionary *> *)parseCHT:(NSData *)data error:(NSError **)error;
+ (nullable NSArray<NSDictionary *> *)parseOpenEmu:(NSData *)data error:(NSError **)error;
+ (NSArray<NSString *> *)supportedCoreIDs;
/// Maximum ASCII bytes accepted by the audited core entry point, excluding its NUL.
+ (NSUInteger)maximumCodeBytesForCore:(NSString *)core;
+ (nullable NSArray<NSString *> *)codesForCheat:(NSDictionary *)cheat core:(NSString *)core console:(NSString *)console;
+ (NSString *)digest:(NSData *)data;
+ (NSString *)gitBlobSHA:(NSData *)data;
/// Stream the actual extracted content, off the emulation/main queues. No basename-only identity.
+ (NSString *)identityContentPath:(NSString *)path;
/// Read SYSTEM.CNF from a bounded ISO9660 data track; never infer serial from its filename.
+ (nullable NSString *)playStationSerialAtPath:(NSString *)path;
+ (nullable NSDictionary *)identityAtPath:(NSString *)path console:(NSString *)console core:(NSString *)core;
/// `identities` holds {type,value,scheme}; hash scopes are never interchangeable.
/// A hash mismatch is never promoted by a similar name. Title matches are candidates only.
+ (NSString *)matchGame:(NSDictionary *)game identity:(NSDictionary *)identity;
+ (NSString *)versionTitle:(NSString *)title;
+ (NSString *)searchTitle:(NSString *)title;
+ (NSDictionary *)metadataForTitle:(NSString *)title;
/// FBNeo uses native INI files and core options, not retro_cheat_set.
+ (BOOL)canInstallFBNeoPrograms:(NSArray<NSDictionary *> *)programs game:(NSDictionary *)game;
+ (nullable NSDictionary *)installFBNeoPrograms:(NSArray<NSDictionary *> *)programs game:(NSDictionary *)game
                               systemDirectory:(NSString *)directory error:(NSError **)error;
/// Copy only an intact receipt-backed native file into an isolated session folder.
+ (nullable NSDictionary *)stageManagedFBNeoDriver:(NSString *)driver systemDirectory:(NSString *)directory
                                      destination:(NSString *)destination error:(NSError **)error;
@end
NS_ASSUME_NONNULL_END
