#import <Flutter/Flutter.h>

NS_ASSUME_NONNULL_BEGIN

/// Settings › General › "120 Hz interface" (Build 440).
///
/// `+load` installs the engine hook (UiRefreshRateEngineHook.h) before
/// UIApplicationMain, so the Flutter view's Metal layer, the vsync waiter and
/// the touch-rate link all read the policy from their creation. The method
/// channel `neostation/ui_refresh_rate` reports the state (`getState`) and
/// stores the preference (`setEnabled`), applied at the next launch.
@interface UiRefreshRatePlugin : NSObject <FlutterPlugin>

/// The state reported to Dart (also used by the simulator tests).
- (NSDictionary<NSString *, id> *)currentState;

@end

NS_ASSUME_NONNULL_END
