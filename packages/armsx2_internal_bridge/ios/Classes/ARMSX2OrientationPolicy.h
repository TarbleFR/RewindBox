// Orientations an ARMSX2 session allows from the skins the player CHOSE. Plain
// C so the table is tested without UIKit (test/orientation_policy). Same rule
// as LibretroOrientationPolicy.h and DOLOrientationPolicy.h (the pods cannot
// import each other). Mask values mirror UIInterfaceOrientationMask.
#pragma once
#include <stdbool.h>

enum {
  ARMSX2PolicyMaskPortrait = 1 << 1,
  ARMSX2PolicyMaskLandscape = (1 << 3) | (1 << 4),
  ARMSX2PolicyMaskAllButUpsideDown = (1 << 1) | (1 << 3) | (1 << 4),
};

/// `portrait` / `landscape`: a skin is selected for that orientation (game
/// first, then console) and gives a usable layout there. The skin file's other
/// layouts and the stock controls are never a choice.
/// Only portrait chosen: portrait only; only landscape chosen: landscape only;
/// both chosen, or none: the session turns with the phone. The session applies
/// the mask to the application only when a skin is chosen.
static inline unsigned ARMSX2PolicyMask(bool portrait, bool landscape) {
  if (portrait && !landscape) return ARMSX2PolicyMaskPortrait;
  if (landscape && !portrait) return ARMSX2PolicyMaskLandscape;
  return ARMSX2PolicyMaskAllButUpsideDown;
}
