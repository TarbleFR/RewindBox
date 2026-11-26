#include "nvn_deswizzle.h"
#include <assert.h>
#include <time.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
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
            uint32_t state = 193u; for (size_t i = 0; i < L.size; i++) {state ^= state << 13; state ^= state >> 17; state ^= state << 5; bl[i] = (uint8_t)state;}

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
            double dur=now_ms()-t0; elapsed += dur; printf("%d %s %.6f\n",sw2,cases[c].name,dur);
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
int main(void){run_m01_deswizzle(0);return 0;}
