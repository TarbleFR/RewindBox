// SPDX-License-Identifier: GPL-3.0-or-later
// Protocol adopted by the emulation bridges whose render view can be shown
// on the external screen (docs/external-display-universal.md § 3.2). The
// coordinator moves `renderView` into its own window and returns it to
// index 0 of `placeholderView` before the bridge stops its core.
#pragma once
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@protocol NeoExternalRenderHost <NSObject>
/// The view moved to the external window (MTKView, RPCS3MetalView,
/// LibretroMetalView, the ARMSX2 core view).
@property(nonatomic, readonly) UIView *renderView;
/// The iPhone container that takes the view back at index 0 (below the
/// touch controls).
@property(nonatomic, readonly) UIView *placeholderView;
/// YES: the drawable keeps the iPhone size and only a transform maps the
/// view to the TV (Dolphin, RPCS3, ARMSX2). NO: the surface follows the TV
/// and the host is told its new size (libretro).
@property(nonatomic, readonly) BOOL fixedDrawable;
@optional
/// fixedDrawable == NO only: the surface now measures `pointSize` points at
/// `scale` (CGSizeZero = the view is back on the iPhone).
- (void)externalSurfaceDidChange:(CGSize)pointSize scale:(CGFloat)scale;
/// Main thread, after the view moved to (YES) or from (NO) the TV.
- (void)externalDisplayDidChange:(BOOL)active;
@end

NS_ASSUME_NONNULL_END
