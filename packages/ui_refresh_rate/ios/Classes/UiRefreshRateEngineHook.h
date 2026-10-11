#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// "120 Hz interface" policy for the Flutter engine only (Build 440).
///
/// Every iPhone IPA carries `CADisableMinimumFrameDurationOnPhone = YES`
/// (Flutter template, asserted by the delivery workflow), and the emulators
/// were validated with it. The key therefore stays untouched. The option acts
/// on one Flutter.framework class method instead,
/// `+[FlutterDisplayLinkManager displayRefreshRate]`, which only the engine's
/// own vsync waiter, Metal layer, touch-rate link and keyboard link read
/// (through objc_msgSend):
/// - enabled: the engine's value, unchanged (Build 437 behaviour);
/// - disabled: at most 60 Hz.
/// CADisplayLink, UIScreen, NSBundle and every emulator keep their own
/// behaviour. When the class, the method or its signature is not the one
/// validated with Flutter 3.47.2, nothing is replaced and the status says so.

/// NSUserDefaults key of the preference. Absent: enabled (Build 437).
FOUNDATION_EXPORT NSString *const NeoUiRefreshPreferenceKey;
/// Value used while the preference has never been stored.
FOUNDATION_EXPORT const BOOL NeoUiRefreshDefaultEnabled;
/// Highest rate given to the engine while the option is off.
FOUNDATION_EXPORT const double NeoUiRefreshCappedHz;
/// Objective-C type encoding of the validated seam (`+(double)displayRefreshRate`).
FOUNDATION_EXPORT const char NeoUiRefreshExpectedTypeEncoding[];

typedef NS_ENUM(NSInteger, NeoUiRefreshHookStatus) {
  NeoUiRefreshHookStatusNotInstalled = 0,
  NeoUiRefreshHookStatusInstalled = 1,
  NeoUiRefreshHookStatusClassMissing = 2,
  NeoUiRefreshHookStatusMethodMissing = 3,
  NeoUiRefreshHookStatusSignatureMismatch = 4,
};

/// Pure policy. Enabled returns `engineHz`; disabled returns
/// `min(engineHz, NeoUiRefreshCappedHz)`. Zero, negative and NaN values are
/// returned unchanged so the engine keeps its own fallbacks.
FOUNDATION_EXPORT double NeoUiRefreshPolicy(double engineHz, BOOL enabled);

/// Replaces the seam's implementation once. Idempotent; never throws.
FOUNDATION_EXPORT void NeoUiRefreshInstallEngineHook(void);
FOUNDATION_EXPORT NeoUiRefreshHookStatus NeoUiRefreshCurrentHookStatus(void);
/// Raw technical code reported to Dart: installed, notInstalled,
/// classMissing, methodMissing or signatureMismatch.
FOUNDATION_EXPORT NSString *NeoUiRefreshHookStatusName(NeoUiRefreshHookStatus status);

/// The stored preference (NeoUiRefreshDefaultEnabled when absent).
FOUNDATION_EXPORT BOOL NeoUiRefreshStoredEnabled(void);
/// Writes the preference and reads it back. Returns NO when the read-back
/// differs. Never changes the snapshot used by the running process.
FOUNDATION_EXPORT BOOL NeoUiRefreshStoreEnabled(BOOL enabled);
/// The preference used by this process: read once, at the engine's first
/// request (or at the first call of this function), then kept until exit.
FOUNDATION_EXPORT BOOL NeoUiRefreshActiveEnabled(void);
/// The value the engine currently receives (through the hook when it is
/// installed). 0 when the seam does not exist.
FOUNDATION_EXPORT double NeoUiRefreshEngineTargetHz(void);

#ifdef NEO_UI_REFRESH_TESTING
// Simulator test seams only (never compiled into the app).
typedef double (*NeoUiRefreshRateFunction)(id, SEL);
FOUNDATION_EXPORT NeoUiRefreshRateFunction _Nullable NeoUiRefreshTestingSwapOriginal(
    NeoUiRefreshRateFunction _Nullable original);
FOUNDATION_EXPORT void NeoUiRefreshTestingSetActiveEnabled(BOOL enabled);
#endif

NS_ASSUME_NONNULL_END
