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
/// Pass the exact immutable snapshot returned by Take, not a reconstructed
/// dictionary containing its public sessionId. End is idempotent.
FOUNDATION_EXPORT void RBRAPublishSessionState(NSDictionary *configuration,
                                               NSDictionary *state);
FOUNDATION_EXPORT void RBRAEndSession(NSDictionary *configuration);

/// Display-only launch status for players who turned RetroAchievements on.
/// The engine supplies how to show a short toast on its own game view for the
/// exact snapshot returned by Take (it keeps owning the controller, surface and
/// validity checks). The hub derives what to announce from the state the
/// engine actually published (account, game recognition, achievement set,
/// observed Hardcore) and calls the presenter on the main queue with a stable
/// status key and localized text. It never passes credentials. Passing nil, a
/// new launch or RBRAEndSession detaches the presenter.
typedef void (^RBRAStatusPresenter)(NSString *key, NSString *title, NSString *message,
                                    NSTimeInterval duration);
FOUNDATION_EXPORT void RBRASetStatusPresenter(NSDictionary *configuration,
                                              RBRAStatusPresenter _Nullable presenter);

/// "10 points" in the app language of this launch snapshot (display only).
FOUNDATION_EXPORT NSString *RBRAPointsText(NSDictionary *configuration, NSUInteger points);

/// Pure status classification, exposed for tests: nil when no notice applies
/// (RA switched off by the player), otherwise key/message/final entries.
FOUNDATION_EXPORT NSDictionary<NSString *, id> *_Nullable RBRAStatusForState(
    NSDictionary *configuration, NSDictionary *state, BOOL timedOut);

/// UI messages use the app's explicit language, never the iOS preferred locale.
FOUNDATION_EXPORT NSString *RBRALocalizedText(NSString *key, NSString *locale);

#ifdef __cplusplus
}
#endif

NS_ASSUME_NONNULL_END
