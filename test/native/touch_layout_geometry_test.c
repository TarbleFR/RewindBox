// Build 484: geometry of stored touch layouts (NeoTouchLayoutGeometry.h).
#include "NeoTouchLayoutGeometry.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>

static int near(double a, double b) { return fabs(a - b) < 1e-9; }

int main(void) {
  // iPhone 15 landscape: 852 x 393 with a 59 pt notch side and a 21 pt home indicator.
  const NeoTouchRect bounds = {0, 0, 852, 393};
  const NeoTouchRect safe = {59, 0, 852 - 59 - 59, 393 - 21};
  const NeoTouchPoint center = {700, 300};
  const NeoTouchPoint normalized = NeoTouchNormalize(center, safe);
  const NeoTouchPoint back = NeoTouchResolve(normalized, safe);
  assert(near(back.x, center.x) && near(back.y, center.y));

  // The same relative place on another surface (iPad landscape 1194 x 834).
  const NeoTouchRect ipadSafe = {0, 24, 1194, 834 - 24 - 20};
  const NeoTouchPoint ipad = NeoTouchResolve(normalized, ipadSafe);
  assert(near((ipad.x - ipadSafe.x) / ipadSafe.width, normalized.x));
  assert(near((ipad.y - ipadSafe.y) / ipadSafe.height, normalized.y));

  // Landscape left <-> right: the notch changes side, the control keeps its
  // place relative to the safe area.
  const NeoTouchRect mirroredSafe = {59, 0, 852 - 59 - 59, 393 - 21};
  const NeoTouchPoint mirrored = NeoTouchResolve(normalized, mirroredSafe);
  assert(near(mirrored.x, center.x));

  // Clamping keeps a control entirely on the surface.
  NeoTouchPoint clamped = NeoTouchClampCenter((NeoTouchPoint){-40, 500}, 100, 60, bounds);
  assert(near(clamped.x, 50) && near(clamped.y, 393 - 30));
  clamped = NeoTouchClampCenter((NeoTouchPoint){900, -10}, 100, 60, bounds);
  assert(near(clamped.x, 852 - 50) && near(clamped.y, 30));
  // Larger than the surface: centred on that axis.
  clamped = NeoTouchClampCenter((NeoTouchPoint){10, 10}, 900, 60, bounds);
  assert(near(clamped.x, 426) && near(clamped.y, 30));
  // Damaged input never produces NaN.
  clamped = NeoTouchClampCenter((NeoTouchPoint){NAN, INFINITY}, NAN, -5, bounds);
  assert(isfinite(clamped.x) && isfinite(clamped.y));

  // Ranges.
  assert(near(NeoTouchClampScale(0.1), NEO_TOUCH_MIN_SCALE));
  assert(near(NeoTouchClampScale(9), NEO_TOUCH_MAX_SCALE));
  assert(near(NeoTouchClampScale(NAN), 1.0));
  assert(near(NeoTouchClampOpacity(0), NEO_TOUCH_MIN_OPACITY));
  assert(near(NeoTouchClampOpacity(2), 1.0));
  assert(near(NeoTouchClampOpacity(INFINITY), 1.0));
  assert(NeoTouchValidNormalized(0.5) && NeoTouchValidNormalized(-0.4) && NeoTouchValidNormalized(1.4));
  assert(!NeoTouchValidNormalized(-0.6) && !NeoTouchValidNormalized(1.6) && !NeoTouchValidNormalized(NAN));

  // Orientation classes.
  assert(!NeoTouchIsPortrait(852, 393) && NeoTouchIsPortrait(393, 852) && !NeoTouchIsPortrait(500, 500));

  // Corner-handle resize: twice the distance doubles the size, within limits.
  const NeoTouchPoint c = {100, 100};
  assert(near(NeoTouchScaleFromDrag(1.0, c, (NeoTouchPoint){130, 140}, (NeoTouchPoint){160, 180}), 2.0));
  assert(near(NeoTouchScaleFromDrag(1.0, c, (NeoTouchPoint){130, 140}, (NeoTouchPoint){100, 100}), NEO_TOUCH_MIN_SCALE));
  assert(near(NeoTouchScaleFromDrag(1.2, c, (NeoTouchPoint){101, 101}, (NeoTouchPoint){300, 300}), 1.2));
  puts("PASS touch layout geometry");
  return 0;
}
