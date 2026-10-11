// SPDX-License-Identifier: GPL-3.0-or-later
// Build 442: placement of the iPhone-sized Dolphin render view on an external
// screen. Pure CoreGraphics so the policy executes on macOS CI too.
#pragma once
#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#include <math.h>

typedef NS_ENUM(NSInteger, DOLExternalDisplayMode) {
  DOLExternalDisplayModeOff = 0,   // system mirroring, as before
  DOLExternalDisplayModeFit = 1,   // whole image; bars only when the aspect differs (default)
  DOLExternalDisplayModeFill = 2,  // a 4:3 image zoomed to the TV width, top and bottom cut
};

static inline DOLExternalDisplayMode DOLExternalDisplayModeFromValue(id _Nullable value) {
  if (![value isKindOfClass:NSNumber.class]) return DOLExternalDisplayModeFit;
  const NSInteger mode = [(NSNumber*)value integerValue];
  return mode >= DOLExternalDisplayModeOff && mode <= DOLExternalDisplayModeFill
      ? (DOLExternalDisplayMode)mode : DOLExternalDisplayModeFit;
}

static inline BOOL DOLExternalDisplayUsableSize(CGSize size) {
  return isfinite(size.width) && isfinite(size.height) && size.width > 0 && size.height > 0;
}

/// Scale applied to the render view (`source`, the iPhone's logical size) on
/// an external screen of `screen` points. Dolphin draws the game at the full
/// height of the source and letterboxes only sideways on a phone wider than
/// 16:9, so Fit makes the source height fill the screen: it crops nothing but
/// the phone's own black side bars and never a 16:9 width. Fill zooms a 4:3
/// image to the screen width (top and bottom cut), capped at 4/3 of Fit.
static inline CGFloat DOLExternalDisplayScale(CGSize screen, CGSize source, DOLExternalDisplayMode mode) {
  if (!DOLExternalDisplayUsableSize(screen) || !DOLExternalDisplayUsableSize(source) ||
      mode == DOLExternalDisplayModeOff) return 1;
  const CGFloat heightScale = screen.height / source.height;
  const CGFloat widescreen = source.height * 16.0 / 9.0;
  const CGFloat fit = MIN(heightScale, screen.width / widescreen);
  if (mode != DOLExternalDisplayModeFill) return fit;
  const CGFloat standard = source.height * 4.0 / 3.0;
  const CGFloat fill = screen.width / standard;
  return MAX(fit, MIN(fill, fit * 4.0 / 3.0));
}

/// The centred frame of the scaled render view on the external screen.
static inline CGRect DOLExternalDisplayFrame(CGSize screen, CGSize source, DOLExternalDisplayMode mode) {
  if (!DOLExternalDisplayUsableSize(screen) || !DOLExternalDisplayUsableSize(source)) return CGRectZero;
  const CGFloat scale = DOLExternalDisplayScale(screen, source, mode);
  const CGSize size = CGSizeMake(source.width * scale, source.height * scale);
  return CGRectMake((screen.width - size.width) / 2, (screen.height - size.height) / 2, size.width, size.height);
}
