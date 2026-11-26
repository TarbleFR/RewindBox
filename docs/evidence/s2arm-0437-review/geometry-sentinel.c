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
    static const int flags_v[] = {0,0x10,0x20,0x40,0x60,0x200,0x220};
    static const int samp[] = {0,1,2,4,8,16}; static const int pkg[] = {0,1,4,0x404,0x31};
    int nc = 36000; nvn_texdesc *cases = calloc(nc,sizeof(*cases)); unsigned s=0x07654321u;
    for(int n=0;n<nc;n++){
        s = 1664525u*s+1013904223u; uint32_t a=s;
        s = 1664525u*s+1013904223u; uint32_t b=s;
        s = 1664525u*s+1013904223u; uint32_t c=s;
        cases[n]=(nvn_texdesc){a%11,(a>>8)%192,flags_v[(a>>16)%7],samp[(a>>24)%6],
                 1+(b%2048),1+((b>>12)%1024),1+((b>>24)%12),(c%13),0,pkg[(c>>8)%5]};
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
        h=mix64(h,nst); h=mix64(h,tw); h=mix64(h,ths); h=mix64(h,tds);
        for (unsigned lv = 0; lv <= (d->levels?d->levels:1)+1; lv++) {
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

    printf("count=%d digest=%016llx\n",nc,(unsigned long long)h); free(cases);
}
