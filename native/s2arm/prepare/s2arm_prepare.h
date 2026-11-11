// RewindBox: preparing a Switch 2 playlist game on the device, without a
// computer. This library replaces S2Arm's bash/Python packing stages one by
// one; each replaced stage is checked in CI against S2Arm at the pinned commit
// (tools/s2arm_prototype/pin.json). See docs/s2arm-study-2026-11-11.md, batch 4.
//
// Stages covered so far: the unpack step for Switch 2 export folders (s2arm_ns2_dump.h,
// with ZBIC normalisation, s2arm_zbic.h) and the code stage (S2Arm pack/stage_rewrite.sh: address-need
// table, NRO conversion and exports, module rewriting, main.npdm, GPU driver
// list). Not covered: its optional widescreen, frame-rate and patch tables, and
// the other stages (unpack from NSP/XCI, system data, RomFS index, package layout).
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
    RB_S2ARM_PREPARE_UNSUPPORTED = 6, // a form this library does not handle yet (NRO hidden in another file)
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

typedef struct {
    const char *exefs_dir;   // unpacked ExeFS of the game
    const char *romfs_dir;   // unpacked RomFS, or NULL: the NRO steps are then skipped
    const char *output_dir;  // existing, writable
    // Called before each step ("addr_need", "nro", a module name, "tables") with its index and the step count. May be NULL.
    void (*progress)(void *context, const char *step, int index, int count);
    int (*cancelled)(void *context); // polled between steps. May be NULL.
    void *context;
} rb_s2arm_code_request;

// The whole code stage of S2Arm's packer (pack/stage_rewrite.sh without its optional
// widescreen, frame-rate and community-patch tables), in its order: address-need table,
// NRO conversion, rewriting of the ExeFS modules and of the converted NROs, main.npdm,
// NRO exports table, GPU driver list. Outputs land in output_dir as the packer lays them
// out; the intermediate nroexe directory is removed at the end. An ExeFS holding ZBIC NSOs
// (flag 0x80, Switch 2) is first normalised as S2Arm's unpack step does (s2arm_zbic.h) into
// <output>/nsoexe, removed at the end; bad ZBIC data or unknown NSO flag bits fail with
// RB_S2ARM_PREPARE_INVALID. rb_s2arm_prepare_rewrite does not normalise.
int rb_s2arm_prepare_code(const rb_s2arm_code_request *request, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
