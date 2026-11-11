// RewindBox: port of the `--gpu-drivers <exefs>` mode of S2Arm graphics/nvn/games/profile_guess.py
// (gpu_driver_modules with its helpers nso and kind; pinned commit in tools/s2arm_prototype/pin.json).
// Lists the ExeFS modules that are NVIDIA GPU drivers (their NintendoSDK component is NintendoSDK_OpenGL or
// NintendoSDK_Vulkan); the packer writes the list to gpu_drivers.tsv. CI compares the output byte for byte with
// the original on synthetic input (tools/s2arm_prototype/run_modules_test.py).
#pragma once
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_MODULES_OK = 0,
    RB_S2ARM_MODULES_INVALID = 1,  // a module the original cannot parse (it ends in a Python exception), or an image above 1 GiB
    RB_S2ARM_MODULES_IO = 2,       // a directory or file could not be read or written, or out of memory
};

// Writes <output_path> (missing parent directories are created): one module name per line, LF, in sorted
// file-name order. Like the original's print() of an empty join, a game without a driver module gets a file
// holding a single LF. Every file of <exefs_dir> except main, sdk and rtld that starts with "NSO0" is parsed
// (segments LZ4-decompressed by the NSO flag bits 0..2, as the original; ZBIC is not interpreted, the original
// does not either); one that fails to parse fails the whole call, as the original's traceback does.
// A directory entry that is not a readable file fails with RB_S2ARM_MODULES_IO.
// `error` (may be NULL) receives one line on failure. Thread-safe: no global mutable state.
int rb_s2arm_gpu_drivers(const char *exefs_dir, const char *output_path, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
