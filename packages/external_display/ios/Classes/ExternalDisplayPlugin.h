// SPDX-License-Identifier: GPL-3.0-or-later
#import <Flutter/Flutter.h>

NS_ASSUME_NONNULL_BEGIN

/// Flutter side of the external display (docs/external-display-universal.md
/// § 3.6): method channel `neostation/external_display` (getState,
/// setEnabled, setMode, setMenuOnTV, configureMenuEngine, updateMenuEngine,
/// pushMenuState, suspendForUnsupportedEngine, resumeAfterUnsupportedEngine)
/// and event channel `neostation/external_display/events`, which emits the
/// coordinator's state at every NeoStation.ExternalDisplayStateChanged.
@interface ExternalDisplayPlugin : NSObject <FlutterPlugin>

/// The state reported to Dart (also used by the simulator tests).
- (NSDictionary<NSString *, id> *)currentState;

@end

NS_ASSUME_NONNULL_END
