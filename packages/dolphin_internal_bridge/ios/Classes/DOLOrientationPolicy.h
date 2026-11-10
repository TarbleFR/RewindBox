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

/// From what the player CHOSE: `portrait` / `landscape` = a skin is selected for
/// that orientation (game first, then console) and gives a usable layout there.
/// The skin file's other layouts and the default pad are never a choice.
/// - only portrait chosen: portrait only;
/// - only landscape chosen, or nothing: landscape (the DolphiniOS pad, unchanged);
/// - both chosen: the player turns the phone.
static inline unsigned DOLPolicyMask(bool portrait, bool landscape) {
  if (portrait && !landscape) return DOLPolicyMaskPortrait;
  if (portrait && landscape) return DOLPolicyMaskAllButUpsideDown;
  return DOLPolicyMaskLandscape;
}
