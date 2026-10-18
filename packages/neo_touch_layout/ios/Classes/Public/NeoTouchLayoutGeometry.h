// SPDX-License-Identifier: GPL-3.0-or-later
// Portable geometry of NeoStation touch layouts (no UIKit): the native editor,
// the applier and the host-side unit test use exactly these functions.
//
// A stored position is the control's centre relative to the safe area of the
// surface: (0, 0) is its top-left corner, (1, 1) its bottom-right corner. A
// stored size is a factor of the control's stock size on the current surface.
#pragma once

#include <math.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct NeoTouchPoint {
  double x;
  double y;
} NeoTouchPoint;

typedef struct NeoTouchRect {
  double x;
  double y;
  double width;
  double height;
} NeoTouchRect;

#define NEO_TOUCH_MIN_SCALE 0.5
#define NEO_TOUCH_MAX_SCALE 2.5
#define NEO_TOUCH_MIN_OPACITY 0.2
#define NEO_TOUCH_MAX_OPACITY 1.0
// Normalised coordinates outside this range are treated as damaged data and
// fall back to the stock position. Controls may sit up to half a safe area
// outside it (the rounded corners of the screen, the home indicator).
#define NEO_TOUCH_MIN_NORMALIZED (-0.5)
#define NEO_TOUCH_MAX_NORMALIZED 1.5

static inline double NeoTouchClamp(double value, double minimum, double maximum) {
  return value < minimum ? minimum : (value > maximum ? maximum : value);
}

static inline double NeoTouchClampScale(double scale) {
  if (!isfinite(scale)) return 1.0;
  return NeoTouchClamp(scale, NEO_TOUCH_MIN_SCALE, NEO_TOUCH_MAX_SCALE);
}

static inline double NeoTouchClampOpacity(double opacity) {
  if (!isfinite(opacity)) return 1.0;
  return NeoTouchClamp(opacity, NEO_TOUCH_MIN_OPACITY, NEO_TOUCH_MAX_OPACITY);
}

static inline bool NeoTouchValidNormalized(double value) {
  return isfinite(value) && value >= NEO_TOUCH_MIN_NORMALIZED && value <= NEO_TOUCH_MAX_NORMALIZED;
}

/// Surface orientation class: taller than wide is portrait. A square surface
/// is landscape, like the sessions' landscape-only windows.
static inline bool NeoTouchIsPortrait(double width, double height) {
  return height > width;
}

/// Centre in surface coordinates -> position relative to the safe area.
static inline NeoTouchPoint NeoTouchNormalize(NeoTouchPoint center, NeoTouchRect safe) {
  const double width = safe.width > 1.0 ? safe.width : 1.0;
  const double height = safe.height > 1.0 ? safe.height : 1.0;
  NeoTouchPoint result = {(center.x - safe.x) / width, (center.y - safe.y) / height};
  return result;
}

/// Position relative to the safe area -> centre in surface coordinates.
static inline NeoTouchPoint NeoTouchResolve(NeoTouchPoint normalized, NeoTouchRect safe) {
  NeoTouchPoint result = {safe.x + normalized.x * safe.width, safe.y + normalized.y * safe.height};
  return result;
}

/// Keeps a width x height control whose centre is `center` entirely inside
/// `bounds`. A control larger than the surface is centred on that axis.
static inline NeoTouchPoint NeoTouchClampCenter(NeoTouchPoint center, double width, double height,
                                                NeoTouchRect bounds) {
  NeoTouchPoint result = center;
  if (!isfinite(result.x)) result.x = bounds.x + bounds.width * 0.5;
  if (!isfinite(result.y)) result.y = bounds.y + bounds.height * 0.5;
  const double halfWidth = (isfinite(width) && width > 0.0 ? width : 0.0) * 0.5;
  const double halfHeight = (isfinite(height) && height > 0.0 ? height : 0.0) * 0.5;
  if (halfWidth * 2.0 >= bounds.width) result.x = bounds.x + bounds.width * 0.5;
  else result.x = NeoTouchClamp(result.x, bounds.x + halfWidth, bounds.x + bounds.width - halfWidth);
  if (halfHeight * 2.0 >= bounds.height) result.y = bounds.y + bounds.height * 0.5;
  else result.y = NeoTouchClamp(result.y, bounds.y + halfHeight, bounds.y + bounds.height - halfHeight);
  return result;
}

/// Scale of a resize drag from a corner handle: the distance between the
/// finger and the control's centre, relative to the distance at the start.
static inline double NeoTouchScaleFromDrag(double startScale, NeoTouchPoint center, NeoTouchPoint start,
                                           NeoTouchPoint current) {
  const double startDistance = hypot(start.x - center.x, start.y - center.y);
  if (!(startDistance > 4.0)) return NeoTouchClampScale(startScale);
  const double distance = hypot(current.x - center.x, current.y - center.y);
  return NeoTouchClampScale(startScale * distance / startDistance);
}

#ifdef __cplusplus
}
#endif
