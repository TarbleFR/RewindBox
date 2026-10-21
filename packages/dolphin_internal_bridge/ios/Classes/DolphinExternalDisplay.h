// SPDX-License-Identifier: GPL-3.0-or-later
// Build 442: dedicated output on an external screen (AirPlay to an Apple TV,
// Lightning/USB-C adapter). The session's Metal view moves to RewindBox's
// window on that screen, scaled to the TV, while the touch controls, the menu
// and the performance overlay stay on the iPhone. Dolphin keeps drawing into
// the very same CAMetalLayer at the iPhone's size: no core change, no surface
// resize, no second renderer.
//
// Build 447: the window, the screens and the placement belong to the
// external_display pod (docs/external-display-universal.md § 5). This class
// is the bridge's NeoExternalRenderHost: a fixed drawable whose render view
// is the Metal view and whose placeholder is the session's container.
// `start` attaches it to NeoExternalDisplayCoordinator, `stop` detaches it
// before the core shuts down. Off = the global Enabled switch = system
// mirroring, as before.
#pragma once
#import <UIKit/UIKit.h>
#if __has_include(<external_display/NeoExternalRenderHost.h>)
#import <external_display/NeoExternalRenderHost.h>
#else
#import "NeoExternalRenderHost.h"
#endif
#import "DolphinExternalDisplayLayout.h"

NS_ASSUME_NONNULL_BEGIN

/// The global preference (NeoExternalDisplayPreferences: the Build 447 keys,
/// with the read-only fallback to the Build 442 Dolphin key) as the
/// placement of a Dolphin game: Off when the external display is disabled.
FOUNDATION_EXPORT DOLExternalDisplayMode DOLExternalDisplayPreference(void);

@interface DolphinExternalDisplay : NSObject <NeoExternalRenderHost>
/// `render` is the session's Metal view; `placeholder` the iPhone container
/// that owns it when no external screen is used (index 0, below the controls).
- (instancetype)initWithRenderView:(UIView*)render placeholder:(UIView*)placeholder;
/// Attached to the coordinator (between `start` and `stop`).
@property(nonatomic, readonly) BOOL started;
/// The render view is on the external screen right now.
@property(nonatomic, readonly) BOOL active;
/// Main thread. Called by the coordinator after the render view moved to or
/// from the external window.
@property(nonatomic, copy, nullable) void (^stateChanged)(BOOL active);
/// Main thread. Attaches the host: a connected screen takes the view at
/// once, a later connection takes it when it comes.
- (void)start;
/// Main thread. Re-reads the preferences and the screens (settings change).
- (void)refresh;
/// Main thread. Returns the render view to the placeholder (index 0, iPhone
/// frame, scale and drawable settings restored) and detaches the host.
- (void)stop;
@end

NS_ASSUME_NONNULL_END
