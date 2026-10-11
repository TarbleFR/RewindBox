#ifndef LIBRETRO_INPUT_LATCH_H
#define LIBRETRO_INPUT_LATCH_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/// Frames a touch press stays visible to the core at least (face buttons,
/// shoulders, start / select...).
#define LIBRETRO_LATCH_PRESS_FRAMES 3
/// Same for the four D-pad directions: shorter, so a finger sliding on a
/// D-pad never drags a direction it already left for long.
#define LIBRETRO_LATCH_DIRECTION_PRESS_FRAMES 2
/// Frames a release stays visible before the next press of the same input
/// is shown (two quick taps must reach the core as two presses).
#define LIBRETRO_LATCH_RELEASE_FRAMES 1

/// Touch input reaches the core only when the core reads it (input poll or
/// input state, once or a few times per emulated frame). A press that
/// begins and ends between two reads, such as a quick tap or a touch the
/// system delivers late together with its release (screen edges), would
/// light the button on screen and never reach the game; a game that reads
/// its pad every second frame would also miss a press shown for one frame.
///
/// The latch keeps every press edge until the core has seen it, for at
/// least LIBRETRO_LATCH_PRESS_FRAMES emulated frames (directions:
/// LIBRETRO_LATCH_DIRECTION_PRESS_FRAMES), and shows a release for
/// LIBRETRO_LATCH_RELEASE_FRAMES before a new press of an input the core
/// still sees pressed. A press held longer is passed through unchanged, and
/// a latched direction never shows together with its live opposite. The
/// RETRO_DEVICE_POINTER press (DS / 3DS touch screen) is latched the same
/// way. Frames are counted by the frontend (one per retro_run), never by
/// reads: some cores read the pad several times per frame.
///
/// Not thread safe: the caller serialises SetButtons / SetPointer (UI
/// thread) and Buttons / Pointer (emulation thread) under its own lock.
typedef struct {
  uint16_t live;
  uint16_t pending;
  uint16_t exposed;
  uint8_t hold[16];
  uint8_t gap[16];
  bool pointerLive;
  bool pointerPending;
  bool pointerExposed;
  uint8_t pointerHold;
  uint8_t pointerGap;
  uint64_t frame;
  bool started;
} LibretroInputLatch;

/// Releases everything and forgets pending presses (menu opened, controls
/// disabled, session reset).
void LibretroInputLatchReset(LibretroInputLatch *latch);

/// New live state of the touch buttons (RetroPad bits). Every bit that
/// rises becomes a press the core will see.
void LibretroInputLatchSetButtons(LibretroInputLatch *latch, uint16_t buttons);

/// New live state of the touch-screen pointer press.
void LibretroInputLatchSetPointer(LibretroInputLatch *latch, bool pressed);

/// Buttons the core sees during `frame` (monotonic frame counter of the
/// frontend). Several reads in the same frame give the same latched presses
/// plus any press that arrived since the previous read.
uint16_t LibretroInputLatchButtons(LibretroInputLatch *latch, uint64_t frame);

/// Pointer press the core sees during `frame`.
bool LibretroInputLatchPointer(LibretroInputLatch *latch, uint64_t frame);

#ifdef __cplusplus
}
#endif

#endif
