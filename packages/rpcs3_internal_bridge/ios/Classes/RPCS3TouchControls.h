// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#import <neo_touch_layout/NeoTouchLayout.h>

NS_ASSUME_NONNULL_BEGIN

/// A container that only claims the points of its visible, interactive
/// children (through their transforms): elsewhere touches go through.
@interface RPCS3InputPassthroughView : UIView
@end

typedef void (^RPCS3StickChanged)(float x, float y);

/// The PS3 virtual stick (unchanged behaviour: absolute position from the
/// centre, positive Y up as GameController/RPCS3 expect).
@interface RPCS3TouchStickView : UIView
@property(nonatomic, copy, nullable) RPCS3StickChanged valueChanged;
@property(nonatomic, strong) UIView* knob;
@property(nonatomic, assign) BOOL trackingTouch;
- (void)endTracking;
@end

/// Build 484: the RPCS3 touch controls as movable elements of the "ps3"
/// layout. The stock placement is the one of the earlier sessions (D-pad,
/// face buttons, L1/L2/R1/R2, SELECT/START along the top, both sticks).
/// Buttons report rpcs3_ios_pad_* bits; the D-pad's four buttons form one
/// element. The game input controller keeps the pad state and merges it with
/// a physical controller.
@interface RPCS3TouchControlsView : RPCS3InputPassthroughView <NeoTouchLayoutEditorHost>
- (instancetype)initWithLocale:(nullable NSString*)locale NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithFrame:(CGRect)frame NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;
@property(nonatomic, copy, nullable) void (^buttonChanged)(uint64_t bit, BOOL pressed);
/// stick 0 is the left stick, 1 the right one.
@property(nonatomic, copy, nullable) void (^stickChanged)(NSInteger stick, float x, float y);
/// The surface orientation class changed (held controls were released).
@property(nonatomic, copy, nullable) dispatch_block_t orientationChanged;
@property(nonatomic, copy, nullable) NSString* gameKey;
@property(nonatomic, readonly) NSString* orientation;
@property(nonatomic, readonly) BOOL editing;
/// Button and stick views by element identifier ("cross", "dpad.up", "stick.left"...).
- (nullable UIView*)controlForIdentifier:(NSString*)identifier;
/// Releases every pressed button and centres both sticks (visual state and
/// callbacks), as if every finger had left.
- (void)releaseAllInput;
- (void)reloadFromStore;
- (void)endEditingOverride;
/// Stock frames for a surface, by element identifier.
- (NSDictionary<NSString*, NSValue*>*)stockFramesForBounds:(CGRect)bounds safeArea:(UIEdgeInsets)safe;
@end

FOUNDATION_EXPORT void RPCS3TouchControlsRegisterPreview(void);

NS_ASSUME_NONNULL_END
