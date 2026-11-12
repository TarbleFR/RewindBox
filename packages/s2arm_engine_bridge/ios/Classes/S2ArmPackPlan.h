#pragma once
// What the engine will ask the host's prepare_code hook for at boot, read from the image pack this app wrote
// (native/s2arm/prepare rb_s2arm_image_pack: Mach-O wrapper, index in __TEXT,__swidx = "S2AEMB01", u32 count, u32 88,
// then per module name[24] + 4 x (u64 offset, u64 length) for the blocks x0, W, x1, x2). x0, x1 and x2 are code
// (patch 0004: s2a_imgpack_map's code branch, callers loader.c map_image x0/x1/x2); W is data and never reaches the hook.
// Boot modules are the ExeFS ones the code stage rewrites (main, subsdk<N>, sdk); any other entry is a converted NRO,
// mapped later through nn::ro. Plain C, no Apple header: the host test compiles it on any system.
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    unsigned modules;             // index entries
    unsigned boot_modules;        // main / subsdk<N> / sdk entries
    unsigned boot_code_blocks;    // non-empty code blocks of the boot modules
    uint64_t boot_code_bytes;     // their total length (every block is whole 16 KiB pages)
    unsigned later_code_blocks;   // non-empty code blocks of the other entries (NROs)
    uint64_t later_code_bytes;
    uint64_t largest_code_block;  // over all entries
} s2arm_pack_plan;

/// Reads the index of the image pack at path. 0 = ok; -1 = unreadable or malformed (error holds one line).
int s2arm_pack_plan_read(const char *path, s2arm_pack_plan *plan, char *error, size_t error_size);

/// 1 when name is a boot module: main, sdk, or subsdk followed by decimal digits only.
int s2arm_pack_plan_is_boot_module(const char *name);

/// 1 once the hook has served at least every boot code block (count and bytes); 0 otherwise, and always 0 for a plan
/// without boot code. The host then issues the helper's detach (docs/s2arm-engine-bridge.md, "When the helper detaches").
int s2arm_pack_plan_boot_served(const s2arm_pack_plan *plan, unsigned served_blocks, uint64_t served_bytes);

#ifdef __cplusplus
}
#endif
