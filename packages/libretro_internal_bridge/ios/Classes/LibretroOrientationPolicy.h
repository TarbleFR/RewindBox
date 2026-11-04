// Which orientations a game on screen allows, from the skins the player
// chose. Plain C so the decision table is tested without UIKit
// (test/orientation_policy/policy_test.c). The values mirror
// UIInterfaceOrientationMask: portrait 2, landscape 24, all but upside down 26.
#pragma once
#include <stdbool.h>

enum {
  LibretroPolicyMaskPortrait = 1 << 1,
  LibretroPolicyMaskLandscape = (1 << 3) | (1 << 4),
  LibretroPolicyMaskAllButUpsideDown = (1 << 1) | (1 << 3) | (1 << 4),
};

/// Orientation lock of a game, from what the player CHOSE (not from what the
/// skin files could do).
///
/// `portraitChosen`: a skin is selected for portrait (game first, then
/// console) and it gives a usable layout in portrait on this device.
/// `landscapeChosen`: the same for landscape. "Usable" = present for the device
/// class, loaded, not refused, not announced as unplayable by touch. NeoStation's
/// default controls are never a choice: an orientation left on the default (or
/// whose chosen skin cannot be used) is not chosen.
/// - only portrait chosen: portrait only, even for a skin file that also has a
///   landscape layout (the explicit choice wins over the file's capabilities);
/// - only landscape chosen: landscape only, likewise;
/// - both chosen (the same dual skin or two skins) or none: the usual rotation.
static inline unsigned LibretroPolicyMask(bool portraitChosen, bool landscapeChosen) {
  if (portraitChosen && !landscapeChosen) return LibretroPolicyMaskPortrait;
  if (landscapeChosen && !portraitChosen) return LibretroPolicyMaskLandscape;
  return LibretroPolicyMaskAllButUpsideDown;
}
