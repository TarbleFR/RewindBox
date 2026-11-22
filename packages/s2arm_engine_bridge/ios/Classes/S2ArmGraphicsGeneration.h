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
@property(nonatomic, readonly) BOOL requiresVerification;
/// A matching receipt may defer its archive reads until the host has started services.
- (nullable instancetype)verifyForLaunch:(BOOL (^)(void))cancel;
+ (nullable instancetype)planForGame:(NSString *)gid directory:(NSString *)gameDir root:(NSString *)root
                              chain:(NSString *)chain reused:(BOOL)reused error:(NSError **)error;
+ (nullable instancetype)planForGame:(NSString *)gid directory:(NSString *)gameDir root:(NSString *)root
                              chain:(NSString *)chain reused:(BOOL)reused deferArchiveVerification:(BOOL)defer error:(NSError **)error;
/// Only stages compatible files from an already prepared import. The normal launch
/// performs full validation and owns Metal translation, pipeline creation and activation.
+ (nullable instancetype)startupPlanInLibrary:(NSString *)library chain:(nullable NSString *)chain;
/// Select a transaction using the preparation and platform identities.
- (instancetype)initWithDirectory:(NSString *)directory gid:(NSString *)gid buildID:(NSString *)buildID
                          content:(NSString *)content chain:(NSString *)chain hardware:(NSString *)hardware
                          osBuild:(NSString *)osBuild reuseLegacy:(BOOL)reuseLegacy;
- (BOOL)stage:(BOOL (^)(void))cancel progress:(void (^)(NSUInteger files))progress error:(NSError **)error;
/// Export the named phase's bounded diagnostic tables to this game's visible
/// diagnostics folder. Each new guest session has its own UUID and inventory.
- (BOOL)writeEvidenceToDirectory:(NSString *)gameDiagnostics session:(NSString *)session phase:(NSString *)phase;
- (BOOL)activateWithGPU:(const uint64_t *)stats error:(NSError **)error;
@end
/// Only an interrupted pre-configure launch can lend its already open engine
/// to the same game, directories and pending graphics generation. Access to the
/// object is serialized by the bridge's launch gate and work queue.
@interface S2ArmGraphicsRetry : NSObject
@property(nonatomic, readonly) NSString *gid;
- (instancetype)initWithEngine:(void *)engine game:(NSString *)gid paths:(NSArray<NSString *> *)paths;
- (nullable void *)engineForGame:(NSString *)gid paths:(NSArray<NSString *> *)paths;
- (void)consume;
@end
NS_ASSUME_NONNULL_END
