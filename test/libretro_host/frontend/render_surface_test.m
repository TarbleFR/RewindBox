// Behavioural test of LibretroRenderSurface.h: which surface the picture of
// an embedded game is drawn into, and the drawable it gives.
//
// On the iPhone the surface is the game view's bounds at the phone's native
// scale. While the external-display coordinator holds the Metal view in
// NeoStation's window on the TV, it reports that surface in points with the
// TV's scale (NeoExternalRenderHost, fixedDrawable == NO): the drawable then
// has the TV's pixels, whatever the phone's bounds. CGSizeZero at scale 0
// (the view is back on the phone), a size under one point, a scale of 0 or
// a non-finite value are ignored. The second half runs the coordinator's
// own policy (NeoExternalDisplaySurfaceSize of packages/external_display)
// end to end: the surface is the whole TV in every mode and from any
// iPhone layout (review of 12 October 2026, M3), so an iPhone 15 on a 1080p
// Apple TV renders 1920 × 1080 in Automatic, Fit, Fill and Original,
// landscape or portrait, 3840 × 2160 on a 4K screen and 1920 × 1080 on a
// 960 × 540 @2x window. The last part places the picture in that surface
// (LibretroRenderSurfacePlacement): the game areas of the iPhone layout
// scaled uniformly and centred, the black around them left out (a 4:3
// screen takes the TV's full height, 1440 × 1080, from a landscape or a
// portrait phone; a 3:2 GBA screen fills 1620 × 1080; two 3DS screens keep
// their arrangement), and brings a touch screen back to the phone's layout.
// The placement rule itself is also checked on surfaces of other aspects.
// LINK: -framework CoreGraphics
#import <Foundation/Foundation.h>

#import "LibretroRenderSurface.h"
// The pod the bridge depends on (libretro_internal_bridge.podspec); the
// harness searches the bridge's own Classes folder only.
#import "../../../packages/external_display/ios/Classes/NeoExternalDisplayLayout.h"

#include <math.h>
#include <stdio.h>

static int failures = 0;

static void Report(BOOL passed, NSString *message, int line) {
  if (passed) {
    printf("PASS %s\n", message.UTF8String);
  } else {
    printf("FAIL %s (%s:%d)\n", message.UTF8String, __FILE__, line);
    failures++;
  }
}

#define CHECK(condition, ...) Report((condition) ? YES : NO, [NSString stringWithFormat:__VA_ARGS__], __LINE__)

static BOOL SameSize(CGSize a, CGSize b) {
  return fabs(a.width - b.width) < 0.001 && fabs(a.height - b.height) < 0.001;
}

static NSString *Describe(CGSize size) {
  return [NSString stringWithFormat:@"%.1f×%.1f", size.width, size.height];
}

static BOOL SameRect(CGRect a, CGRect b) {
  return fabs(a.origin.x - b.origin.x) < 0.001 && fabs(a.origin.y - b.origin.y) < 0.001 &&
         fabs(a.size.width - b.size.width) < 0.001 && fabs(a.size.height - b.size.height) < 0.001;
}

static NSString *DescribeRect(CGRect rect) {
  return [NSString stringWithFormat:@"%.2f,%.2f %.2f×%.2f", rect.origin.x, rect.origin.y, rect.size.width,
                                    rect.size.height];
}

/// `area` (iPhone points) placed in a surface of `surface` points.
static CGRect Placed(CGRect area, CGSize surface) {
  return LibretroRenderSurfacePlace(LibretroRenderSurfacePlacementMake(area, surface), area);
}

/// The drawable of a game view of `bounds` points at `scale` on the phone
/// while the coordinator reports `external` at `externalScale`.
static CGSize Drawable(CGSize bounds, CGFloat scale, CGSize external, CGFloat externalScale) {
  return LibretroRenderSurfaceDrawableSize(LibretroRenderSurfaceResolve(bounds, scale, external, externalScale));
}

/// The drawable while the coordinator shows the picture of a phone of
/// `phone` points on a TV window of `screen` points at `screenScale`, in
/// `mode` (NeoExternalDisplaySurfaceSize applied like placeRenderView does).
static CGSize SurfaceOnTV(CGSize phone, CGSize screen, NeoExternalDisplayMode stored) {
  NeoExternalDisplayMode mode = NeoExternalDisplayEffectiveMode(stored, NeoExternalContentGame);
  return NeoExternalDisplaySurfaceSize(screen, phone, mode);
}

static CGSize DrawableOnTV(CGSize phone, CGFloat phoneScale, CGSize screen, CGFloat screenScale,
                           NeoExternalDisplayMode stored) {
  return Drawable(phone, phoneScale, SurfaceOnTV(phone, screen, stored), screenScale);
}

int main(int argc, const char *argv[]) {
  (void)argc;
  (void)argv;
  @autoreleasepool {
    const CGSize landscape = CGSizeMake(852, 393);  // iPhone 15, @3x
    const CGSize portrait = CGSizeMake(393, 852);
    const CGSize none = CGSizeZero;

    // On the phone: the bounds at the native scale.
    LibretroRenderSurface phone = LibretroRenderSurfaceResolve(landscape, 3, none, 0);
    CHECK(!phone.external && SameSize(phone.points, landscape) && phone.scale == 3,
          @"no external surface: the phone's bounds at its scale");
    CHECK(SameSize(Drawable(landscape, 3, none, 0), CGSizeMake(2556, 1179)), @"phone drawable 2556×1179 (%@)",
          Describe(Drawable(landscape, 3, none, 0)));
    CHECK(SameSize(Drawable(landscape, 0, none, 0), landscape), @"unknown phone scale counts as 1");
    CHECK(SameSize(Drawable(landscape, NAN, none, 0), landscape), @"non-finite phone scale counts as 1");

    // On the TV: the surface the coordinator reported, whatever the phone's bounds.
    LibretroRenderSurface tv = LibretroRenderSurfaceResolve(landscape, 3, CGSizeMake(1920, 1080), 1);
    CHECK(tv.external && SameSize(tv.points, CGSizeMake(1920, 1080)) && tv.scale == 1,
          @"external surface kept in points at the TV's scale");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(1920, 1080), 1), CGSizeMake(1920, 1080)),
          @"1920×1080 @1x surface: 1920×1080 drawable (the TV's pixels, not the phone's)");
    CHECK(SameSize(Drawable(portrait, 3, CGSizeMake(1920, 1080), 1), CGSizeMake(1920, 1080)),
          @"the phone's orientation does not change the external drawable");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(960, 540), 2), CGSizeMake(1920, 1080)),
          @"960×540 @2x surface: 1920×1080 drawable");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(1279.5, 719.5), 1), CGSizeMake(1280, 720)),
          @"half points round to whole pixels");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(1920, 1440), 1), CGSizeMake(1920, 1440)),
          @"a reported surface taller than a 1080p screen keeps its height (the drawable is the surface reported)");

    // Degenerate reports fall back to the phone.
    CHECK(!LibretroRenderSurfaceResolve(landscape, 3, none, 0).external, @"CGSizeZero at scale 0: back on the phone");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(1920, 0), 1), CGSizeMake(2556, 1179)),
          @"a surface without height is ignored");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(1920, 1080), 0), CGSizeMake(2556, 1179)),
          @"a surface at scale 0 is ignored");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(0.5, 0.5), 1), CGSizeMake(2556, 1179)),
          @"a surface under one point is ignored");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(NAN, 1080), 1), CGSizeMake(2556, 1179)),
          @"a non-finite surface is ignored");
    CHECK(SameSize(Drawable(landscape, 3, CGSizeMake(1920, 1080), INFINITY), CGSizeMake(2556, 1179)),
          @"a non-finite scale is ignored");
    CHECK(SameSize(Drawable(CGSizeMake(0, 0), 3, none, 0), CGSizeMake(1, 1)), @"the drawable is never under 1×1");

    // Back and forth: the external report, then CGSizeZero, then the phone again.
    CGSize before = Drawable(landscape, 3, none, 0);
    CGSize during = Drawable(landscape, 3, CGSizeMake(1920, 1080), 1);
    CGSize after = Drawable(landscape, 3, none, 0);
    CHECK(SameSize(before, after) && !SameSize(before, during), @"the phone drawable comes back unchanged after the TV");

    // The coordinator's policy end to end (NeoExternalDisplaySurfaceSize).
    const CGSize fullHD = CGSizeMake(1920, 1080);
    CHECK(SameSize(DrawableOnTV(landscape, 3, fullHD, 1, NeoExternalDisplayModeFit), fullHD),
          @"iPhone 15 landscape, 1080p TV, Fit: 1920×1080 (%@)",
          Describe(DrawableOnTV(landscape, 3, fullHD, 1, NeoExternalDisplayModeFit)));
    CHECK(SameSize(DrawableOnTV(landscape, 3, fullHD, 1, NeoExternalDisplayModeAutomatic), fullHD),
          @"Automatic is Fit for a game: 1920×1080");
    // Retired assertions (review of 12 October 2026, M3): Fill gave a
    // 1920×1440 surface cut by the window, Original the phone's format
    // (1920×886) and a portrait phone a 498×1080 pillar. The surface is now
    // the whole TV in every mode; each game keeps its own aspect through the
    // placement below, and the formats apply to the fixed drawables only.
    CHECK(SameSize(DrawableOnTV(landscape, 3, fullHD, 1, NeoExternalDisplayModeFill), fullHD),
          @"Fill: the whole TV, 1920×1080, nothing drawn off the screen (%@)",
          Describe(DrawableOnTV(landscape, 3, fullHD, 1, NeoExternalDisplayModeFill)));
    CHECK(SameSize(DrawableOnTV(landscape, 3, fullHD, 1, NeoExternalDisplayModeOriginal), fullHD),
          @"Original: the whole TV, 1920×1080 (%@)",
          Describe(DrawableOnTV(landscape, 3, fullHD, 1, NeoExternalDisplayModeOriginal)));
    CHECK(SameSize(DrawableOnTV(landscape, 3, CGSizeMake(3840, 2160), 1, NeoExternalDisplayModeFit), CGSizeMake(3840, 2160)),
          @"4K screen, Fit: 3840×2160");
    CHECK(SameSize(DrawableOnTV(landscape, 3, CGSizeMake(960, 540), 2, NeoExternalDisplayModeFit), fullHD),
          @"960×540 @2x window, Fit: 1920×1080");
    CHECK(SameSize(DrawableOnTV(portrait, 3, fullHD, 1, NeoExternalDisplayModeFit), fullHD),
          @"portrait phone, Fit: the whole TV, no pillar (%@)", Describe(DrawableOnTV(portrait, 3, fullHD, 1, NeoExternalDisplayModeFit)));
    const NeoExternalDisplayMode modes[] = {NeoExternalDisplayModeAutomatic, NeoExternalDisplayModeFit, NeoExternalDisplayModeFill,
                                            NeoExternalDisplayModeOriginal};
    for (size_t index = 0; index < sizeof(modes) / sizeof(modes[0]); ++index) {
      CHECK(SameSize(SurfaceOnTV(landscape, fullHD, modes[index]), fullHD) && SameSize(SurfaceOnTV(portrait, fullHD, modes[index]), fullHD),
            @"mode %ld: the surface is the TV, landscape and portrait", (long)modes[index]);
    }
    CHECK(SameSize(DrawableOnTV(landscape, 3, CGSizeZero, 0, NeoExternalDisplayModeFit), CGSizeMake(2556, 1179)),
          @"no screen: the coordinator's zero surface leaves the phone drawable");

    // The picture in the external surface (LibretroRenderSurfacePlacement):
    // the game areas of the iPhone layout, scaled uniformly and centred so
    // they fill the surface, the black around them left out. A 4:3 screen
    // at the full height of the landscape phone, controls at its sides.
    const CGRect landscapeArea = CGRectMake(164, 0, 524, 393);
    CHECK(SameRect(Placed(landscapeArea, fullHD), CGRectMake(240, 0, 1440, 1080)),
          @"landscape 4:3 screen, Fit: 1440×1080 at the TV's full height (%@)", DescribeRect(Placed(landscapeArea, fullHD)));
    // A portrait phone keeps its screen in the upper part, the controls
    // below; on the TV the screen alone is placed, at the TV's full height.
    const CGRect portraitArea = CGRectMake(0, 60, 393, 294.75);
    CHECK(SameRect(Placed(portraitArea, SurfaceOnTV(portrait, fullHD, NeoExternalDisplayModeFit)), CGRectMake(240, 0, 1440, 1080)),
          @"portrait 4:3 screen: 1440×1080 at the TV's full height, like landscape (%@)",
          DescribeRect(Placed(portraitArea, SurfaceOnTV(portrait, fullHD, NeoExternalDisplayModeFit))));
    // A 3:2 GBA screen fills 1620×1080 of a 1080p TV from either orientation.
    const CGRect gbaPortrait = CGRectMake(0, 80, 393, 262);
    const CGRect gbaLandscape = CGRectMake(131.25, 0, 589.5, 393);
    CHECK(SameRect(Placed(gbaPortrait, SurfaceOnTV(portrait, fullHD, NeoExternalDisplayModeFit)), CGRectMake(150, 0, 1620, 1080)),
          @"portrait GBA screen: 1620×1080, centred (%@)",
          DescribeRect(Placed(gbaPortrait, SurfaceOnTV(portrait, fullHD, NeoExternalDisplayModeFit))));
    CHECK(SameRect(Placed(gbaLandscape, SurfaceOnTV(landscape, fullHD, NeoExternalDisplayModeFit)), CGRectMake(150, 0, 1620, 1080)),
          @"landscape GBA screen: 1620×1080, centred (%@)",
          DescribeRect(Placed(gbaLandscape, SurfaceOnTV(landscape, fullHD, NeoExternalDisplayModeFit))));
    for (size_t index = 0; index < sizeof(modes) / sizeof(modes[0]); ++index) {
      CHECK(SameRect(Placed(landscapeArea, SurfaceOnTV(landscape, fullHD, modes[index])), CGRectMake(240, 0, 1440, 1080)),
            @"mode %ld: the 4:3 screen keeps its aspect at the TV's full height", (long)modes[index]);
    }
    // The placement rule on surfaces of other aspects (a host can report
    // any): a surface of the picture's own 4:3 aspect is filled exactly, a
    // wider one keeps 4:3 at its height, a narrow one puts the screen at
    // its width, centred.
    CHECK(SameRect(Placed(landscapeArea, CGSizeMake(1920, 1440)), CGRectMake(0, 0, 1920, 1440)),
          @"a 1920×1440 surface of the picture's own aspect is filled exactly (%@)",
          DescribeRect(Placed(landscapeArea, CGSizeMake(1920, 1440))));
    CHECK(SameRect(Placed(landscapeArea, CGSizeMake(1920, 886)),
                   CGRectMake((1920 - 886 * 4.0 / 3.0) / 2, 0, 886 * 4.0 / 3.0, 886)),
          @"a wider surface: 4:3 at its height, centred (%@)",
          DescribeRect(Placed(landscapeArea, CGSizeMake(1920, 886))));
    CHECK(SameRect(Placed(portraitArea, CGSizeMake(498, 1080)), CGRectMake(0, 353.25, 498, 373.5)),
          @"a narrow 498×1080 surface: the screen fills its width, centred (%@)",
          DescribeRect(Placed(portraitArea, CGSizeMake(498, 1080))));
    // Two 3DS screens stacked on the phone keep their arrangement and gap.
    const CGRect top = CGRectMake(0, 50, 400, 240);
    const CGRect bottom = CGRectMake(40, 300, 320, 240);
    LibretroRenderSurfacePlacement stacked =
        LibretroRenderSurfacePlacementMake(CGRectUnion(top, bottom), CGSizeMake(800, 980));
    CHECK(SameRect(LibretroRenderSurfacePlace(stacked, top), CGRectMake(0, 0, 800, 480)) &&
              SameRect(LibretroRenderSurfacePlace(stacked, bottom), CGRectMake(80, 500, 640, 480)),
          @"3DS screens stacked: both scaled by 2, the 10-point gap kept (%@ / %@)",
          DescribeRect(LibretroRenderSurfacePlace(stacked, top)), DescribeRect(LibretroRenderSurfacePlace(stacked, bottom)));
    // The touch screen comes back to the phone's layout, where the overlay
    // maps the touches: the presenter's output in the surface, unplaced.
    CHECK(SameRect(LibretroRenderSurfaceUnplace(stacked, CGRectMake(80, 500, 640, 480)), bottom),
          @"the touch screen placed on the TV maps back to the phone's layout (%@)",
          DescribeRect(LibretroRenderSurfaceUnplace(stacked, CGRectMake(80, 500, 640, 480))));
    LibretroRenderSurfacePlacement fit = LibretroRenderSurfacePlacementMake(landscapeArea, fullHD);
    CHECK(SameRect(LibretroRenderSurfaceUnplace(fit, LibretroRenderSurfacePlace(fit, CGRectMake(200, 10, 100, 50))),
                   CGRectMake(200, 10, 100, 50)),
          @"place then unplace is the identity");
    // Degenerate inputs: the identity placement leaves the areas where the
    // phone laid them out, and never divides by zero on the way back.
    LibretroRenderSurfacePlacement identity = LibretroRenderSurfacePlacementIdentity();
    CHECK(SameRect(LibretroRenderSurfacePlace(identity, landscapeArea), landscapeArea) &&
              SameRect(LibretroRenderSurfaceUnplace(identity, landscapeArea), landscapeArea),
          @"identity placement");
    CHECK(SameRect(Placed(landscapeArea, CGSizeZero), landscapeArea), @"no surface: identity");
    CHECK(SameRect(LibretroRenderSurfacePlace(LibretroRenderSurfacePlacementMake(CGRectZero, fullHD), landscapeArea),
                   landscapeArea),
          @"no game area: identity");
    CHECK(SameRect(LibretroRenderSurfacePlace(LibretroRenderSurfacePlacementMake(CGRectMake(NAN, 0, 524, 393), fullHD),
                                              landscapeArea),
                   landscapeArea),
          @"non-finite area: identity");
    LibretroRenderSurfacePlacement zeroFactor = identity;
    zeroFactor.factor = 0;
    CHECK(SameRect(LibretroRenderSurfaceUnplace(zeroFactor, landscapeArea), landscapeArea),
          @"a zero factor unplaces as the identity");
  }
  printf("%s: %d failure(s)\n", failures == 0 ? "render_surface_test passed" : "render_surface_test FAILED", failures);
  return failures == 0 ? 0 : 1;
}
