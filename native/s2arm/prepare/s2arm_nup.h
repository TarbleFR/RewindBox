// RewindBox: port of S2Arm pack/ns2_nup.py (Apache-2.0, pinned commit in tools/s2arm_prototype/pin.json;
// its container reading comes from the reference port's scripts/pack_nup.py, MIT, and follows the public
// NUP specification v1, https://github.com/a55uka/nup SPEC.md): a Switch 2 NUP container (.nup: base,
// updates and DLC in one file, not encrypted, no keys needed) becomes the export folder layout that the
// Switch 2 library imports and rb_s2arm_ns2_dump reads:
//
//   <out>/base/exefs|romfs/...                                 the base (see below without one)
//   <out>/updates/<version>/exefs|romfs/...                    the newest update only
//   <out>/updates/<version>/control.nacp, icon_AmericanEnglish.dat   when its package carries control data
//   <out>/dlc/<title id>/0/romfs/...                           each DLC
//
// A container without a base (an update marked standalone_update, or a base record with no file) gets the
// newest update written as base/ too, as the original does. Files are stored as they are or as one zstd
// frame (zstd 1.5.7's decoder, s2arm_zstd.c); each one is checked against its size and SHA-256 while it is
// written. The result is built in <out>.tmp and renamed at the end; <out>/.ns2_nup_key holds the SHA-256
// of the table of contents' SHA-256 and a version tag of this port, so an unchanged container is reused.
//
// CI compares the trees with the original, byte for byte, on synthetic containers
// (tools/s2arm_prototype/run_nup_test.py). Deliberate differences: the content of .ns2_nup_key (the
// original hashes its own script); <out>.tmp is removed on failure; the copy of the update as base/ is a
// clonefile(2) on Apple systems (the original clones file by file on macOS) and a byte copy elsewhere;
// a progress callback and a cancel poll; error lines in English.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_NUP_OK = 0,
    RB_S2ARM_NUP_INVALID = 1,    // not a NUP, or a container the original refuses (bad header, table, record, name, size or SHA-256)
    RB_S2ARM_NUP_IO = 2,         // a file could not be read or written, or out of memory
    RB_S2ARM_NUP_CANCELLED = 5,
};

typedef struct {
    uint64_t program_id;      // from the NPDM of the base / updates (ACI0)
    uint64_t bytes;           // bytes of the files the expansion writes (base, newest update, DLC; not the copy as base/)
    uint32_t update_version;  // the newest update's version, 0 = none
    uint32_t dlc_count;
    int has_base;             // 0: the newest update is the whole game (written as base/ too)
} rb_s2arm_nup_info;

typedef struct {
    const char *nup_path;    // the .nup file, or a folder holding exactly one (ns2_nup.py find_nup)
    const char *output_dir;  // the export folder to make; replaced; <output_dir>.tmp while working
    void (*note)(void *context, const char *line);                    // information lines (may be NULL)
    int (*cancelled)(void *context);                                  // polled between chunks (may be NULL)
    void (*progress)(void *context, uint64_t done, uint64_t total);  // bytes written so far of info.bytes (may be NULL)
    void *context;
} rb_s2arm_nup_request;

// ns2_nup.py --detect: path itself when it is a NUP (by its first bytes, whatever its extension), or the only
// .nup file of the folder path. Writes it into nup (NUL-terminated) and returns 0; 1 when there is none.
int rb_s2arm_nup_detect(const char *path, char *nup, size_t nup_size);

// The container's content as ns2_nup.py scan() checks it, without writing anything.
int rb_s2arm_nup_inspect(const char *nup_path, rb_s2arm_nup_info *info, char *error, size_t error_size);

// ns2_nup.py <x.nup> <out>. info (may be NULL) is filled once the container is read. error (may be NULL)
// receives one line on failure. Not thread-safe with respect to the same output_dir.
int rb_s2arm_nup_expand(const rb_s2arm_nup_request *request, rb_s2arm_nup_info *info, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
