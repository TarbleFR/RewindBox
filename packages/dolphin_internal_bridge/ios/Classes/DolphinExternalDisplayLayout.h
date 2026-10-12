// SPDX-License-Identifier: GPL-3.0-or-later
// Build 442 placement vocabulary of the iPhone-sized Dolphin render view on
// an external screen, kept for the 442 tests. Since Build 447 the policy
// itself lives in the external_display pod (NeoExternalDisplayLayout.h):
// every DOL function delegates to it, so Fit and Fill stay number for number
// what the 442 tests assert, and Original is the global format added by
// Build 447. Pure CoreGraphics so the policy executes on macOS CI too.
//
// The external_display pod publishes its headers as <external_display/…>
// (its podspec's public_header_files); outside CocoaPods (macOS policy
// tests, iPhone syntax checks) the same header is found on a plain include
// path.
#pragma once
#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#if __has_include(<external_display/NeoExternalDisplayLayout.h>)
#import <external_display/NeoExternalDisplayLayout.h>
#else
#import "NeoExternalDisplayLayout.h"
#endif

typedef NS_ENUM(NSInteger, DOLExternalDisplayMode) {
  DOLExternalDisplayModeOff = 0,       // system mirroring, as before (the global Enabled switch is off)
  DOLExternalDisplayModeFit = 1,       // whole image; bars only when the aspect differs (442 default)
  DOLExternalDisplayModeFill = 2,      // a 4:3 image zoomed to the TV width, top and bottom cut
  DOLExternalDisplayModeOriginal = 3,  // Build 447: the iPhone's own format, centred at the TV height
};

/// The global preference (NeoExternalDisplayPreferences) as the placement
/// of a Dolphin game: Automatic is Fit for a game, exactly as the
/// coordinator resolves it (NeoExternalDisplayEffectiveMode). Off is not a
/// global mode but the Enabled switch: DOLExternalDisplayPreference() adds it.
static inline DOLExternalDisplayMode DOLExternalDisplayModeFromGlobal(NeoExternalDisplayMode mode) {
  switch (NeoExternalDisplayEffectiveMode(mode, NeoExternalContentGame)) {
    case NeoExternalDisplayModeFill: return DOLExternalDisplayModeFill;
    case NeoExternalDisplayModeOriginal: return DOLExternalDisplayModeOriginal;
    case NeoExternalDisplayModeFit:
    case NeoExternalDisplayModeAutomatic: break;
  }
  return DOLExternalDisplayModeFit;
}

/// The global mode the coordinator applies for a DOL mode. Off has no global
/// counterpart (it is Enabled = NO) and maps to Fit, the 442 default, for a
/// caller that only needs a placement.
static inline NeoExternalDisplayMode DOLExternalDisplayGlobalMode(DOLExternalDisplayMode mode) {
  switch (mode) {
    case DOLExternalDisplayModeFill: return NeoExternalDisplayModeFill;
    case DOLExternalDisplayModeOriginal: return NeoExternalDisplayModeOriginal;
    case DOLExternalDisplayModeFit:
    case DOLExternalDisplayModeOff: break;
  }
  return NeoExternalDisplayModeFit;
}

/// Scale applied to the render view (`source`, the iPhone's logical size) on
/// an external screen of `screen` points: NeoExternalDisplayScale for Fit,
/// Fill and Original; 1 for Off, where the view never leaves the iPhone.
static inline CGFloat DOLExternalDisplayScale(CGSize screen, CGSize source, DOLExternalDisplayMode mode) {
  if (mode == DOLExternalDisplayModeOff) return 1;
  return NeoExternalDisplayScale(screen, source, DOLExternalDisplayGlobalMode(mode));
}

/// The centred frame of the scaled render view on the external screen
/// (NeoExternalDisplayFrame); for Off, the unscaled source centred.
static inline CGRect DOLExternalDisplayFrame(CGSize screen, CGSize source, DOLExternalDisplayMode mode) {
  if (mode != DOLExternalDisplayModeOff) return NeoExternalDisplayFrame(screen, source, DOLExternalDisplayGlobalMode(mode));
  if (!NeoExternalDisplayUsableSize(screen) || !NeoExternalDisplayUsableSize(source)) return CGRectZero;
  return CGRectMake((screen.width - source.width) / 2, (screen.height - source.height) / 2, source.width, source.height);
}
