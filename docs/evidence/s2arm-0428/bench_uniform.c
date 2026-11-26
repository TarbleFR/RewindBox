#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "rb_ubo_versions.h"

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
static uint64_t xorshift64(uint64_t *s) {
    uint64_t x = *s;
    x ^= x << 13; x ^= x >> 7; x ^= x << 17;
    return (*s = x);
}

static rb_ub_versions g_ring;
_Alignas(4096) static uint8_t g_guest[8 * 1024 * 1024];

static void run_scenario(const char *name, int disjoint_hazards, int ubo_pages, unsigned offset, int verify) {
    memset(&g_ring, 0, sizeof g_ring);
    uint64_t base_addr = (uintptr_t)g_guest;
    // Synthetic workload sized from a Zelda window. Addresses and hazards are generated.
    const int FRAMES = 300;
    const int INFLIGHT = 32;
    const int HAZARDS_PER_FRAME = 180;
    const int CAPTURES_PER_FRAME = 80;
    const int LOOKUPS_PER_FRAME = 54;

    uint64_t rng = 0x517cc1b727220a95ull ^ ((uint64_t)disjoint_hazards << 8) ^ (uint64_t)ubo_pages;
    uint64_t fnv = 14695981039346656037ull;
    uint64_t ok_n = 0, fail_opaque = 0;

    uint8_t out[4096], have[4096], payload[512];
    for (int i = 0; i < 512; i++) payload[i] = (uint8_t)((i * 73u + 5u) & 0xffu);

    uint64_t t_hazard = 0, t_capture = 0, t_lookup = 0;
    uint64_t t0 = now_ns();

    for (int f = 1; f <= FRAMES; f++) {
        rb_ub_frame *fr = rb_ub_begin(&g_ring, (uint64_t)f);

        uint64_t th0 = now_ns();
        for (int h = 0; h < HAZARDS_PER_FRAME; h++) {
            uint64_t r = xorshift64(&rng);
            uint64_t off;
            if (disjoint_hazards) {
                off = (h & 2) ? ((r >> 8) % (2u * 1024u * 1024u - 256u))
                              : (6u * 1024u * 1024u + ((r >> 8) % (2u * 1024u * 1024u - 256u)));
            } else {
                off = 2u * 1024u * 1024u + ((r >> 8) % ((uint64_t)ubo_pages * 4096u - 256u));
            }
            off &= ~15ull;
            uint64_t sz = 16u + ((r >> 24) & 240u);
            if (h & 1) rb_ub_transfer(fr, base_addr + off, sz);
            else rb_ub_opaque(fr, base_addr + off, sz);
        }
        t_hazard += now_ns() - th0;

        uint64_t tc0 = now_ns();
        for (int c = 0; c < CAPTURES_PER_FRAME; c++) {
            uint64_t r = xorshift64(&rng);
            uint64_t off = 2u * 1024u * 1024u + ((r % (uint64_t)ubo_pages) * 4096u) + ((r >> 12) & 3584u);
            size_t sz = 64u + ((r >> 24) & 192u);
            payload[0] = (uint8_t)(f ^ c);
            rb_ub_capture(fr, base_addr + off, sz, payload);
        }
        t_capture += now_ns() - tc0;

        uint64_t tl0 = now_ns();
        uint64_t done = f > INFLIGHT ? (uint64_t)(f - INFLIGHT) : 0;
        for (int q = 0; q < LOOKUPS_PER_FRAME; q++) {
            uint64_t r = xorshift64(&rng);
            uint64_t off = 2u * 1024u * 1024u + ((r % (uint64_t)ubo_pages) * 4096u) + ((r >> 12) & 2048u);
            off += offset;
            size_t len = (q % 4 == 0) ? 2048u : (q % 4 == 1) ? 1024u : 256u;
            memset(have, 0, len);
            size_t cov_a = (r >> 20) % (len / 2);
            size_t cov_n = 64u + ((r >> 28) % 128u);
            if (cov_a + cov_n > len) cov_n = len - cov_a;
            memset(have + cov_a, 1, cov_n);
            memset(out, 0xA5, len);
            int why = 0;
            int ok = rb_ub_base_ex(&g_ring, done, (uint64_t)f, base_addr + off, base_addr + off + len, out, have, &why);
            fnv = (fnv ^ (uint64_t)ok ^ ((uint64_t)why << 4)) * 1099511628211ull;
            if (verify) {
                for (size_t k = 0; k < len; ++k) {
                    fnv = (fnv ^ out[k]) * 1099511628211ull;
                    fnv = (fnv ^ have[k]) * 1099511628211ull;
                }
            }
            if (ok) {
                ok_n++;
                for (size_t k = 0; k < len; k += 17)
                    fnv = (fnv ^ out[k]) * 1099511628211ull;
            } else if (why == RB_UB_FAIL_OPAQUE) fail_opaque++;
        }
        t_lookup += now_ns() - tl0;
    }

    printf("%-16s total=%6.2f ms (hazard=%5.2f capture=%5.2f lookup=%6.2f) ok=%5llu fail=%5llu hash=%016llx\n",
           name, (now_ns() - t0) / 1e6, t_hazard / 1e6, t_capture / 1e6, t_lookup / 1e6,
           (unsigned long long)ok_n, (unsigned long long)fail_opaque, (unsigned long long)fnv);
}

int main(int argc, char **argv) {
    int verify = argc == 2 && strcmp(argv[1], "--verify") == 0;
    for (size_t i = 0; i < sizeof g_guest; i++) g_guest[i] = (uint8_t)((i * 131u + 17u) & 0xffu);
    run_scenario("hot", 1, 12, 0, verify);
    run_scenario("pages64", 1, 64, 0, verify);
    run_scenario("overlap", 0, 128, 0, verify);
    run_scenario("unaligned", 1, 12, 7, verify);
    run_scenario("crosspage", 1, 12, 3073, verify);
    run_scenario("cross_overlap", 0, 128, 3073, verify);
    return 0;
}
