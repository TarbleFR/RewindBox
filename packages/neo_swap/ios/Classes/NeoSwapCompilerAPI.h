// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>
#define NEOSWAP_COMPILER_ABI 1u
typedef struct NeoSwapCompilerAPI {
    uint32_t struct_size, abi_version;
    uint64_t (*try_acquire)(uint64_t estimated_bytes, uint64_t current_headroom);
    void (*release)(uint64_t ticket);
} NeoSwapCompilerAPI;
#ifdef __cplusplus
extern "C" {
#endif
__attribute__((visibility("default"))) const NeoSwapCompilerAPI* NeoSwap_GetCompilerAPI(uint32_t abi);
#ifdef __cplusplus
}
#endif
