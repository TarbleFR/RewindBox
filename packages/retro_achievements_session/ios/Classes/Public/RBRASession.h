#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

#ifdef __cplusplus
extern "C" {
#endif

/// Called once, before starting the engine. The returned immutable dictionary
/// owns its credentials for this launch. Never include it in logs or Flutter
/// events. A missing, expired, consumed or mismatched handle disables RA.
FOUNDATION_EXPORT NSDictionary<NSString *, id> *RBRATakeLaunchConfiguration(
    NSDictionary *arguments, NSString *engine);

/// Publish observed engine state, not merely the requested setting. Only
/// non-secret status fields are forwarded; obsolete session callbacks are ignored.
FOUNDATION_EXPORT void RBRAPublishSessionState(NSDictionary *configuration,
                                               NSDictionary *state);
FOUNDATION_EXPORT void RBRAEndSession(NSDictionary *configuration);

/// UI messages use the app's explicit language, never the iOS preferred locale.
FOUNDATION_EXPORT NSString *RBRALocalizedText(NSString *key, NSString *locale);

#ifdef __cplusplus
}
#endif

NS_ASSUME_NONNULL_END
