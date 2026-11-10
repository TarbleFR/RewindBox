// SPDX-License-Identifier: GPL-3.0-or-later
// Controller skins for the embedded ARMSX2 (PlayStation 2), docs/dolphin-skins.md.
//
// Reads the skin chosen for the console (and the game) from
//   Documents/Libretro/Config/Frontend/ps2.json
// and the installed skin from Documents/Libretro/Skins/<id>/info.json, draws it
// over the session and sends its touches as ARMSX2PadButton indices and stick
// vectors. Without a skin ("default" or nothing stored) nothing is created.
#pragma once
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Logical input of a raw skin input: `cross circle square triangle l1 l2 r1 r2
/// select start l3 r3`, the D-pad `up down left right`, the left stick
/// `stickUp…`, the right stick `rstickUp…` and `menu`. nil for anything else
/// (no Nintendo name is guessed). Same table as DolphinSkins.canonicalInput('ps2').
FOUNDATION_EXPORT NSString* _Nullable ARMSX2SkinCanonicalInput(NSString* _Nullable raw);

/// "ps2" for a PlayStation 2 skin's gameTypeIdentifier, else nil.
FOUNDATION_EXPORT NSString* _Nullable ARMSX2SkinConsoleOfGameType(NSString* _Nullable gameTypeIdentifier);

@interface ARMSX2SkinOverlay : UIView
- (instancetype)initWithGameKey:(nullable NSString*)gameKey NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithFrame:(CGRect)frame NS_UNAVAILABLE;
- (nullable instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;

/// Some orientation has a usable skin.
@property(nonatomic, readonly) BOOL hasSkin;
/// The portrait orientation has one.
@property(nonatomic, readonly) BOOL portraitAvailable;
/// Orientations of the session (ARMSX2PolicyMask) from the skins chosen for
/// portrait and landscape that parsed.
@property(nonatomic, readonly) UIInterfaceOrientationMask supportedOrientationMask;
/// The current bounds' orientation has one.
@property(nonatomic, readonly) BOOL layoutActive;
/// The current skin has a Menu control of its own (then the session's floating
/// menu button is not drawn over it).
@property(nonatomic, readonly) BOOL hasMenuControl;
/// Where the game goes, in the overlay's coordinates (CGRectNull without one).
@property(nonatomic, readonly) CGRect screenFrame;
/// The current skin cuts its screen with the pack's own cutout (`screens[].screenCutout`):
/// the opening its body draws, not a rectangle.
@property(nonatomic, readonly) BOOL screenCutoutActive;
/// A digital pad button changed (ARMSX2PadButton 0...15).
@property(nonatomic, copy, nullable) void (^buttonChanged)(uint32_t button, BOOL pressed);
/// Both sticks, each -1...1, positive Y down.
@property(nonatomic, copy, nullable) void (^sticksChanged)(float leftX, float leftY, float rightX, float rightY);
/// The skin's Menu control: opens the in-game session menu.
@property(nonatomic, copy, nullable) dispatch_block_t menuHandler;
/// Called after a layout pass that changed the active skin or its screen.
@property(nonatomic, copy, nullable) dispatch_block_t layoutChanged;
/// Every held input released (buttons, D-pad, sticks), as when the finger leaves.
- (void)releaseAllInputs;
@end

NS_ASSUME_NONNULL_END
