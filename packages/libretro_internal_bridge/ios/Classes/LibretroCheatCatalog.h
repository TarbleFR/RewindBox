#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
/// Downloaded catalogues live separately from imported RetroArch configuration.
/// Bundled indices are available immediately; matching game files are cached on demand.
@interface LibretroCheatCatalog : NSObject
- (instancetype)initWithDirectory:(NSString *)directory;
+ (NSArray<NSDictionary *> *)sources;
+ (nullable NSString *)folderForConsole:(NSString *)console;
/// Resource bundle override for integration tests. Read only from background queues.
@property(nonatomic, copy, nullable) NSString *bundledDirectory;
@property(nonatomic, copy, nullable) void (^diagnostic)(NSString *message);
- (NSDictionary *)resolveIdentity:(NSDictionary *)identity;
/// Injectable bounded transport for deterministic parser/cache/network tests. Runs off-main.
@property(nonatomic, copy, nullable) NSData *_Nullable (^fetch)(NSURL *url, NSUInteger limit, NSError **error);
- (void)loadSource:(NSString *)source console:(NSString *)console completion:(void (^)(NSDictionary *_Nullable))completion;
- (void)installSource:(NSString *)source console:(NSString *)console update:(BOOL)update
           completion:(void (^)(NSDictionary *_Nullable catalog, NSError *_Nullable error))completion;
- (void)checkSource:(NSString *)source completion:(void (^)(NSString *_Nullable revision, NSError *_Nullable error))completion;
- (void)downloadGame:(NSDictionary *)game completion:(void (^)(NSArray<NSDictionary *> *_Nullable cheats, NSError *_Nullable error))completion;
- (void)removeSource:(NSString *)source console:(NSString *)console completion:(void (^)(void))completion;
@end
NS_ASSUME_NONNULL_END
