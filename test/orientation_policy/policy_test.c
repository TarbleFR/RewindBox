// Behaviour of the portrait-lock decision of the libretro and Dolphin bridges
// (LibretroOrientationPolicy.h, DOLOrientationPolicy.h). Plain C: no UIKit.
// Every row is one situation of the request; both engines must agree.
#include <stdio.h>
#include <string.h>
#include "../../packages/libretro_internal_bridge/ios/Classes/LibretroOrientationPolicy.h"
#include "../../packages/dolphin_internal_bridge/ios/Classes/DOLOrientationPolicy.h"

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

// Libretro: (portrait skin in portrait, same skin in landscape, landscape skin in landscape)
static void libretro(const char *name, bool pp, bool pl, bool ll, unsigned want) {
  char label[160];
  snprintf(label, sizeof label, "libretro: %s", name);
  expect(label, LibretroPolicyMask(pp, pl, ll), want);
}
// Dolphin: (portrait assigned, landscape assigned, portrait skin offers landscape)
static void dolphin(const char *name, bool p, bool l, bool offers, unsigned want) {
  char label[160];
  snprintf(label, sizeof label, "dolphin: %s", name);
  expect(label, DOLPolicyMask(p, l, offers), want);
}

int main(void) {
  expect("constants: portrait", LibretroPolicyMaskPortrait, UIKIT_PORTRAIT);
  expect("constants: landscape", LibretroPolicyMaskLandscape, UIKIT_LANDSCAPE);
  expect("constants: all but upside down", LibretroPolicyMaskAllButUpsideDown, UIKIT_ALL_BUT_UPSIDE_DOWN);
  expect("constants: dolphin portrait", DOLPolicyMaskPortrait, UIKIT_PORTRAIT);
  expect("constants: dolphin landscape", DOLPolicyMaskLandscape, UIKIT_LANDSCAPE);
  expect("constants: dolphin all", DOLPolicyMaskAllButUpsideDown, UIKIT_ALL_BUT_UPSIDE_DOWN);

  // Portrait-only skin, landscape left on the implicit default controls: locked.
  libretro("portrait-only skin, landscape default", true, false, false, UIKIT_PORTRAIT);
  // The same skin written to both keys: its landscape layout is missing, still portrait only.
  libretro("portrait-only skin assigned to both keys", true, false, false, UIKIT_PORTRAIT);
  // Dual-layout skin assigned to both, or to portrait only: the usual behaviour.
  libretro("dual skin, both orientations", true, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("dual skin assigned to portrait only", true, true, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  // Two distinct skins assigned on purpose: the explicit assignment wins, nothing is locked.
  libretro("portrait-only skin + another skin for landscape", true, false, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  // Back to the default controls, or a skin refused / unplayable in portrait: lock released.
  libretro("default controls", false, false, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("portrait skin refused or unplayable", false, false, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("landscape skin only", false, false, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  // A portrait-only skin that became playable only in landscape is not a portrait skin.
  libretro("nothing usable in portrait", false, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);

  dolphin("portrait-only skin, landscape default", true, false, false, UIKIT_PORTRAIT);
  dolphin("portrait-only skin also named for landscape (no layout)", true, false, false, UIKIT_PORTRAIT);
  dolphin("dual skin, both assigned", true, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  dolphin("dual skin, assigned to portrait only", true, false, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  dolphin("portrait-only skin + another skin for landscape", true, true, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  dolphin("no skin: the DolphiniOS pad stays landscape", false, false, false, UIKIT_LANDSCAPE);
  dolphin("landscape skin only stays landscape", false, true, false, UIKIT_LANDSCAPE);

  // The two engines agree on every combination they both express.
  int disagreements = 0;
  for (int pp = 0; pp < 2; pp++)
    for (int pl = 0; pl < 2; pl++)
      for (int ll = 0; ll < 2; ll++) {
        unsigned a = LibretroPolicyMask(pp, pl, ll);
        unsigned b = pp ? DOLPolicyMask(true, ll, pl) : UIKIT_ALL_BUT_UPSIDE_DOWN;
        if (a != b) disagreements++;
      }
  expect("engines agree when a portrait skin is usable", (unsigned)disagreements, 0u);

  printf(failures ? "%d failure(s)\n" : "all passed\n", failures);
  return failures ? 1 : 0;
}
