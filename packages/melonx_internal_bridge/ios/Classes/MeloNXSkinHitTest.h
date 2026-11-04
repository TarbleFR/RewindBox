// SPDX-License-Identifier: GPL-3.0-or-later
// Which control of a skin layout a touch reaches. Plain C so the decision is
// compiled and run on the shipped archives by the host tests
// (test/pocket_skin_input_chain_test.py) exactly as MeloNXSkinOverlay runs it.
// The MeloNX pod's own copy of the Dolphin pod's DOLSkinHitTest.h (a pod cannot import
// the other); the host test proves the copies give the same answer.
//
// Coordinates are mapping points. Items are in drawing order (the last one is
// drawn on top). Three passes:
// 1. the control actually drawn under the point: its frame contains the point
//    and its normal sprite is opaque there (alpha >= 50 %), last drawn first;
//    an item without an alpha map counts as opaque over its whole frame;
// 2. else, among the frames containing the point, the one whose centre is
//    nearest (a gap between interlocking shapes goes to the closer control);
// 3. else, the same among the extended touch areas (frame + extendedEdges).
// A layout whose frames and touch areas never overlap (every earlier pack) gets
// exactly the previous answer: one candidate per pass, the last drawn one.
#pragma once
#include <stdint.h>

typedef struct {
  double x, y, width, height;        // drawn frame
  double hx, hy, hwidth, hheight;    // frame grown by its extended edges
  const uint8_t* alpha;              // normal sprite alpha, row-major, or NULL
  long alphaWidth, alphaHeight;
  int active;                        // has an input (a decorative item never answers)
} MLXSkinHitItem;

static inline int MLXSkinHitContains(double x, double y, double width, double height, double px, double py) {
  // CGRectContainsPoint: min <= p < max.
  return width > 0 && height > 0 && px >= x && px < x + width && py >= y && py < y + height;
}

static inline int MLXSkinHitOpaque(const MLXSkinHitItem* item, double px, double py) {
  if (item->alpha == 0 || item->alphaWidth <= 0 || item->alphaHeight <= 0) return 1;
  long u = (long)((px - item->x) / item->width * (double)item->alphaWidth);
  long v = (long)((py - item->y) / item->height * (double)item->alphaHeight);
  if (u < 0) u = 0;
  if (v < 0) v = 0;
  if (u >= item->alphaWidth) u = item->alphaWidth - 1;
  if (v >= item->alphaHeight) v = item->alphaHeight - 1;
  return item->alpha[v * item->alphaWidth + u] >= 128;
}

static inline long MLXSkinHitIndex(const MLXSkinHitItem* items, long count, double px, double py) {
  for (long i = count - 1; i >= 0; i--) {
    const MLXSkinHitItem* item = &items[i];
    if (item->active && MLXSkinHitContains(item->x, item->y, item->width, item->height, px, py) &&
        MLXSkinHitOpaque(item, px, py))
      return i;
  }
  for (int pass = 0; pass < 2; pass++) {
    long best = -1;
    double bestDistance = 0;
    for (long i = count - 1; i >= 0; i--) {
      const MLXSkinHitItem* item = &items[i];
      if (!item->active) continue;
      const int inside = pass == 0 ? MLXSkinHitContains(item->x, item->y, item->width, item->height, px, py)
                                   : MLXSkinHitContains(item->hx, item->hy, item->hwidth, item->hheight, px, py);
      if (!inside) continue;
      const double dx = px - (item->x + item->width / 2), dy = py - (item->y + item->height / 2);
      const double distance = dx * dx + dy * dy;
      if (best < 0 || distance < bestDistance) {
        best = i;
        bestDistance = distance;
      }
    }
    if (best >= 0) return best;
  }
  return -1;
}
