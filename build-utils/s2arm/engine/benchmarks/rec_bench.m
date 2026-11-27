// macOS-only measurement of the encode-thread dispatch share in nvn_rec.h (S2Arm 0467):
// the real Objective-C runtime's objc_msgSend per record (as rec_exec does for every record
// but RO_T_ADDR) against a per-class cached IMP for every record, and a fresh DmRecEnc-like
// stand-in per pass ([X new] + release) against a reused one. The method bodies are trivial
// stand-ins: the result bounds the dispatch share only. It is not a Metal driver cost, a game
// replay, an iPhone measurement or a frame-time claim.
// cc -O3 -fobjc-arc -framework Foundation rec_bench.m -o rec_bench
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static inline uint64_t mix(uint64_t h, uint64_t v) { return (h ^ v) * 0x100000001b3ull; }

@interface BEnc : NSObject { @public uint64_t h; }
- (void)setRenderPipelineState:(uint64_t)p;
- (void)setDepthStencilState:(uint64_t)s;
- (void)setViewport:(uint64_t)a y:(uint64_t)b;
- (void)setScissor:(uint64_t)a w:(uint64_t)b;
- (void)setCullMode:(uint64_t)m;
- (void)setStencilFront:(uint64_t)f back:(uint64_t)b;
- (void)drawIndexed:(uint64_t)p count:(uint64_t)n buffer:(uint64_t)g;
- (void)setArgumentTable:(uint64_t)t atStages:(uint64_t)s;
- (void)endEncoding;
@end
@implementation BEnc
- (void)setRenderPipelineState:(uint64_t)p { h = mix(h, 3ull << 48 ^ p); }
- (void)setDepthStencilState:(uint64_t)s { h = mix(h, 4ull << 48 ^ s); }
- (void)setViewport:(uint64_t)a y:(uint64_t)b { h = mix(h, 5ull << 48 ^ a ^ b * 3); }
- (void)setScissor:(uint64_t)a w:(uint64_t)b { h = mix(h, 6ull << 48 ^ a ^ b * 3); }
- (void)setCullMode:(uint64_t)m { h = mix(h, 7ull << 48 ^ m); }
- (void)setStencilFront:(uint64_t)f back:(uint64_t)b { h = mix(h, 8ull << 48 ^ f ^ b * 3); }
- (void)drawIndexed:(uint64_t)p count:(uint64_t)n buffer:(uint64_t)g { h = mix(h, 9ull << 48 ^ p ^ n * 3 ^ g * 7); }
- (void)setArgumentTable:(uint64_t)t atStages:(uint64_t)s { h = mix(h, 2ull << 48 ^ t ^ s * 3); }
- (void)endEncoding { h = mix(h, 1ull << 48); }
@end
@interface BTab : NSObject { @public uint64_t h; }
- (void)setAddress:(uint64_t)g atIndex:(NSUInteger)i;
- (void)setTexture:(uint64_t)t atIndex:(NSUInteger)i;
- (void)setSamplerState:(uint64_t)t atIndex:(NSUInteger)i;
@end
@implementation BTab
- (void)setAddress:(uint64_t)g atIndex:(NSUInteger)i { h = mix(h, 13ull << 48 ^ g ^ i * 3); }
- (void)setTexture:(uint64_t)t atIndex:(NSUInteger)i { h = mix(h, 14ull << 48 ^ t ^ i * 3); }
- (void)setSamplerState:(uint64_t)t atIndex:(NSUInteger)i { h = mix(h, 15ull << 48 ^ t ^ i * 3); }
@end
@interface BStandIn : NSObject { @public int render; } @end
@implementation BStandIn @end

enum { O_PSO, O_DSS, O_VP, O_SC, O_CULL, O_SREF, O_DRAW, O_TABLE, O_END, O_ADDR, O_TEX, O_SAMP };
typedef struct { uint32_t op; uint64_t a[3]; } rec;

// Record mix per draw as in the 0468 draft: 2 table addresses, a draw, every 4th draw a pipeline,
// depth state, viewport, scissor, texture and sampler, every 8th cull mode and stencil reference
static size_t build(rec *r, int passes, int draws) {
    size_t n = 0;
    for (int p = 0; p < passes; p++) {
        r[n++] = (rec){O_TABLE, {1, 31, 0}};
        for (int d = 0; d < draws; d++) {
            uint64_t g = 0x100000ull + (uint64_t)(p * 256 + d * 16);
            if (!(d & 3)) { r[n++] = (rec){O_PSO, {g}}; r[n++] = (rec){O_DSS, {g + 1}}; r[n++] = (rec){O_VP, {1280, 720}}; r[n++] = (rec){O_SC, {0, 1280}}; }
            if (!(d & 7)) { r[n++] = (rec){O_CULL, {2}}; r[n++] = (rec){O_SREF, {(uint64_t)d & 255, (uint64_t)d & 255}}; }
            r[n++] = (rec){O_ADDR, {g, 0}}; r[n++] = (rec){O_ADDR, {g + 64, 1}};
            if (!(d & 3)) { r[n++] = (rec){O_TEX, {g + 128, 2}}; r[n++] = (rec){O_SAMP, {g + 192, 3}}; }
            r[n++] = (rec){O_DRAW, {3, 36, g}};
        }
        r[n++] = (rec){O_END, {0, 0, 0}};
    }
    return n;
}

// Baseline: rec_exec as in 0467, setAddress:atIndex: through an IMP cached per table class, the rest objc_msgSend
static __attribute__((noinline)) void exec_base(const rec *r, size_t n, BEnc *e, BTab *t) {
    static Class tc; static void (*tf)(id, SEL, uint64_t, NSUInteger);
    for (size_t i = 0; i < n; i++) { const uint64_t *a = r[i].a;
        switch (r[i].op) {
        case O_PSO: [e setRenderPipelineState:a[0]]; break;
        case O_DSS: [e setDepthStencilState:a[0]]; break;
        case O_VP: [e setViewport:a[0] y:a[1]]; break;
        case O_SC: [e setScissor:a[0] w:a[1]]; break;
        case O_CULL: [e setCullMode:a[0]]; break;
        case O_SREF: [e setStencilFront:a[0] back:a[1]]; break;
        case O_DRAW: [e drawIndexed:a[0] count:a[1] buffer:a[2]]; break;
        case O_TABLE: [e setArgumentTable:a[0] atStages:a[1]]; break;
        case O_END: [e endEncoding]; break;
        case O_ADDR: { Class k = object_getClass(t);
            if (k != tc || !tf) { tf = (void (*)(id, SEL, uint64_t, NSUInteger))class_getMethodImplementation(k, @selector(setAddress:atIndex:)); tc = k; }
            tf(t, @selector(setAddress:atIndex:), a[0], a[1]); break; }
        case O_TEX: [t setTexture:a[0] atIndex:a[1]]; break;
        case O_SAMP: [t setSamplerState:a[0] atIndex:a[1]]; break;
        }
    }
}
// Candidate: every record through an IMP cached per receiver class (looked up again when the class changes)
typedef void (*f1)(id, SEL, uint64_t); typedef void (*f2)(id, SEL, uint64_t, uint64_t); typedef void (*f3)(id, SEL, uint64_t, uint64_t, uint64_t); typedef void (*f0)(id, SEL);
static struct { Class ec, tc; IMP i[12]; } g_c;
#define IMPF(k, cls, sel) (g_c.i[k] ? g_c.i[k] : (g_c.i[k] = class_getMethodImplementation(cls, sel)))
static __attribute__((noinline)) void exec_cand(const rec *r, size_t n, BEnc *e, BTab *t) {
    Class ek = object_getClass(e), tk = object_getClass(t);
    if (ek != g_c.ec) { for (int k = 0; k < 9; k++) g_c.i[k] = NULL; g_c.ec = ek; }
    if (tk != g_c.tc) { for (int k = 9; k < 12; k++) g_c.i[k] = NULL; g_c.tc = tk; }
    for (size_t i = 0; i < n; i++) { const uint64_t *a = r[i].a;
        switch (r[i].op) {
        case O_PSO: ((f1)IMPF(O_PSO, ek, @selector(setRenderPipelineState:)))(e, @selector(setRenderPipelineState:), a[0]); break;
        case O_DSS: ((f1)IMPF(O_DSS, ek, @selector(setDepthStencilState:)))(e, @selector(setDepthStencilState:), a[0]); break;
        case O_VP: ((f2)IMPF(O_VP, ek, @selector(setViewport:y:)))(e, @selector(setViewport:y:), a[0], a[1]); break;
        case O_SC: ((f2)IMPF(O_SC, ek, @selector(setScissor:w:)))(e, @selector(setScissor:w:), a[0], a[1]); break;
        case O_CULL: ((f1)IMPF(O_CULL, ek, @selector(setCullMode:)))(e, @selector(setCullMode:), a[0]); break;
        case O_SREF: ((f2)IMPF(O_SREF, ek, @selector(setStencilFront:back:)))(e, @selector(setStencilFront:back:), a[0], a[1]); break;
        case O_DRAW: ((f3)IMPF(O_DRAW, ek, @selector(drawIndexed:count:buffer:)))(e, @selector(drawIndexed:count:buffer:), a[0], a[1], a[2]); break;
        case O_TABLE: ((f2)IMPF(O_TABLE, ek, @selector(setArgumentTable:atStages:)))(e, @selector(setArgumentTable:atStages:), a[0], a[1]); break;
        case O_END: ((f0)IMPF(O_END, ek, @selector(endEncoding)))(e, @selector(endEncoding)); break;
        case O_ADDR: ((f2)IMPF(O_ADDR, tk, @selector(setAddress:atIndex:)))(t, @selector(setAddress:atIndex:), a[0], a[1]); break;
        case O_TEX: ((f2)IMPF(O_TEX, tk, @selector(setTexture:atIndex:)))(t, @selector(setTexture:atIndex:), a[0], a[1]); break;
        case O_SAMP: ((f2)IMPF(O_SAMP, tk, @selector(setSamplerState:atIndex:)))(t, @selector(setSamplerState:atIndex:), a[0], a[1]); break;
        }
    }
}
static uint64_t ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec; }
static volatile uintptr_t g_sink;
// Stand-in per pass: [BStandIn new] + release (0467) or one reused object
static __attribute__((noinline)) uint64_t standins(int fresh, int n) {
    BStandIn *keep = [BStandIn new]; uint64_t t0 = ns();
    for (int i = 0; i < n; i++) {
        if (fresh) { BStandIn *s = [BStandIn new]; s->render = i & 1; g_sink += (uintptr_t)(__bridge void *)s; }
        else { keep->render = i & 1; g_sink += (uintptr_t)(__bridge void *)keep; }
    }
    return ns() - t0;
}

// Submit side (patch 0469): the wrapper's call to the stand-in (objc_msgSend + the stand-in's method writing the record) against the same record written directly after a class test
typedef struct { uint32_t op, nobj; uint64_t a[15]; } srec;
enum { SREC_N = 1 << 16 };
static srec g_srec[SREC_N]; static uint32_t g_sn; static uint64_t g_sh;
static inline srec *sput(uint32_t op) { if (g_sn == SREC_N) { for (uint32_t i = 0; i < g_sn; i++) g_sh = mix(g_sh, g_srec[i].op ^ g_srec[i].a[0] ^ g_srec[i].a[1] * 3 ^ g_srec[i].a[2] * 7 ^ g_srec[i].a[7] * 11); g_sn = 0; } srec *r = &g_srec[g_sn++]; r->op = op; r->nobj = 0; return r; }
static inline void sw_pso(uint64_t p) { sput(O_PSO)->a[0] = p; }
static inline void sw_dss(uint64_t p) { sput(O_DSS)->a[0] = p; }
static inline void sw_vp(uint64_t a, uint64_t b) { srec *r = sput(O_VP); r->a[0] = a; r->a[1] = b; }
static inline void sw_sc(uint64_t a, uint64_t b) { srec *r = sput(O_SC); r->a[0] = a; r->a[1] = b; }
static inline void sw_cull(uint64_t m) { sput(O_CULL)->a[0] = m; }
static inline void sw_sref(uint64_t f, uint64_t b) { srec *r = sput(O_SREF); r->a[0] = f; r->a[1] = b; }
static inline void sw_draw(uint64_t p, uint64_t n, uint64_t g) { srec *r = sput(O_DRAW); r->a[0] = p; r->a[1] = n; r->a[2] = 1; r->a[3] = g; r->a[4] = 4096; r->a[5] = 1; r->a[6] = 0; r->a[7] = 0; }
@interface BStand : NSObject
- (void)setRenderPipelineState:(uint64_t)p; - (void)setDepthStencilState:(uint64_t)s; - (void)setViewport:(uint64_t)a y:(uint64_t)b; - (void)setScissor:(uint64_t)a w:(uint64_t)b;
- (void)setCullMode:(uint64_t)m; - (void)setStencilFront:(uint64_t)f back:(uint64_t)b; - (void)drawIndexed:(uint64_t)p count:(uint64_t)n buffer:(uint64_t)g;
@end
@implementation BStand
- (void)setRenderPipelineState:(uint64_t)p { sw_pso(p); } - (void)setDepthStencilState:(uint64_t)s { sw_dss(s); } - (void)setViewport:(uint64_t)a y:(uint64_t)b { sw_vp(a, b); }
- (void)setScissor:(uint64_t)a w:(uint64_t)b { sw_sc(a, b); } - (void)setCullMode:(uint64_t)m { sw_cull(m); } - (void)setStencilFront:(uint64_t)f back:(uint64_t)b { sw_sref(f, b); }
- (void)drawIndexed:(uint64_t)p count:(uint64_t)n buffer:(uint64_t)g { sw_draw(p, n, g); }
@end
static inline int sdirect(id e) { static Class k; if (__builtin_expect(!k, 0)) k = [BStand class]; return e && object_getClass(e) == k; }
static __attribute__((noinline)) void submit_side(int direct, id e, int passes, int draws) {
    for (int p = 0; p < passes; p++) for (int d = 0; d < draws; d++) {
        uint64_t g = 0x100000ull + (uint64_t)(p * 256 + d * 16);
        if (!(d & 3)) {
            if (direct && sdirect(e)) sw_pso(g); else [e setRenderPipelineState:g];
            if (direct && sdirect(e)) sw_dss(g + 1); else [e setDepthStencilState:g + 1];
            if (direct && sdirect(e)) sw_vp(1280, 720); else [e setViewport:1280 y:720];
            if (direct && sdirect(e)) sw_sc(0, 1280); else [e setScissor:0 w:1280];
        }
        if (!(d & 7)) { if (direct && sdirect(e)) sw_cull(2); else [e setCullMode:2]; if (direct && sdirect(e)) sw_sref((uint64_t)d & 255, (uint64_t)d & 255); else [e setStencilFront:(uint64_t)d & 255 back:(uint64_t)d & 255]; }
        if (direct && sdirect(e)) sw_draw(3, 36, g); else [e drawIndexed:3 count:36 buffer:g];
    }
}
static uint64_t submit_hash(void) { uint64_t h = g_sh; for (uint32_t i = 0; i < g_sn; i++) h = mix(h, g_srec[i].op ^ g_srec[i].a[0] ^ g_srec[i].a[1] * 3 ^ g_srec[i].a[2] * 7 ^ g_srec[i].a[7] * 11); return h ^ g_sn; }
static uint64_t submit_run(int direct, id e, double *ns_per_call, uint64_t *calls) {
    g_sn = 0; g_sh = 0; enum { SP = 512, SD = 64, SR = 40 }; uint64_t t0 = ns();
    for (int r = 0; r < SR; r++) submit_side(direct, e, SP, SD);
    uint64_t c = (uint64_t)SR * SP * (SD + SD / 4 * 4 + SD / 8 * 2); *calls = c; *ns_per_call = (double)(ns() - t0) / (double)c; return submit_hash();
}
static int cmpd(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }
int main(void) { @autoreleasepool {
    enum { PASSES = 512, DRAWS = 64, REPEAT = 40, PAIRS = 12, STANDINS = 200000 };
    rec *r = malloc(sizeof(rec) * (size_t)PASSES * (DRAWS * 13 + 2)); size_t n = build(r, PASSES, DRAWS);
    BEnc *e0 = [BEnc new], *e1 = [BEnc new]; BTab *t0 = [BTab new], *t1 = [BTab new];
    exec_base(r, n, e0, t0); exec_cand(r, n, e1, t1);   // warm-up, then the parity check
    if (e0->h != e1->h || t0->h != t1->h) { fprintf(stderr, "PARITY FAIL\n"); return 1; }
    double base[PAIRS], cand[PAIRS], pct[PAIRS], sf[PAIRS], sr[PAIRS], spct[PAIRS];
    printf("kind,pair,variant,ns_per_record_or_object,hash\n");
    for (int p = 0; p < PAIRS; p++) {
        for (int k = 0; k < 2; k++) {
            int c = (p & 1) ^ k; BEnc *e = c ? e1 : e0; BTab *t = c ? t1 : t0; uint64_t s = ns();
            for (int rep = 0; rep < REPEAT; rep++) (c ? exec_cand : exec_base)(r, n, e, t);
            double v = (double)(ns() - s) / ((double)n * REPEAT); if (c) cand[p] = v; else base[p] = v;
        }
        if (e0->h != e1->h || t0->h != t1->h) { fprintf(stderr, "PARITY FAIL pair %d\n", p); return 1; }
        printf("dispatch,%d,base,%.4f,%016llx\ndispatch,%d,cached_imp,%.4f,%016llx\n", p, base[p], (unsigned long long)(e0->h ^ t0->h), p, cand[p], (unsigned long long)(e1->h ^ t1->h));
        pct[p] = 100.0 * (cand[p] / base[p] - 1.0);
        for (int k = 0; k < 2; k++) { int fresh = !((p & 1) ^ k); double v = (double)standins(fresh, STANDINS) / STANDINS; if (fresh) sf[p] = v; else sr[p] = v; }
        printf("standin,%d,fresh,%.4f,0\nstandin,%d,reused,%.4f,0\n", p, sf[p], p, sr[p]);
        spct[p] = sf[p] - sr[p];
    }
    qsort(base, PAIRS, 8, cmpd); qsort(cand, PAIRS, 8, cmpd); qsort(pct, PAIRS, 8, cmpd); qsort(sf, PAIRS, 8, cmpd); qsort(sr, PAIRS, 8, cmpd); qsort(spct, PAIRS, 8, cmpd);
    fprintf(stderr, "records/pass %zu; dispatch ns/record median base %.4f cached_imp %.4f paired %.2f%% (p25 %.2f%%, p75 %.2f%%); stand-in ns median fresh %.2f reused %.2f paired diff %.2f ns (p25 %.2f, p75 %.2f)\n",
            n / PASSES, (base[5] + base[6]) / 2, (cand[5] + cand[6]) / 2, (pct[5] + pct[6]) / 2, (pct[2] + pct[3]) / 2, (pct[8] + pct[9]) / 2,
            (sf[5] + sf[6]) / 2, (sr[5] + sr[6]) / 2, (spct[5] + spct[6]) / 2, (spct[2] + spct[3]) / 2, (spct[8] + spct[9]) / 2);
    {   // Submit side (patch 0469)
        BStand *st = [BStand new]; double a, b; uint64_t calls, h0 = submit_run(0, st, &a, &calls), h1 = submit_run(1, st, &b, &calls);
        if (h0 != h1) { fprintf(stderr, "SUBMIT PARITY FAIL\n"); return 1; }
        double sb[PAIRS], sc[PAIRS], sp[PAIRS];
        for (int p = 0; p < PAIRS; p++) {
            for (int k = 0; k < 2; k++) { int d = (p & 1) ^ k; double v; if (submit_run(d, st, &v, &calls) != h0) { fprintf(stderr, "SUBMIT PARITY FAIL pair %d\n", p); return 1; } if (d) sc[p] = v; else sb[p] = v; }
            printf("submit,%d,message,%.4f,%016llx\nsubmit,%d,direct,%.4f,%016llx\n", p, sb[p], (unsigned long long)h0, p, sc[p], (unsigned long long)h0);
            sp[p] = 100.0 * (sc[p] / sb[p] - 1.0);
        }
        qsort(sb, PAIRS, 8, cmpd); qsort(sc, PAIRS, 8, cmpd); qsort(sp, PAIRS, 8, cmpd);
        fprintf(stderr, "submit side: %llu calls a sample; ns/call median message %.4f direct %.4f paired %.2f%% (p25 %.2f%%, p75 %.2f%%)\n", (unsigned long long)calls,
                (sb[5] + sb[6]) / 2, (sc[5] + sc[6]) / 2, (sp[5] + sp[6]) / 2, (sp[2] + sp[3]) / 2, (sp[8] + sp[9]) / 2);
    }
    free(r);
    return 0;
} }
