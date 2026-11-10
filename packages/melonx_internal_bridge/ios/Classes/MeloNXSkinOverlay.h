// SPDX-License-Identifier: GPL-3.0-or-later
// Controller skins for the embedded MeloNX (Nintendo Switch), docs/dolphin-skins.md.
//
// Reads the skin chosen for the console (and the game) from
//   Documents/Libretro/Config/Frontend/switch.json
// and the installed skin from Documents/Libretro/Skins/<id>/info.json, draws it
// over the session and sends its touches as the embedded Core's button indices
// and stick vectors. Without a skin ("default" or nothing stored) nothing is created.
#pragma once
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Logical input of a raw skin input: `a b x y l r zl zr minus plus l3 r3`, the
/// D-pad `up down left right`, the left stick `stickUp…`, the right stick
/// `rstickUp…`, `menu` (RewindBox session menu), `home` and `capture` (console
/// buttons the embedded Core cannot receive). nil for anything else (no other
/// console's name is guessed). Same table as DolphinSkins.canonicalInput('switch').
FOUNDATION_EXPORT NSString* _Nullable MeloNXSkinCanonicalInput(NSString* _Nullable raw);

/// "switch" for a Nintendo Switch skin's gameTypeIdentifier, else nil.
FOUNDATION_EXPORT NSString* _Nullable MeloNXSkinConsoleOfGameType(NSString* _Nullable gameTypeIdentifier);

@interface MeloNXSkinOverlay : UIView
- (instancetype)initWithGameKey:(nullable NSString*)gameKey NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithFrame:(CGRect)frame NS_UNAVAILABLE;
- (nullable instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;

/// Some orientation has a usable skin.
@property(nonatomic, readonly) BOOL hasSkin;
/// The portrait orientation has one.
@property(nonatomic, readonly) BOOL portraitAvailable;
/// Orientations of the session from the skins chosen for portrait and landscape
/// that parsed (only portrait: portrait; only landscape: landscape; else both).
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
/// A digital pad button changed: the embedded Core's index (A 0, B 1, X 2, Y 3,
/// Minus 4, Plus 6, L3 7, R3 8, L 9, R 10, Up 11, Down 12, Left 13, Right 14, ZL 15,
/// ZR 16; neostation_melonx_input_button).
@property(nonatomic, copy, nullable) void (^buttonChanged)(uint32_t button, BOOL pressed);
/// Both sticks, each -1...1, positive Y down (the session inverts Y for the Core,
/// as it does for the Melo-Controller).
@property(nonatomic, copy, nullable) void (^sticksChanged)(float leftX, float leftY, float rightX, float rightY);
/// The skin's Menu control: opens the RewindBox session menu.
@property(nonatomic, copy, nullable) dispatch_block_t menuHandler;
/// A console button the embedded Core cannot receive ("home", "capture") was
/// pressed: the session tells the player, nothing is sent to the game.
@property(nonatomic, copy, nullable) void (^systemButtonHandler)(NSString* name);
/// Called after a layout pass that changed the active skin or its screen.
@property(nonatomic, copy, nullable) dispatch_block_t layoutChanged;
/// Every held input released (buttons, D-pad, sticks), as when the finger leaves.
- (void)releaseAllInputs;
@end

NS_ASSUME_NONNULL_END
