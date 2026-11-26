// SPDX-License-Identifier: Apache-2.0
// Autonomous Apple A18 Pro S2Arm benchmark suite (bench_core.c).
// Exercises REAL S2Arm C sources and rule headers with 100% deterministic,
// synthetic & homebrew-representative workloads (ZERO user logs or game files).
//
// Compile against any S2Arm source tree:
//   clang -std=gnu11 -O2 -Wall -Wextra -Werror \
//     -I<tree>/graphics/nvn/gfx/nvn -I<tree>/graphics/nvn/gfx/nvn/include \
//     -I<tree>/graphics/nvn/gfx/tex \
//     bench_core.c <tree>/graphics/nvn/gfx/tex/nvn_deswizzle.c \
//     <tree>/graphics/nvn/gfx/nvn/nvn_tex.c \
//     <tree>/graphics/nvn/gfx/nvn/nvn_dirty.c -lm -lpthread -o bench_core

#define _GNU_SOURCE
#include <assert.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "nvn.h"
#include "nvn_deswizzle.h"
#include "nvn_dirty.h"
#include "nvn_fi_rule.h"
#include "nvn_hmap.h"
#include "nvn_tex.h"
#include "rb_args_ubo.h"
#include "rb_cache_warm_rule.h"
#include "rb_draw_barriers.h"
#include "rb_dsnap_rule.h"
#include "rb_fluid_pso_rule.h"
#include "rb_rt_cont.h"
#include "rb_thermal_pacing.h"
#include "rb_treg_cand.h"
#include "rb_ubo_versions.h"
#include "rb_view_scope.h"

#ifdef HAS_RB_PASS_CUT_RULE
#include "rb_pass_cut_rule.h"
#endif
#ifdef HAS_RB_DRAW_FAST_RULE
#include "rb_draw_fast_rule.h"
#endif

// Minimal host stubs required by nvn_dirty.c
void dm_fault_hook_register(int (*fn)(void *addr, int is_write, void *uc)) { (void)fn; }
void dm_guest_write_prep_register(void (*fn)(void *addr, size_t len)) { (void)fn; }
void dm_log(const char *fmt, ...) { (void)fmt; }

static inline double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e3 + (double)ts.tv_nsec * 1e-6;
}

static inline uint64_t fnv1a_bytes(uint64_t h, const void *data, size_t n) {
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < n; i++) {
        h ^= p[i];
        h *= 0x100000001b3ull;
    }
    return h;
}

static inline uint64_t fnv1a_u64(uint64_t h, uint64_t v) {
    return (h ^ v) * 0x100000001b3ull;
}

// ============================================================================
// M01: Texture Deswizzle / Swizzle (REAL nvn_deswizzle.c + nvn_tex.c)
// Tests both Switch 2 (nvn_gob_switch2=1) and Switch 1 (=0) GOB layouts across
// RGBA8 1024x1024, BC7-like 2048x1024, 3D 256x256x4, and odd 300x177 RGBA8.
// Verifies bit-exact parity against naive nvn_bl_offset reference.
// ============================================================================
static uint64_t naive_deswizzle_hash(const nvn_texdesc *d, const uint8_t *src, uint8_t *ref_buf, size_t pitch) {
    uint32_t rb, rows, slices, bpb;
    uint64_t base;
    unsigned th, td;
    assert(nvn_deswizzle_geom(d, 0, 0, &rb, &rows, &slices, &base, &th, &td, &bpb) == 0);
    uint32_t lb = nvn_tex_level_gobs(d, 0) * 64;
    if (lb < rb) lb = rb;
    const uint8_t *bl = src + base;
    for (uint32_t z = 0; z < slices; z++) {
        for (uint32_t y = 0; y < rows; y++) {
            uint8_t *row = ref_buf + ((size_t)z * rows + y) * pitch;
            for (uint32_t x = 0; x < rb; x += 16) {
                uint32_t n = rb - x < 16 ? rb - x : 16;
                memcpy(row + x, bl + nvn_bl_offset(x, y, z, lb, rows, th, td), n);
            }
        }
    }
    return fnv1a_bytes(0xcbf29ce484222325ull, ref_buf, (size_t)slices * rows * pitch);
}

static void run_m01_deswizzle(int verify_only) {
    struct {
        const char *name;
        nvn_texdesc d;
        int iters;
    } cases[4] = {
        {"rgba8_1024", {.target = 1, .format = 0x25, .width = 1024, .height = 1024, .depth = 1, .levels = 1, .samples = 1}, verify_only ? 1 : 6},
        {"bc7_2048x1024", {.target = 1, .format = 0x7d, .width = 2048, .height = 1024, .depth = 1, .levels = 1, .samples = 1}, verify_only ? 1 : 8},
        {"rgba8_3d_128x128x8", {.target = 2, .format = 0x25, .width = 128, .height = 128, .depth = 8, .levels = 1, .samples = 1}, verify_only ? 1 : 12},
        {"rgba8_odd_300x177", {.target = 1, .format = 0x25, .width = 300, .height = 177, .depth = 1, .levels = 1, .samples = 1}, verify_only ? 1 : 24},
    };
    uint64_t total_bytes = 0;
    uint64_t hash = 0xcbf29ce484222325ull;
    double elapsed = 0.0;

    for (int sw2 = 0; sw2 <= 1; sw2++) {
        nvn_gob_switch2 = sw2;
        for (int c = 0; c < 4; c++) {
            nvn_texlayout L;
            nvn_tex_layout(&cases[c].d, &L);
            uint32_t rb, rows, slices, bpb;
            uint64_t base;
            unsigned th, td;
            assert(nvn_deswizzle_geom(&cases[c].d, 0, 0, &rb, &rows, &slices, &base, &th, &td, &bpb) == 0);
            size_t pitch = (rb + 63u) & ~63u;
            size_t lin_sz = (size_t)slices * rows * pitch;
            uint8_t *bl = (uint8_t *)malloc(L.size + 64);
            uint8_t *lin = (uint8_t *)calloc(1, lin_sz + 64);
            uint8_t *ref = (uint8_t *)calloc(1, lin_sz + 64);
            uint8_t *rt = (uint8_t *)calloc(1, L.size + 64);
            assert(bl && lin && ref && rt);
            for (size_t i = 0; i < L.size; i++) bl[i] = (uint8_t)((i * 131u + (unsigned)c * 37u + (unsigned)sw2 * 19u) & 0xffu);

            uint64_t expected = naive_deswizzle_hash(&cases[c].d, bl, ref, pitch);
            double t0 = now_ms();
            for (int it = 0; it < cases[c].iters; it++) {
                assert(nvn_deswizzle(&cases[c].d, 0, 0, bl, lin, pitch) == 0);
                if (it == 0) {
                    assert(memcmp(lin, ref, lin_sz) == 0);
                    assert(nvn_swizzle(&cases[c].d, 0, 0, lin, pitch, rt) == 0);
                    memset(lin, 0, lin_sz);
                    assert(nvn_deswizzle(&cases[c].d, 0, 0, rt, lin, pitch) == 0);
                    assert(memcmp(lin, ref, lin_sz) == 0);
                }
                total_bytes += (uint64_t)slices * rows * rb;
            }
            elapsed += (now_ms() - t0);
            hash = fnv1a_u64(hash, expected);
            free(bl);
            free(lin);
            free(ref);
            free(rt);
        }
    }
    nvn_gob_switch2 = 1;
    double mb_s = elapsed > 0.0 ? ((double)total_bytes / (1024.0 * 1024.0)) / (elapsed / 1000.0) : 0.0;
    printf("{\"module\":\"M01_deswizzle\",\"time_ms\":%.4f,\"bytes\":%llu,\"throughput_mbs\":%.2f,\"checksum\":\"%016llx\"}\n",
           elapsed, (unsigned long long)total_bytes, mb_s, (unsigned long long)hash);
}

// ============================================================================
// M02: Hash Table Hot-Path Lookups (REAL nvn_hmap.h)
// 8-byte serials (g_by_serial/g_tex_live), 64-byte alias keys, 184-byte PSO keys.
// ============================================================================
static void run_m02_hmap(int verify_only) {
    const int scale = verify_only ? 10 : 1;
    nvn_hmap m8, m64, m184;
    nvn_hm_init(&m8, 8);
    nvn_hm_init(&m64, 64);
    nvn_hm_init(&m184, 184);

    enum { N8 = 4096, N64 = 512, N184 = 1024 };
    uint64_t *k8 = (uint64_t *)malloc(sizeof(uint64_t) * N8);
    uint8_t *k64 = (uint8_t *)calloc(N64, 64);
    uint8_t *k184 = (uint8_t *)calloc(N184, 184);
    assert(k8 && k64 && k184);

    for (int i = 0; i < N8; i++) {
        k8[i] = 10000ull + (uint64_t)i * 3ull;
        nvn_hm_put(&m8, &k8[i], (void *)(uintptr_t)(i + 1));
    }
    for (int i = 0; i < N64; i++) {
        uint64_t pool = 0x100000000ull + ((uint64_t)(i & 15) << 24);
        uint64_t off = (uint64_t)i * 65536ull;
        memcpy(k64 + (size_t)i * 64, &pool, 8);
        memcpy(k64 + (size_t)i * 64 + 8, &off, 8);
        k64[(size_t)i * 64 + 60] = (uint8_t)(i & 0xff);
        nvn_hm_put(&m64, k64 + (size_t)i * 64, (void *)(uintptr_t)(i + 1000));
    }
    for (int i = 0; i < N184; i++) {
        // Near-identical PSO keys differing near head (shader ptrs) and tail (blend/depth state)
        uint64_t vs = 0x200000000ull + (uint64_t)(i & 63) * 64ull;
        uint64_t fs = 0x300000000ull + (uint64_t)(i >> 2) * 64ull;
        memcpy(k184 + (size_t)i * 184, &vs, 8);
        memcpy(k184 + (size_t)i * 184 + 8, &fs, 8);
        k184[(size_t)i * 184 + 176] = (uint8_t)(i & 0xff);
        k184[(size_t)i * 184 + 180] = (uint8_t)((i >> 8) & 0xff);
        nvn_hm_put(&m184, k184 + (size_t)i * 184, (void *)(uintptr_t)(i + 5000));
    }

    uint64_t acc = 0;
    const int lookups8 = 800000 / scale;
    const int lookups64 = 200000 / scale;
    const int lookups184 = 400000 / scale;
    double t0 = now_ms();
    for (int i = 0; i < lookups8; i++) {
        uint64_t q = (i & 3) == 0 ? (99999999ull + (uint64_t)i) : k8[(unsigned)(i * 2654435761u) & (N8 - 1)];
        acc += (uintptr_t)nvn_hm_get(&m8, &q);
    }
    for (int i = 0; i < lookups64; i++) {
        int idx = (int)((unsigned)(i * 1140071481u) & (N64 - 1));
        acc += (uintptr_t)nvn_hm_get(&m64, k64 + (size_t)idx * 64);
    }
    for (int i = 0; i < lookups184; i++) {
        int idx = (int)((unsigned)(i * 2246822519u) & (N184 - 1));
        acc += (uintptr_t)nvn_hm_get(&m184, k184 + (size_t)idx * 184);
    }
    double elapsed = now_ms() - t0;

    // Verify put/del integrity
    uint64_t delk = k8[123];
    assert(nvn_hm_del(&m8, &delk) == (void *)(uintptr_t)124);
    assert(nvn_hm_get(&m8, &delk) == NULL);

    free(m8.keys); free(m8.vals);
    free(m64.keys); free(m64.vals);
    free(m184.keys); free(m184.vals);
    free(k8); free(k64); free(k184);

    printf("{\"module\":\"M02_hmap\",\"time_ms\":%.4f,\"ops\":%d,\"checksum\":\"%016llx\"}\n",
           elapsed, lookups8 + lookups64 + lookups184, (unsigned long long)acc);
}

// ============================================================================
// M03: Pool Address Cache Locality + Vertex Buffer Binding Hot Path
// Models nvn_mtl.m pc_get() + bind_vbufs() across 60,000 draws with sequential
// uniform-ring strides + 4 active vertex streams (128B A18 Pro cache lines).
// ============================================================================
typedef struct { uintptr_t lo, hi, base; void *buf; uint64_t gpu; uintptr_t host; } bench_pc_ent;
enum { BENCH_PC_BITS = 10, BENCH_PC_RECENT = 8 };

static void run_m03_pool_vbuf(int verify_only) {
    const int draws = verify_only ? 6000 : 60000;
    enum { NPOOLS = 64 };
    bench_pc_ent pools[NPOOLS];
    for (int i = 0; i < NPOOLS; i++) {
        uintptr_t lo = 0x1000000000ull + (uint64_t)i * 0x01000000ull; // 16 MiB pools
        pools[i] = (bench_pc_ent){lo, lo + 0x01000000ull, lo, (void *)(uintptr_t)(i + 1), 0x8000000000ull + (uint64_t)i * 0x01000000ull, lo};
    }

    // State mimicking S.vbuf[16] + enc_r_vbuf table cache
    struct { uint64_t address; uint64_t size; } vbuf[16];
    memset(vbuf, 0, sizeof vbuf);
    uint64_t vt_addr[32] = {0};
    uint32_t vt_valid = 0;

    static struct { uint64_t gen; unsigned next; bench_pc_ent r[BENCH_PC_RECENT], e[1u << BENCH_PC_BITS]; } pc;
    memset(&pc, 0, sizeof pc);
    pc.gen = 1;
    uint64_t pool_gen = 1;
    (void)pool_gen;

    uint64_t table_writes = 0, slot_checks = 0, pc_misses = 0, hash = 0xcbf29ce484222325ull;
    uint16_t bound_mask = 0, dirty_mask = 0;
    (void)bound_mask; (void)dirty_mask;

    double t0 = now_ms();
    for (int d = 0; d < draws; d++) {
        // Every draw updates UBO[0] in a sequential ring (moves across 4 KiB pages continuously!)
        uint64_t ubo_addr = pools[d & 3].lo + (uint64_t)((d * 256u) & 0x3fffffu);
        // Every 4 draws binds new vertex buffer on slot 0..2; slot 3 static across whole pass
        if ((d & 3) == 0) {
            int s = (d >> 2) % 3;
            vbuf[s].address = pools[4 + (d & 7)].lo + (uint64_t)((d * 512u) & 0x7ffffu);
            vbuf[s].size = 4096;
            bound_mask |= (uint16_t)(1u << s);
            dirty_mask |= (uint16_t)(1u << s);
        }
        if (d == 0) {
            vbuf[3].address = pools[12].lo + 4096;
            vbuf[3].size = 65536;
            bound_mask |= (uint16_t)(1u << 3);
            dirty_mask |= (uint16_t)(1u << 3);
        }

        // 1) Pool address lookup for UBO ring
        const bench_pc_ent *hit = NULL;
#ifdef HAS_RB_DRAW_FAST_RULE
        // MRU-first check: stays in 1 single 128-byte A18 Pro cache line!
        for (unsigned k = 0; k < 2; k++) {
            const bench_pc_ent *x = &pc.r[k];
            if (ubo_addr >= x->lo && ubo_addr + 256 <= x->hi) { hit = x; break; }
        }
        if (!hit) {
            unsigned sl = (unsigned)(((ubo_addr >> 16) * 0x9E3779B97F4A7C15ull) >> (64 - BENCH_PC_BITS));
            bench_pc_ent *c = &pc.e[sl];
            if (ubo_addr >= c->lo && ubo_addr + 256 <= c->hi) {
                hit = c;
                pc.r[1] = pc.r[0]; pc.r[0] = *c;
            } else {
                for (unsigned k = 2; k < BENCH_PC_RECENT; k++) {
                    const bench_pc_ent *x = &pc.r[k];
                    if (ubo_addr >= x->lo && ubo_addr + 256 <= x->hi) { hit = x; *c = *x; pc.r[1] = pc.r[0]; pc.r[0] = *x; break; }
                }
            }
        }
        if (!hit) {
            pc_misses++;
            int pi = (int)((ubo_addr - 0x1000000000ull) >> 24);
            unsigned sl = (unsigned)(((ubo_addr >> 16) * 0x9E3779B97F4A7C15ull) >> (64 - BENCH_PC_BITS));
            pc.e[sl] = pools[pi];
            for (int k = BENCH_PC_RECENT - 1; k > 0; k--) pc.r[k] = pc.r[k - 1];
            pc.r[0] = pools[pi];
            hit = &pc.r[0];
        }
#else
        // Exact 0436 pc_get() behavior: probes 48 KiB direct-mapped table by 4 KiB page FIRST!
        unsigned sl = (unsigned)(((ubo_addr >> 12) * 0x9E3779B97F4A7C15ull) >> (64 - BENCH_PC_BITS));
        bench_pc_ent *c = &pc.e[sl];
        if (ubo_addr >= c->lo && ubo_addr + 256 <= c->hi) hit = c;
        else {
            for (unsigned k = 0; k < BENCH_PC_RECENT; k++) {
                const bench_pc_ent *x = &pc.r[k];
                if (ubo_addr >= x->lo && ubo_addr + 256 <= x->hi) { *c = *x; hit = c; break; }
            }
        }
        if (!hit) {
            pc_misses++;
            int pi = (int)((ubo_addr - 0x1000000000ull) >> 24);
            pc.e[sl] = pools[pi];
            pc.r[pc.next++ % BENCH_PC_RECENT] = pools[pi];
            hit = &pc.e[sl];
        }
#endif
        uint64_t ubo_gpu = hit->gpu + (ubo_addr - hit->base);
        hash = fnv1a_u64(hash, ubo_gpu);

        // 2) Vertex buffer binding (bind_vbufs)
#ifdef HAS_RB_DRAW_FAST_RULE
        uint16_t dm = rb_vbuf_dirty_mask_take(&dirty_mask, bound_mask, pool_gen, &pool_gen);
        while (dm) {
            int s = __builtin_ctz(dm);
            dm &= (uint16_t)(dm - 1);
            slot_checks++;
            uint64_t addr = vbuf[s].address;
            if (!addr) continue;
            int pi = (int)((addr - 0x1000000000ull) >> 24);
            uint64_t gpu = pools[pi].gpu + (addr - pools[pi].base);
            uint32_t bit = 1u << (14 + s);
            if (!(vt_valid & bit) || vt_addr[14 + s] != gpu) {
                vt_addr[14 + s] = gpu;
                vt_valid |= bit;
                table_writes++;
            }
        }
        (void)bound_mask;
#else
        for (int s = 0; s < 16; s++) {
            slot_checks++;
            uint64_t addr = vbuf[s].address;
            if (!addr) continue;
            int pi = (int)((addr - 0x1000000000ull) >> 24);
            uint64_t gpu = pools[pi].gpu + (addr - pools[pi].base);
            uint32_t bit = 1u << (14 + s);
            if (!(vt_valid & bit) || vt_addr[14 + s] != gpu) {
                vt_addr[14 + s] = gpu;
                vt_valid |= bit;
                table_writes++;
            }
        }
        dirty_mask = 0;
#endif
        // Verify checksum includes active vertex table state
        hash = fnv1a_u64(hash, vt_addr[14] ^ vt_addr[15] ^ vt_addr[16] ^ vt_addr[17]);
    }
    double elapsed = now_ms() - t0;
    printf("{\"module\":\"M03_pool_vbuf\",\"time_ms\":%.4f,\"draws\":%d,\"slot_checks\":%llu,\"table_writes\":%llu,\"pc_misses\":%llu,\"checksum\":\"%016llx\"}\n",
           elapsed, draws, (unsigned long long)slot_checks, (unsigned long long)table_writes,
           (unsigned long long)pc_misses, (unsigned long long)hash);
}

// ============================================================================
// M04: Argument Block Encoding + len_fill + Shader Alternation + Cross-Pass
// Directly exercises rb_args_ubo.h + len_fill UBO bounds generation cache +
// dirty-slot UBO patching (including texture-less vertex shaders!) + bit-exact
// verification against a naive full-rebuild reference (wrong MUST be 0).
// ============================================================================
typedef struct {
    int nb;
    int kept; // 1 = has textures/samplers, 0 = UBO-only vertex shader
    int ubo_slots[8];
    int n_ubo;
    int tex_slots[8];
    int n_tex;
    rb_args_masks masks;
    uint64_t ab_slots[24];
    uint64_t ab_pass;
    uint64_t ab_agen;
    int has_ab;
#ifdef RB_ARGS_HAS_SLOT_GENS
    rb_args_slot_snap ab_snap;
#endif
} bench_sh;

static void run_m04_args_ubo(int verify_only) {
    const int frames = verify_only ? 2 : 20;
    const int passes_per_frame = 40;
    const int draws_per_pass = 30;
    // 4 shaders: VS_A, VS_B (texture-less, 6 UBOs each), FS_A, FS_B (4 UBOs + 6 textures each)
    bench_sh sh[4];
    memset(sh, 0, sizeof sh);
    for (int i = 0; i < 4; i++) {
        sh[i].kept = (i >= 2);
        sh[i].n_ubo = (i < 2) ? 6 : 4;
        for (int u = 0; u < sh[i].n_ubo; u++) {
            sh[i].ubo_slots[u] = u;
            sh[i].masks.ubo |= (uint16_t)(1u << u);
        }
        sh[i].n_tex = (i >= 2) ? 6 : 0;
        for (int t = 0; t < sh[i].n_tex; t++) {
            sh[i].tex_slots[t] = t;
            sh[i].masks.tex[0] |= (UINT64_C(1) << t);
            sh[i].masks.needs_rmu = 1;
        }
        sh[i].masks.built = 1;
        sh[i].nb = sh[i].n_ubo + sh[i].n_tex;
    }

    uint64_t ubo_addr[2][16], ubo_size[2][16];
    uint64_t tex_rid[2][16];
    for (int st = 0; st < 2; st++) {
        for (int r = 0; r < 16; r++) {
            ubo_addr[st][r] = 0x4000000000ull + (uint64_t)st * 0x10000000ull + (uint64_t)r * 0x10000ull;
            ubo_size[st][r] = (r < 6) ? 1024u : 0u;
            tex_rid[st][r] = 0x90000000ull + (uint64_t)r * 17ull;
        }
    }

    // len_fill cache (exact 0436 behavior vs generation fast-path)
    uint32_t last_ubolen[2][16];
    uint64_t last_ubolen_agen[2] = {0, 0};
    uint64_t last_ubolen_gpu[2] = {0, 0};
#ifdef RB_ARGS_HAS_SLOT_GENS
    uint64_t ubolen_size_gen[2] = {1, 1};
    uint64_t last_ubolen_sgen[2] = {0, 0};
    rb_args_stage_gens stage_gens[2];
    memset(stage_gens, 0, sizeof stage_gens);
    stage_gens[0].other_gen = 1; stage_gens[1].other_gen = 1;
#endif
    uint64_t full_rebuilds = 0, partial_rebuilds = 0, whole_reuses = 0;
    uint64_t ubo_lookups = 0, tex_lookups = 0, len_fill_scans = 0, rmu_locks = 0;
    uint64_t wrong = 0, hash = 0xcbf29ce484222325ull;
    uint64_t pass_serial = 1, arena_gen = 1;
    bench_sh *owner[2] = {NULL, NULL};
    uint8_t dirty[2] = {RB_ARGS_FULL, RB_ARGS_FULL};
    rb_args_mod mod[2];
    memset(mod, 0, sizeof mod);

    double t0 = now_ms();
    for (int f = 0; f < frames; f++) {
        arena_gen++;
        for (int p = 0; p < passes_per_frame; p++) {
            pass_serial++;
            // Simulate rp_begin_ex_: 0436 calls args_dirty_all() marking FULL + mod.other=1!
#ifndef RB_ARGS_HAS_SLOT_GENS
            dirty[0] = RB_ARGS_FULL; dirty[1] = RB_ARGS_FULL;
            rb_args_mod_mark_other(&mod[0]); rb_args_mod_mark_other(&mod[1]);
#endif
            for (int d = 0; d < draws_per_pass; d++) {
                // Per-draw UBO[0] transform update on VS; every 3 draws update FS UBO[0];
                // every 5 draws alternate shader A <-> B (classic material/shadow ping-pong!)
                ubo_addr[0][0] += 256;
                dirty[0] = rb_args_mark_uniform(dirty[0], RB_ARGS_MODE_ON);
                rb_args_mod_ubo(&mod[0], 0);
#ifdef RB_ARGS_HAS_SLOT_GENS
                rb_args_stage_bump_ubo(&stage_gens[0], 0);
#endif
                if ((d % 3) == 0) {
                    ubo_addr[1][0] += 256;
                    dirty[1] = rb_args_mark_uniform(dirty[1], RB_ARGS_MODE_ON);
                    rb_args_mod_ubo(&mod[1], 0);
#ifdef RB_ARGS_HAS_SLOT_GENS
                    rb_args_stage_bump_ubo(&stage_gens[1], 0);
#endif
                }
                if ((d % 10) == 0) {
                    tex_rid[1][2] += 1;
                    dirty[1] = RB_ARGS_FULL;
                    rb_args_mod_tex_range(&mod[1], 2, 1);
#ifdef RB_ARGS_HAS_SLOT_GENS
                    rb_args_stage_bump_tex(&stage_gens[1], 2);
#endif
                }
                int alt = ((d / 5) & 1);
                int sh_idx[2] = {alt, 2 + alt};

                for (int st = 0; st < 2; st++) {
                    bench_sh *s = &sh[sh_idx[st]];
                    // Reference exact block (always full)
                    uint64_t ref_slots[24];
                    memset(ref_slots, 0, sizeof ref_slots);
                    for (int u = 0; u < s->n_ubo; u++) ref_slots[u] = ubo_addr[st][s->ubo_slots[u]] ^ 0x55aaull;
                    for (int t = 0; t < s->n_tex; t++) ref_slots[8 + t] = tex_rid[st][s->tex_slots[t]];
                    uint64_t ref_ubolen_h = 0xcbf29ce484222325ull;
                    for (int r = 0; r < 16; r++) ref_ubolen_h = fnv1a_u64(ref_ubolen_h, (ubo_size[st][r] + 15u) / 16u);
                    ref_slots[20] = ref_ubolen_h;

                    uint64_t cur_slots[24];
                    int did_reuse = 0, did_partial = 0;
                    uint16_t dirty_ubo_mask = 0xffffu;
                    int skip_kept_tex = 0;

#ifdef RB_ARGS_HAS_SLOT_GENS
                    // Slot-generation fast path: survives A->B->A program switches AND cross-pass!
                    int can_snap = s->has_ab && s->ab_agen == arena_gen;
                    if (can_snap) {
                        rb_args_diff diff = rb_args_stage_diff(&stage_gens[st], &s->ab_snap, &s->masks);
                        if (diff.unchanged) {
                            did_reuse = 1;
                            memcpy(cur_slots, s->ab_slots, sizeof cur_slots);
                        } else if (diff.partial_ok) {
                            did_partial = 1;
                            dirty_ubo_mask = diff.ubo_dirty;
                            skip_kept_tex = diff.tex_unchanged;
                        }
                    }
#else
                    // Exact 0436 logic: owner must match, mod must clear, texture-less shaders (kept==0) always FULL!
                    int same_owner = (owner[st] == s);
                    int same_pass = (s->ab_pass == pass_serial);
                    int same_arena = (s->ab_agen == arena_gen);
                    if (s->has_ab && same_owner && same_arena && same_pass && !dirty[st]) {
                        did_reuse = 1;
                        memcpy(cur_slots, s->ab_slots, sizeof cur_slots);
                    } else if (s->has_ab && same_owner && same_arena && same_pass && rb_args_can_reuse_masked(&mod[st], &s->masks)) {
                        did_reuse = 1;
                        memcpy(cur_slots, s->ab_slots, sizeof cur_slots);
                    } else {
                        rb_args_gate g;
                        memset(&g, 0, sizeof g);
                        g.mode = RB_ARGS_MODE_ON;
                        g.stage = (uint8_t)st;
                        g.dirty = dirty[st];
                        g.same_pass = (uint8_t)same_pass;
                        g.same_sub = 1;
                        g.same_arena = (uint8_t)same_arena;
                        g.same_stage = 1;
                        g.kept = (uint8_t)s->kept;
                        g.have = (uint8_t)s->has_ab;
                        g.same_views = 1;
                        g.owner = (uint8_t)same_owner;
                        int why = rb_args_why_v2(&g, 1, 1, !mod[st].other);
                        if (why == RB_ARGS_PARTIAL) {
                            did_partial = 1;
                            skip_kept_tex = (dirty[st] == RB_ARGS_UNIFORM || dirty[st] == RB_ARGS_CLEAN);
                            dirty_ubo_mask = 0xffffu; // 0436 re-walks ALL UBOs even during PARTIAL!
                        }
                    }
#endif
                    if (did_reuse) {
                        whole_reuses++;
                    } else {
                        if (did_partial) {
                            partial_rebuilds++;
                            memcpy(cur_slots, s->ab_slots, sizeof cur_slots);
                        } else {
                            full_rebuilds++;
                            memset(cur_slots, 0, sizeof cur_slots);
                            dirty_ubo_mask = 0xffffu;
                            skip_kept_tex = 0;
                        }
                        int need_rmu = rb_args_needs_rmu_lock(&s->masks, did_partial, !skip_kept_tex && did_partial);
                        if (need_rmu && !skip_kept_tex) rmu_locks++;
                        for (int u = 0; u < s->n_ubo; u++) {
                            int r = s->ubo_slots[u];
                            if (did_partial && !(dirty_ubo_mask & (1u << r))) continue;
                            ubo_lookups++;
                            cur_slots[u] = ubo_addr[st][r] ^ 0x55aaull;
                        }
                        if (!skip_kept_tex) {
                            for (int t = 0; t < s->n_tex; t++) {
                                tex_lookups++;
                                cur_slots[8 + t] = tex_rid[st][s->tex_slots[t]];
                            }
                        }
                        // len_fill(NVN_RB_UBOLEN)
#ifdef RB_ARGS_HAS_SLOT_GENS
                        if (last_ubolen_agen[st] == arena_gen && last_ubolen_sgen[st] == ubolen_size_gen[st]) {
                            cur_slots[20] = last_ubolen_gpu[st];
                        } else {
                            len_fill_scans++;
                            uint32_t q[16];
                            uint64_t h = 0xcbf29ce484222325ull;
                            for (int r = 0; r < 16; r++) { q[r] = (uint32_t)((ubo_size[st][r] + 15u) / 16u); h = fnv1a_u64(h, q[r]); }
                            memcpy(last_ubolen[st], q, sizeof q);
                            last_ubolen_agen[st] = arena_gen;
                            last_ubolen_sgen[st] = ubolen_size_gen[st];
                            last_ubolen_gpu[st] = h;
                            cur_slots[20] = h;
                        }
#else
                        len_fill_scans++;
                        uint32_t q[16];
                        uint64_t h = 0xcbf29ce484222325ull;
                        for (int r = 0; r < 16; r++) { q[r] = (uint32_t)((ubo_size[st][r] + 15u) / 16u); h = fnv1a_u64(h, q[r]); }
                        if (last_ubolen_agen[st] == arena_gen && !memcmp(q, last_ubolen[st], sizeof q)) {
                            cur_slots[20] = last_ubolen_gpu[st];
                        } else {
                            memcpy(last_ubolen[st], q, sizeof q);
                            last_ubolen_agen[st] = arena_gen;
                            last_ubolen_gpu[st] = h;
                            cur_slots[20] = h;
                        }
#endif
                        memcpy(s->ab_slots, cur_slots, sizeof cur_slots);
                        s->ab_pass = pass_serial;
                        s->ab_agen = arena_gen;
                        s->has_ab = 1;
#ifdef RB_ARGS_HAS_SLOT_GENS
                        rb_args_stage_capture(&s->ab_snap, &stage_gens[st]);
#endif
                        owner[st] = s;
                        dirty[st] = RB_ARGS_CLEAN;
                        rb_args_mod_clear(&mod[st]);
                    }
                    if (memcmp(cur_slots, ref_slots, sizeof ref_slots) != 0) wrong++;
                    hash = fnv1a_u64(hash, cur_slots[0] ^ cur_slots[8] ^ cur_slots[20]);
                }
            }
        }
    }
    double elapsed = now_ms() - t0;
    assert(wrong == 0);
    printf("{\"module\":\"M04_args_ubo\",\"time_ms\":%.4f,\"reused\":%llu,\"partial\":%llu,\"full\":%llu,\"ubo_lookups\":%llu,\"tex_lookups\":%llu,\"len_fill_scans\":%llu,\"rmu_locks\":%llu,\"wrong\":%llu,\"checksum\":\"%016llx\"}\n",
           elapsed, (unsigned long long)whole_reuses, (unsigned long long)partial_rebuilds,
           (unsigned long long)full_rebuilds, (unsigned long long)ubo_lookups,
           (unsigned long long)tex_lookups, (unsigned long long)len_fill_scans,
           (unsigned long long)rmu_locks, (unsigned long long)wrong, (unsigned long long)hash);
}

// ============================================================================
// M05: TBDR Mid-Pass Cut Bandwidth + 2-Slot LRU Depth Snapshot Cache
// Synthetic 100-pass open-world frame (MRT G-buffer + shadows + post-FX)
// ============================================================================
static void run_m05_tbdr_pass_cut(int verify_only) {
    const int frames = verify_only ? 10 : 300;
    // Synthetic open-world frame profile:
    //   Pass 0: Shadow pass (450 draws, 1x D32F 2048x2048 = 16 MB)
    //   Pass 1: Main MRT G-buffer (800 draws, 4x color + D32F @ 1440x810 = 36 MB)
    //   Pass 2: Lighting/decals (350 draws, 2x color + D32F @ 1440x810 = 18 MB, reads depth feedback!)
    //   Pass 3: Transparents (240 draws, 1x color + D32F @ 1440x810 = 11 MB, reads depth feedback!)
    //   Pass 4..9: Lightweight UI/post passes (40 draws each, 1x color = 4.6 MB)
    struct { int draws; int n_color; int has_depth; uint64_t att_bytes; } passes[10] = {
        {450, 0, 1, 16ull << 20},
        {800, 4, 1, 36ull << 20},
        {350, 2, 1, 18ull << 20},
        {240, 1, 1, 11ull << 20},
        {40,  1, 0, 5ull << 20}, {40, 1, 0, 5ull << 20}, {40, 1, 0, 5ull << 20},
        {40,  1, 0, 5ull << 20}, {40, 1, 0, 5ull << 20}, {40, 1, 0, 5ull << 20},
    };
    const int base_cut = 64;
    uint64_t mid_pass_splits = 0;
    uint64_t extra_dram_bytes = 0;
    uint64_t dsnap_blits = 0;
    uint64_t dsnap_bytes = 0;

    rb_dsnap_slot ds_slots[RB_DSNAP_SLOTS];
    memset(ds_slots, 0, sizeof ds_slots);
    uint64_t ds_tick = 0;

    double t0 = now_ms();
    for (int f = 0; f < frames; f++) {
        uint64_t draw_cnt = 0, cut_draw0 = 0;
        rb_dsnap_cache_stale_all(ds_slots);
        for (int p = 0; p < 10; p++) {
            // Between-pass cut check (always zero extra Store+Load)
            if (draw_cnt - cut_draw0 >= (uint64_t)base_cut) cut_draw0 = draw_cnt;
            int seg_inflight = 0; // worst-case CPU-bound frame where prior CB completed
            for (int d = 0; d < passes[p].draws; d++) {
#ifdef HAS_RB_PASS_CUT_RULE
                int eff_cut = rb_pass_cut_draws(base_cut, passes[p].n_color, passes[p].has_depth, passes[p].att_bytes);
#else
                int eff_cut = base_cut;
#endif
                if (eff_cut > 0 && draw_cnt - cut_draw0 >= (uint64_t)eff_cut && seg_inflight == 0) {
                    mid_pass_splits++;
                    extra_dram_bytes += 2ull * passes[p].att_bytes; // Store + reload every bound attachment!
                    cut_draw0 = draw_cnt;
                    seg_inflight = 1;
                } else if (seg_inflight > 0 && (d % 96) == 95) {
                    seg_inflight = 0;
                }
                draw_cnt++;
            }
            // Depth feedback snapshot reuse test (passes 2 & 3 sample depth from pass 1, color-only pass 4 preserves it)
            if (p == 2 || p == 3) {
                int hit = rb_dsnap_cache_find(ds_slots, 1001, 0xaaaa, 0, 0, 1, 0, 0, ++ds_tick);
                if (hit < 0) {
                    int dst = rb_dsnap_cache_pick(ds_slots, 1001, 0xaaaa, 0, 0, 1);
                    rb_dsnap_cache_publish(ds_slots, dst, 1001, 0x10000, 0x50000, 0xaaaa, 0xbbbb, 0, 0, 1, 0, ++ds_tick);
                    dsnap_blits++;
                    dsnap_bytes += (1440ull * 810ull * 4ull);
                }
            }
        }
    }
    double elapsed = now_ms() - t0;
    double extra_mb_per_frame = (double)extra_dram_bytes / (1024.0 * 1024.0) / (double)frames;
    double dsnap_mb_per_frame = (double)dsnap_bytes / (1024.0 * 1024.0) / (double)frames;
    printf("{\"module\":\"M05_tbdr_pass_cut\",\"time_ms\":%.4f,\"mid_pass_splits\":%llu,\"extra_dram_mb_per_frame\":%.2f,\"dsnap_blits\":%llu,\"dsnap_mb_per_frame\":%.2f,\"checksum\":\"%016llx\"}\n",
           elapsed, (unsigned long long)mid_pass_splits, extra_mb_per_frame,
           (unsigned long long)dsnap_blits, dsnap_mb_per_frame,
           (unsigned long long)(mid_pass_splits ^ dsnap_blits));
}

// ============================================================================
// M06: In-flight Uniform Buffer Reconstruction (REAL rb_ubo_versions.h)
// ============================================================================
static void run_m06_ubo_versions(int verify_only) {
    const int frames = verify_only ? 20 : 180;
    static rb_ub_versions ring;
    memset(&ring, 0, sizeof ring);
    static uint8_t mem[64 * 4096];
    for (size_t i = 0; i < sizeof mem; i++) mem[i] = (uint8_t)(i * 73u + 19u);
    uint8_t out[4096], have[4096];
    uint64_t ok = 0, hash = 0xcbf29ce484222325ull;
    uint64_t fence = 1;

    double t0 = now_ms();
    for (int f = 0; f < frames; f++) {
        for (int sub = 0; sub < 6; sub++) {
            uint64_t cur_f = fence++;
            rb_ub_frame *fr = rb_ub_begin(&ring, cur_f);
            for (int w = 0; w < 6; w++) {
                uint64_t off = (uint64_t)((f * 3 + w) % 16) * 4096ull + (uint64_t)((w * 128) & 2047);
                uint8_t patch[256];
                for (int b = 0; b < 256; b++) patch[b] = (uint8_t)((f + sub + w + b) & 0xff);
                rb_ub_capture(fr, (uint64_t)(uintptr_t)(mem + off), 256, patch);
            }
            for (int q = 0; q < 15; q++) {
                uint64_t off = (uint64_t)((f * 3 + (q & 7)) % 16) * 4096ull + 64ull;
                uint64_t lo = (uint64_t)(uintptr_t)(mem + off);
                uint64_t done = cur_f > 20 ? cur_f - 20 : 0;
                memset(have, 0, 512);
                if (rb_ub_base(&ring, done, cur_f, lo, lo + 512, out, have)) {
                    ok++;
                    hash = fnv1a_u64(hash, ((uint64_t)out[0] << 8) ^ out[255] ^ out[511]);
                }
            }
        }
    }
    double elapsed = now_ms() - t0;
    assert(ok > 0);
    printf("{\"module\":\"M06_ubo_versions\",\"time_ms\":%.4f,\"reconstructions\":%llu,\"checksum\":\"%016llx\"}\n",
           elapsed, (unsigned long long)ok, (unsigned long long)hash);
}

// ============================================================================
// M07: Striped Dirty Range Tracking & Pool Span Lookup (REAL nvn_dirty.c)
// ============================================================================
static void run_m07_dirty_stripes(int verify_only) {
    const int iters = verify_only ? 10000 : 100000;
    const size_t pool_sz = 256u * 4096u; // 1 MiB (> RB_DIRTY_STRIPE_MIN_PAGES -> activates striped tracking!)
    uint8_t *backing = (uint8_t *)calloc(1, pool_sz);
    assert(backing != NULL);
    nvn_dirty_add_range(backing, pool_sz);
    uint64_t stamp = nvn_dirty_now();
    const void *span = NULL;
    uint64_t hash = 0xcbf29ce484222325ull;
    double t0 = now_ms();
    for (int i = 0; i < iters; i++) {
        size_t off = (size_t)((i * 4096u) & (pool_sz - 4096u));
        uint64_t w = nvn_dirty_range_writes(&span, backing + off, 4096);
        int dirty = nvn_dirty_since_span(span, backing + off, 4096, stamp);
        hash = fnv1a_u64(hash, w ^ (uint64_t)dirty);
    }
    double elapsed = now_ms() - t0;
    nvn_dirty_remove_range(backing);
    free(backing);
    printf("{\"module\":\"M07_dirty_stripes\",\"time_ms\":%.4f,\"ops\":%d,\"checksum\":\"%016llx\"}\n",
           elapsed, iters, (unsigned long long)hash);
}

// ============================================================================
// M08: Fluid Pipelines & Cold/Warm Cache Policy (REAL rb_fluid_pso_rule.h + rb_cache_warm_rule.h)
// ============================================================================
static void run_m08_pso_cold_warm(int verify_only) {
    const int reps = verify_only ? 100 : 10000;
    uint64_t hash = 0xcbf29ce484222325ull;
    int corrupt = 0, unbounded = 0;
    double t0 = now_ms();
    for (int r = 0; r < reps; r++) {
        // Test persistent RT fidelity protection + skippable fluid cap
        rb_fluid_pso_in p1 = {.fluid_on = 1, .ref_profile = 0, .may_skip = 1, .storage_writes = 0, .persistent_rt = 0,
                              .course_exact = 1, .async_pso = 1, .observed_first = 1, .fluid_ms = 6, .fluid_left_ms = 12,
                              .pso_wait_ms = 2000, .pso_unsafe_ms = 10000};
        rb_fluid_pso_out o1 = rb_fluid_pso_decide(&p1);
        if (o1.required || o1.wait_ms > 6) unbounded++;

        rb_fluid_pso_in p2 = p1;
        p2.persistent_rt = 1;
        p2.may_skip = 0;
        rb_fluid_pso_out o2 = rb_fluid_pso_decide(&p2);
        if (!o2.required || o2.fluid_cap) corrupt++;

        // Cold burst + warm Fair disk staging
        unsigned lim = 0;
        size_t blim = 0;
        int burst_ok = 0;
        rb_reg_policy(0, 120, 1, 0, &lim, &blim, &burst_ok);
        int xadmit = rb_reg_xlate_admit(burst_ok, 0, 0, 16, 4096, 1024);
        int w_fair = -1, w_ser = -1;
        int ok_fair = rb_disk_warm_admit(1, 0, 0, 0, 0, 0, 2048ull << 20, 1, &w_fair);
        int ok_ser = rb_disk_warm_admit(2, 0, 0, 0, 0, 0, 2048ull << 20, 1, &w_ser);
        assert(lim == 32 && burst_ok == 1 && xadmit == 1 && ok_fair == 1 && w_fair == 0 && ok_ser == 0);
        hash = fnv1a_u64(hash, (uint64_t)(o1.wait_ms ^ (o2.required << 4) ^ lim ^ (unsigned)xadmit));
    }
    double elapsed = now_ms() - t0;
    assert(corrupt == 0 && unbounded == 0);
    printf("{\"module\":\"M08_pso_cold_warm\",\"time_ms\":%.4f,\"ops\":%d,\"corrupt\":%d,\"unbounded\":%d,\"checksum\":\"%016llx\"}\n",
           elapsed, reps * 4, corrupt, unbounded, (unsigned long long)hash);
}

// ============================================================================
// M09: Streaming Candidate Bitset & Lock-Free pool_gpu Fast Path (REAL rb_treg_cand.h)
// ============================================================================
static rb_treg_cand_set g_cand;
static void run_m09_stream_pool_gpu(int verify_only) {
    const int calls = verify_only ? 50000 : 1000000;
    memset(&g_cand, 0, sizeof g_cand);
    for (uint32_t i = 0; i < 1024; i++) {
        if ((i & 3) == 0) rb_treg_cand_set_id(&g_cand, i);
    }
    uint64_t hits = 0, fast_ok = 0;
    double t0 = now_ms();
    for (int i = 0; i < calls; i++) {
        hits += (uint64_t)rb_treg_cand_test(&g_cand, (uint32_t)(i & 1023));
        fast_ok += (uint64_t)rb_pool_gpu_fast_ok(1, 1, 1, 0, 0, 0, 1, 1, (uint64_t)(i + 1));
    }
    double elapsed = now_ms() - t0;
    assert(hits == (uint64_t)(calls / 4) && fast_ok > (uint64_t)(calls - calls / 16384 - 2));
    printf("{\"module\":\"M09_stream_pool_gpu\",\"time_ms\":%.4f,\"ops\":%d,\"hits\":%llu,\"checksum\":\"%016llx\"}\n",
           elapsed, calls, (unsigned long long)hits, (unsigned long long)(hits ^ fast_ok));
}

// ============================================================================
// M10: Frame Generation & Frame Pacing Stability (REAL nvn_fi_rule.h + rb_thermal_pacing.h)
// ============================================================================
static void run_m10_frame_pacing_fi(int verify_only) {
    const int frames = verify_only ? 900 : 90000;
    int primed = 0, toggles = 0, prev_linked = 0;
    unsigned consec_dec = 0;
    dm_fi_link_hyst hyst;
    dm_fi_link_hyst_reset(&hyst);
    uint64_t hash = 0xcbf29ce484222325ull;
    double t0 = now_ms();
    for (int f = 0; f < frames; f++) {
        int allow = (f % 30 >= 10) ? 1 : 0;
        int want_prime = dm_fi_should_prime(1, allow, 1.0 / 30.0, 0, &consec_dec);
        primed += want_prime;
        int want_link = (f % 60 < 25) ? 1 : 0;
        int linked = dm_fi_link_hyst_step(&hyst, want_link);
        if (linked != prev_linked) { toggles++; prev_linked = linked; }
        uint64_t comp = rb_present_budget(1, 16666667ull);
        assert(comp == RB_PRESENT_COMP_NS);
        hash = fnv1a_u64(hash, (uint64_t)(want_prime ^ (linked << 1)));
    }
    double elapsed = now_ms() - t0;
    printf("{\"module\":\"M10_frame_pacing_fi\",\"time_ms\":%.4f,\"frames\":%d,\"primed\":%d,\"toggles\":%d,\"checksum\":\"%016llx\"}\n",
           elapsed, frames, primed, toggles, (unsigned long long)hash);
}

int main(int argc, char **argv) {
    int verify_only = 0;
    const char *only = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--verify-only")) verify_only = 1;
        else if (!strcmp(argv[i], "--only") && i + 1 < argc) only = argv[++i];
    }
    if (!only || !strcmp(only, "M01")) run_m01_deswizzle(verify_only);
    if (!only || !strcmp(only, "M02")) run_m02_hmap(verify_only);
    if (!only || !strcmp(only, "M03")) run_m03_pool_vbuf(verify_only);
    if (!only || !strcmp(only, "M04")) run_m04_args_ubo(verify_only);
    if (!only || !strcmp(only, "M05")) run_m05_tbdr_pass_cut(verify_only);
    if (!only || !strcmp(only, "M06")) run_m06_ubo_versions(verify_only);
    if (!only || !strcmp(only, "M07")) run_m07_dirty_stripes(verify_only);
    if (!only || !strcmp(only, "M08")) run_m08_pso_cold_warm(verify_only);
    if (!only || !strcmp(only, "M09")) run_m09_stream_pool_gpu(verify_only);
    if (!only || !strcmp(only, "M10")) run_m10_frame_pacing_fi(verify_only);
    return 0;
}
