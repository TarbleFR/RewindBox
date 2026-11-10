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

/// Whether the bounds a session was just given are still those of the screen that opened
/// it. UIKit turns the window after the presentation: a phone held sideways opening a
/// portrait-only session (or the reverse) first lays the session out in bounds its mask
/// does not allow. The session then settles in the turned bounds (height x width), and
/// what must be right from the start (the surface the core reads once) is computed there.
static inline bool DOLPolicyBoundsWillTurn(unsigned mask, double width, double height) {
  if (width < 1 || height < 1) return false;
  const bool portrait = height > width;
  const bool allowsPortrait = (mask & DOLPolicyMaskPortrait) != 0;
  const bool allowsLandscape = (mask & DOLPolicyMaskLandscape) != 0;
  return portrait ? (!allowsPortrait && allowsLandscape) : (!allowsLandscape && allowsPortrait);
}
