#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "rb_draw_fast_rule.h"

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

typedef struct { double originX, originY, width, height, znear, zfar; } FakeVP;
typedef struct { size_t x, y, width, height; } FakeSC;
typedef struct { int x, y, w, h; } p_scissor;
typedef struct { int cull, front, mode, offset_en; } poly_st;
typedef struct { float factor, units, clamp; } p_poly_offset;

typedef struct {
    unsigned ok;
    int previous_widen;
    uint32_t sref[2];
    FakeVP vp;
    FakeSC sc;
    int cull, wind, fill, clip, origin_ll, rast_flip;
    float bias[3], blend[4];
} EdState;

typedef struct {
    uint32_t st_ref[2];
    int has_vp, has_sc, depth_clamp;
    float vp[4], dr[2], blend_color[4];
    uint8_t vp_sw[4];
    p_scissor sc;
    poly_st poly;
    p_poly_offset po;
    int tw, th;
    double rs;
    uint64_t pass_serial;
    int dss_dirty, wd, origin_ll, rast_flip;
} DrawIn;

typedef struct {
    uint64_t emits;
    uint64_t hash;
    int drawn;
} Trace;

static inline void mix(Trace *t, uint64_t v) {
    t->emits++;
    t->hash ^= v + 0x9E3779B97F4A7C15ull + (t->hash << 6) + (t->hash >> 2);
}

static int encoder_diff(const EdState *a, const EdState *b) {
    return a->ok != b->ok || memcmp(a->sref,b->sref,sizeof a->sref) ||
       memcmp(&a->vp,&b->vp,sizeof a->vp) || memcmp(&a->sc,&b->sc,sizeof a->sc) ||
       a->cull != b->cull || a->wind != b->wind || a->fill != b->fill || a->clip != b->clip ||
       memcmp(a->bias,b->bias,sizeof a->bias) || memcmp(a->blend,b->blend,sizeof a->blend);
}

static int run_orig(const DrawIn *in, EdState *ed, uint64_t *cur_ds_pass, int *dss_dirty, Trace *tr) {
    if (*dss_dirty || *cur_ds_pass != in->pass_serial) { *cur_ds_pass = in->pass_serial; *dss_dirty = 0; mix(tr, 1); }
    if (!(ed->ok & RB_ED_SREF) || ed->sref[0] != in->st_ref[0] || ed->sref[1] != in->st_ref[1]) {
        mix(tr, 0x10000ull | ((uint64_t)in->st_ref[0] << 8) | in->st_ref[1]);
        ed->sref[0] = in->st_ref[0]; ed->sref[1] = in->st_ref[1]; ed->ok |= RB_ED_SREF;
    }
    FakeVP v = in->has_vp
        ? (FakeVP){in->vp[0], in->vp[1], in->vp[2], in->vp[3], in->dr[0], in->dr[1]}
        : (FakeVP){0, 0, in->tw / in->rs, in->th / in->rs, 0, 1};
    if (in->wd > 0) { v.originX += 1.0; v.width += 2.0; }
    if (in->rs != 1.0) { v.originX *= in->rs; v.originY *= in->rs; v.width *= in->rs; v.height *= in->rs; }
    if (in->origin_ll) { v.originY += v.height; v.height = -v.height; }
    uint32_t sw; memcpy(&sw, in->vp_sw, 4);
    if (sw == 0x100) { v.originY += v.height; v.height = -v.height; }
    if (!(ed->ok & RB_ED_VP) || memcmp(&ed->vp, &v, sizeof v)) {
        uint64_t b0 = 0; memcpy(&b0, &v.width, 8);
        mix(tr, 0x20000ull ^ b0);
        ed->vp = v; ed->ok |= RB_ED_VP;
    }
    FakeSC sc = {0, 0, (size_t)in->tw, (size_t)in->th};
    if (in->has_sc) {
        long sx = in->sc.x + (in->wd > 0 ? 1 : 0), sy = in->sc.y, sww = in->sc.w, sh = in->sc.h;
        long x0 = sx < 0 ? 0 : sx, y0 = sy <= 0 ? 0 : sy, x1 = sx + sww, y1 = sy + sh;
        if (x1 > in->tw) x1 = in->tw; if (y1 > in->th) y1 = in->th;
        if (x1 <= x0 || y1 <= y0) return 0;
        sc = (FakeSC){(size_t)x0, (size_t)y0, (size_t)(x1 - x0), (size_t)(y1 - y0)};
    }
    if (!(ed->ok & RB_ED_SC) || memcmp(&ed->sc, &sc, sizeof sc)) {
        mix(tr, 0x30000ull ^ ((uint64_t)sc.x << 24) ^ ((uint64_t)sc.width << 8) ^ sc.height);
        ed->sc = sc; ed->ok |= RB_ED_SC;
    }
    if (in->poly.cull == 3) return 0;
    int cu = in->poly.cull, wi = (in->poly.front == 1) != (in->rast_flip != 0), fi = in->poly.mode, cl = !in->depth_clamp;
    float bi[3] = {0, 0, 0}; if (in->poly.offset_en & 4) { bi[0] = in->po.units; bi[1] = in->po.factor; bi[2] = in->po.clamp; }
    if (!(ed->ok & RB_ED_CULL) || ed->cull != cu) { mix(tr, 0x40000ull | (uint64_t)cu); ed->cull = cu; ed->ok |= RB_ED_CULL; }
    if (!(ed->ok & RB_ED_WIND) || ed->wind != wi) { mix(tr, 0x50000ull | (uint64_t)wi); ed->wind = wi; ed->ok |= RB_ED_WIND; }
    if (!(ed->ok & RB_ED_FILL) || ed->fill != fi) { mix(tr, 0x60000ull | (uint64_t)fi); ed->fill = fi; ed->ok |= RB_ED_FILL; }
    if (!(ed->ok & RB_ED_BIAS) || memcmp(ed->bias, bi, sizeof bi)) { uint32_t u = 0; memcpy(&u, &bi[0], 4); mix(tr, 0x70000ull ^ u); memcpy(ed->bias, bi, sizeof bi); ed->ok |= RB_ED_BIAS; }
    if (!(ed->ok & RB_ED_CLIP) || ed->clip != cl) { mix(tr, 0x80000ull | (uint64_t)cl); ed->clip = cl; ed->ok |= RB_ED_CLIP; }
    if (!(ed->ok & RB_ED_BLEND) || memcmp(ed->blend, in->blend_color, sizeof ed->blend)) { uint32_t u = 0; memcpy(&u, &in->blend_color[0], 4); mix(tr, 0x90000ull ^ u); memcpy(ed->blend, in->blend_color, sizeof ed->blend); ed->ok |= RB_ED_BLEND; }
    return 1;
}

static int run_fast(const DrawIn *in, EdState *ed, uint64_t *cur_ds_pass, int *dss_dirty, unsigned *ed_dirty, Trace *tr) {
    if (ed->previous_widen || in->wd) *ed_dirty |= RB_ED_VP | RB_ED_SC;
    ed->previous_widen = in->wd;
    const unsigned need = rb_ed_effective_dirty(ed->ok, *ed_dirty, in->wd > 0, in->origin_ll, ed->origin_ll, in->rast_flip, ed->rast_flip);
    if (__builtin_expect(!*dss_dirty && *cur_ds_pass == in->pass_serial && need == 0, 1)) return 1;
    if (*dss_dirty || *cur_ds_pass != in->pass_serial) { *cur_ds_pass = in->pass_serial; *dss_dirty = 0; mix(tr, 1); }
    if (!need) return 1;
    if ((need & RB_ED_SREF) && (!(ed->ok & RB_ED_SREF) || ed->sref[0] != in->st_ref[0] || ed->sref[1] != in->st_ref[1])) {
        mix(tr, 0x10000ull | ((uint64_t)in->st_ref[0] << 8) | in->st_ref[1]);
        ed->sref[0] = in->st_ref[0]; ed->sref[1] = in->st_ref[1]; ed->ok |= RB_ED_SREF;
    }
    if (need & RB_ED_VP) {
        FakeVP v = in->has_vp
            ? (FakeVP){in->vp[0], in->vp[1], in->vp[2], in->vp[3], in->dr[0], in->dr[1]}
            : (FakeVP){0, 0, in->tw / in->rs, in->th / in->rs, 0, 1};
        if (in->wd > 0) { v.originX += 1.0; v.width += 2.0; }
        if (in->rs != 1.0) { v.originX *= in->rs; v.originY *= in->rs; v.width *= in->rs; v.height *= in->rs; }
        if (in->origin_ll) { v.originY += v.height; v.height = -v.height; }
        uint32_t sw; memcpy(&sw, in->vp_sw, 4);
        if (sw == 0x100) { v.originY += v.height; v.height = -v.height; }
        if (!(ed->ok & RB_ED_VP) || memcmp(&ed->vp, &v, sizeof v)) {
            uint64_t b0 = 0; memcpy(&b0, &v.width, 8);
            mix(tr, 0x20000ull ^ b0);
            ed->vp = v; ed->ok |= RB_ED_VP;
        }
        ed->origin_ll = in->origin_ll;
    }
    if (need & RB_ED_SC) {
        FakeSC sc = {0, 0, (size_t)in->tw, (size_t)in->th};
        if (in->has_sc) {
            long sx = in->sc.x + (in->wd > 0 ? 1 : 0), sy = in->sc.y, sww = in->sc.w, sh = in->sc.h;
            long x0 = sx < 0 ? 0 : sx, y0 = sy <= 0 ? 0 : sy, x1 = sx + sww, y1 = sy + sh;
            if (x1 > in->tw) x1 = in->tw; if (y1 > in->th) y1 = in->th;
            if (x1 <= x0 || y1 <= y0) return 0;
            sc = (FakeSC){(size_t)x0, (size_t)y0, (size_t)(x1 - x0), (size_t)(y1 - y0)};
        }
        if (!(ed->ok & RB_ED_SC) || memcmp(&ed->sc, &sc, sizeof sc)) {
            mix(tr, 0x30000ull ^ ((uint64_t)sc.x << 24) ^ ((uint64_t)sc.width << 8) ^ sc.height);
            ed->sc = sc; ed->ok |= RB_ED_SC;
        }
    }
    if (need & (RB_ED_CULL | RB_ED_WIND | RB_ED_FILL | RB_ED_BIAS | RB_ED_CLIP | RB_ED_BLEND)) {
        if (in->poly.cull == 3) return 0;
        if (need & RB_ED_CULL) {
            int cu = in->poly.cull;
            if (!(ed->ok & RB_ED_CULL) || ed->cull != cu) { mix(tr, 0x40000ull | (uint64_t)cu); ed->cull = cu; ed->ok |= RB_ED_CULL; }
        }
        if (need & RB_ED_WIND) {
            int wi = (in->poly.front == 1) != (in->rast_flip != 0);
            if (!(ed->ok & RB_ED_WIND) || ed->wind != wi) { mix(tr, 0x50000ull | (uint64_t)wi); ed->wind = wi; ed->ok |= RB_ED_WIND; }
            ed->rast_flip = in->rast_flip;
        }
        if (need & RB_ED_FILL) {
            int fi = in->poly.mode;
            if (!(ed->ok & RB_ED_FILL) || ed->fill != fi) { mix(tr, 0x60000ull | (uint64_t)fi); ed->fill = fi; ed->ok |= RB_ED_FILL; }
        }
        if (need & RB_ED_BIAS) {
            float bi[3] = {0, 0, 0}; if (in->poly.offset_en & 4) { bi[0] = in->po.units; bi[1] = in->po.factor; bi[2] = in->po.clamp; }
            if (!(ed->ok & RB_ED_BIAS) || memcmp(ed->bias, bi, sizeof bi)) { uint32_t u = 0; memcpy(&u, &bi[0], 4); mix(tr, 0x70000ull ^ u); memcpy(ed->bias, bi, sizeof bi); ed->ok |= RB_ED_BIAS; }
        }
        if (need & RB_ED_CLIP) {
            int cl = !in->depth_clamp;
            if (!(ed->ok & RB_ED_CLIP) || ed->clip != cl) { mix(tr, 0x80000ull | (uint64_t)cl); ed->clip = cl; ed->ok |= RB_ED_CLIP; }
        }
        if (need & RB_ED_BLEND) {
            if (!(ed->ok & RB_ED_BLEND) || memcmp(ed->blend, in->blend_color, sizeof ed->blend)) { uint32_t u = 0; memcpy(&u, &in->blend_color[0], 4); mix(tr, 0x90000ull ^ u); memcpy(ed->blend, in->blend_color, sizeof ed->blend); ed->ok |= RB_ED_BLEND; }
        }
    }
    *ed_dirty = 0;
    return 1;
}

static uint64_t rng = 0xfeedfacecafebeefull;
static uint32_t r32(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return (uint32_t)rng; }

int main(void) {
    // The per-draw comparison covers every encoded value, including all viewport / scissor / bias / blend components.
    // 1) Differential fuzz test: 200,000 adversarial draws (empty scissors, cull=3, pass breaks, widen, origin_ll, rast_flip)
    DrawIn st = { .has_vp = 1, .vp = {0,0,1920,1080}, .dr = {0,1}, .sc = {0,0,1920,1080}, .has_sc = 1, .tw = 1920, .th = 1080, .rs = 1.0, .pass_serial = 1 };
    EdState edA = {0}, edB = {0};
    uint64_t dspA = 0, dspB = 0;
    int ddA = 1, ddB = 1;
    unsigned ed_dirty = RB_ED_ALL;
    Trace trA = {0}, trB = {0};
    for (int i = 0; i < 200000; i++) {
        uint32_t op = r32() % 20;
        if (op == 0) { st.pass_serial++; edA.ok = 0; edB.ok = 0; }
        else if (op == 1) { st.sc.x = (int)(r32() % 100) - 20; st.sc.w = (r32() % 5 == 0) ? 0 : 1280; st.has_sc = 1; ed_dirty |= RB_ED_SC; }
        else if (op == 2) { st.poly.cull = (int)(r32() % 4); st.poly.front = (int)(r32() & 1); st.poly.mode = (int)(r32() & 1); st.poly.offset_en = (r32() & 1) ? 4 : 0; ed_dirty |= (RB_ED_CULL | RB_ED_WIND | RB_ED_FILL | RB_ED_BIAS); }
        else if (op == 3) { st.vp[2] = (float)(640 + (r32() % 1280)); st.has_vp = 1; ed_dirty |= RB_ED_VP; }
        else if (op == 4) { st.st_ref[0] = r32() & 255; st.st_ref[1] = r32() & 255; ed_dirty |= RB_ED_SREF; }
        else if (op == 5) { st.po.units = (float)(r32() % 10); ed_dirty |= RB_ED_BIAS; }
        else if (op == 6) { st.depth_clamp = (int)(r32() & 1); ed_dirty |= RB_ED_CLIP; }
        else if (op == 7) { st.blend_color[0] = (float)(r32() % 10) * 0.1f; ed_dirty |= RB_ED_BLEND; }
        else if (op == 8) { st.origin_ll = (int)(r32() & 1); }
        else if (op == 9) { st.rast_flip = (int)(r32() & 1); }
        else if (op == 10) { st.wd = (int)(r32() & 1); }
        else if (op == 11) { ddA = ddB = 1; }
        int rA = run_orig(&st, &edA, &dspA, &ddA, &trA);
        int rB = run_fast(&st, &edB, &dspB, &ddB, &ed_dirty, &trB);
        if (encoder_diff(&edA,&edB) || dspA != dspB || ddA != ddB || rA != rB || trA.emits != trB.emits || trA.hash != trB.hash) {
            fprintf(stderr, "MISMATCH at step %d: rA=%d rB=%d emits=%llu/%llu hash=%llx/%llx\n",
                    i, rA, rB, (unsigned long long)trA.emits, (unsigned long long)trB.emits,
                    (unsigned long long)trA.hash, (unsigned long long)trB.hash);
            return 1;
        }
    }
    printf("FUZZ PASS: 200000/200000 draws exact parity (emits=%llu hash=0x%016llx)\n",
           (unsigned long long)trA.emits, (unsigned long long)trA.hash);

    // 2) Steady-state benchmark: 60 frames x 40 passes x 50 draws = 120,000 draws (realistic 75% clean bursts, 25% partial dirty)
    // Repeated 4x = 480,000 draws for crisp timing.
    DrawIn b = { .has_vp = 1, .vp = {0,0,1920,1080}, .dr = {0,1}, .sc = {0,0,1920,1080}, .has_sc = 1, .tw = 1920, .th = 1080, .rs = 1.0, .pass_serial = 1 };
    for (int run = 0; run < 7; run++) {
        b.sc.x = 0; b.poly.cull = 0;
        EdState e1 = {0}, e2 = {0}; uint64_t p1 = 0, p2 = 0; int d1 = 1, d2 = 1; unsigned dm = RB_ED_ALL;
        Trace t1 = {0}, t2 = {0};
        uint64_t s0 = now_ns();
        for (int pass = 1; pass <= 9600; pass++) {
            b.pass_serial = (uint64_t)pass; e1.ok = 0;
            for (int d = 0; d < 50; d++) {
                if ((d & 7) == 4) b.sc.x = (d >> 3) & 1;
                if ((d & 15) == 8) b.poly.cull = (d >> 4) & 1;
                t1.drawn += run_orig(&b, &e1, &p1, &d1, &t1);
            }
        }
        uint64_t dt1 = now_ns() - s0;
        b.sc.x = 0; b.poly.cull = 0;
        uint64_t s1 = now_ns();
        for (int pass = 1; pass <= 9600; pass++) {
            b.pass_serial = (uint64_t)pass; e2.ok = 0;
            for (int d = 0; d < 50; d++) {
                if ((d & 7) == 4) { b.sc.x = (d >> 3) & 1; dm |= RB_ED_SC; }
                if ((d & 15) == 8) { b.poly.cull = (d >> 4) & 1; dm |= (RB_ED_CULL | RB_ED_WIND | RB_ED_FILL | RB_ED_BIAS); }
                t2.drawn += run_fast(&b, &e2, &p2, &d2, &dm, &t2);
            }
        }
        uint64_t dt2 = now_ns() - s1;
        if (encoder_diff(&e1,&e2) || p1 != p2 || d1 != d2 || t1.drawn != t2.drawn || t1.emits != t2.emits || t1.hash != t2.hash) {
            fprintf(stderr, "BENCH PARITY FAIL!\n"); return 1;
        }
        printf("run %d: orig=%.3f ms fast=%.3f ms (%.2fx, emits=%llu)\n",
               run + 1, (double)dt1 / 1e6, (double)dt2 / 1e6, (double)dt1 / (double)dt2, (unsigned long long)t1.emits);
    }
    return 0;
}
