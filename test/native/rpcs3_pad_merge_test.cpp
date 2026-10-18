// Build 484: touch controls and a physical controller feeding one PS3 pad.
#include "RPCS3PadMerge.h"

#include <cassert>
#include <cmath>

static rpcs3_ios_pad_state pad(uint64_t buttons, float lx, float ly, float rx, float ry, float l2, float r2) {
  rpcs3_ios_pad_state state = {};
  state.size = sizeof(state);
  state.connected = 1;
  state.buttons = buttons;
  state.left_x = lx;
  state.left_y = ly;
  state.right_x = rx;
  state.right_y = ry;
  state.l2 = l2;
  state.r2 = r2;
  return state;
}

int main() {
  const rpcs3_ios_pad_state touch = pad(rpcs3_ios_pad_cross | rpcs3_ios_pad_l2, -0.9f, 0.1f, 0.0f, 0.0f, 1.0f, 0.0f);
  const rpcs3_ios_pad_state physical = pad(rpcs3_ios_pad_up | rpcs3_ios_pad_r1, 0.2f, 0.2f, 0.4f, -0.3f, 0.0f, 0.6f);

  // Both sources: buttons combined, the stronger trigger, the stick pushed furthest.
  rpcs3_ios_pad_state merged = RPCS3MergePadStates(&touch, 1, &physical, 1);
  assert(merged.size == sizeof(merged) && merged.connected == 1);
  assert(merged.buttons == (rpcs3_ios_pad_cross | rpcs3_ios_pad_l2 | rpcs3_ios_pad_up | rpcs3_ios_pad_r1));
  assert(merged.l2 == 1.0f && std::fabs(merged.r2 - 0.6f) < 1e-6f);
  assert(merged.left_x == -0.9f && merged.left_y == 0.1f);
  assert(merged.right_x == 0.4f && merged.right_y == -0.3f);

  // Hidden touch controls (controller policy): exactly the physical pad.
  merged = RPCS3MergePadStates(&touch, 0, &physical, 1);
  assert(merged.buttons == physical.buttons && merged.l2 == 0.0f && std::fabs(merged.r2 - 0.6f) < 1e-6f);
  assert(merged.left_x == 0.2f && merged.right_y == -0.3f);

  // No controller: exactly the touch pad.
  merged = RPCS3MergePadStates(&touch, 1, &physical, 0);
  assert(merged.buttons == touch.buttons && merged.l2 == 1.0f && merged.r2 == 0.0f);
  assert(merged.left_x == -0.9f && merged.right_x == 0.0f);

  // Neither (editor open, or everything released): connected and neutral.
  merged = RPCS3MergePadStates(&touch, 0, &physical, 0);
  assert(merged.connected == 1 && merged.buttons == 0 && merged.l2 == 0.0f && merged.r2 == 0.0f);
  assert(merged.left_x == 0.0f && merged.left_y == 0.0f && merged.right_x == 0.0f && merged.right_y == 0.0f);

  // A released source never cancels a held one (no stuck or lost input).
  const rpcs3_ios_pad_state released = pad(0, 0, 0, 0, 0, 0, 0);
  merged = RPCS3MergePadStates(&released, 1, &physical, 1);
  assert(merged.buttons == physical.buttons && merged.right_x == 0.4f);
  merged = RPCS3MergePadStates(&touch, 1, &released, 1);
  assert(merged.buttons == touch.buttons && merged.left_x == -0.9f);
  return 0;
}
