#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
/// Shared, bounded catalogue parsers and per-core native-code adapters. No code is
/// enabled by parsing, downloading, importing or restoring saved preferences.
@interface LibretroCheats : NSObject
+ (nullable NSArray<NSDictionary *> *)parseCHT:(NSData *)data error:(NSError **)error;
+ (nullable NSArray<NSDictionary *> *)parseOpenEmu:(NSData *)data error:(NSError **)error;
+ (NSArray<NSString *> *)supportedCoreIDs;
+ (nullable NSArray<NSString *> *)codesForCheat:(NSDictionary *)cheat core:(NSString *)core console:(NSString *)console;
+ (NSString *)digest:(NSData *)data;
+ (NSString *)gitBlobSHA:(NSData *)data;
/// Stream the actual extracted content, off the emulation/main queues. No basename-only identity.
+ (NSString *)identityContentPath:(NSString *)path;
+ (nullable NSDictionary *)identityAtPath:(NSString *)path console:(NSString *)console core:(NSString *)core;
/// A hash mismatch is never promoted by a similar name. Title matches are candidates only.
+ (NSString *)matchGame:(NSDictionary *)game identity:(NSDictionary *)identity;
+ (NSString *)versionTitle:(NSString *)title;
+ (NSString *)searchTitle:(NSString *)title;
@end
NS_ASSUME_NONNULL_END
