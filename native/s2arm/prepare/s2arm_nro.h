// RewindBox: port of two S2Arm stages that read the NROs of a RomFS (pinned commit in
// tools/s2arm_prototype/pin.json): tools/nro_exports.py (the exports table nro_exports.tsv) and
// runtime/rewriter/nro_to_nso.py (NRO -> NSO conversion and nro_modules.tsv). CI compares the output files byte for
// byte with the originals on synthetic input (tools/s2arm_prototype/run_modules_test.py).
#pragma once
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_NRO_OK = 0,
    RB_S2ARM_NRO_INVALID = 1,      // a bad NRO or NRR (the original reports 【红】 and exits 1), or a file above 1 GiB
    RB_S2ARM_NRO_IO = 2,           // a file or directory could not be read or written, or out of memory
    // The NRR files under romfs/.nrr register NRO hashes that no *.nro file of the RomFS has. The original then
    // scans every other RomFS file for NROs stored raw or inside zstd frames; that scan needs zstd and is not
    // implemented. Nothing is guessed: the call stops after the *.nro files were converted, and the outputs
    // of this call are not to be used.
    RB_S2ARM_NRO_UNSUPPORTED = 3,
};

// Writes <output_path> (missing parent directories are created): the header line, then one "symbol<TAB>file" row
// per exported symbol of every *.nro file (any depth, extension case-insensitive, sorted by RomFS-relative path,
// '/' separated). Without a RomFS directory or without any *.nro nothing is written and RB_S2ARM_NRO_OK is
// returned, as the original. Symbol names are decoded as UTF-8 with replacement, as the original does.
int rb_s2arm_nro_exports(const char *romfs_dir, const char *output_path, char *error, size_t error_size);
// The same, calling seen (may be NULL) with the count of RomFS entries walked so far, for a progress display.
int rb_s2arm_nro_exports_ex(const char *romfs_dir, const char *output_path, void (*seen)(void *context, unsigned long long entries),
                            void *context, char *error, size_t error_size);

// Converts every *.nro file of <romfs_dir> to an NSO named nro0, nro1, ... in <output_dir> (same content is stored
// once, in sorted RomFS-relative path order) and writes <output_dir>/nro_modules.tsv. Without any module nothing is
// written and RB_S2ARM_NRO_OK is returned. Returns RB_S2ARM_NRO_UNSUPPORTED in the situation described above.
int rb_s2arm_nro_to_nso(const char *romfs_dir, const char *output_dir, char *error, size_t error_size);
// The same, calling seen (may be NULL) with the count of RomFS entries walked so far, for a progress display.
int rb_s2arm_nro_to_nso_ex(const char *romfs_dir, const char *output_dir, void (*seen)(void *context, unsigned long long entries),
                           void *context, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
