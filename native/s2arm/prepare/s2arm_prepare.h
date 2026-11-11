// RewindBox: preparing a Switch 2 playlist game on the device, without a
// computer. This library replaces S2Arm's bash/Python packing stages one by
// one; each replaced stage is checked in CI against S2Arm at the pinned commit
// (tools/s2arm_prototype/pin.json). See docs/s2arm-study-2026-11-11.md, batch 4.
//
// Stage covered so far: rewrite (S2Arm pack/stage_rewrite.sh, the module loop
// and main.npdm). Not yet covered: address-need table, NRO conversion and
// exports, GPU driver list, widescreen and frame-rate tables.
#pragma once
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_PREPARE_OK = 0,
    RB_S2ARM_PREPARE_INVALID = 1,   // bad request, missing exefs/main or main.npdm, not an NSO
    RB_S2ARM_PREPARE_IO = 2,        // a file could not be read or written
    RB_S2ARM_PREPARE_GAPS = 3,      // the rewriter found code it cannot rewrite; the game is not supported
    RB_S2ARM_PREPARE_REWRITER = 4,  // the rewriter failed for another reason
    RB_S2ARM_PREPARE_CANCELLED = 5,
};

typedef struct {
    const char *exefs_dir;   // unpacked ExeFS of the game
    const char *output_dir;  // existing, writable; receives <module>.patched.bin and tables, main.npdm
    // Called before each module with its name, 0-based index and the module count. May be NULL.
    void (*progress)(void *context, const char *module, int index, int count);
    // Polled between modules; non-zero stops with RB_S2ARM_PREPARE_CANCELLED. May be NULL.
    int (*cancelled)(void *context);
    void *context;
} rb_s2arm_rewrite_request;

// Rewrites every code module the runtime loads (main, subsdk0-9, sdk; nothing
// else in ExeFS is a module) with S2Arm's rewriter in its packing defaults
// (Apple target, spin gate on), one module at a time, and copies main.npdm.
// Each module's rewriter log goes to <output_dir>/<module>.rewrite.log.
// On failure `error` (may be NULL) receives one line and the outputs of the
// failing module are not to be used.
int rb_s2arm_prepare_rewrite(const rb_s2arm_rewrite_request *request, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
