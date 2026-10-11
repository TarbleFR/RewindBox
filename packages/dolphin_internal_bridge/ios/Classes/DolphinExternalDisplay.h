// SPDX-License-Identifier: GPL-3.0-or-later
// Build 442: dedicated output on an external screen (AirPlay to an Apple TV,
// Lightning/USB-C adapter). The session's Metal view moves to a window on
// that screen, scaled to the TV, while the touch controls, the menu and the
// performance overlay stay on the iPhone. Dolphin keeps drawing into the very
// same CAMetalLayer at the iPhone's size: no core change, no surface resize,
// no second renderer. Off = system mirroring, as before.
#pragma once
#import <UIKit/UIKit.h>
#import "DolphinExternalDisplayLayout.h"

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString* const DOLExternalDisplayModeKey;
FOUNDATION_EXPORT NSString* const DOLExternalDisplayChangedNotification;
FOUNDATION_EXPORT DOLExternalDisplayMode DOLExternalDisplayPreference(void);

@interface DolphinExternalDisplay : NSObject
/// `render` is the session's Metal view; `placeholder` the iPhone container
/// that owns it when no external screen is used (index 0, below the controls).
- (instancetype)initWithRenderView:(UIView*)render placeholder:(UIView*)placeholder;
@property(nonatomic, readonly) BOOL active;
@property(nonatomic, readonly, nullable) UIScreen* screen;
@property(nonatomic, readonly) DOLExternalDisplayMode mode;
/// Main thread. Called after the render view moved to or from the external
/// window.
@property(nonatomic, copy, nullable) void (^stateChanged)(BOOL active);
/// Test seams. `externalScreens` lists the candidate screens (default: every
/// connected screen but the main one); `windowFactory` builds the window.
@property(nonatomic, copy, nullable) NSArray<UIScreen*>* (^externalScreens)(void);
@property(nonatomic, copy, nullable) UIWindow* (^windowFactory)(UIScreen* screen);
/// Main thread. Observes screen connections and the preference, then applies.
- (void)start;
/// Main thread. Re-reads the preference and the screens (settings change).
- (void)refresh;
/// Main thread. Returns the render view to the placeholder and stops observing.
- (void)stop;
@end

NS_ASSUME_NONNULL_END
