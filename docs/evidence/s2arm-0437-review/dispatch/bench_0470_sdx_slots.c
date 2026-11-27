// 0470: store lookahead walk (nvn_mtl.m sdx_walk), the draw whose program is not loaded yet (prog_peek nil).
// Baseline (S2Arm 0468): such a draw scans all 6 x (NTEX + 32) = 1 728 slots of g_pp_slot and adds a READ
// event for each live one. Candidate: each stage keeps the list of its live slots, rebuilt only after a
// bind touched that stage (one OR per bind op on the walk's hot path). Same events, same order: the list is
// ascending, and a slot is only listed when non-zero. Events, buckets and order hashed byte for byte.
// Regimes: share of draws whose program is not loaded (0 %: steady frames, the cost is the OR per bind).
#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define NTEX 256
#define NS (NTEX + 32)
typedef struct { uint32_t seq, rtseq; uint64_t ser; const uint8_t *op; uint16_t lv, sl; uint8_t kind, plane, anyls, why; } sdx_ev;
#define SDX_HB 2048
static uint64_t g_sdx_hk[SDX_HB]; static uint16_t g_sdx_hb[SDX_HB]; static uint32_t g_sdx_nb;
static sdx_ev *g_sdx; static uint32_t g_sdx_n, g_sdx_cap; static int g_sdx_ok;
static uint64_t g_pp_slot[6][NS];
static uint16_t g_pp_live[6][NS], g_pp_nlive[6]; static uint8_t g_pp_ldirty;   // candidate
static int sdx_bucket(uint64_t ser, int add) {
    if (!ser) return -1;
    for (uint32_t i = (uint32_t)(ser * 0x9E3779B97F4A7C15ull >> 53), n = 0; n < SDX_HB; i = (i + 1) & (SDX_HB - 1), n++) {
        if (g_sdx_hk[i] == ser) return g_sdx_hb[i];
        if (!g_sdx_hk[i]) { if (!add) return -1; if (g_sdx_nb >= SDX_HB / 2) { g_sdx_ok = 0; return -1; } g_sdx_hk[i] = ser; g_sdx_hb[i] = (uint16_t)g_sdx_nb; return (int)g_sdx_nb++; }
    }
    return -1;
}
static __attribute__((noinline)) void sdx_ev_add(sdx_ev e) {
    if (sdx_bucket(e.ser, 0) < 0) return;
    if (g_sdx_n == g_sdx_cap) { size_t c = g_sdx_cap ? g_sdx_cap * 2 : 4096; void *q = realloc(g_sdx, c * sizeof *g_sdx); if (!q) { g_sdx_ok = 0; return; } g_sdx = q; g_sdx_cap = (uint32_t)c; }
    g_sdx[g_sdx_n++] = e;
}
static uint64_t rng(uint64_t *s) { *s ^= *s << 13; *s ^= *s >> 7; *s ^= *s << 17; return *s; }
// Synthetic command stream, decoded once per submission: binds (stage, first, n, serials) and draws (program loaded or not, reads).
enum { OPB = 1, OPD = 2 };
typedef struct { uint8_t op, stage, n, loaded; uint16_t first; uint64_t ser[8]; uint16_t reads[8]; uint8_t nreads; } op_t;
static op_t *g_ops; static int g_nops;
static void make(uint64_t seed, int draws, int nil_pct, int targets) {
    uint64_t s = seed | 1; g_nops = 0;
    free(g_ops); g_ops = calloc((size_t)draws * 4 + 16, sizeof *g_ops);
    for (int k = 0; k < draws; k++) {
        int nb = 1 + (int)(rng(&s) % 3);   // 1-3 bind ops a draw: fragment mostly, vertex sometimes
        for (int b = 0; b < nb; b++) { op_t *o = &g_ops[g_nops++]; o->op = OPB; o->stage = (rng(&s) % 4) ? 4 : 0;
            o->n = (uint8_t)(1 + rng(&s) % 8); o->first = (uint16_t)(rng(&s) % 24); if (rng(&s) % 16 == 0) o->first += NTEX;   // an image slot now and then
            for (int i = 0; i < o->n; i++) { uint64_t x = rng(&s); o->ser[i] = (x % 11 == 0) ? 0 : ((x & 3) ? 100000 + (x >> 8) % 4096 : 1 + (x >> 8) % (uint64_t)(2 * targets)); } }
        op_t *d = &g_ops[g_nops++]; d->op = OPD; d->loaded = (int)(rng(&s) % 100) >= nil_pct;
        d->nreads = (uint8_t)(2 + rng(&s) % 6); for (int i = 0; i < d->nreads; i++) d->reads[i] = (uint16_t)(rng(&s) % 32);
    }
}
static uint64_t submit(int nw, uint64_t seed, int targets) {
    memset(g_sdx_hk, 0, sizeof g_sdx_hk); g_sdx_nb = 0; g_sdx_n = 0; g_sdx_ok = 1;
    for (int t = 1; t <= 2 * targets; t++) sdx_bucket((uint64_t)t, 1);
    uint64_t s = seed | 1;
    for (int st = 0; st < 6; st++) for (int k = 0; k < NS; k++) g_pp_slot[st][k] = (k < 12 && (st == 0 || st == 4)) ? 1 + rng(&s) % (uint64_t)(2 * targets) : 0;
    g_pp_ldirty = 0x3f;
    for (int i = 0; i < g_nops && g_sdx_ok; i++) { const op_t *o = &g_ops[i]; uint32_t seq = (uint32_t)i;
        if (o->op == OPB) {
            if (o->stage < 6 && o->first + o->n <= NS) { for (int k = 0; k < o->n; k++) g_pp_slot[o->stage][o->first + k] = o->ser[k]; if (nw) g_pp_ldirty |= (uint8_t)(1u << o->stage); }
            continue;
        }
        if (!o->loaded) {
            if (!nw) { for (int st = 0; st < 6; st++) for (int k = 0; k < NS; k++) if (g_pp_slot[st][k]) sdx_ev_add((sdx_ev){seq, 0, g_pp_slot[st][k], 0, 0, 0, 1, 0, 0, 1}); }
            else for (int st = 0; st < 6; st++) {
                if (g_pp_ldirty & (1u << st)) { uint16_t n = 0; for (int k = 0; k < NS; k++) if (g_pp_slot[st][k]) g_pp_live[st][n++] = (uint16_t)k; g_pp_nlive[st] = n; g_pp_ldirty &= (uint8_t)~(1u << st); }
                for (int j = 0; j < g_pp_nlive[st]; j++) sdx_ev_add((sdx_ev){seq, 0, g_pp_slot[st][g_pp_live[st][j]], 0, 0, 0, 1, 0, 0, 1});
            }
        } else for (int r = 0; r < o->nreads; r++) { uint64_t ser = g_pp_slot[4][o->reads[r]]; if (ser) sdx_ev_add((sdx_ev){seq, 0, ser, 0, 0, 0, 1, 0, 0, 1}); }
        sdx_ev_add((sdx_ev){seq, 0, 1, 0, 0, 0, 3, 0, 0, 2});   // its colour attachment
    }
    uint64_t h = 0xcbf29ce484222325ull; const unsigned char *b = (const unsigned char *)g_sdx;
    for (size_t i = 0; i < (size_t)g_sdx_n * sizeof *g_sdx; i++) h = (h ^ b[i]) * 0x100000001b3ull;
    return h ^ g_sdx_n ^ ((uint64_t)g_sdx_nb << 40);
}
static double now_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e3 + t.tv_nsec * 1e-6; }
static uint64_t run(int nw, int subs, int targets, double *ms) {
    uint64_t h = 0; double t0 = now_ms();
    for (int i = 0; i < subs; i++) h = h * 31 + submit(nw, 0x51 + (uint64_t)i, targets);
    *ms = now_ms() - t0; return h;
}
static int cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }
int main(int argc, char **argv) {
    int verify = argc > 1 && !strcmp(argv[1], "--verify");
    int nil[] = {0, 2, 10, 100};
    for (unsigned g = 0; g < 4; g++) {
        make(0x9e37 + g, 2000, nil[g], 24);
        int subs = verify ? 8 : 200; double a, b;
        uint64_t h = run(0, subs, 24, &a); uint32_t ev = g_sdx_n; assert(run(1, subs, 24, &b) == h);
        if (verify) { printf("VERIFY PASS nil=%d%% hash %016llx events/sub %u\n", nil[g], (unsigned long long)h, ev); continue; }
        enum { P = 12 }; double o[P], n[P], p[P];
        for (int i = 0; i < P; i++) { int f = i & 1;
            for (int k = 0; k < 2; k++) { int nw = f ^ k; double t; assert(run(nw, subs, 24, &t) == h); if (nw) n[i] = t; else o[i] = t; }
            p[i] = 100 * (n[i] / o[i] - 1); }
        qsort(o, P, 8, cmp); qsort(n, P, 8, cmp); qsort(p, P, 8, cmp);
        printf("nil=%3d%% draws=2000 events/sub=%u: old_med=%.3f new_med=%.3f ms (%d subs) paired_med=%.2f%% p25=%.2f%% p75=%.2f%% min=%.2f%% max=%.2f%%\n",
               nil[g], ev, (o[5] + o[6]) / 2, (n[5] + n[6]) / 2, subs, (p[5] + p[6]) / 2, (p[2] + p[3]) / 2, (p[8] + p[9]) / 2, p[0], p[P - 1]);
    }
    free(g_sdx); free(g_ops); return 0;
}
