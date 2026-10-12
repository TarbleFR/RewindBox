// SPDX-License-Identifier: GPL-3.0-or-later
// Placement policy of NeoStation's content on an external screen (AirPlay to
// an Apple TV, Lightning/USB-C adapter). Pure CoreGraphics so the policy
// executes on macOS CI too (test/external_display_layout_test.mm).
//
// Fit and Fill reproduce the Build 442 Dolphin policy
// (DolphinExternalDisplayLayout.h: DOLExternalDisplayScale/Frame) number for
// number; Original and the surface size are new, and so is the parsing of
// the build SDK that gates the iOS 27 scene accessory. No UIKit here.
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
/// resolution instead of being scaled (libretro, NeoExternalRenderHost with
/// fixedDrawable == NO): the whole screen, in every mode. The host places
/// each game's picture in it at the game's own aspect
/// (LibretroRenderSurfacePlacement: the game areas of the iPhone layout
/// scaled uniformly and centred), so a portrait phone no longer gives a
/// pillar of the phone's format and a 3:2 GBA screen fills 1620 × 1080 of
/// a 1080p TV (review of 12 October 2026, M3). `source` (the iPhone layout
/// the host draws from) and `mode` are kept by the signature: the formats
/// of Fit, Fill and Original apply to the fixed drawables (Dolphin, RPCS3,
/// ARMSX2), whose view is only scaled. Zero when either size is unusable.
static inline CGSize NeoExternalDisplaySurfaceSize(CGSize screen, CGSize source, NeoExternalDisplayMode mode) {
  (void)mode;
  if (!NeoExternalDisplayUsableSize(screen) || !NeoExternalDisplayUsableSize(source)) return CGSizeZero;
  return screen;
}

/// Only Fill cuts part of the image.
static inline BOOL NeoExternalDisplayModeCrops(NeoExternalDisplayMode mode) {
  return mode == NeoExternalDisplayModeFill;
}

/// iOS 27 regime: "In apps built with the iOS 27.0 SDK,
/// windowExternalDisplayNonInteractive scenes are no longer offered
/// automatically" (Apple release note 177015874). An app built with an
/// earlier SDK keeps the automatic connection on iOS 27, so the scene
/// accessory path is only taken by a binary built with this SDK major or
/// later.
static const NSInteger NeoExternalDisplayAccessorySDKMajor = 27;

/// The leading number of `text` when it is made of numbers separated by
/// dots ("26", "26.2", "26.2.1"); 0 otherwise (empty, a letter, "26.", a
/// value too large to be a version).
static inline NSInteger NeoExternalDisplayVersionMajor(NSString *_Nullable text) {
  if (![text isKindOfClass:NSString.class] || text.length == 0) return 0;
  NSInteger major = 0;
  BOOL inMajor = YES;
  BOOL digitSeen = NO;
  for (NSUInteger index = 0; index < text.length; ++index) {
    const unichar character = [text characterAtIndex:index];
    if (character >= '0' && character <= '9') {
      if (inMajor) {
        major = major * 10 + (character - '0');
        if (major > 10000) return 0;
      }
      digitSeen = YES;
    } else if (character == '.' && digitSeen) {
      inMajor = NO;
      digitSeen = NO;
    } else {
      return 0;
    }
  }
  return digitSeen ? major : 0;
}

/// Major version of the SDK the app binary was built with, from the main
/// bundle's Info.plist written by Xcode: DTPlatformVersion ("26.2") first,
/// else DTSDKName (letters, then the version: "iphoneos26.2",
/// "iphonesimulator26.2"). 0 when both are missing or unparsable: the
/// accessory regime then stays off (the automatic connection of the
/// external scene is the behaviour of every SDK before 27).
static inline NSInteger NeoExternalDisplaySDKMajorVersion(NSString *_Nullable platformVersion,
                                                          NSString *_Nullable sdkName) {
  const NSInteger platform = NeoExternalDisplayVersionMajor(platformVersion);
  if (platform > 0) return platform;
  if (![sdkName isKindOfClass:NSString.class]) return 0;
  NSUInteger letters = 0;
  while (letters < sdkName.length) {
    const unichar character = [sdkName characterAtIndex:letters];
    if (!((character >= 'a' && character <= 'z') || (character >= 'A' && character <= 'Z'))) break;
    ++letters;
  }
  if (letters == 0 || letters == sdkName.length) return 0;
  return NeoExternalDisplayVersionMajor([sdkName substringFromIndex:letters]);
}
