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

// Libretro: (portrait skin in portrait, same skin in landscape,
//            landscape skin in landscape, same skin in portrait)
static void libretro(const char *name, bool pp, bool pl, bool ll, bool lp, unsigned want) {
  char label[160];
  snprintf(label, sizeof label, "libretro: %s", name);
  expect(label, LibretroPolicyMask(pp, pl, ll, lp), want);
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
  libretro("portrait-only skin, landscape default", true, false, false, false, UIKIT_PORTRAIT);
  // The same skin written to both keys: its landscape layout is missing, still portrait only.
  libretro("portrait-only skin assigned to both keys", true, false, false, false, UIKIT_PORTRAIT);
  // Landscape-only skin, portrait left on the implicit default controls: locked (mirror).
  libretro("landscape-only skin, portrait default", false, false, true, false, UIKIT_LANDSCAPE);
  libretro("landscape-only skin assigned to both keys", false, false, true, false, UIKIT_LANDSCAPE);
  // Dual-layout skin assigned to both, or to one orientation only: the usual behaviour.
  libretro("dual skin, both orientations", true, true, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("dual skin assigned to portrait only", true, true, false, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("dual skin assigned to landscape only", false, false, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  // Two distinct skins assigned on purpose: the explicit assignments win, nothing is locked.
  libretro("portrait-only skin + another skin for landscape", true, false, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("portrait-only + landscape-only skins", true, false, true, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("landscape-only skin + another skin for portrait", true, true, true, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  // Back to the default controls, or skins refused / unplayable: lock released.
  libretro("default controls", false, false, false, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("portrait skin refused or unplayable", false, false, false, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("landscape skin refused or unplayable", false, false, false, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  // A skin only usable in the other orientation than the one it is assigned to locks nothing.
  libretro("portrait key holds a landscape-only skin", false, true, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  libretro("landscape key holds a portrait-only skin", true, false, false, true, UIKIT_PORTRAIT);

  dolphin("portrait-only skin, landscape default", true, false, false, UIKIT_PORTRAIT);
  dolphin("portrait-only skin also named for landscape (no layout)", true, false, false, UIKIT_PORTRAIT);
  dolphin("dual skin, both assigned", true, true, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  dolphin("dual skin, assigned to portrait only", true, false, true, UIKIT_ALL_BUT_UPSIDE_DOWN);
  dolphin("portrait-only skin + another skin for landscape", true, true, false, UIKIT_ALL_BUT_UPSIDE_DOWN);
  dolphin("no skin: the DolphiniOS pad stays landscape", false, false, false, UIKIT_LANDSCAPE);
  dolphin("landscape skin only stays landscape", false, true, false, UIKIT_LANDSCAPE);
  dolphin("landscape-only skin: landscape lock (already the session default)", false, true, true, UIKIT_LANDSCAPE);

  // Exhaustive: at most one lock, and a lock needs a usable skin in the locked orientation.
  int bad = 0;
  for (int bits = 0; bits < 16; bits++) {
    bool pp = bits & 1, pl = bits & 2, ll = bits & 4, lp = bits & 8;
    unsigned m = LibretroPolicyMask(pp, pl, ll, lp);
    if (m != UIKIT_PORTRAIT && m != UIKIT_LANDSCAPE && m != UIKIT_ALL_BUT_UPSIDE_DOWN) bad++;
    if (m == UIKIT_PORTRAIT && !(pp && !pl && !ll)) bad++;
    if (m == UIKIT_LANDSCAPE && !(ll && !lp && !pp)) bad++;
    // Mirror symmetry: swapping the roles swaps the lock.
    unsigned mirror = LibretroPolicyMask(ll, lp, pp, pl);
    if ((m == UIKIT_PORTRAIT) != (mirror == UIKIT_LANDSCAPE)) bad++;
    if ((m == UIKIT_LANDSCAPE) != (mirror == UIKIT_PORTRAIT)) bad++;
  }
  expect("exhaustive: valid masks, locks justified, mirror symmetry", (unsigned)bad, 0u);

  printf(failures ? "%d failure(s)\n" : "all passed\n", failures);
  return failures ? 1 : 0;
}
