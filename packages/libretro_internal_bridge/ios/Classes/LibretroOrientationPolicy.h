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

/// Portrait lock of a game.
///
/// The inputs say whether a layout is USABLE on this device (present for the
/// device class, loaded, not refused, not announced as unplayable by touch):
/// - `portraitSkinInPortrait`: the skin chosen for portrait, in portrait;
/// - `portraitSkinInLandscape`: that same skin, in landscape (what the skin
///   itself offers, whether or not it is assigned to landscape);
/// - `landscapeSkinInLandscape`: the skin chosen for landscape, in landscape.
///
/// Locked only for a skin that is portrait only on this device while no
/// other skin is assigned to landscape. NeoStation's default landscape
/// controls (the implicit fallback) are not a second layout. Priority
/// decision when two DISTINCT skins are assigned on purpose (a portrait-only
/// one for portrait, another for landscape): the explicit assignment wins and
/// both orientations stay allowed; nothing is locked or unassigned.
/// A skin that offers both layouts keeps the usual behaviour even if only one
/// orientation is assigned to it.
static inline unsigned LibretroPolicyMask(bool portraitSkinInPortrait, bool portraitSkinInLandscape,
                                          bool landscapeSkinInLandscape) {
  if (portraitSkinInPortrait && !portraitSkinInLandscape && !landscapeSkinInLandscape) {
    return LibretroPolicyMaskPortrait;
  }
  return LibretroPolicyMaskAllButUpsideDown;
}
