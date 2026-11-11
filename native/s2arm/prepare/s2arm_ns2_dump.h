// RewindBox: port of S2Arm pack/ns2_dump.py (Apache-2.0, pinned commit in
// tools/s2arm_prototype/pin.json): a Switch 2 game exported from the console as a loose
// folder becomes the unpack directory the rest of the packer reads:
//
//   <export>/base/exefs/{main,main.npdm,rtld,sdk,subsdk*}   base program
//   <export>/base/romfs/...
//   <export>/updates/<version>/exefs|romfs/...               updates (the newest one is used)
//   <export>/dlc/<title id>/<n>/romfs/...  or  dlc/<title id>/romfs/...   add-on content
//
// gives <out>/exefs/ (from the newest update with a main, else the base; ZBIC NSOs
// normalised in process, see s2arm_zbic.h), <out>/romfs/ (the update alone when it is a
// full image, i.e. holds a file byte-identical to the base, else base overlaid with the
// update), <out>/aoc/<index>/ + aoc.tsv (index = DLC title id - program id - 0x1000),
// <out>/ctl/control.nacp (the exported one when present, else synthesised exactly as the
// original, with README.synth), <out>/icon.jpg when exported, and <out>/unpack.tsv.
// The program id comes from base/exefs/main.npdm (ACI0). The result is built in
// <out>.tmp and renamed at the end; <out>/.ns2_dump_key lets an unchanged export be reused.
//
// CI compares the trees with the original, byte for byte, on synthetic export folders
// (tools/s2arm_prototype/run_ns2_dump_test.py). Deliberate differences (all documented in
// docs/s2arm-study-2026-11-11.md, "ZBIC and export folder"): the content of
// .ns2_dump_key (the original hashes its own script and the nx_unpack binary; this port
// hashes a version tag of its own); <out>.tmp is removed on failure; case-insensitive
// path collisions are detected with ASCII case folding (Python lower() also folds
// non-ASCII letters); version and DLC folder names are ASCII only; a module above
// max_module_bytes (default 1 GiB) is refused.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_NS2_OK = 0,
    RB_S2ARM_NS2_INVALID = 1,    // not an export folder, malformed NPDM/NSO, unknown NSO flags, ZBIC that does not decode,
                                 // no romfs, path case collision (every place the original stops with a red line or an exception)
    RB_S2ARM_NS2_IO = 2,         // a file could not be read, copied or written, or out of memory
    RB_S2ARM_NS2_CANCELLED = 5,
};

typedef struct {
    const char *export_dir;  // the export folder, or a folder holding one directly inside (as --detect accepts)
    const char *output_dir;  // unpack directory; replaced; <output_dir>.tmp is used while working
    const char *name;        // title used when the export has no control.nacp (--name); NULL or "" = folder name
    // 0: copy the RomFS and DLC files into output_dir (the original's tree; CI compares it).
    // 1: do not copy them; list them instead in output_dir/data_sources.tsv
    //    ("area<TAB>relative path<TAB>source path", area = romfs or aoc/<index>) so that the
    //    device can read the exported files in place. exefs, ctl and the tables are written as usual.
    int reference_data;
    void (*note)(void *context, const char *line);  // progress / information lines (may be NULL)
    int (*cancelled)(void *context);                // polled between files and ZBIC blocks (may be NULL)
    void *context;
    // Cap on one module in memory: a ZBIC module's normalised size (and its file) and a module's
    // decoded image in the save-kind scan; 0 = 1 GiB. Checked before anything is decoded.
    // Deliberate difference: the originals try anything up to ~2 GiB.
    size_t max_module_bytes;
} rb_s2arm_ns2_dump_request;

// ns2_dump.py --detect: root itself or one of its subfolders (in name order) holding
// base/exefs/main.npdm. On success writes that folder into dump (NUL-terminated) and the
// program id; RB_S2ARM_NS2_INVALID when there is none or its NPDM is malformed.
int rb_s2arm_ns2_detect(const char *root, char *dump, size_t dump_size, uint64_t *program_id, char *error, size_t error_size);

// ns2_dump.py <export> <out> [--name N]. `error` (may be NULL) receives one line on failure.
// Not thread-safe with respect to the same output_dir; no global mutable state otherwise.
int rb_s2arm_ns2_dump(const rb_s2arm_ns2_dump_request *request, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
