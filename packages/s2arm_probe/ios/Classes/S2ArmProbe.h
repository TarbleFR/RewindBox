// RewindBox diagnostic: can S2Arm-rewritten code run from JIT memory?
// See docs/s2arm-prototype-2026-11-10.md. Not part of any player path.
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// JIT helper command 1 (brk #0xf00d, x16 = 1): x0 = address (0 = let the helper
// allocate), x1 = length. Returns x0 after the helper handled it, 0 on failure.
typedef uint64_t (*rb_s2arm_prepare_fn)(uint64_t address, uint64_t length);
// Synchronous journal line. It must be durable when the call returns: the step
// that follows may end the process.
typedef void (*rb_s2arm_log_fn)(const char *step, const char *status, const char *detail);

enum {
    RB_S2ARM_PROBE_SELF_MAPPED = 1u << 0, // also try process-mapped RX memory; may end the process
};
enum { // result bits of rb_s2arm_probe_attached
    RB_S2ARM_MODE_FIXED = 1 << 0, // code runs at a chosen address inside the window
    RB_S2ARM_MODE_ARENA = 1 << 1, // code and data share one helper-allocated region
};

// Phase 1: while the JIT helper is attached, before any detach. Never executes a brk.
// Returns the modes available for phase 2 (0 = none), or -1 if it could not start.
int rb_s2arm_probe_attached(rb_s2arm_prepare_fn prepare, rb_s2arm_log_fn log, uint32_t flags);
// Phase 2: after the helper has detached. Loads and runs the rewritten synthetic
// module, then releases the window. Call it whenever phase 1 returned >= 0.
// Returns 0 if every check passed, 1 otherwise, -1 if phase 1 gave no mode.
int rb_s2arm_probe_detached(rb_s2arm_log_fn log);

#ifdef __cplusplus
}
#endif
