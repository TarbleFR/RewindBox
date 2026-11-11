// RewindBox: port of S2Arm tools/addr_need.py (pinned commit in
// tools/s2arm_prototype/pin.json). Writes the identity-bound memory table
// addr_need.tsv from the program's code alone. CI compares the output byte for
// byte with the original on synthetic NSO/NPDM input
// (tools/s2arm_prototype/run_addr_need_test.py).
#pragma once
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_ADDR_OK = 0,
    RB_S2ARM_ADDR_INVALID = 1,      // malformed NSO / NPDM, or out-of-range read the original rejects
    RB_S2ARM_ADDR_IO = 2,           // a file could not be read or written, or out of memory
    RB_S2ARM_ADDR_UNSUPPORTED = 3,  // ZBIC-compressed NSO (flag 0x80): not implemented
};

// Writes <output_path> (the addr_need.tsv table, UTF-8, LF; missing parent
// directories are created). main_nso and npdm are files of the unpacked ExeFS.
// The build id is read from main_nso (16 bytes at 0x40, 32 lowercase hex
// characters), as the packer passes it. The NSO itself is only parsed when the
// NPDM SystemResourceSize is non-zero, as in the original.
// `error` (may be NULL) receives one line on failure. Thread-safe: no global
// mutable state.
int rb_s2arm_addr_need(const char *main_nso, const char *npdm, const char *output_path, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
