// Behaviour of LibretroInputLatch: touch presses shorter than a core read,
// quick repeated taps, held presses, D-pad slides and the touch-screen
// pointer, frame by frame as the core sees them. Plain C (also compiled
// with `clang -x c` outside macOS).
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "LibretroInputLatch.h"

static int failures = 0;

#define CHECK(condition, message)                                \
  do {                                                           \
    if (condition) {                                             \
      printf("PASS %s\n", message);                              \
    } else {                                                     \
      printf("FAIL %s (%s:%d)\n", message, __FILE__, __LINE__); \
      failures++;                                                \
    }                                                            \
  } while (0)

// RetroPad ids (libretro.h).
enum { PAD_B = 0, PAD_Y = 1, PAD_SELECT = 2, PAD_START = 3, PAD_UP = 4, PAD_DOWN = 5, PAD_LEFT = 6, PAD_RIGHT = 7,
       PAD_A = 8, PAD_X = 9, PAD_L = 10, PAD_R = 11 };
#define BIT(id) ((uint16_t)(1u << (id)))

static LibretroInputLatch Fresh(void) {
  LibretroInputLatch latch;
  LibretroInputLatchReset(&latch);
  return latch;
}

/// Bits of `mask` the core sees in each of `count` frames starting at
/// `first`, as a string of 0 / 1 (one read per frame).
static void Frames(LibretroInputLatch *latch, uint64_t first, int count, uint16_t mask, char *out) {
  for (int index = 0; index < count; index++) {
    out[index] = (LibretroInputLatchButtons(latch, first + (uint64_t)index) & mask) != 0 ? '1' : '0';
  }
  out[count] = '\0';
}

static void PointerFrames(LibretroInputLatch *latch, uint64_t first, int count, char *out) {
  for (int index = 0; index < count; index++) {
    out[index] = LibretroInputLatchPointer(latch, first + (uint64_t)index) ? '1' : '0';
  }
  out[count] = '\0';
}

int main(void) {
  char seen[32];

  // A tap that begins and ends between two reads (the button lit on
  // screen, the core never read it before this fix).
  LibretroInputLatch latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_A));
  LibretroInputLatchSetButtons(&latch, 0);
  Frames(&latch, 1, 5, BIT(PAD_A), seen);
  CHECK(strcmp(seen, "11100") == 0, "a tap shorter than one read reaches the core for 3 frames");
  if (strcmp(seen, "11100") != 0) printf("  seen %s\n", seen);

  // Several reads in one frame (mupen64plus reads per controller access).
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_B));
  LibretroInputLatchSetButtons(&latch, 0);
  bool sameFrame = (LibretroInputLatchButtons(&latch, 10) & BIT(PAD_B)) &&
                   (LibretroInputLatchButtons(&latch, 10) & BIT(PAD_B)) &&
                   (LibretroInputLatchButtons(&latch, 10) & BIT(PAD_B));
  Frames(&latch, 11, 3, BIT(PAD_B), seen);
  CHECK(sameFrame && strcmp(seen, "110") == 0, "the hold counts frames, not reads");

  // A held press passes through, and its release is immediate once the
  // minimum is over.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_A));
  Frames(&latch, 1, 6, BIT(PAD_A), seen);
  CHECK(strcmp(seen, "111111") == 0, "a held press stays pressed");
  LibretroInputLatchSetButtons(&latch, 0);
  Frames(&latch, 7, 2, BIT(PAD_A), seen);
  CHECK(strcmp(seen, "00") == 0, "a long press is released on the next frame");

  // A press shorter than the minimum but seen by the core is extended.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_START));
  Frames(&latch, 1, 1, BIT(PAD_START), seen);
  LibretroInputLatchSetButtons(&latch, 0);
  Frames(&latch, 2, 4, BIT(PAD_START), seen);
  CHECK(strcmp(seen, "1100") == 0, "a one-frame press lasts 3 frames in total");

  // Two quick taps during the hold of the first one: the core sees two
  // presses with a release between them.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_A));
  LibretroInputLatchSetButtons(&latch, 0);
  Frames(&latch, 1, 1, BIT(PAD_A), seen);
  LibretroInputLatchSetButtons(&latch, BIT(PAD_A));
  LibretroInputLatchSetButtons(&latch, 0);
  Frames(&latch, 2, 6, BIT(PAD_A), seen);
  CHECK(strcmp(seen, "011100") == 0, "a second quick tap is shown as a new press after a release");
  if (strcmp(seen, "011100") != 0) printf("  seen %s\n", seen);

  // Released and pressed again between two reads while held: the core
  // sees the release, then the new press.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_B));
  Frames(&latch, 1, 4, BIT(PAD_B), seen);
  LibretroInputLatchSetButtons(&latch, 0);
  LibretroInputLatchSetButtons(&latch, BIT(PAD_B));
  Frames(&latch, 5, 3, BIT(PAD_B), seen);
  CHECK(strcmp(seen, "011") == 0, "a re-press between two reads shows one released frame");

  // Multitouch: two buttons pressed together, released independently.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_A) | BIT(PAD_B));
  uint16_t both = LibretroInputLatchButtons(&latch, 1);
  LibretroInputLatchSetButtons(&latch, BIT(PAD_B));
  for (uint64_t frame = 2; frame <= 4; frame++) LibretroInputLatchButtons(&latch, frame);
  uint16_t after = LibretroInputLatchButtons(&latch, 5);
  CHECK(both == (BIT(PAD_A) | BIT(PAD_B)) && after == BIT(PAD_B), "A+B together, then B alone");

  // D-pad: a finger sliding from up to down never shows up and down
  // together, even while up is still latched.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_UP));
  LibretroInputLatchButtons(&latch, 1);
  LibretroInputLatchSetButtons(&latch, BIT(PAD_DOWN));
  uint16_t slid = LibretroInputLatchButtons(&latch, 2);
  CHECK(slid == BIT(PAD_DOWN), "sliding to the opposite direction drops the latched one");
  LibretroInputLatchSetButtons(&latch, BIT(PAD_DOWN) | BIT(PAD_RIGHT));
  uint16_t diagonal = LibretroInputLatchButtons(&latch, 3);
  CHECK(diagonal == (BIT(PAD_DOWN) | BIT(PAD_RIGHT)), "a diagonal shows both directions");

  // A quick D-pad tap is shown for 2 frames.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_LEFT));
  LibretroInputLatchSetButtons(&latch, 0);
  Frames(&latch, 1, 4, BIT(PAD_LEFT), seen);
  CHECK(strcmp(seen, "1100") == 0, "a quick direction tap reaches the core for 2 frames");

  // Frames without any read still count.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_X));
  LibretroInputLatchSetButtons(&latch, 0);
  bool first = (LibretroInputLatchButtons(&latch, 1) & BIT(PAD_X)) != 0;
  bool later = (LibretroInputLatchButtons(&latch, 9) & BIT(PAD_X)) != 0;
  CHECK(first && !later, "the hold expires with emulated frames even without reads");

  // A frame counter that goes back (new host) counts as one frame.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_R));
  LibretroInputLatchSetButtons(&latch, 0);
  LibretroInputLatchButtons(&latch, 100);
  bool back = (LibretroInputLatchButtons(&latch, 1) & BIT(PAD_R)) != 0;
  CHECK(back, "a frame counter going back keeps the remaining hold");

  // Reset forgets presses the core has not seen yet (menu opened).
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_L));
  LibretroInputLatchSetButtons(&latch, 0);
  LibretroInputLatchReset(&latch);
  CHECK(LibretroInputLatchButtons(&latch, 1) == 0, "reset drops pending presses");

  // Touch-screen pointer: a stylus tap between two reads.
  latch = Fresh();
  LibretroInputLatchSetPointer(&latch, true);
  LibretroInputLatchSetPointer(&latch, false);
  PointerFrames(&latch, 1, 5, seen);
  CHECK(strcmp(seen, "11100") == 0, "a quick touch-screen tap reaches the core for 3 frames");
  latch = Fresh();
  LibretroInputLatchSetPointer(&latch, true);
  PointerFrames(&latch, 1, 5, seen);
  LibretroInputLatchSetPointer(&latch, false);
  bool released = !LibretroInputLatchPointer(&latch, 6);
  CHECK(strcmp(seen, "11111") == 0 && released, "a held stylus stays pressed and releases at once after");

  // Buttons and pointer read in the same frame share the frame count.
  latch = Fresh();
  LibretroInputLatchSetButtons(&latch, BIT(PAD_Y));
  LibretroInputLatchSetButtons(&latch, 0);
  LibretroInputLatchSetPointer(&latch, true);
  LibretroInputLatchSetPointer(&latch, false);
  int frames = 0;
  for (uint64_t frame = 1; frame <= 6; frame++) {
    bool button = (LibretroInputLatchButtons(&latch, frame) & BIT(PAD_Y)) != 0;
    bool pointer = LibretroInputLatchPointer(&latch, frame);
    if (button && pointer) frames++;
  }
  CHECK(frames == 3, "buttons and pointer latch over the same frames");

  if (failures > 0) {
    printf("%d input latch check(s) failed\n", failures);
    return 1;
  }
  printf("All input latch checks passed\n");
  return 0;
}
