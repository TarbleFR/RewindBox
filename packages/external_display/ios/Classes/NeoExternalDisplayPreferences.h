// SPDX-License-Identifier: GPL-3.0-or-later
// Global external-display preferences (docs/external-display-universal.md
// § 3.5). NSUserDefaults only; every write is read back and refused as
// SAVE_FAILED by the caller when iOS did not keep it (120 Hz pattern).
#pragma once
#import <Foundation/Foundation.h>
#import "NeoExternalDisplayLayout.h"

NS_ASSUME_NONNULL_BEGIN

/// bool, default YES. NO = system mirroring, as before.
FOUNDATION_EXPORT NSString *const NeoExternalDisplayEnabledKey;
/// int 0..3 (NeoExternalDisplayMode), default Automatic.
FOUNDATION_EXPORT NSString *const NeoExternalDisplayModeKey;
/// bool, default YES: the menu's second Flutter engine is shown on the TV.
FOUNDATION_EXPORT NSString *const NeoExternalDisplayMenuOnTVKey;
/// Build 442 per-Dolphin key, read only when the global mode is absent
/// (0 → disabled, 1 → Fit, 2 → Fill). Never rewritten.
FOUNDATION_EXPORT NSString *const NeoExternalDisplayLegacyDolphinModeKey;
/// Posted after every successful write so a live session re-applies.
FOUNDATION_EXPORT NSString *const NeoExternalDisplayChangedNotification;

@interface NeoExternalDisplayPreferences : NSObject
+ (BOOL)enabled;
+ (NeoExternalDisplayMode)mode;
+ (BOOL)menuOnTV;
/// Each returns NO when NSUserDefaults did not keep the value (no
/// notification is posted then).
+ (BOOL)storeEnabled:(BOOL)enabled;
+ (BOOL)storeMode:(NeoExternalDisplayMode)mode;
+ (BOOL)storeMenuOnTV:(BOOL)enabled;
@end

NS_ASSUME_NONNULL_END
