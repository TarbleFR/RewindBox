// Behaviour of the orientation lock decision of the libretro and Dolphin bridges
// (LibretroOrientationPolicy.h, DOLOrientationPolicy.h). Plain C: no UIKit.
// The decision follows what the player CHOSE, never what the skin file could do:
// only portrait chosen -> portrait, only landscape chosen -> landscape,
// both -> usual rotation. The inputs that decide which orientations count as
// chosen (store inheritance, real skins) are exercised by
// test/libretro_host/frontend/orientation_selection_test.m on macOS.
#include <stdio.h>
#include "../../packages/libretro_internal_bridge/ios/Classes/LibretroOrientationPolicy.h"
#include "../../packages/dolphin_internal_bridge/ios/Classes/DOLOrientationPolicy.h"
#include "../../packages/armsx2_internal_bridge/ios/Classes/ARMSX2OrientationPolicy.h"

// UIInterfaceOrientationMask values (UIKit): Portrait 1<<1, PortraitUpsideDown 1<<2,
// LandscapeRight 1<<3, LandscapeLeft 1<<4.
#define UIKIT_PORTRAIT 2u
#define UIKIT_LANDSCAPE 24u
#define UIKIT_ALL_BUT_UPSIDE_DOWN 26u

static int failures = 0;
static void expect(const char *name, unsigned got, unsigned want) {
  if (got != want) {
    printf("FAIL %s: got %u want %u\n", name, got, want);
    failures++;
  } else {
    printf("ok   %s\n", name);
  }
}

int main(void) {
  expect("constants: portrait", LibretroPolicyMaskPortrait, UIKIT_PORTRAIT);
  expect("constants: landscape", LibretroPolicyMaskLandscape, UIKIT_LANDSCAPE);
  expect("constants: all but upside down", LibretroPolicyMaskAllButUpsideDown, UIKIT_ALL_BUT_UPSIDE_DOWN);
  expect("constants: dolphin portrait", DOLPolicyMaskPortrait, UIKIT_PORTRAIT);
  expect("constants: dolphin landscape", DOLPolicyMaskLandscape, UIKIT_LANDSCAPE);
  expect("constants: dolphin all", DOLPolicyMaskAllButUpsideDown, UIKIT_ALL_BUT_UPSIDE_DOWN);
  expect("constants: armsx2 portrait", ARMSX2PolicyMaskPortrait, UIKIT_PORTRAIT);
  expect("constants: armsx2 landscape", ARMSX2PolicyMaskLandscape, UIKIT_LANDSCAPE);
  expect("constants: armsx2 all", ARMSX2PolicyMaskAllButUpsideDown, UIKIT_ALL_BUT_UPSIDE_DOWN);

  // (portrait chosen, landscape chosen)
  expect("libretro: portrait only chosen", LibretroPolicyMask(true, false), UIKIT_PORTRAIT);
  expect("libretro: landscape only chosen", LibretroPolicyMask(false, true), UIKIT_LANDSCAPE);
  expect("libretro: both chosen", LibretroPolicyMask(true, true), UIKIT_ALL_BUT_UPSIDE_DOWN);
  expect("libretro: none chosen (default controls)", LibretroPolicyMask(false, false), UIKIT_ALL_BUT_UPSIDE_DOWN);
  expect("dolphin: portrait only chosen", DOLPolicyMask(true, false), UIKIT_PORTRAIT);
  expect("dolphin: landscape only chosen", DOLPolicyMask(false, true), UIKIT_LANDSCAPE);
  expect("dolphin: both chosen", DOLPolicyMask(true, true), UIKIT_ALL_BUT_UPSIDE_DOWN);
  expect("dolphin: none chosen (the DolphiniOS pad stays landscape)", DOLPolicyMask(false, false), UIKIT_LANDSCAPE);

  expect("armsx2: portrait only chosen", ARMSX2PolicyMask(true, false), UIKIT_PORTRAIT);
  expect("armsx2: landscape only chosen", ARMSX2PolicyMask(false, true), UIKIT_LANDSCAPE);
  expect("armsx2: both chosen", ARMSX2PolicyMask(true, true), UIKIT_ALL_BUT_UPSIDE_DOWN);
  expect("armsx2: none chosen (the session turns with the phone)", ARMSX2PolicyMask(false, false), UIKIT_ALL_BUT_UPSIDE_DOWN);

  // The bounds a session is first laid out in may still be those of the screen that
  // opened it; the surface the Dolphin core reads once is computed for the settled ones.
  expect("turn: portrait-only session opened sideways", DOLPolicyBoundsWillTurn(UIKIT_PORTRAIT, 852, 393), 1u);
  expect("turn: portrait-only session already upright", DOLPolicyBoundsWillTurn(UIKIT_PORTRAIT, 393, 852), 0u);
  expect("turn: landscape-only session opened upright", DOLPolicyBoundsWillTurn(UIKIT_LANDSCAPE, 393, 852), 1u);
  expect("turn: landscape-only session already sideways", DOLPolicyBoundsWillTurn(UIKIT_LANDSCAPE, 852, 393), 0u);
  expect("turn: both orientations allowed, upright", DOLPolicyBoundsWillTurn(UIKIT_ALL_BUT_UPSIDE_DOWN, 393, 852), 0u);
  expect("turn: both orientations allowed, sideways", DOLPolicyBoundsWillTurn(UIKIT_ALL_BUT_UPSIDE_DOWN, 852, 393), 0u);
  expect("turn: no bounds yet", DOLPolicyBoundsWillTurn(UIKIT_PORTRAIT, 0, 0), 0u);

  // Exhaustive: no lock without a choice, never both locks, the choice is
  // independent of the skin file's capabilities (they are not an input).
  int bad = 0;
  for (int bits = 0; bits < 4; bits++) {
    bool p = bits & 1, l = bits & 2;
    unsigned lib = LibretroPolicyMask(p, l);
    unsigned dol = DOLPolicyMask(p, l);
    if (lib == UIKIT_PORTRAIT && !(p && !l)) bad++;
    if (lib == UIKIT_LANDSCAPE && !(l && !p)) bad++;
    if (dol == UIKIT_PORTRAIT && !(p && !l)) bad++;
    // The three engines agree whenever a skin is chosen.
    if ((p || l) && lib != dol) bad++;
    if (ARMSX2PolicyMask(p, l) != lib) bad++;
    // Mirror symmetry of the lock.
    if ((LibretroPolicyMask(p, l) == UIKIT_PORTRAIT) != (LibretroPolicyMask(l, p) == UIKIT_LANDSCAPE)) bad++;
  }
  expect("exhaustive: locks justified, engines agree, mirror symmetry", (unsigned)bad, 0u);

  printf(failures ? "%d failure(s)\n" : "all passed\n", failures);
  return failures ? 1 : 0;
}
