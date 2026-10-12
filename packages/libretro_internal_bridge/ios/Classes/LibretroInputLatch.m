// Plain C (no Objective-C): also compiled as C by the portable tests.
#include "LibretroInputLatch.h"

#include <stddef.h>
#include <string.h>

// RetroPad ids (libretro.h): RETRO_DEVICE_ID_JOYPAD_UP 4, DOWN 5, LEFT 6, RIGHT 7.
#define LATCH_UP 4u
#define LATCH_DOWN 5u
#define LATCH_LEFT 6u
#define LATCH_RIGHT 7u
#define LATCH_BIT(index) ((uint16_t)(1u << (index)))
#define LATCH_DIRECTIONS \
  ((uint16_t)(LATCH_BIT(LATCH_UP) | LATCH_BIT(LATCH_DOWN) | LATCH_BIT(LATCH_LEFT) | LATCH_BIT(LATCH_RIGHT)))

void LibretroInputLatchReset(LibretroInputLatch *latch) {
  if (latch == NULL) return;
  memset(latch, 0, sizeof(*latch));
}

void LibretroInputLatchSetButtons(LibretroInputLatch *latch, uint16_t buttons) {
  if (latch == NULL) return;
  uint16_t rising = (uint16_t)(buttons & ~latch->live);
  // A finger that slid onto a direction drops the opposite one it left
  // before the core read it: one slide never shows both ends of an axis.
  if ((rising & LATCH_BIT(LATCH_UP)) != 0) latch->pending &= (uint16_t)~LATCH_BIT(LATCH_DOWN);
  if ((rising & LATCH_BIT(LATCH_DOWN)) != 0) latch->pending &= (uint16_t)~LATCH_BIT(LATCH_UP);
  if ((rising & LATCH_BIT(LATCH_LEFT)) != 0) latch->pending &= (uint16_t)~LATCH_BIT(LATCH_RIGHT);
  if ((rising & LATCH_BIT(LATCH_RIGHT)) != 0) latch->pending &= (uint16_t)~LATCH_BIT(LATCH_LEFT);
  latch->pending |= rising;
  latch->live = buttons;
}

void LibretroInputLatchSetPointer(LibretroInputLatch *latch, bool pressed) {
  if (latch == NULL) return;
  if (pressed && !latch->pointerLive) latch->pointerPending = true;
  latch->pointerLive = pressed;
}

void LibretroInputLatchSetAnalog(LibretroInputLatch *latch, const int16_t analog[2][2]) {
  if (latch == NULL || analog == NULL) return;
  for (unsigned index = 0; index < 4; index++) {
    int16_t value = analog[index / 2][index % 2];
    // A press keeps the newest value of its finger until the core reads
    // it; released before that read, it keeps its last value.
    if (value != 0 && (latch->axisLive[index] == 0 || latch->axisPending[index])) {
      latch->axisPending[index] = true;
      latch->axisPendingValue[index] = value;
    }
    latch->axisLive[index] = value;
  }
}

static uint8_t LatchCountdown(uint8_t value, uint64_t elapsed) {
  return elapsed >= value ? 0 : (uint8_t)(value - elapsed);
}

/// Counts down holds and gaps by the frames elapsed since the last read. A
/// frame number that goes back (new frame counter) counts as one frame.
static void LatchAdvance(LibretroInputLatch *latch, uint64_t frame) {
  uint64_t elapsed = 0;
  if (latch->started && frame != latch->frame) elapsed = frame > latch->frame ? frame - latch->frame : 1;
  latch->started = true;
  latch->frame = frame;
  if (elapsed == 0) return;
  for (unsigned bit = 0; bit < 16; bit++) {
    latch->hold[bit] = LatchCountdown(latch->hold[bit], elapsed);
    latch->gap[bit] = LatchCountdown(latch->gap[bit], elapsed);
  }
  latch->pointerHold = LatchCountdown(latch->pointerHold, elapsed);
  latch->pointerGap = LatchCountdown(latch->pointerGap, elapsed);
  for (unsigned index = 0; index < 4; index++) {
    latch->axisHold[index] = LatchCountdown(latch->axisHold[index], elapsed);
    latch->axisGap[index] = LatchCountdown(latch->axisGap[index], elapsed);
  }
}

/// One input: a pending press is shown once the core has seen a release
/// (when it still sees the previous press), then for `pressFrames` frames
/// at least; otherwise the live state, extended by the remaining hold.
static bool LatchDecide(bool live, bool *pending, bool exposed, uint8_t *hold, uint8_t *gap, uint8_t pressFrames) {
  if (*pending) {
    if (exposed) {
      if (*gap == 0) *gap = LIBRETRO_LATCH_RELEASE_FRAMES;
      *hold = 0;
      return false;
    }
    if (*gap > 0) return false;
    *pending = false;
    *hold = pressFrames;
    return true;
  }
  return live || *hold > 0;
}

/// When both directions of an axis would show, the one a finger drives now
/// (live, or a press shown for the first time) wins over the one only kept
/// by the latch.
static uint16_t LatchSeparate(LibretroInputLatch *latch, uint16_t shown, uint16_t driven, unsigned first,
                              unsigned second) {
  uint16_t a = LATCH_BIT(first), b = LATCH_BIT(second);
  if ((shown & a) == 0 || (shown & b) == 0) return shown;
  bool aDriven = (driven & a) != 0, bDriven = (driven & b) != 0;
  if (aDriven && !bDriven) {
    latch->hold[second] = 0;
    return (uint16_t)(shown & ~b);
  }
  if (bDriven && !aDriven) {
    latch->hold[first] = 0;
    return (uint16_t)(shown & ~a);
  }
  return shown;
}

uint16_t LibretroInputLatchButtons(LibretroInputLatch *latch, uint64_t frame) {
  if (latch == NULL) return 0;
  LatchAdvance(latch, frame);
  uint16_t shown = 0;
  uint16_t driven = 0;
  for (unsigned bit = 0; bit < 16; bit++) {
    uint16_t mask = LATCH_BIT(bit);
    bool pending = (latch->pending & mask) != 0;
    bool live = (latch->live & mask) != 0;
    uint8_t pressFrames =
        (LATCH_DIRECTIONS & mask) != 0 ? LIBRETRO_LATCH_DIRECTION_PRESS_FRAMES : LIBRETRO_LATCH_PRESS_FRAMES;
    bool wasPending = pending;
    bool on = LatchDecide(live, &pending, (latch->exposed & mask) != 0, &latch->hold[bit], &latch->gap[bit],
                          pressFrames);
    if (pending) {
      latch->pending |= mask;
    } else {
      latch->pending &= (uint16_t)~mask;
    }
    if (!on) continue;
    shown |= mask;
    if (live || (wasPending && !pending)) driven |= mask;
  }
  shown = LatchSeparate(latch, shown, driven, LATCH_UP, LATCH_DOWN);
  shown = LatchSeparate(latch, shown, driven, LATCH_LEFT, LATCH_RIGHT);
  latch->exposed = shown;
  return shown;
}

bool LibretroInputLatchPointer(LibretroInputLatch *latch, uint64_t frame) {
  if (latch == NULL) return false;
  LatchAdvance(latch, frame);
  bool pending = latch->pointerPending;
  bool on = LatchDecide(latch->pointerLive, &pending, latch->pointerExposed, &latch->pointerHold, &latch->pointerGap,
                        LIBRETRO_LATCH_PRESS_FRAMES);
  latch->pointerPending = pending;
  latch->pointerExposed = on;
  return on;
}

void LibretroInputLatchAnalog(LibretroInputLatch *latch, uint64_t frame, int16_t analog[2][2]) {
  if (analog == NULL) return;
  memset(analog, 0, sizeof(int16_t) * 4);
  if (latch == NULL) return;
  LatchAdvance(latch, frame);
  for (unsigned index = 0; index < 4; index++) {
    bool pending = latch->axisPending[index];
    int16_t live = latch->axisLive[index];
    bool on = LatchDecide(live != 0, &pending, latch->axisExposed[index] != 0, &latch->axisHold[index],
                          &latch->axisGap[index], LIBRETRO_LATCH_PRESS_FRAMES);
    // The press just shown keeps its value for the hold; the live value
    // wins while a finger deflects the axis.
    if (latch->axisPending[index] && !pending) latch->axisHeld[index] = latch->axisPendingValue[index];
    latch->axisPending[index] = pending;
    int16_t shown = !on ? 0 : live != 0 ? live : latch->axisHeld[index];
    latch->axisExposed[index] = shown;
    analog[index / 2][index % 2] = shown;
  }
}
