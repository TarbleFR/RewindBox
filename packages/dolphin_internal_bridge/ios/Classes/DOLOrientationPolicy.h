// Orientations a Dolphin session allows from the skins chosen for it. Plain C
// so the decision table is tested without UIKit (test/orientation_policy).
// Same rule as LibretroOrientationPolicy.h in the libretro bridge (the two
// pods cannot import each other). Mask values mirror UIInterfaceOrientationMask.
#pragma once
#include <stdbool.h>

enum {
  DOLPolicyMaskPortrait = 1 << 1,
  DOLPolicyMaskLandscape = (1 << 3) | (1 << 4),
  DOLPolicyMaskAllButUpsideDown = (1 << 1) | (1 << 3) | (1 << 4),
};

/// `portrait`: a usable skin is assigned to portrait; `landscape`: a usable skin
/// is assigned to landscape; `portraitSkinOffersLandscape`: the portrait
/// skin itself has a usable landscape layout.
/// - nothing for portrait: landscape only (the DolphiniOS pad, unchanged);
/// - portrait skin without its own landscape layout and no skin assigned to
///   landscape: portrait only. The default pad in landscape is not a second layout;
/// - otherwise (the skin offers both, or two skins were assigned on purpose,
///   the explicit assignment winning): both, the player turns the phone.
static inline unsigned DOLPolicyMask(bool portrait, bool landscape, bool portraitSkinOffersLandscape) {
  if (!portrait) return DOLPolicyMaskLandscape;
  if (!landscape && !portraitSkinOffersLandscape) return DOLPolicyMaskPortrait;
  return DOLPolicyMaskAllButUpsideDown;
}
