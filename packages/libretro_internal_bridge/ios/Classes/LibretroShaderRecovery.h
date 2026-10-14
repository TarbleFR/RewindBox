#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Durable activation attempts, separate from the user's shader preferences.
/// A session interrupted by process termination while compiling or rendering
/// a shader is not retried automatically for the same core, game and preset.
/// Manual selection may retry. The first completed GPU frame moves the attempt
/// to the active marker, kept until normal stop or shader deactivation. An
/// interrupted session is evidence of interruption, not proof that the shader
/// caused the process to end (iOS may also terminate an app for other reasons).
@interface LibretroShaderRecovery : NSObject
- (instancetype)initWithDirectory:(NSString *)directory;
@property(nonatomic, readonly) BOOL canProtect;
- (BOOL)blocksAutomaticPreset:(NSString *)preset core:(NSString *)core game:(NSString *)game;
/// Writes and fsyncs before returning a token. nil refuses activation when
/// the protection cannot be saved. Every completion must use its own token:
/// an old callback cannot clear a newer attempt.
- (nullable NSString *)beginPreset:(NSString *)preset core:(NSString *)core game:(NSString *)game;
- (void)finishToken:(NSString *)token confirmed:(BOOL)confirmed;
/// Shader disabled or switched to a built-in effect: the previous downloaded
/// shader no longer renders. Does not clear an independent compilation attempt.
- (void)deactivatePreset;
/// A normal session stop cancels pending attempts, without clearing older
/// interrupted presets. Crashes leave the pending marker on disk.
- (void)finishSession;
@end

/// Localized explanation selected by the native UI; technical codes remain
/// in the session journal and are never substituted for translated text.
FOUNDATION_EXPORT NSString *LibretroShaderFailureTextKey(NSString *_Nullable code);

NS_ASSUME_NONNULL_END
