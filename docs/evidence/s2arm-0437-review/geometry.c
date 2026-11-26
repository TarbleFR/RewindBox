#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "nvn_tex.h"
#include "nvn_deswizzle.h"

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static uint64_t mix64(uint64_t h, uint64_t v) {
    h ^= v + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2);
    return h;
}

int main(void) {
    static const int targets[] = {0, 1, 2, 3, 4, 8, 9, 10};
    static const int formats[] = {0x01, 0x0d, 0x25, 0x42, 0x44, 0x45, 0x8b, 0x9a};
    static const int flags_v[] = {0, 0x20, 0x40, 0x200, 0x220};
    static const uint32_t dims_v[] = {32, 64, 100, 260, 512, 700, 1024};
    static const int pkgs[] = {0, 1, 4, (4 << 8) + 4};
    nvn_texdesc cases[4096];
    int nc = 0;
    for (int ti = 0; ti < 8 && nc < 4096; ti++)
    for (int fi = 0; fi < 8 && nc < 4096; fi++)
    for (int fl = 0; fl < 5 && nc < 4096; fl++)
    for (int di = 0; di < 7 && nc < 4096; di++)
    for (int pi = 0; pi < 4 && nc < 4096; pi++) {
        if ((ti + fi + fl + di + pi) % 3 != 0) continue;
        uint32_t w = dims_v[di], h = dims_v[(di + 2) % 7];
        uint32_t depth = targets[ti] == 2 ? 16 : (targets[ti] == 4 ? 6 : (targets[ti] == 9 ? 12 : 1));
        uint32_t levels = (flags_v[fl] & 0x40) || targets[ti] == 10 ? 1 : 6;
        cases[nc++] = (nvn_texdesc){targets[ti], formats[fi], flags_v[fl], 0, w, h, depth, levels, 0, pkgs[pi]};
    }

    // Check parity hash across ALL APIs
    uint64_t h = 0x123456789abcdef0ull;
    for (int i = 0; i < nc; i++) {
        const nvn_texdesc *d = &cases[i];
        nvn_texlayout L;
        nvn_tex_layout(d, &L);
        h = mix64(h, L.size); h = mix64(h, L.layer_size);
        h = mix64(h, ((uint64_t)L.align << 32) | ((uint64_t)L.layers << 16) | ((uint64_t)L.tileH << 8) | L.tileD);
        uint32_t st[4] = {0}; nvn_tex_sparse_layout(d, st);
        h = mix64(h, ((uint64_t)st[0] << 32) | st[1]);
        h = mix64(h, ((uint64_t)st[2] << 32) | st[3]);
        uint32_t tw = 0, ths = 0, tds = 0;
        int nst = nvn_tex_sparse_tiles(d, &tw, &ths, &tds);
        h = mix64(h, ((uint64_t)(uint32_t)nst << 32) | (tw ^ ths ^ tds));
        for (unsigned lv = 0; lv < d->levels; lv++) {
            uint64_t off = nvn_tex_level_offset(d, lv);
            uint32_t gobs = nvn_tex_level_gobs(d, lv);
            unsigned th = 0, td = 0;
            nvn_tex_level_tiles(d, lv, &th, &td);
            h = mix64(h, off);
            h = mix64(h, ((uint64_t)gobs << 16) | (th << 8) | td);
            for (unsigned lay = 0; lay < (L.layers > 2 ? 2 : L.layers); lay++) {
                uint32_t rb = 0, rows = 0, sl = 0, bpb = 0;
                uint64_t base = 0; unsigned gth = 0, gtd = 0;
                int rc = nvn_deswizzle_geom(d, lv, lay, &rb, &rows, &sl, &base, &gth, &gtd, &bpb);
                h = mix64(h, (uint64_t)(rc + 2));
                if (rc == 0) {
                    h = mix64(h, base);
                    h = mix64(h, ((uint64_t)rb << 32) | rows);
                    h = mix64(h, ((uint64_t)sl << 32) | (bpb << 16) | (gth << 8) | gtd);
                }
            }
        }
    }

    // Timing: realistic streamed mip/tile geometry query burst (200k queries)
    nvn_texdesc hot[8] = {
        {1, 0x25, 0,     0, 1024, 1024, 1, 11, 0, 0},       // RGBA8 1024x1024 11 mips
        {1, 0x44, 0,     0, 2048, 2048, 1, 12, 0, 0},       // BC7/BC3 2048x2048 12 mips
        {1, 0x8b, 0x20,  0, 1024, 1024, 1, 11, 0, 0},       // ASTC 6x6 sparse 1024x1024
        {1, 0x25, 0x200, 0, 260,  260,  1, 9,  0, 0},       // MINIMAL_LAYOUT terrain
        {4, 0x44, 0,     0, 512,  512,  8, 10, 0, 0},       // 2D_ARRAY 8 layers
        {2, 0x25, 0,     0, 64,   64,   64, 7, 0, 0},       // 3D LUT
        {1, 0x8b, 0x20,  0, 512,  512,  1, 10, 0, (4<<8)+4},// packaged sparse
        {1, 0x42, 0,     0, 128,  128,  1, 8,  0, 0},       // BC1 small streamed
    };
    uint64_t t0 = now_ns();
    uint64_t acc = 0;
    for (int r = 0; r < 25000; r++) {
        for (int i = 0; i < 8; i++) {
            uint32_t rb = 0, rows = 0, sl = 0, bpb = 0;
            uint64_t base = 0; unsigned th = 0, td = 0;
            unsigned lv = (unsigned)(r & 3);
            unsigned lay = hot[i].target == 4 ? (unsigned)(r & 3) : 0u;
#ifdef USE_GEOM_EX
            uint32_t gobs = 0;
            if (nvn_deswizzle_geom_ex(&hot[i], lv, lay, &rb, &rows, &sl, &base, &th, &td, &bpb, &gobs) == 0)
                acc += base + rb + rows + sl + th + td + bpb + gobs;
#else
            if (nvn_deswizzle_geom(&hot[i], lv, lay, &rb, &rows, &sl, &base, &th, &td, &bpb) == 0)
                acc += base + rb + rows + sl + th + td + bpb + nvn_tex_level_gobs(&hot[i], lv);
#endif
        }
    }
    uint64_t dt = now_ns() - t0;
    printf("cases=%d hash=0x%016llx acc=0x%016llx ms=%.3f\n",
           nc, (unsigned long long)h, (unsigned long long)acc, (double)dt / 1e6);
    return 0;
}
