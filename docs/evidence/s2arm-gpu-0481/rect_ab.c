#define _POSIX_C_SOURCE 200809L
#include "nvn_deswizzle.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int nvn_deswizzle_rect_2d(const nvn_texdesc *d, const void *storage, size_t storage_size,
                          uint32_t xbyte, uint32_t yrow, uint32_t width_bytes, uint32_t rows,
                          void *dst);

enum { Guard = 37, Pairs = 12, Repeats = 8 };
static unsigned comparisons, refusals, padded_layouts;
static volatile uint64_t sink;

static void fill(uint8_t *p, size_t length) {
    uint32_t state = 0xc45e28f1;
    for (size_t i = 0; i < length; ++i) {
        state ^= state << 13; state ^= state >> 17; state ^= state << 5;
        p[i] = (uint8_t)state;
    }
}

static size_t reference_offset(unsigned x, unsigned y, unsigned height_gobs,
                               unsigned width_gobs, int switch2) {
    size_t block_bytes = 512ul * height_gobs;
    size_t base = (size_t)(y / (8 * height_gobs)) * width_gobs * block_bytes
        + (size_t)(x / 64) * block_bytes + (y / 8 % height_gobs) * 512u;
    unsigned within = (x % 64 / 32) * 256 + x % 16;
    if (switch2) within += (y % 8 / 4) * 128 + (x % 32 / 16) * 64
        + (y % 4 / 2) * 32 + (y % 2) * 16;
    else within += (y % 8 / 2) * 64 + (x % 32 / 16) * 32 + (y % 2) * 16;
    return base + within;
}

static void parity(nvn_texdesc d) {
    nvn_texlayout layout;
    nvn_tex_layout(&d, &layout);
    int bw, bh;
    unsigned bpb = nvn_fmt_bpb(d.format, &bw, &bh);
    assert(bpb > 0);
    unsigned pitch = ((d.width + bw - 1) / bw) * bpb;
    unsigned height = (d.height + bh - 1) / bh;
    unsigned gobs = nvn_tex_level_gobs(&d, 0);
    unsigned th, td;
    nvn_tex_level_tiles(&d, 0, &th, &td);
    assert(td == 0 && layout.size > 0);
    padded_layouts += gobs > (pitch + 63u) / 64;
    uint8_t *src = malloc(layout.size);
    uint8_t *full = malloc((size_t)pitch * height);
    assert(src && full);
    fill(src, layout.size);
    assert(nvn_deswizzle(&d, 0, 0, src, full, pitch) == 0);
    for (unsigned ry = 0; ry < height; ry += 8) {
        for (unsigned rx = 0; rx < pitch; rx += 64) {
            unsigned w = pitch - rx;
            unsigned h = height - ry;
            if ((rx / 64 + ry / 8) % 3) {
                if (w > 64) w = 64;
                if (h > 8) h = 8;
            }
            size_t n = (size_t)w * h;
            uint8_t *out = malloc(n + 2 * Guard);
            assert(out); memset(out, 0xa5, n + 2 * Guard);
            assert(nvn_deswizzle_rect_2d(&d, src, layout.size, rx, ry, w, h, out + Guard) == 0);
            for (unsigned y = 0; y < h; ++y) {
                assert(!memcmp(out + Guard + (size_t)y*w, full + (size_t)(ry+y)*pitch + rx, w));
                for (unsigned x = 0; x < w; ++x) {
                    size_t offset = reference_offset(rx+x, ry+y, 1u << th, gobs, nvn_gob_switch2);
                    assert(offset < layout.size && src[offset] == out[Guard + (size_t)y*w+x]);
                }
            }
            for (unsigned i = 0; i < Guard; ++i) assert(out[i] == 0xa5 && out[Guard+n+i] == 0xa5);
            ++comparisons; free(out);
        }
    }
    free(src); free(full);
}

static void invalid(nvn_texdesc d, size_t capacity, unsigned x, unsigned y, unsigned w, unsigned h) {
    uint8_t src[8192], out[8192];
    memset(src, 0x56, sizeof src); memset(out, 0xa5, sizeof out);
    assert(capacity <= sizeof src);
    assert(nvn_deswizzle_rect_2d(&d, src, capacity, x, y, w, h, out + Guard) != 0);
    for (size_t i=0; i<sizeof out; ++i) assert(out[i] == 0xa5);
    ++refusals;
}

static void verify(void) {
    struct { int fmt; unsigned w, h; } cases[] = {
        {0x25, 259, 37}, {0x42, 259, 133}, {0x8b, 387, 197}, {0x25, 3, 5}
    };
    const int layouts[] = {0, 1, 1 + (2 << 8) + 1};
    for (int order = 0; order < 2; ++order) {
        nvn_gob_switch2 = order;
        for (unsigned c = 0; c < sizeof cases/sizeof *cases; ++c) {
            for (unsigned l = 0; l < sizeof layouts/sizeof *layouts; ++l) {
                nvn_texdesc d = {.target=1,.format=cases[c].fmt,.width=cases[c].w,
                    .height=cases[c].h,.depth=1,.levels=1,.samples=1,.pkg_layout=layouts[l]};
                parity(d);
            }
        }
    }
    assert(padded_layouts);
    nvn_texdesc d = {.target=1,.format=0x25,.width=64,.height=32,.levels=1,.samples=1,.depth=1};
    invalid(d, 0, 0, 0, 64, 8); invalid(d, 1, 0, 0, 64, 8);
    invalid(d, 512, 64, 16, 64, 8);
    invalid(d, 8192, 0, 0, 0, 8); invalid(d, 8192, 0, 0, 64, 0);
    invalid(d, 8192, 1, 0, 64, 8); invalid(d, 8192, 0, 1, 64, 8);
    invalid(d, 8192, 192, 24, 65, 8); invalid(d, 8192, 192, 24, 64, 9);
    invalid(d, 8192, 0, 0, UINT32_MAX, 8); invalid(d, 8192, 0, 0, 64, UINT32_MAX);
    d.target=2; invalid(d, 8192, 0, 0, 64, 8); d.target=1;
    d.levels=2; invalid(d, 8192, 0, 0, 64, 8); d.levels=1;
    d.samples=4; invalid(d, 8192, 0, 0, 64, 8); d.samples=1;
    d.flags=0x10; invalid(d, 8192, 0, 0, 64, 8);
    d.flags=0x40; invalid(d, 8192, 0, 0, 64, 8);
    d.flags=0x20; invalid(d, 8192, 0, 0, 64, 8);
    printf("verified %u independent byte-and-crop comparisons, %u untouched refusal outputs, %u padded layouts\n",
           comparisons, refusals, padded_layouts);
}

static uint64_t nanos(void) {
    struct timespec t;
    assert(clock_gettime(CLOCK_MONOTONIC, &t) == 0);
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + t.tv_nsec;
}

static void time_load(unsigned pages) {
    nvn_texdesc d = {.target=1,.format=0x25,.width=2048,.height=2048,.depth=1,.levels=1,.samples=1};
    nvn_texlayout layout;
    nvn_tex_layout(&d, &layout);
    nvn_gob_switch2 = 1;
    const unsigned pitch = 8192, height = 2048, rw=128, rh=128;
    assert(layout.tileH == 4 && layout.size == (size_t)pitch*height);
    uint8_t *src=malloc(layout.size), *full=malloc(layout.size), *rect=malloc((size_t)pages*rw*rh);
    assert(src && full && rect); fill(src,layout.size);
    memset(full,0,layout.size); memset(rect,0,(size_t)pages*rw*rh);
    puts("pair,position,mode,calls,output_bytes_per_call,wall_ns");
    for (int pair = -1; pair < Pairs; ++pair) {
        for (unsigned pos=0; pos < 2; ++pos) {
            int tight=(pos != 0) ^ (pair >= 0 && (pair & 1));
            uint64_t begin=nanos();
            for (unsigned it=0; it < Repeats; ++it) {
                unsigned key=(unsigned)(pair+1)*17u+it*61u;
                unsigned x=(key%64u)*rw, y=((key/64u)%16u)*rh;
                int rc;
                if (tight) {
                    rc=0;
                    for (unsigned page=0; page<pages; page++) {
                        unsigned at=(key + page*181u) % 1024u;
                        x=(at%64u)*rw; y=(at/64u)*rh;
                        rc |= nvn_deswizzle_rect_2d(&d,src,layout.size,x,y,rw,rh,
                                                    rect + (size_t)page*rw*rh);
                        sink += rect[(size_t)page*rw*rh];
                    }
                } else {
                    rc=nvn_deswizzle(&d,0,0,src,full,pitch);
                    sink += full[(size_t)y*pitch+x];
                }
                assert(rc == 0);
            }
            uint64_t elapsed=nanos()-begin;
            if (pair >= 0) printf("%d,%u,%s,%d,%zu,%" PRIu64 "\n",pair+1,pos+1,
                tight?"rect":"full",Repeats,tight?(size_t)pages*rw*rh:layout.size,elapsed);
        }
    }
    free(src); free(full); free(rect);
}

int main(int argc, char **argv) {
    if (argc == 1) verify();
    else if (argc == 2 && !strcmp(argv[1], "--time")) time_load(1);
    else if (argc == 3 && !strcmp(argv[1], "--time-pages")) {
        unsigned pages = (unsigned)strtoul(argv[2], NULL, 10);
        if (!pages || pages > 1024) return 2;
        time_load(pages);
    }
    else return 2;
    return 0;
}
