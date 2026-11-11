// SPDX-License-Identifier: BSD-3-Clause
#import <UIKit/UIKit.h>
#import <neo_touch_layout/NeoTouchLayout.h>

NS_ASSUME_NONNULL_BEGIN

/// Layout key of the Xbox 360 touch controls (neo_touch_layout store,
/// `TouchControls/xbox360.json`; console preference
/// `NeoStation.TouchControls.xbox360.HideWithControllerConnected`).
FOUNDATION_EXPORT NSString* const XeniaTouchLayoutKey;

/// Xbox 360 touch controls of the XeniOS session, built on RewindBox's
/// shared touch-layout layer (docs/build484-touch-controls.md): every control
/// is one movable element, the stored layout adds one transform per control
/// so its drawing and touch area stay together, and the shared editor edits
/// them in place. The state is an Xbox 360 pad of user 0: X_INPUT_GAMEPAD_*
/// bits, sticks in [-1, 1] with Y up (XInput), triggers in [0, 1].
@interface RBXeniaTouchControlsView : UIView <NeoTouchLayoutEditorHost>
- (instancetype)initWithLocale:(nullable NSString*)locale NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithFrame:(CGRect)frame NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;

@property(nonatomic, readonly) uint32_t buttons;
@property(nonatomic, readonly) float leftX, leftY, rightX, rightY;
@property(nonatomic, readonly) float leftTrigger, rightTrigger;

/// The surface orientation class changed (held controls were released).
@property(nonatomic, copy, nullable) dispatch_block_t orientationChanged;
/// Per-game layout key (sanitized by NeoTouchLayoutGameKey).
@property(nonatomic, copy, nullable) NSString* gameKey;
@property(nonatomic, readonly) NSString* orientation;
@property(nonatomic, readonly) BOOL editing;

/// Releases every held control and centres both sticks.
- (void)releaseAllInput;
- (void)reloadFromStore;
/// Ends the editor's override: the stored layout applies again.
- (void)endEditingOverride;
/// Stock frames for a surface, by element identifier (tests and diagnostics).
- (NSDictionary<NSString*, NSValue*>*)stockFramesForBounds:(CGRect)bounds safeArea:(UIEdgeInsets)safe;
@end

/// Registers the Xbox 360 preview with NeoTouchLayoutRegistry, so the
/// editor opens from Settings without a session.
FOUNDATION_EXPORT void XeniaTouchControlsRegisterPreview(void);

NS_ASSUME_NONNULL_END
