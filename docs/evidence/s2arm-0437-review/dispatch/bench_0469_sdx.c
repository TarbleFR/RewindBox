// 0469: store lookahead index (nvn_mtl.m sdx_ev_add / nvn_be_sub_index counting sort), copied from S2Arm 0468.
// Baseline: the bucket of each event is looked up again twice in the sort. Candidate: the bucket found when
// the event is added is kept in a parallel uint16 array. Same events, same order, compared byte for byte.
#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef struct { uint32_t seq, rtseq; uint64_t ser; const uint8_t *op; uint16_t lv, sl; uint8_t kind, plane, anyls, why; } sdx_ev;
#define SDX_HB 2048
static uint64_t g_sdx_hk[SDX_HB]; static uint16_t g_sdx_hb[SDX_HB]; static uint32_t g_sdx_nb, g_sdx_bcnt[SDX_HB + 1], g_sdx_bst[SDX_HB + 1];
static sdx_ev *g_sdx, *g_sdx_tmp; static uint16_t *g_sdx_bk; static uint32_t g_sdx_n, g_sdx_cap; static int g_sdx_ok;
static int sdx_bucket(uint64_t ser, int add) {
    if (!ser) return -1;
    for (uint32_t i = (uint32_t)(ser * 0x9E3779B97F4A7C15ull >> 53), n = 0; n < SDX_HB; i = (i + 1) & (SDX_HB - 1), n++) {
        if (g_sdx_hk[i] == ser) return g_sdx_hb[i];
        if (!g_sdx_hk[i]) { if (!add) return -1; if (g_sdx_nb >= SDX_HB / 2) { g_sdx_ok = 0; return -1; } g_sdx_hk[i] = ser; g_sdx_hb[i] = (uint16_t)g_sdx_nb; return (int)g_sdx_nb++; }
    }
    return -1;
}
static int grow(void **p, size_t n) { void *q = realloc(*p, n); if (!q) return 0; *p = q; return 1; }
static __attribute__((noinline)) void add_old(sdx_ev e) { if (sdx_bucket(e.ser, 0) < 0) return; if (g_sdx_n == g_sdx_cap) { size_t c = g_sdx_cap ? g_sdx_cap * 2 : 4096; if (!grow((void **)&g_sdx, c * sizeof *g_sdx) || !grow((void **)&g_sdx_tmp, c * sizeof *g_sdx)) return; g_sdx_cap = c; } g_sdx[g_sdx_n++] = e; }
static __attribute__((noinline)) void add_new(sdx_ev e) { int b = sdx_bucket(e.ser, 0); if (b < 0) return; if (g_sdx_n == g_sdx_cap) { size_t c = g_sdx_cap ? g_sdx_cap * 2 : 4096; if (!grow((void **)&g_sdx, c * sizeof *g_sdx) || !grow((void **)&g_sdx_tmp, c * sizeof *g_sdx) || !grow((void **)&g_sdx_bk, c * sizeof *g_sdx_bk)) return; g_sdx_cap = c; } g_sdx_bk[g_sdx_n] = (uint16_t)b; g_sdx[g_sdx_n++] = e; }
static void sort_old(void) {
    memset(g_sdx_bcnt, 0, (g_sdx_nb + 1) * sizeof *g_sdx_bcnt);
    for (uint32_t i = 0; i < g_sdx_n; i++) g_sdx_bcnt[sdx_bucket(g_sdx[i].ser, 0)]++;
    for (uint32_t b = 0, acc = 0; b <= g_sdx_nb; b++) { g_sdx_bst[b] = acc; acc += b < g_sdx_nb ? g_sdx_bcnt[b] : 0; }
    for (uint32_t b = 0; b < g_sdx_nb; b++) g_sdx_bcnt[b] = g_sdx_bst[b];
    for (uint32_t i = 0; i < g_sdx_n; i++) g_sdx_tmp[g_sdx_bcnt[sdx_bucket(g_sdx[i].ser, 0)]++] = g_sdx[i];
    sdx_ev *t = g_sdx; g_sdx = g_sdx_tmp; g_sdx_tmp = t;
}
static void sort_new(void) {
    memset(g_sdx_bcnt, 0, (g_sdx_nb + 1) * sizeof *g_sdx_bcnt);
    for (uint32_t i = 0; i < g_sdx_n; i++) g_sdx_bcnt[g_sdx_bk[i]]++;
    for (uint32_t b = 0, acc = 0; b <= g_sdx_nb; b++) { g_sdx_bst[b] = acc; acc += b < g_sdx_nb ? g_sdx_bcnt[b] : 0; }
    for (uint32_t b = 0; b < g_sdx_nb; b++) g_sdx_bcnt[b] = g_sdx_bst[b];
    for (uint32_t i = 0; i < g_sdx_n; i++) g_sdx_tmp[g_sdx_bcnt[g_sdx_bk[i]]++] = g_sdx[i];
    sdx_ev *t = g_sdx; g_sdx = g_sdx_tmp; g_sdx_tmp = t;
}
static uint64_t rng(uint64_t *s) { *s ^= *s << 13; *s ^= *s >> 7; *s ^= *s << 17; return *s; }
// One submission: draws in render passes over `targets` attachments; each draw reads `reads` slots
// (a quarter of them attachments of earlier passes, the rest sampled-only textures not in the set) and
// records its colour + depth attachments; a pass starts with a clear of each attachment
static uint64_t submit(int nw, uint64_t seed, int draws, int targets, int reads) {
    memset(g_sdx_hk, 0, sizeof g_sdx_hk); g_sdx_nb = 0; g_sdx_n = 0; g_sdx_ok = 1;
    uint64_t s = seed | 1; uint32_t seq = 0, rtseq = 0; uint64_t c = 0, d = 0;
    void (*add)(sdx_ev) = nw ? add_new : add_old;
    for (int k = 0; k < draws && g_sdx_ok; k++) {
        if (k % 48 == 0) { c = 1 + rng(&s) % (uint64_t)targets; d = 1 + (uint64_t)targets + rng(&s) % (uint64_t)targets; rtseq = seq++;
            sdx_bucket(c, 1); sdx_bucket(d, 1);
            add((sdx_ev){seq, rtseq, c, 0, 0, 0, 4, 0, 0, 0}); add((sdx_ev){seq++, rtseq, d, 0, 0, 0, 4, 1, 0, 0}); }
        for (int r = 0; r < reads; r++) { uint64_t x = rng(&s); uint64_t ser = (x & 3) ? 100000 + (x >> 8) % 4096 : 1 + (x >> 8) % (uint64_t)(2 * targets);
            add((sdx_ev){seq, 0, ser, 0, 0, 0, 1, 0, 0, 1}); }
        add((sdx_ev){seq, rtseq, c, 0, 0, 0, 3, 0, 0, 2}); add((sdx_ev){seq, rtseq, d, 0, 0, 0, 3, 8, 0, 2}); seq++;
    }
    (nw ? sort_new : sort_old)();
    uint64_t h = 0xcbf29ce484222325ull; const unsigned char *b = (const unsigned char *)g_sdx;
    for (size_t i = 0; i < (size_t)g_sdx_n * sizeof *g_sdx; i++) h = (h ^ b[i]) * 0x100000001b3ull;
    for (uint32_t i = 0; i <= g_sdx_nb; i++) h = (h ^ g_sdx_bst[i]) * 0x100000001b3ull;
    return h ^ g_sdx_n;
}
static double now_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e3 + t.tv_nsec * 1e-6; }
static uint64_t run(int nw, int subs, int draws, int targets, int reads, double *ms) {
    free(g_sdx); free(g_sdx_tmp); free(g_sdx_bk); g_sdx = g_sdx_tmp = NULL; g_sdx_bk = NULL; g_sdx_cap = 0;   // each variant grows its own arrays
    uint64_t h = 0; double t0 = now_ms();
    for (int i = 0; i < subs; i++) h = h * 31 + submit(nw, 0x9e37 + (uint64_t)i, draws, targets, reads);
    *ms = now_ms() - t0; return h;
}
static int cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }
int main(int argc, char **argv) {
    int verify = argc > 1 && !strcmp(argv[1], "--verify");
    struct { int draws, targets, reads; } R[] = {{300, 8, 4}, {1500, 24, 6}, {4000, 64, 8}};
    for (unsigned g = 0; g < 3; g++) {
        int subs = verify ? 20 : 400; double a, b;
        uint64_t h = run(0, subs, R[g].draws, R[g].targets, R[g].reads, &a); assert(run(1, subs, R[g].draws, R[g].targets, R[g].reads, &b) == h);
        if (verify) { printf("VERIFY PASS regime %u hash %016llx events %u buckets %u\n", g, (unsigned long long)h, g_sdx_n, g_sdx_nb); continue; }
        enum { P = 12 }; double o[P], n[P], p[P];
        for (int i = 0; i < P; i++) { int f = i & 1;
            for (int k = 0; k < 2; k++) { int nw = f ^ k; double t; assert(run(nw, subs, R[g].draws, R[g].targets, R[g].reads, &t) == h); if (nw) n[i] = t; else o[i] = t; }
            p[i] = 100 * (n[i] / o[i] - 1); }
        qsort(o, P, 8, cmp); qsort(n, P, 8, cmp); qsort(p, P, 8, cmp);
        printf("regime draws=%d targets=%d reads=%d events/sub=%u: old_med=%.3f new_med=%.3f ms (%d subs) paired_med=%.2f%% p25=%.2f%% p75=%.2f%%\n",
               R[g].draws, R[g].targets, R[g].reads, g_sdx_n, (o[5] + o[6]) / 2, (n[5] + n[6]) / 2, subs, (p[5] + p[6]) / 2, (p[2] + p[3]) / 2, (p[8] + p[9]) / 2);
    }
    free(g_sdx); free(g_sdx_tmp); free(g_sdx_bk); return 0;
}
