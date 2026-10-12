// Placement policy of NeoStation's picture on an external screen
// (packages/external_display/ios/Classes/NeoExternalDisplayLayout.h).
// Executes the production header with Foundation and CoreGraphics only and
// compares Fit/Fill, number for number, with a frozen copy of the Build 442
// arithmetic (Build442Scale/Build442Frame below, taken from
// DolphinExternalDisplayLayout.h at revision a221ae0c, the Build 444
// delivery). The Dolphin header of Build 447 delegates to the production
// policy, so it is compared with the same frozen copy, never with the
// policy it delegates to. The window lifecycle runs in the iOS Simulator
// (external_display_ui_test.py). No device claim.
#include "NeoExternalDisplayLayout.h"
#include "DolphinExternalDisplayLayout.h"
#include <cassert>
#include <cstdio>

static bool Near(double a, double b) { return fabs(a - b) < 0.01; }
static bool NearSize(CGSize a, double w, double h) { return Near(a.width, w) && Near(a.height, h); }

// Frozen copy of the Build 442 arithmetic: the bodies of
// DOLExternalDisplayUsableSize, DOLExternalDisplayScale and
// DOLExternalDisplayFrame at revision a221ae0c, identifiers renamed and
// nothing else. It is the reference of this test and never changes.
typedef NS_ENUM(NSInteger, Build442Mode) {
  Build442ModeOff = 0,
  Build442ModeFit = 1,
  Build442ModeFill = 2,
};

static inline BOOL Build442UsableSize(CGSize size) {
  return isfinite(size.width) && isfinite(size.height) && size.width > 0 && size.height > 0;
}

static inline CGFloat Build442Scale(CGSize screen, CGSize source, Build442Mode mode) {
  if (!Build442UsableSize(screen) || !Build442UsableSize(source) ||
      mode == Build442ModeOff) return 1;
  const CGFloat heightScale = screen.height / source.height;
  const CGFloat widescreen = source.height * 16.0 / 9.0;
  const CGFloat fit = MIN(heightScale, screen.width / widescreen);
  if (mode != Build442ModeFill) return fit;
  const CGFloat standard = source.height * 4.0 / 3.0;
  const CGFloat fill = screen.width / standard;
  return MAX(fit, MIN(fill, fit * 4.0 / 3.0));
}

static inline CGRect Build442Frame(CGSize screen, CGSize source, Build442Mode mode) {
  if (!Build442UsableSize(screen) || !Build442UsableSize(source)) return CGRectZero;
  const CGFloat scale = Build442Scale(screen, source, mode);
  const CGSize size = CGSizeMake(source.width * scale, source.height * scale);
  return CGRectMake((screen.width - size.width) / 2, (screen.height - size.height) / 2, size.width, size.height);
}

int main() { @autoreleasepool {
  const CGSize tv = CGSizeMake(1920, 1080);          // 16:9 Apple TV / AirPlay
  const CGSize phone = CGSizeMake(852, 393);         // iPhone 15 landscape, 2.17:1
  const CGSize wide = CGSizeMake(932, 430);          // iPhone 15 Pro Max
  const CGSize square = CGSizeMake(1024, 768);       // 4:3 projector
  const CGSize ultra = CGSizeMake(2560, 1080);       // 21:9 monitor
  const CGSize pad = CGSizeMake(1024, 768);          // a 4:3 source (iPad)
  int cases = 0;
#define CHECK(expr, label) do { assert((expr) && label); ++cases; } while (0)

  // The frozen copy is the 442 header: its own numbers on the reference
  // pair (1920×1080 TV, 852×393 phone) before anything is compared with it.
  CHECK(Near(Build442Scale(tv, phone, Build442ModeFit), 1080.0 / 393.0), "442 fit = TV height / phone height");
  CHECK(Near(Build442Scale(tv, phone, Build442ModeFill), 1080.0 / 393.0 * 4.0 / 3.0), "442 fill = 4/3 × fit on a 16:9 TV");
  CHECK(Build442Scale(tv, phone, Build442ModeOff) == 1, "442 off = 1");
  CHECK(CGRectEqualToRect(Build442Frame(tv, CGSizeZero, Build442ModeFit), CGRectZero), "442 zero frame");

  // Preference parsing: Automatic by default, anything else only when valid.
  CHECK(NeoExternalDisplayModeFromValue(nil) == NeoExternalDisplayModeAutomatic, "default automatic");
  CHECK(NeoExternalDisplayModeFromValue(@"2") == NeoExternalDisplayModeAutomatic, "string ignored");
  CHECK(NeoExternalDisplayModeFromValue(@0) == NeoExternalDisplayModeAutomatic, "automatic");
  CHECK(NeoExternalDisplayModeFromValue(@1) == NeoExternalDisplayModeFit, "fit");
  CHECK(NeoExternalDisplayModeFromValue(@2) == NeoExternalDisplayModeFill, "fill");
  CHECK(NeoExternalDisplayModeFromValue(@3) == NeoExternalDisplayModeOriginal, "original");
  CHECK(NeoExternalDisplayModeFromValue(@4) == NeoExternalDisplayModeAutomatic && NeoExternalDisplayModeFromValue(@-1) == NeoExternalDisplayModeAutomatic, "out of range");

  // Automatic resolves to Fit for a game only; the menu fills the window.
  CHECK(NeoExternalDisplayEffectiveMode(NeoExternalDisplayModeAutomatic, NeoExternalContentGame) == NeoExternalDisplayModeFit, "automatic game = fit");
  CHECK(NeoExternalDisplayEffectiveMode(NeoExternalDisplayModeAutomatic, NeoExternalContentMenu) == NeoExternalDisplayModeAutomatic, "automatic menu stays");
  CHECK(NeoExternalDisplayEffectiveMode(NeoExternalDisplayModeAutomatic, NeoExternalContentNone) == NeoExternalDisplayModeAutomatic, "automatic none stays");
  CHECK(NeoExternalDisplayEffectiveMode(NeoExternalDisplayModeFill, NeoExternalContentGame) == NeoExternalDisplayModeFill, "fill game");
  CHECK(NeoExternalDisplayEffectiveMode(NeoExternalDisplayModeOriginal, NeoExternalContentMenu) == NeoExternalDisplayModeOriginal, "original menu");

  // Fit and Fill are the Build 442 numbers, screen by screen and source by
  // source: the production policy against the frozen copy, then the
  // delegating Dolphin header against the same copy (its Off stays 1).
  const CGSize screens[] = {tv, square, ultra, CGSizeMake(3840, 2160), CGSizeMake(1280, 720)};
  const CGSize sources[] = {phone, wide, pad, CGSizeMake(667, 375)};
  for (CGSize screen : screens) {
    for (CGSize source : sources) {
      CHECK(NeoExternalDisplayScale(screen, source, NeoExternalDisplayModeFit) == Build442Scale(screen, source, Build442ModeFit), "fit scale = 442");
      CHECK(NeoExternalDisplayScale(screen, source, NeoExternalDisplayModeFill) == Build442Scale(screen, source, Build442ModeFill), "fill scale = 442");
      CHECK(CGRectEqualToRect(NeoExternalDisplayFrame(screen, source, NeoExternalDisplayModeFit), Build442Frame(screen, source, Build442ModeFit)), "fit frame = 442");
      CHECK(CGRectEqualToRect(NeoExternalDisplayFrame(screen, source, NeoExternalDisplayModeFill), Build442Frame(screen, source, Build442ModeFill)), "fill frame = 442");
      CHECK(NeoExternalDisplayScale(screen, source, NeoExternalDisplayModeAutomatic) == NeoExternalDisplayScale(screen, source, NeoExternalDisplayModeFit), "automatic scale = fit");
      CHECK(DOLExternalDisplayScale(screen, source, DOLExternalDisplayModeFit) == Build442Scale(screen, source, Build442ModeFit), "Dolphin delegation: fit scale = 442");
      CHECK(DOLExternalDisplayScale(screen, source, DOLExternalDisplayModeFill) == Build442Scale(screen, source, Build442ModeFill), "Dolphin delegation: fill scale = 442");
      CHECK(CGRectEqualToRect(DOLExternalDisplayFrame(screen, source, DOLExternalDisplayModeFit), Build442Frame(screen, source, Build442ModeFit)), "Dolphin delegation: fit frame = 442");
      CHECK(CGRectEqualToRect(DOLExternalDisplayFrame(screen, source, DOLExternalDisplayModeFill), Build442Frame(screen, source, Build442ModeFill)), "Dolphin delegation: fill frame = 442");
      CHECK(DOLExternalDisplayScale(screen, source, DOLExternalDisplayModeOff) == Build442Scale(screen, source, Build442ModeOff), "Dolphin delegation: off = 442");
    }
  }
  // The DOL vocabulary maps onto the global modes both ways.
  CHECK(DOLExternalDisplayModeFromGlobal(NeoExternalDisplayModeAutomatic) == DOLExternalDisplayModeFit, "global automatic = Dolphin fit");
  CHECK(DOLExternalDisplayModeFromGlobal(NeoExternalDisplayModeFill) == DOLExternalDisplayModeFill, "global fill = Dolphin fill");
  CHECK(DOLExternalDisplayModeFromGlobal(NeoExternalDisplayModeOriginal) == DOLExternalDisplayModeOriginal, "global original = Dolphin original");
  CHECK(DOLExternalDisplayGlobalMode(DOLExternalDisplayModeOff) == NeoExternalDisplayModeFit, "Dolphin off places as fit (Enabled = NO is the switch)");
  CHECK(DOLExternalDisplayScale(tv, phone, DOLExternalDisplayModeOriginal) == NeoExternalDisplayScale(tv, phone, NeoExternalDisplayModeOriginal), "Dolphin original = global original");

  // Fit on a 16:9 TV: the phone height fills the TV height; the game's 16:9
  // region (393 × 16/9 = 698.7 pt) then spans the whole TV width.
  const CGFloat fit = NeoExternalDisplayScale(tv, phone, NeoExternalDisplayModeFit);
  CHECK(Near(fit, 1080.0 / 393.0), "fit scale = TV height / phone height");
  CHECK(Near(393.0 * 16.0 / 9.0 * fit, 1920), "a 16:9 game fills the TV width exactly");
  CHECK(Near(393.0 * 4.0 / 3.0 * fit, 1440), "a 4:3 game is pillarboxed at 1440 px");
  CGRect frame = NeoExternalDisplayFrame(tv, phone, NeoExternalDisplayModeFit);
  CHECK(Near(frame.size.height, 1080) && Near(CGRectGetMidX(frame), 960) && Near(CGRectGetMidY(frame), 540), "centred, full height");
  CHECK(frame.size.width > 1920, "only the phone's own side bars overflow the TV");
  CHECK(Near((frame.size.width - 1920) / 2, (852 - 393.0 * 16.0 / 9.0) / 2 * fit), "overflow equals the phone's black side bars");

  // Fill zooms a 4:3 image to the TV width: 4/3 of Fit, top and bottom cut.
  const CGFloat fill = NeoExternalDisplayScale(tv, phone, NeoExternalDisplayModeFill);
  CHECK(Near(fill, fit * 4.0 / 3.0), "fill = 4/3 × fit on a 16:9 TV");
  CHECK(Near(393.0 * 4.0 / 3.0 * fill, 1920), "a 4:3 game fills the TV width");
  frame = NeoExternalDisplayFrame(tv, phone, NeoExternalDisplayModeFill);
  CHECK(Near(frame.size.height, 1440) && Near(frame.origin.y, -180), "25 % of the height is cut, centred");

  // Original keeps the phone's format: letterboxed by the width on a 16:9
  // TV, so the picture is exactly the iPhone's, side bars included.
  const CGFloat original = NeoExternalDisplayScale(tv, phone, NeoExternalDisplayModeOriginal);
  CHECK(Near(original, 1920.0 / 852.0), "original bounded by the TV width");
  frame = NeoExternalDisplayFrame(tv, phone, NeoExternalDisplayModeOriginal);
  CHECK(Near(frame.size.width, 1920) && Near(frame.size.height, 393.0 * 1920.0 / 852.0) && Near(frame.origin.x, 0), "original: phone format centred");
  CHECK(frame.size.height < 1080 && Near(CGRectGetMidY(frame), 540), "original: letterboxed, centred");
  CHECK(Near(NeoExternalDisplayScale(square, phone, NeoExternalDisplayModeOriginal), 1024.0 / 852.0), "original on 4:3: width bound");
  CHECK(Near(NeoExternalDisplayScale(tv, pad, NeoExternalDisplayModeOriginal), 1080.0 / 768.0), "original 4:3 source on 16:9: height bound");
  CHECK(original < fit, "original never exceeds fit on a 16:9 TV");

  // A wider phone changes nothing on the TV: the height rule is phone-independent.
  CHECK(Near(430.0 * 16.0 / 9.0 * NeoExternalDisplayScale(tv, wide, NeoExternalDisplayModeFit), 1920), "Pro Max fit");

  // A 4:3 screen must never cut a 16:9 game: Fit is limited by the width.
  const CGFloat squareFit = NeoExternalDisplayScale(square, phone, NeoExternalDisplayModeFit);
  CHECK(Near(393.0 * 16.0 / 9.0 * squareFit, 1024), "16:9 width fits a 4:3 screen");
  CHECK(393.0 * squareFit < 768, "letterboxed on a 4:3 screen");
  const CGFloat squareFill = NeoExternalDisplayScale(square, phone, NeoExternalDisplayModeFill);
  CHECK(squareFill >= squareFit && squareFill <= squareFit * 4.0 / 3.0 + 1e-9, "fill never exceeds 4/3 of fit");

  // Surface size when the engine draws at the TV's resolution (libretro).
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(tv, phone, NeoExternalDisplayModeFit), 1920, 1080), "fit surface = the TV");
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(tv, phone, NeoExternalDisplayModeAutomatic), 1920, 1080), "automatic surface = fit");
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(square, phone, NeoExternalDisplayModeFit), 1024, 576), "fit surface letterboxed on 4:3");
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(tv, pad, NeoExternalDisplayModeFit), 1440, 1080), "fit surface of a 4:3 source is pillarboxed");
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(tv, phone, NeoExternalDisplayModeFill), 1920, 1440), "fill surface: 4:3 frame extended, top and bottom cut");
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(square, phone, NeoExternalDisplayModeFill), 1024, 768), "fill surface fills a 4:3 screen");
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(ultra, phone, NeoExternalDisplayModeFill), 1920, 1440), "fill surface capped at 4/3 of fit on 21:9");
  CHECK(NearSize(NeoExternalDisplaySurfaceSize(tv, phone, NeoExternalDisplayModeOriginal), 1920, 393.0 * 1920.0 / 852.0), "original surface = source × scale");
  const CGSize surfaceFit = NeoExternalDisplaySurfaceSize(tv, phone, NeoExternalDisplayModeFit);
  CHECK(surfaceFit.width <= 1920 && surfaceFit.height <= 1080, "fit never exceeds the screen");

  // Only Fill crops.
  CHECK(NeoExternalDisplayModeCrops(NeoExternalDisplayModeFill), "fill crops");
  CHECK(!NeoExternalDisplayModeCrops(NeoExternalDisplayModeFit) && !NeoExternalDisplayModeCrops(NeoExternalDisplayModeOriginal) && !NeoExternalDisplayModeCrops(NeoExternalDisplayModeAutomatic), "others do not");

  // Degenerate sizes are harmless.
  CHECK(NeoExternalDisplayScale(CGSizeZero, phone, NeoExternalDisplayModeFit) == 1, "zero screen");
  CHECK(NeoExternalDisplayScale(tv, CGSizeMake(NAN, 10), NeoExternalDisplayModeOriginal) == 1, "nan source");
  CHECK(CGRectEqualToRect(NeoExternalDisplayFrame(tv, CGSizeZero, NeoExternalDisplayModeFit), CGRectZero), "zero frame");
  CHECK(CGSizeEqualToSize(NeoExternalDisplaySurfaceSize(CGSizeZero, phone, NeoExternalDisplayModeFill), CGSizeZero), "zero surface");
  CHECK(CGSizeEqualToSize(NeoExternalDisplaySurfaceSize(tv, CGSizeMake(10, INFINITY), NeoExternalDisplayModeFit), CGSizeZero), "infinite surface");

  printf("PASS: %d external display placement assertions (Fit/Fill = frozen Build 442 copy, Dolphin delegation = the same copy; Original = phone format; TV-resolution surfaces)\n", cases);
  return 0;
} }
