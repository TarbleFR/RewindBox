#import <Foundation/Foundation.h>

#import "LibretroSkin.h"

NS_ASSUME_NONNULL_BEGIN

/// iPhone verdict of a skin for one console.
typedef NS_ENUM(NSInteger, LibretroSkinCompatibilityStatus) {
  /// An iPhone layout whose controls all reach the core with Delta's own
  /// names.
  LibretroSkinCompatibilityCompatible = 0,
  /// Playable on iPhone after an automatic conversion that succeeded:
  /// other emulators' input names, a stick driving a D-pad, dead extra
  /// buttons, or an iPad layout whose controls stay large enough.
  LibretroSkinCompatibilityAdaptable,
  /// Not offered: no usable iPhone layout, essential controls missing, no
  /// touch control at all, or no artwork.
  LibretroSkinCompatibilityIncompatible,
};

/// "compatible", "adaptable", "incompatible".
FOUNDATION_EXPORT NSString *LibretroSkinCompatibilityStatusName(LibretroSkinCompatibilityStatus status);

/// Reason codes (translated by Dart, LibretroLocale.skinCompatibilityKeys).
FOUNDATION_EXPORT NSString *const LibretroSkinCompatOtherConsole;     // SKIN_COMPAT_OTHER_CONSOLE
FOUNDATION_EXPORT NSString *const LibretroSkinCompatNoPhoneLayout;    // SKIN_COMPAT_NO_PHONE_LAYOUT
FOUNDATION_EXPORT NSString *const LibretroSkinCompatTabletAdapted;    // SKIN_COMPAT_TABLET_ADAPTED
FOUNDATION_EXPORT NSString *const LibretroSkinCompatTabletTooSmall;   // SKIN_COMPAT_TABLET_TOO_SMALL
FOUNDATION_EXPORT NSString *const LibretroSkinCompatNoTouchControls;  // SKIN_COMPAT_NO_TOUCH_CONTROLS
FOUNDATION_EXPORT NSString *const LibretroSkinCompatMissingControls;  // SKIN_COMPAT_MISSING_CONTROLS
FOUNDATION_EXPORT NSString *const LibretroSkinCompatAdaptedInputs;    // SKIN_COMPAT_ADAPTED_INPUTS
FOUNDATION_EXPORT NSString *const LibretroSkinCompatDeadButtons;      // SKIN_COMPAT_DEAD_BUTTONS
FOUNDATION_EXPORT NSString *const LibretroSkinCompatNoArtwork;        // SKIN_COMPAT_NO_ARTWORK
FOUNDATION_EXPORT NSString *const LibretroSkinCompatSmallControls;    // SKIN_COMPAT_SMALL_CONTROLS

/// Smallest side, in points, of the touch area of every essential control
/// of an iPad layout shown on the smallest supported iPhone for that layout
/// to count as adaptable (Apple's minimum hit target is 44 points; Delta's
/// own iPhone skins use about 36 for their smallest essential buttons).
FOUNDATION_EXPORT const double LibretroSkinTabletMinimumControlPoints;  // 36
/// Below this, an iPhone layout's essential control is reported small
/// (remark only, the creator's layout is kept).
FOUNDATION_EXPORT const double LibretroSkinSmallControlPoints;  // 24

@interface LibretroSkinCompatibilityReport : NSObject
@property(nonatomic, readonly) LibretroSkinCompatibilityStatus status;
@property(nonatomic, readonly, copy) NSString *console;
/// {"portrait" | "landscape": "compatible" | "adaptable" | "incompatible" |
/// "missing"}: the verdict of each iPhone orientation ("missing": the skin
/// has no layout for it, NeoStation's default skin is used).
@property(nonatomic, readonly, copy) NSDictionary<NSString *, NSString *> *orientations;
/// Reason codes, most important first, without duplicates.
@property(nonatomic, readonly, copy) NSArray<NSString *> *reasons;
/// Essential logical controls missing from an orientation that has a layout
/// (canonical names, "directions" for the D-pad or stick).
@property(nonatomic, readonly, copy) NSArray<NSString *> *missingControls;
/// Recommended controls missing (remark only).
@property(nonatomic, readonly, copy) NSArray<NSString *> *missingOptionalControls;
/// Raw names converted for this console, and raw names that stay dead.
@property(nonatomic, readonly, copy) NSArray<NSString *> *adaptedInputs;
@property(nonatomic, readonly, copy) NSArray<NSString *> *unsupportedInputs;
/// Drawn controls that send nothing.
@property(nonatomic, readonly) NSUInteger deadItems;
/// The iPhone uses the skin's iPad layouts.
@property(nonatomic, readonly) BOOL tabletLayout;
/// Smallest side of an essential control's touch area on the reference
/// iPhone (points; 0 when unknown).
@property(nonatomic, readonly) double smallestControlPoints;

- (LibretroSkinCompatibilityStatus)statusForOrientation:(LibretroSkinOrientation)orientation;
/// Dictionary for Dart: {status, console, orientations, reasons,
/// missingControls, missingOptionalControls, adaptedInputs,
/// unsupportedInputs, deadItems, tabletLayout, smallestControlPoints}.
- (NSDictionary<NSString *, id> *)dictionary;
@end

/// The central iPhone filter of skins, shared by every catalog, the import
/// from Files, the skin pages and the session. It runs on a parsed
/// LibretroSkin (the real parser, so the verdict is about what NeoStation
/// will really do) and lays each layout out with LibretroSkinLayout on the
/// smallest iPhone that would show it (375 x 667 standard, 390 x 844 edge to
/// edge, both for an iPad layout).
///
/// Essential controls per console (all needed in an orientation for it to
/// be playable by touch): nes, gb, gbc, sms, gg, sg1000: directions, a, b,
/// start; gba: + l, r; snes: directions, a, b, x, y, l, r, start; md, mcd,
/// 32x: directions, a, b, c, start; arcade: directions, a, b, start, select
/// (coin); nds: snes + touchScreen; n64: directions (D-pad or stick), a, b,
/// z, start; psx, psp: directions (psp: or stick), a, b, x, y, l, r, start;
/// 3ds: directions (or Circle Pad), a, b, x, y, l, r, start, touchScreen.
/// Lot 1: pce, tg16, pccd, tgcd, ws, wsc, ngp, ngpc, lynx, duck, wsv:
/// directions, a, b, start; vb: + l, r; 2600: directions, b; 7800:
/// directions, a, b, select, start; 5200: directions, a, b, start; cv:
/// directions, a, b, y, x (keypad 1 and 2); mini: directions, a, b, c; gw:
/// directions, a, select, start; ard, wasm4: directions, a, b; uze: snes.
/// Recommended (remark only): select (nes, gb, gbc, gba, snes, nds, psx,
/// psp, 3ds, pce, tg16, pccd, tgcd, duck, wsv, uze), mode / x / y / z (md,
/// mcd, 32x), l, r, C buttons (n64), l2 / r2 (psx, 3ds), right stick (3ds),
/// the Y pad (ws, wsc), the right D-pad (vb), the keypad (5200, cv).
@interface LibretroSkinCompatibility : NSObject

+ (LibretroSkinCompatibilityReport *)evaluateSkin:(LibretroSkin *)skin console:(NSString *)console;

/// Evaluates, then lets an iPhone use the iPad layouts of an adaptable
/// iPad-only skin (LibretroSkin.phoneUsesTabletLayouts).
+ (LibretroSkinCompatibilityReport *)prepareSkin:(LibretroSkin *)skin console:(NSString *)console;

+ (NSArray<NSString *> *)essentialControlsForConsole:(NSString *)console;

@end

NS_ASSUME_NONNULL_END
