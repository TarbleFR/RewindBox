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

/// Orientation lock of a game, symmetric for portrait and landscape.
///
/// The inputs say whether a layout is USABLE on this device (present for the
/// device class, loaded, not refused, not announced as unplayable by touch):
/// - `portraitSkinInPortrait` / `portraitSkinInLandscape`: the skin chosen for
///   portrait, in each orientation (what the skin itself offers, whether or
///   not it is assigned there);
/// - `landscapeSkinInLandscape` / `landscapeSkinInPortrait`: the skin chosen
///   for landscape, in each orientation.
///
/// Portrait only: the portrait skin is playable in portrait, offers no
/// landscape layout and no other skin is playably assigned to landscape.
/// Landscape only: the mirror image. NeoStation's default controls (the
/// implicit fallback of the other orientation) are not a second layout.
/// Priority decision when two DISTINCT skins are assigned on purpose (for
/// instance a portrait-only one for portrait and a landscape-only one for
/// landscape): the explicit assignments win, both orientations stay allowed and
/// nothing is locked or unassigned. A skin that offers both layouts keeps the
/// usual behaviour even if only one orientation is assigned to it.
static inline unsigned LibretroPolicyMask(bool portraitSkinInPortrait, bool portraitSkinInLandscape,
                                          bool landscapeSkinInLandscape, bool landscapeSkinInPortrait) {
  if (portraitSkinInPortrait && !portraitSkinInLandscape && !landscapeSkinInLandscape) {
    return LibretroPolicyMaskPortrait;
  }
  if (landscapeSkinInLandscape && !landscapeSkinInPortrait && !portraitSkinInPortrait) {
    return LibretroPolicyMaskLandscape;
  }
  return LibretroPolicyMaskAllButUpsideDown;
}
