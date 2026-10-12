// Where the picture of an embedded game is drawn: the game view's own bounds
// on the iPhone, or the surface the external-display coordinator gave the
// Metal view while it is in NeoStation's window on the TV
// (NeoExternalRenderHost with fixedDrawable == NO: the surface follows the
// television, so the core's picture is rendered at the TV's resolution).
// Pure CoreGraphics so the rule executes in the portable frontend tests
// (test/libretro_host/frontend/render_surface_test.m); no UIKit here.
#pragma once
#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>

#include <math.h>

typedef struct {
  /// Size of the surface in points.
  CGSize points;
  /// Pixels per point of the surface.
  CGFloat scale;
  /// YES while the surface is the external display's.
  BOOL external;
} LibretroRenderSurface;

/// A surface the coordinator reports: finite, at least one point each way,
/// positive scale. CGSizeZero at scale 0 (the view is back on the iPhone)
/// is not one.
static inline BOOL LibretroRenderSurfaceUsable(CGSize points, CGFloat scale) {
  return isfinite(points.width) && isfinite(points.height) && isfinite(scale) && points.width >= 1 &&
         points.height >= 1 && scale > 0;
}

/// The external surface when the coordinator gave a usable one, else the
/// iPhone view's bounds at the phone's scale (1 when unknown).
static inline LibretroRenderSurface LibretroRenderSurfaceResolve(CGSize bounds, CGFloat boundsScale, CGSize external,
                                                                 CGFloat externalScale) {
  LibretroRenderSurface surface;
  if (LibretroRenderSurfaceUsable(external, externalScale)) {
    surface.points = external;
    surface.scale = externalScale;
    surface.external = YES;
    return surface;
  }
  surface.points = bounds;
  surface.scale = isfinite(boundsScale) && boundsScale > 0 ? boundsScale : 1;
  surface.external = NO;
  return surface;
}

/// Pixels of the drawable: points × scale, rounded, never under 1 × 1.
static inline CGSize LibretroRenderSurfaceDrawableSize(LibretroRenderSurface surface) {
  return CGSizeMake(MAX(1, round(surface.points.width * surface.scale)),
                    MAX(1, round(surface.points.height * surface.scale)));
}

/// How the picture laid out on the iPhone is placed in the external
/// surface. The skin lays the game areas out for the phone (a portrait
/// phone keeps its screen in the upper part, a landscape skin leaves room
/// for the controls at the sides); the Metal view only draws those areas,
/// black elsewhere. On the TV that black is not wanted: the union of the
/// areas (`areas`, iPhone points) is scaled uniformly by `factor` and
/// centred at `origin` in the surface, so the picture fills the surface in
/// one dimension while the areas keep their arrangement (two 3DS screens
/// stay stacked). The identity placement (factor 1, origin 0, no areas)
/// leaves the areas where the phone laid them out.
typedef struct {
  CGRect areas;
  CGFloat factor;
  CGPoint origin;
} LibretroRenderSurfacePlacement;

static inline LibretroRenderSurfacePlacement LibretroRenderSurfacePlacementIdentity(void) {
  LibretroRenderSurfacePlacement placement;
  placement.areas = CGRectZero;
  placement.factor = 1;
  placement.origin = CGPointZero;
  return placement;
}

/// The placement of `areas` in a surface of `surface` points; the identity
/// when either is degenerate (under one point, not finite).
static inline LibretroRenderSurfacePlacement LibretroRenderSurfacePlacementMake(CGRect areas, CGSize surface) {
  LibretroRenderSurfacePlacement placement = LibretroRenderSurfacePlacementIdentity();
  if (!LibretroRenderSurfaceUsable(areas.size, 1) || !LibretroRenderSurfaceUsable(surface, 1) ||
      !isfinite(areas.origin.x) || !isfinite(areas.origin.y)) {
    return placement;
  }
  placement.areas = areas;
  placement.factor = MIN(surface.width / areas.size.width, surface.height / areas.size.height);
  placement.origin = CGPointMake((surface.width - areas.size.width * placement.factor) / 2,
                                 (surface.height - areas.size.height * placement.factor) / 2);
  return placement;
}

/// A game area in iPhone points, placed in the surface (surface points).
static inline CGRect LibretroRenderSurfacePlace(LibretroRenderSurfacePlacement placement, CGRect area) {
  return CGRectMake(placement.origin.x + (area.origin.x - placement.areas.origin.x) * placement.factor,
                    placement.origin.y + (area.origin.y - placement.areas.origin.y) * placement.factor,
                    area.size.width * placement.factor, area.size.height * placement.factor);
}

/// The inverse: a rectangle of the surface (a touch screen the presenter
/// placed) back in iPhone points, where the overlay maps the touches.
static inline CGRect LibretroRenderSurfaceUnplace(LibretroRenderSurfacePlacement placement, CGRect rect) {
  const CGFloat factor = placement.factor > 0 ? placement.factor : 1;
  return CGRectMake(placement.areas.origin.x + (rect.origin.x - placement.origin.x) / factor,
                    placement.areas.origin.y + (rect.origin.y - placement.origin.y) / factor,
                    rect.size.width / factor, rect.size.height / factor);
}
