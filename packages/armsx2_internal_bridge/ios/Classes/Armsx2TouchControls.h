// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#import <neo_touch_layout/NeoTouchLayout.h>

NS_ASSUME_NONNULL_BEGIN

/// The PS2 virtual stick of the ARMSX2 session (unchanged behaviour: a pan
/// relative to where the finger started, positive Y down).
@interface Armsx2VirtualStickView : UIView
@property(nonatomic, copy, nullable) void (^valueChanged)(float x, float y);
@property(nonatomic, strong) UIView* knob;
/// Ends a drag in progress and reports a centred stick.
- (void)recenter;
@end

/// Build 484: the ARMSX2 touch controls as movable elements.
///
/// The stock placement is the one of the earlier sessions (D-pad, the four
/// face buttons, L1/L2/R1/R2, START/SELECT and both sticks, landscape and
/// portrait). Each control is one element of the "ps2" layout: the stored
/// layout adds one transform per control, so its drawing and its touch area
/// stay together. Buttons send ARMSX2PadButton indices (0 Up ... 13 Select)
/// through `buttonChanged`; the sticks through `sticksChanged`.
@interface Armsx2TouchControlsView : UIView <NeoTouchLayoutEditorHost>
- (instancetype)initWithLocale:(nullable NSString*)locale NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithFrame:(CGRect)frame NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;
@property(nonatomic, copy, nullable) void (^buttonChanged)(uint32_t button, BOOL pressed);
@property(nonatomic, copy, nullable) void (^sticksChanged)(float leftX, float leftY, float rightX, float rightY);
/// The surface orientation class changed (held controls were released).
@property(nonatomic, copy, nullable) dispatch_block_t orientationChanged;
@property(nonatomic, copy, nullable) NSString* gameKey;
@property(nonatomic, readonly) NSString* orientation;
@property(nonatomic, readonly) BOOL editing;
/// Releases every held button and centres both sticks (visuals and inputs).
- (void)releaseAllInput;
- (void)reloadFromStore;
/// Ends the editor's override: the stored layout applies again.
- (void)endEditingOverride;
/// Stock frames for a surface, by element identifier (tests and diagnostics).
- (NSDictionary<NSString*, NSValue*>*)stockFramesForBounds:(CGRect)bounds safeArea:(UIEdgeInsets)safe;
@end

/// Registers the PS2 preview with NeoTouchLayoutRegistry.
FOUNDATION_EXPORT void Armsx2TouchControlsRegisterPreview(void);

NS_ASSUME_NONNULL_END
