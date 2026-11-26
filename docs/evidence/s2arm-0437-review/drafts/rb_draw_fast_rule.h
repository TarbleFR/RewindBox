// SPDX-License-Identifier: Apache-2.0
// RewindBox (patch 0438): Apple A18 Pro per-draw CPU locality & fast-path rules
//   1. pc_get() 2-slot MRU first-check fits inside ONE 128-byte A18 Pro cache line (96B + gen/next)
//      with 64 KiB page shift (addr >> 16) for the direct-mapped fallback table.
//   2. bind_vbufs() dirty-bitmask + __builtin_ctz iteration skips empty/unchanged vertex slots.
//   3. draw_impl() cold diagnostic env guard folds 7 per-draw checks into 1 predicted branch.
#pragma once
#include <stdint.h>

enum {
    RB_PC_PAGE_SHIFT = 16,
    RB_PC_MRU_HOT = 2,
};

// Direct-mapped pool-cache slot index using 64 KiB granule (16x fewer collisions on sequential
// uniform/vertex/index rings than 4 KiB pages while remaining valid across 64 KiB pool alignments).
static inline unsigned rb_pc_slot64k(uint64_t addr, unsigned bits) {
    return (unsigned)(((addr >> RB_PC_PAGE_SHIFT) * UINT64_C(0x9E3779B97F4A7C15)) >> (64u - bits));
}

// Compute the exact 16-bit mask of bound vertex buffer slots that bind_vbufs() must update.
// Any pool-generation bump re-validates all currently bound slots; otherwise only slots mutated
// by OP_BIND_VBUF since the last bind_vbufs() are walked via __builtin_ctz().
static inline uint16_t rb_vbuf_dirty_mask_take(uint16_t *dirty_mask, uint16_t bound_mask,
                                               uint64_t cur_pool_gen, uint64_t *seen_pool_gen) {
    uint16_t m = *dirty_mask;
    if (*seen_pool_gen != cur_pool_gen) {
        *seen_pool_gen = cur_pool_gen;
        m |= bound_mask;
    }
    *dirty_mask = 0;
    return (uint16_t)(m & bound_mask);
}

// RewindBox (patch 0444): O(1) dynamic render-encoder state dirty-mask for draw_pass_state().
// Steady-state draw bursts inside a render pass avoid recomputing MTLViewport/MTLScissorRect/
// rasterizer/blend structs and 4 memcmp calls (108 bytes) per draw.
enum {
    RB_ED_SREF  = 1u << 0,
    RB_ED_VP    = 1u << 1,
    RB_ED_SC    = 1u << 2,
    RB_ED_CULL  = 1u << 3,
    RB_ED_WIND  = 1u << 4,
    RB_ED_FILL  = 1u << 5,
    RB_ED_BIAS  = 1u << 6,
    RB_ED_CLIP  = 1u << 7,
    RB_ED_BLEND = 1u << 8,
    RB_ED_ALL   = (1u << 9) - 1u,
};

static inline unsigned rb_ed_effective_dirty(unsigned ok_mask, unsigned dirty_mask,
                                             int widen_on, int origin_ll, int last_origin_ll,
                                             int rast_flip, int last_rast_flip) {
    unsigned need = dirty_mask | ((~ok_mask) & RB_ED_ALL);
    if (__builtin_expect(widen_on != 0, 0)) need |= (RB_ED_VP | RB_ED_SC);
    if (__builtin_expect(origin_ll != last_origin_ll, 0)) need |= RB_ED_VP;
    if (__builtin_expect(rast_flip != last_rast_flip, 0)) need |= RB_ED_WIND;
    return need;
}
