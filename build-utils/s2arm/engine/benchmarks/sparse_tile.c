// Run after applying the candidate to S2Arm sources:
// cc -O2 -I graphics/nvn/gfx/tex /path/to/RewindBox/build-utils/s2arm/engine/benchmarks/sparse_tile.c graphics/nvn/gfx/tex/nvn_deswizzle.c graphics/nvn/gfx/nvn/nvn_tex.c -o /tmp/bench_sparse
#define _POSIX_C_SOURCE 200809L
#include "nvn_deswizzle.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

enum { TILE = 65536, SAMPLES = 9, TILES_PER_PASS = 1024 };
static uint64_t nanoseconds(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) abort();
    return (uint64_t)t.tv_sec * 1000000000 + (uint64_t)t.tv_nsec;
}

static int compare(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

static void bench(unsigned working_tiles) {
    nvn_texdesc d = {.target = 1, .format = 0x44, .flags = 0x20, .width = 8192,
                     .height = 8192, .depth = 1, .levels = 1, .pkg_layout = 4};
    const size_t size = (size_t)working_tiles * TILE;
    uint8_t *src = malloc(size), *dst = malloc(size);
    if (!src || !dst) abort();
    for (size_t i = 0; i < size; i++) { src[i] = (uint8_t)(i ^ (i >> 7)); dst[i] = 0; }
    uint64_t times[2][SAMPLES], sum[2] = {0,0};
    nvn_gob_switch2 = 1;
    for (int sample = -1; sample < SAMPLES; sample++) {
        for (int arm = 0; arm < 2; arm++) {
            int grouped = (sample + arm + 1) & 1;
            uint64_t start = nanoseconds();
            for (unsigned n = 0; n < TILES_PER_PASS; n++) {
                size_t offset = (size_t)(n % working_tiles) * TILE;
                uint32_t width, rows;
                if (nvn_deswizzle_tile_mode(&d, 0, 0, 0, src + offset, dst + offset, 1024, &width, &rows, grouped)
                    || width != 1024 || rows != 64) abort();
            }
            uint64_t elapsed = nanoseconds() - start;
            if (sample >= 0) times[grouped][sample] = elapsed;
            for (size_t i = 0; i < size; i += 127) sum[grouped] += dst[i];
        }
    }
    if (sum[0] != sum[1]) abort();
    for (int arm = 0; arm < 2; arm++) {
        qsort(times[arm], SAMPLES, sizeof times[arm][0], compare);
        printf("%u working tiles, grouped=%d: median %.3f us/tile (min %.3f, max %.3f), checksum %" PRIu64 "\n",
            working_tiles, arm, times[arm][4] / (1000. * TILES_PER_PASS),
            times[arm][0] / (1000. * TILES_PER_PASS), times[arm][8] / (1000. * TILES_PER_PASS), sum[arm]);
    }
    free(dst); free(src);
}

int main(void) { bench(1); bench(1024); }
