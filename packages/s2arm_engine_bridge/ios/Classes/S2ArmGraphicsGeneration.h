#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
/// A game-specific cache transaction. The legacy wire directory and an earlier
/// active generation remain playable throughout copying, translation and verification.
@interface S2ArmGraphicsGeneration : NSObject
@property(nonatomic, readonly) NSString *gid;
@property(nonatomic, readonly) NSString *buildID;
@property(nonatomic, readonly) NSString *wire;
@property(nonatomic, readonly) NSString *gameDir;
@property(nonatomic, readonly) BOOL active;
+ (nullable instancetype)planForGame:(NSString *)gid directory:(NSString *)gameDir root:(NSString *)root
                              chain:(NSString *)chain reused:(BOOL)reused error:(NSError **)error;
/// Select a transaction using the preparation and platform identities.
- (instancetype)initWithDirectory:(NSString *)directory gid:(NSString *)gid buildID:(NSString *)buildID
                          content:(NSString *)content chain:(NSString *)chain hardware:(NSString *)hardware
                          osBuild:(NSString *)osBuild reuseLegacy:(BOOL)reuseLegacy;
- (BOOL)stage:(BOOL (^)(void))cancel progress:(void (^)(NSUInteger files))progress error:(NSError **)error;
- (BOOL)activateWithGPU:(const uint64_t *)stats error:(NSError **)error;
@end
NS_ASSUME_NONNULL_END
