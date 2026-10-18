// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <math.h>
#include "Rpcs3CoreABI.h"

// Build 484: one PS3 pad fed by the touch controls and a physical controller
// at the same time (when "hide touch controls with a controller" is off).
// Buttons are combined, each trigger keeps its stronger pull and each stick
// the input pushed further from the centre. An inactive source counts as
// released; the result is always a connected pad.
static inline rpcs3_ios_pad_state RPCS3MergePadStates(const rpcs3_ios_pad_state* touch, int touchActive,
                                                      const rpcs3_ios_pad_state* physical, int physicalActive) {
  rpcs3_ios_pad_state merged = {};
  merged.size = sizeof(merged);
  merged.connected = 1;
  const rpcs3_ios_pad_state* sources[2] = {touchActive ? touch : 0, physicalActive ? physical : 0};
  float leftMagnitude = 0.0f;
  float rightMagnitude = 0.0f;
  for (int index = 0; index < 2; ++index) {
    const rpcs3_ios_pad_state* source = sources[index];
    if (!source) continue;
    merged.buttons |= source->buttons;
    merged.l2 = fmaxf(merged.l2, source->l2);
    merged.r2 = fmaxf(merged.r2, source->r2);
    const float left = hypotf(source->left_x, source->left_y);
    if (left > leftMagnitude) {
      leftMagnitude = left;
      merged.left_x = source->left_x;
      merged.left_y = source->left_y;
    }
    const float right = hypotf(source->right_x, source->right_y);
    if (right > rightMagnitude) {
      rightMagnitude = right;
      merged.right_x = source->right_x;
      merged.right_y = source->right_y;
    }
  }
  return merged;
}
