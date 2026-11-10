// SPDX-License-Identifier: GPL-3.0-or-later
// Controller skins for the embedded Dolphin (docs/dolphin-skins.md).
//
// A GameCube or Wii skin (.deltaskin / .manicskin) imported and chosen in
// Consoles › Skins, the same screens, folders and selection files as the
// embedded libretro consoles:
//   Documents/Libretro/Skins/<id>/info.json            the imported skin
//   Documents/Libretro/Config/Frontend/<gc|wii>.json   {"console": {"skin.portrait": id,
//                                                       "skin.landscape": id}, "games": {key: {...}}}
// The overlay draws the skin over the session, sends its touches to the same
// inputs as the DolphiniOS pad (TCManagerInterface) and tells the session
// where the game goes (the skin's screen). Without a skin for the console
// ("default" or nothing stored) it is never created and nothing changes.
#pragma once
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Logical input of a raw skin input, the table of DolphinSkins.canonicalInput
/// (lib/services/dolphin_skins.dart): nil when the console has nothing for it.
FOUNDATION_EXPORT NSString* _Nullable DOLSkinCanonicalInput(BOOL wii, NSString* raw);

/// Console of a skin's gameTypeIdentifier ("gc", "wii"), as
/// DolphinSkins.consoleOfGameType.
FOUNDATION_EXPORT NSString* _Nullable DOLSkinConsoleOfGameType(NSString* gameTypeIdentifier);

@interface DOLSkinOverlay : UIView
/// Reads the selection of the console (and of `gameKey` when it has one)
/// and the chosen skins at once.
- (instancetype)initWithWii:(BOOL)wii gameKey:(nullable NSString*)gameKey NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithFrame:(CGRect)frame NS_UNAVAILABLE;
- (nullable instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;

/// Some orientation has a usable skin.
@property(nonatomic, readonly) BOOL hasSkin;
/// The portrait orientation has one: the session may turn upright.
@property(nonatomic, readonly) BOOL portraitAvailable;
/// Orientations of the session (DOLPolicyMask), from the skins chosen for
/// portrait and landscape that parsed: portrait only, landscape only (also
/// without any skin) or both. Read once the
/// overlay exists, before the session is presented.
@property(nonatomic, readonly) UIInterfaceOrientationMask supportedOrientationMask;
/// The current bounds' orientation has one.
@property(nonatomic, readonly) BOOL layoutActive;
/// The current layout has a Menu control (the session then hides its own
/// floating menu button, DOLSessionChromePolicy.h).
@property(nonatomic, readonly) BOOL hasMenuControl;
/// Where the game goes, in the overlay's coordinates (CGRectNull when the
/// current orientation has no skin).
@property(nonatomic, readonly) CGRect screenFrame;
/// Where the game goes when the overlay has `bounds` (the skin chosen for that
/// orientation), CGRectNull without one. The same computation as the layout: the session
/// uses it for the surface the core reads at launch, when UIKit has not yet turned the
/// window to the orientation the session allows.
- (CGRect)screenFrameForBounds:(CGRect)bounds;
/// The current skin cuts its screen with the pack's own cutout (`screens[].screenCutout`):
/// the opening its body draws, not a rectangle.
@property(nonatomic, readonly) BOOL screenCutoutActive;
/// The skin's menu input (and its quick save / quick load, whose states are
/// in that menu).
@property(nonatomic, copy, nullable) dispatch_block_t menuHandler;
/// Called after a layout pass that changed the active skin or its screen.
@property(nonatomic, copy, nullable) dispatch_block_t layoutChanged;

/// Every held input released (buttons, D-pads, sticks, triggers), as when
/// the finger leaves; the Wii pointer keeps its place, like the pad's.
- (void)releaseAllInputs;
@end

NS_ASSUME_NONNULL_END
