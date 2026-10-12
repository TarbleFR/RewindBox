// SPDX-License-Identifier: GPL-3.0-or-later
// Placement policy of NeoStation's content on an external screen (AirPlay to
// an Apple TV, Lightning/USB-C adapter). Pure CoreGraphics so the policy
// executes on macOS CI too (test/external_display_layout_test.mm).
//
// Fit and Fill reproduce the Build 442 Dolphin policy
// (DolphinExternalDisplayLayout.h: DOLExternalDisplayScale/Frame) number for
// number; Original and the surface size are new. No UIKit here.
#pragma once
#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#include <math.h>

typedef NS_ENUM(NSInteger, NeoExternalDisplayMode) {
  NeoExternalDisplayModeAutomatic = 0,  // menu: whole window; game: Fit
  NeoExternalDisplayModeFit = 1,        // whole image; bars only when the aspect differs
  NeoExternalDisplayModeFill = 2,       // a 4:3 image zoomed to the TV width, top and bottom cut (announced crop)
  NeoExternalDisplayModeOriginal = 3,   // the iPhone's own format, centred at the TV height
};

typedef NS_ENUM(NSInteger, NeoExternalContentKind) {
  NeoExternalContentNone = 0,
  NeoExternalContentMenu = 1,
  NeoExternalContentGame = 2,
};

/// The stored preference as a mode; anything out of range is Automatic.
static inline NeoExternalDisplayMode NeoExternalDisplayModeFromValue(id _Nullable value) {
  if (![value isKindOfClass:NSNumber.class]) return NeoExternalDisplayModeAutomatic;
  const NSInteger mode = [(NSNumber *)value integerValue];
  return mode >= NeoExternalDisplayModeAutomatic && mode <= NeoExternalDisplayModeOriginal
      ? (NeoExternalDisplayMode)mode : NeoExternalDisplayModeAutomatic;
}

/// The mode applied to `content`: Automatic becomes Fit for a game; the menu
/// always fills the window, so Automatic stays Automatic for it.
static inline NeoExternalDisplayMode NeoExternalDisplayEffectiveMode(NeoExternalDisplayMode stored,
                                                                     NeoExternalContentKind content) {
  if (stored == NeoExternalDisplayModeAutomatic && content == NeoExternalContentGame) return NeoExternalDisplayModeFit;
  return stored;
}

static inline BOOL NeoExternalDisplayUsableSize(CGSize size) {
  return isfinite(size.width) && isfinite(size.height) && size.width > 0 && size.height > 0;
}

/// Scale applied to a render view of `source` points (the iPhone's logical
/// size) on an external screen of `screen` points.
///
/// Fit and Fill are the Build 442 rules: the engines draw the game at the
/// full height of the source and letterbox only sideways on a phone wider
/// than 16:9, so Fit makes the source height fill the screen (it crops
/// nothing but the phone's own black side bars and never a 16:9 width) and
/// Fill zooms a 4:3 image to the screen width, capped at 4/3 of Fit.
/// Original keeps the phone's format: the screen height over the source
/// height, bounded by the width. Automatic is Fit (it only reaches here for
/// a game).
static inline CGFloat NeoExternalDisplayScale(CGSize screen, CGSize source, NeoExternalDisplayMode mode) {
  if (!NeoExternalDisplayUsableSize(screen) || !NeoExternalDisplayUsableSize(source)) return 1;
  const CGFloat heightScale = screen.height / source.height;
  if (mode == NeoExternalDisplayModeOriginal) return MIN(heightScale, screen.width / source.width);
  const CGFloat widescreen = source.height * 16.0 / 9.0;
  const CGFloat fit = MIN(heightScale, screen.width / widescreen);
  if (mode != NeoExternalDisplayModeFill) return fit;
  const CGFloat standard = source.height * 4.0 / 3.0;
  const CGFloat fill = screen.width / standard;
  return MAX(fit, MIN(fill, fit * 4.0 / 3.0));
}

/// The centred frame of the scaled render view on the external screen.
static inline CGRect NeoExternalDisplayFrame(CGSize screen, CGSize source, NeoExternalDisplayMode mode) {
  if (!NeoExternalDisplayUsableSize(screen) || !NeoExternalDisplayUsableSize(source)) return CGRectZero;
  const CGFloat scale = NeoExternalDisplayScale(screen, source, mode);
  const CGSize size = CGSizeMake(source.width * scale, source.height * scale);
  return CGRectMake((screen.width - size.width) / 2, (screen.height - size.height) / 2, size.width, size.height);
}

/// Size in points of the render surface when the engine draws at the TV's
/// resolution instead of being scaled (libretro). Fit: the scaled source
/// frame limited to what the screen shows (the phone's side bars are off
/// screen). Fill: the 4:3 frame at the Fill scale, limited to the screen
/// width (its height extends beyond the screen: the announced crop).
/// Original: the source at the Original scale. Automatic is Fit.
static inline CGSize NeoExternalDisplaySurfaceSize(CGSize screen, CGSize source, NeoExternalDisplayMode mode) {
  if (!NeoExternalDisplayUsableSize(screen) || !NeoExternalDisplayUsableSize(source)) return CGSizeZero;
  const CGFloat scale = NeoExternalDisplayScale(screen, source, mode);
  if (mode == NeoExternalDisplayModeOriginal) return CGSizeMake(source.width * scale, source.height * scale);
  if (mode == NeoExternalDisplayModeFill) {
    const CGFloat standard = source.height * 4.0 / 3.0;
    return CGSizeMake(MIN(standard * scale, screen.width), source.height * scale);
  }
  const CGRect frame = NeoExternalDisplayFrame(screen, source, mode);
  return CGSizeMake(MIN(frame.size.width, screen.width), MIN(frame.size.height, screen.height));
}

/// Only Fill cuts part of the image.
static inline BOOL NeoExternalDisplayModeCrops(NeoExternalDisplayMode mode) {
  return mode == NeoExternalDisplayModeFill;
}
