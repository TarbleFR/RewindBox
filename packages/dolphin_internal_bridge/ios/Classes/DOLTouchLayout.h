// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#import <neo_touch_layout/NeoTouchLayout.h>

NS_ASSUME_NONNULL_BEGIN

@class DOLTouchOverlay;

/// Build 484: stored touch layouts on Dolphin's DolphiniOS touch controls.
///
/// Every button, stick and D-pad of the original GameCube, Wii Remote +
/// Nunchuk and Classic Controller layouts (and the Wii Shake control) is one
/// element. The nib keeps placing them (stock layout); this adapter adds the
/// stored transform on each layout pass, so the drawing and the touch area of
/// a control move and scale together. The overlay's hit testing follows the
/// transforms. Layouts are keyed "gc", "wii" and "wii-classic".
@interface DOLTouchLayout : NSObject <NeoTouchLayoutEditorHost>
- (instancetype)initWithOverlay:(DOLTouchOverlay*)overlay locale:(nullable NSString*)locale NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;
@property(nonatomic, weak, readonly, nullable) DOLTouchOverlay* overlay;
@property(nonatomic, copy, nullable) NSString* gameKey;
@property(nonatomic, copy, readonly) NSString* layoutKey;
@property(nonatomic, readonly) NSString* orientation;
@property(nonatomic, readonly) BOOL editing;
/// Called on the main thread when the surface orientation class changes
/// (held controls were already released by the overlay).
@property(nonatomic, copy, nullable) dispatch_block_t orientationChanged;
/// Re-reads the stored layout (after Save, or a change from the settings).
- (void)reloadFromStore;
/// Ends the editor's override: the stored layout applies again.
- (void)endEditingOverride;
@end

/// The Dolphin controls without a game, for the editor opened from the
/// settings: never interactive, never sends input.
@interface DOLTouchLayoutPreviewView : UIView <NeoTouchLayoutEditorHost>
- (instancetype)initWithLayoutKey:(NSString*)layoutKey locale:(nullable NSString*)locale;
@end

/// Registers the GameCube, Wii and Classic previews with NeoTouchLayoutRegistry.
FOUNDATION_EXPORT void DOLTouchLayoutRegisterPreviews(void);

NS_ASSUME_NONNULL_END
