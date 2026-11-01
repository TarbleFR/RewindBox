#import <Foundation/Foundation.h>

@class LibretroCoreHost;

NS_ASSUME_NONNULL_BEGIN

/// One RetroAchievements client for one immutable central launch snapshot.
/// Evaluation and server responses stay on the emulation thread. The pinned
/// synchronous hash calculation runs separately before evaluation starts.
/// No engine-local preference or stored account is used.
@interface LibretroAchievements : NSObject

- (instancetype)initWithConsoleId:(unsigned)consoleId
                            host:(LibretroCoreHost *)host
                   configuration:(NSDictionary *)configuration;
/// Pinned rcheevos rules, shared with the core's option mutation boundary.
+ (BOOL)isHardcoreOptionAllowedForLibrary:(NSString *)library consoleId:(unsigned)consoleId
                                     key:(NSString *)key value:(NSString *)value;

@property(nonatomic, copy, nullable) void (^unlocked)(NSUInteger achievementID, NSString *title, NSString *description);
@property(nonatomic, copy, nullable) dispatch_block_t stateChanged;
@property(nonatomic, readonly) BOOL loggedIn;
@property(nonatomic, readonly, nullable) NSString *username;
@property(nonatomic, readonly) BOOL gameLoaded;
@property(nonatomic, readonly) BOOL hardcoreActive;
@property(nonatomic, readonly) unsigned totalCount;
@property(nonatomic, readonly) unsigned unlockedCount;

/// Emulation thread, after the content is loaded. Idempotent for this launch.
- (void)startWithContentPath:(NSString *)path;
- (void)doFrame;
- (void)idle;
- (BOOL)canPause;
- (void)resetGame;
- (void)shutdown;

// Transitional declarations for the old menu, removed with that menu in step 3.
// They never read, write or authenticate an engine-local account.
+ (BOOL)enabled;
+ (void)setEnabled:(BOOL)enabled;
+ (BOOL)hasStoredLogin;
- (void)loginWithUsername:(NSString *)username password:(NSString *)password completion:(void (^)(BOOL))completion;
- (void)logout;

@end

NS_ASSUME_NONNULL_END
