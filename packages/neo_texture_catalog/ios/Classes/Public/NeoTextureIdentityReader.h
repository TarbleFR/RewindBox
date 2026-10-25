// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Reads, outside a game, the identifiers an embedded engine names its texture
/// folders after (NeoTextureIdentity.h): PS2 serial and boot ELF CRC, GameCube
/// and Wii game ID and revision, PSP disc ID and version, 3DS program ID.
/// Bounded reads only; results are cached by path, size and modification date.
@interface NeoTextureIdentityReader : NSObject
/// Identity dictionary {system, title, regions, revision, crc, path, format,
/// identities:[{type, scheme, value}]} or nil, with `problem` set to the
/// reason (unreadable, unsupportedFormat, noSystemCnf, noBoot2, noSerial,
/// noDiscID, noTitleID, notGame). Blocks: call it off the main thread.
+ (nullable NSDictionary *)identityForPath:(NSString *)path
                                    system:(NSString *)system
                                     title:(nullable NSString *)title
                                   problem:(NSString *_Nullable *_Nullable)problem;
/// Same, for a library scan: a PS2 disc gives its serial without its boot ELF CRC.
+ (nullable NSDictionary *)quickIdentityForPath:(NSString *)path
                                         system:(NSString *)system
                                          title:(nullable NSString *)title
                                        problem:(NSString *_Nullable *_Nullable)problem;
/// The identity the running engine itself reported, in the same form.
+ (NSDictionary *)identityWithSystem:(NSString *)system
                               value:(NSString *)value
                            revision:(nullable NSString *)revision
                                 crc:(nullable NSString *)crc
                               title:(nullable NSString *)title;
/// Cache file (default Library/Caches/NeoStation/Textures/identities.json).
+ (void)setCachePath:(nullable NSString *)path;
@end

NS_ASSUME_NONNULL_END
