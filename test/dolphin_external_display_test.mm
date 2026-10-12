// Build 442: placement of the iPhone-sized Dolphin render view on an external
// screen (AirPlay / adapter). Executes the production header with Foundation
// and CoreGraphics only; the window lifecycle runs in the iOS Simulator
// (dolphin_external_display_ui_test.py). No device claim.
//
// Build 447: the DOL functions delegate to NeoExternalDisplayLayout.h of the
// external_display pod (compiled here as <external_display/…>, staged by
// dolphin_external_display_test.py as the pod publishes it). Every 442
// number below is unchanged; the "preference parsing" block of 442
// (DOLExternalDisplayModeFromValue) is retired because the Build 442 key is
// now parsed by NeoExternalDisplayPreferences' read-only fallback (tested in
// external_display_ui_test.py) and replaced by the global ↔ Dolphin mapping.
#include "DolphinExternalDisplayLayout.h"
#include <cassert>
#include <cstdio>

static bool Near(double a, double b) { return fabs(a - b) < 0.01; }

int main() { @autoreleasepool {
  const CGSize tv = CGSizeMake(1920, 1080);          // 16:9 Apple TV / AirPlay
  const CGSize phone = CGSizeMake(852, 393);         // iPhone 15 landscape, 2.17:1
  const CGSize wide = CGSizeMake(932, 430);          // iPhone 15 Pro Max
  const CGSize square = CGSizeMake(1024, 768);       // 4:3 projector
  int cases = 0;
#define CHECK(expr, label) do { assert((expr) && label); ++cases; } while (0)

  // Global preference → Dolphin placement: Automatic is Fit for a game, as the
  // coordinator resolves it; Off is the Enabled switch (DOLExternalDisplayPreference).
  CHECK(DOLExternalDisplayModeFromGlobal(NeoExternalDisplayModeAutomatic) == DOLExternalDisplayModeFit, "automatic = fit in game");
  CHECK(DOLExternalDisplayModeFromGlobal(NeoExternalDisplayModeFit) == DOLExternalDisplayModeFit, "fit");
  CHECK(DOLExternalDisplayModeFromGlobal(NeoExternalDisplayModeFill) == DOLExternalDisplayModeFill, "fill");
  CHECK(DOLExternalDisplayModeFromGlobal(NeoExternalDisplayModeOriginal) == DOLExternalDisplayModeOriginal, "original");
  // Dolphin placement → the global mode the coordinator applies; Off has none.
  CHECK(DOLExternalDisplayGlobalMode(DOLExternalDisplayModeFit) == NeoExternalDisplayModeFit, "fit global");
  CHECK(DOLExternalDisplayGlobalMode(DOLExternalDisplayModeFill) == NeoExternalDisplayModeFill, "fill global");
  CHECK(DOLExternalDisplayGlobalMode(DOLExternalDisplayModeOriginal) == NeoExternalDisplayModeOriginal, "original global");
  CHECK(DOLExternalDisplayGlobalMode(DOLExternalDisplayModeOff) == NeoExternalDisplayModeFit, "off has no global mode: the 442 default");
  CHECK(DOLExternalDisplayModeFromGlobal(DOLExternalDisplayGlobalMode(DOLExternalDisplayModeFill)) == DOLExternalDisplayModeFill
        && DOLExternalDisplayModeFromGlobal(DOLExternalDisplayGlobalMode(DOLExternalDisplayModeOriginal)) == DOLExternalDisplayModeOriginal,
        "round trip");

  // Delegation: every DOL result is the external_display result, mode by
  // mode, screen by screen and source by source.
  const CGSize screens[] = {tv, square, CGSizeMake(2560, 1080), CGSizeMake(3840, 2160), CGSizeMake(1280, 720)};
  const CGSize sources[] = {phone, wide, CGSizeMake(1024, 768), CGSizeMake(667, 375)};
  const DOLExternalDisplayMode modes[] = {DOLExternalDisplayModeFit, DOLExternalDisplayModeFill, DOLExternalDisplayModeOriginal};
  for (CGSize screen : screens) {
    for (CGSize source : sources) {
      for (DOLExternalDisplayMode mode : modes) {
        const NeoExternalDisplayMode global = DOLExternalDisplayGlobalMode(mode);
        CHECK(DOLExternalDisplayScale(screen, source, mode) == NeoExternalDisplayScale(screen, source, global), "scale delegated");
        CHECK(CGRectEqualToRect(DOLExternalDisplayFrame(screen, source, mode), NeoExternalDisplayFrame(screen, source, global)), "frame delegated");
      }
    }
  }

  // Fit on a 16:9 TV: the phone height fills the TV height; the game's 16:9
  // region (393 × 16/9 = 698.7 pt) then spans the whole TV width.
  const CGFloat fit = DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeFit);
  CHECK(Near(fit, 1080.0 / 393.0), "fit scale = TV height / phone height");
  CHECK(Near(393.0 * 16.0 / 9.0 * fit, 1920), "a 16:9 game fills the TV width exactly");
  CHECK(Near(393.0 * 4.0 / 3.0 * fit, 1440), "a 4:3 game is pillarboxed at 1440 px");
  CGRect frame = DOLExternalDisplayFrame(tv, phone, DOLExternalDisplayModeFit);
  CHECK(Near(frame.size.height, 1080) && Near(CGRectGetMidX(frame), 960) && Near(CGRectGetMidY(frame), 540), "centred, full height");
  CHECK(frame.size.width > 1920, "only the phone's own side bars overflow the TV");
  CHECK(Near((frame.size.width - 1920) / 2, (852 - 393.0 * 16.0 / 9.0) / 2 * fit), "overflow equals the phone's black side bars");

  // Fill zooms a 4:3 image to the TV width: 4/3 of Fit, top and bottom cut.
  const CGFloat fill = DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeFill);
  CHECK(Near(fill, fit * 4.0 / 3.0), "fill = 4/3 × fit on a 16:9 TV");
  CHECK(Near(393.0 * 4.0 / 3.0 * fill, 1920), "a 4:3 game fills the TV width");
  frame = DOLExternalDisplayFrame(tv, phone, DOLExternalDisplayModeFill);
  CHECK(Near(frame.size.height, 1440) && Near(frame.origin.y, -180), "25 % of the height is cut, centred");

  // Original (Build 447): the phone's own format, bounded by the TV width.
  const CGFloat original = DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeOriginal);
  CHECK(Near(original, 1920.0 / 852.0), "original = TV width / phone width on a 16:9 TV");
  frame = DOLExternalDisplayFrame(tv, phone, DOLExternalDisplayModeOriginal);
  CHECK(Near(frame.size.width, 1920) && Near(frame.size.height, 393.0 * 1920.0 / 852.0) && Near(CGRectGetMidY(frame), 540),
        "whole phone picture, letterboxed, centred");

  // Off keeps the view as it is (mirroring handles the TV).
  CHECK(DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeOff) == 1, "off scale");
  CHECK(CGRectEqualToRect(DOLExternalDisplayFrame(tv, phone, DOLExternalDisplayModeOff),
                          CGRectMake((1920 - 852) / 2.0, (1080 - 393) / 2.0, 852, 393)), "off frame");

  // A wider phone changes nothing on the TV: the height rule is phone-independent.
  CHECK(Near(430.0 * 16.0 / 9.0 * DOLExternalDisplayScale(tv, wide, DOLExternalDisplayModeFit), 1920), "Pro Max fit");

  // A 4:3 screen must never cut a 16:9 game: Fit is limited by the width.
  const CGFloat squareFit = DOLExternalDisplayScale(square, phone, DOLExternalDisplayModeFit);
  CHECK(Near(393.0 * 16.0 / 9.0 * squareFit, 1024), "16:9 width fits a 4:3 screen");
  CHECK(393.0 * squareFit < 768, "letterboxed on a 4:3 screen");
  const CGFloat squareFill = DOLExternalDisplayScale(square, phone, DOLExternalDisplayModeFill);
  CHECK(squareFill >= squareFit && squareFill <= squareFit * 4.0 / 3.0 + 1e-9, "fill never exceeds 4/3 of fit");

  // Degenerate sizes are harmless, in every mode.
  CHECK(DOLExternalDisplayScale(CGSizeZero, phone, DOLExternalDisplayModeFit) == 1, "zero screen");
  CHECK(DOLExternalDisplayScale(tv, CGSizeMake(NAN, 10), DOLExternalDisplayModeFit) == 1, "nan source");
  CHECK(DOLExternalDisplayScale(tv, CGSizeZero, DOLExternalDisplayModeOriginal) == 1, "zero source original");
  CHECK(CGRectEqualToRect(DOLExternalDisplayFrame(tv, CGSizeZero, DOLExternalDisplayModeFit), CGRectZero), "zero frame");
  CHECK(CGRectEqualToRect(DOLExternalDisplayFrame(tv, CGSizeZero, DOLExternalDisplayModeOff), CGRectZero), "zero frame off");

  printf("PASS: %d external display placement assertions (Fit crops only the phone's side bars; Fill announced 4:3 zoom; "
         "Original letterboxed; every mode delegated to external_display)\n", cases);
  return 0;
} }
