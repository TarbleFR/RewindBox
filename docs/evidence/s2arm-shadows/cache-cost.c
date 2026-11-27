#define _POSIX_C_SOURCE 200809L
#include "rb_dsnap_rule.h"
#include <stdio.h>
#include <time.h>

enum { OPERATIONS = 65536, REPEATS = 32 };
static rb_dsnap_slot samples[OPERATIONS][RB_DSNAP_SLOTS];
static uint32_t writes[OPERATIONS];

static uint64_t now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

static __attribute__((noinline)) void coarse(rb_dsnap_slot *slot, uint32_t level) {
    (void)level;
    rb_dsnap_cache_stale_tex(slot, 7, 0x100000, 0x80000, 1, 1);
}

static __attribute__((noinline)) void scoped(rb_dsnap_slot *slot, uint32_t level) {
    for (int i = 0; i < RB_DSNAP_SLOTS; ++i) {
        rb_dsnap_slot *s = &slot[i];
        if (rb_dsnap_outside_write(s, 7, 8, level, 0, 1)) continue;
        if (rb_dsnap_tex_stales(s->ser, s->lo, s->hi, 7, 0x100000, 0x80000))
            s->depth_valid = s->stencil_valid = 0;
    }
}

static unsigned run(int mode) {
    unsigned retained = 0;
    for (size_t r = 0; r < REPEATS; ++r)
        for (size_t i = 0; i < OPERATIONS; ++i) {
            rb_dsnap_slot slot[RB_DSNAP_SLOTS] = {samples[i][0], samples[i][1]};
            if (mode) scoped(slot, writes[i]);
            else coarse(slot, writes[i]);
            retained += slot[0].depth_valid + slot[1].depth_valid;
        }
    return retained;
}

int main(void) {
    uint32_t random = 1681;
    for (size_t i = 0; i < OPERATIONS; ++i) {
        random = random * 1664525u + 1013904223u;
        writes[i] = (random >> 13) & 3;
        unsigned alias = (random >> 10) & 1;
        samples[i][0] = (rb_dsnap_slot){.ser=7,.base=8,.tl=0,.ts=0,.nl=1,.lo=0x100000,.hi=0x180000,.depth_valid=1,.stencil_valid=1};
        samples[i][1] = (rb_dsnap_slot){.ser=9,.base=10,.tl=1,.ts=0,.nl=1,
             .lo=alias?0x140000:0x200000,.hi=alias?0x1c0000:0x280000,.depth_valid=1,.stencil_valid=1};
    }
    puts("pair,scope,elapsed_ns_per_clear,retained_slots");
    for (int i = 0; i < 9; ++i) for (int j = 0; j < 2; ++j) {
        int scope = (i+j) % 2;
        uint64_t start = now();
        unsigned retained = run(scope);
        uint64_t length = now() - start;
        printf("%d,%s,%.3f,%u\n", i+1, scope?"scoped":"coarse", length/(double)(OPERATIONS*REPEATS), retained);
    }
}
