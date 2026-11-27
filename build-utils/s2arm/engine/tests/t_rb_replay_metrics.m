// RewindBox: reproducible NVN graphics replay with hardware-independent backend metrics.
// One synthetic NVN2-style frame is recorded through the public NVN API (nvnBootstrapLoader, the production HLE recorder) and replayed by the production
// backend (nvn_mtl.m, included) on the Mac's Metal device: shadow depth pass, two-target G-buffer pass with 256 objects, a compute pass feeding a storage
// buffer, a lighting pass that samples the G-buffer, two downsample passes, a composite and a UI pass with alpha blending, split render-target rebinds,
// redundant state binds and NVN barriers, as games issue them. Shaders are hand-written MSL with production reflections (nvn_refl_from_json).
// Metrics come from the encode stream itself (patch 0469 hooks), not from timings: records by kind (render / compute encoders, pipeline and fixed-function
// state, argument bindings, barriers and fences, draws, dispatches, copies, commits), attachment loads / stores in bytes from the actual pass descriptors,
// frame scratch (arena) allocations, residency additions and the engine's own ledgers. Equivalence: an FNV digest of the state every draw and dispatch sees
// (canonical pipeline, depth state, raster state, textures and samplers by first-seen order, bound buffer slots) and of the read-back pixels of every target.
// Run with DM_NVN_ENC_THREAD=1 (records on Metal 3 and Metal 4); one optimization switch per process; compare the METRICS lines of two runs.
#include <math.h>
#include <time.h>
#include <stdatomic.h>
static void rbm_put(unsigned op);
static void rbm_exec(const void *r);
static uint64_t rbm_arena_calls, rbm_arena_bytes, rbm_res_adds;
#define S2A_REC_PUT_HOOK(op) rbm_put((unsigned)(op))
#define S2A_REC_EXEC_HOOK(r) rbm_exec((const void *)(r))
#define S2A_ARENA_HOOK(n) (rbm_arena_calls++, rbm_arena_bytes += (n))
#define S2A_RES_HOOK() (rbm_res_adds++)
// A GPU without residency sets (the Mac runner's paravirtual device): every allocation the engine makes resident is declared on each encoder instead (rbm_track)
static int rbm_tracked;
#define S2A_NO_RESIDENCY_SET() (rbm_tracked = 1, fprintf(stderr, "replay metrics: no residency set on this GPU, resources declared per encoder\n"))
#include "nvn_mtl.m"
#include "nvn_protos.h"

extern void *h_nvnBootstrapLoader(const char *name);
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr, "SETUP FAIL %s:%d %s\n", __FILE__, __LINE__, #x); exit(2); } } while (0)
static void *api(const char *name) { void *p = h_nvnBootstrapLoader(name); REQUIRE(p); return p; }
#define API(name) ((NVNT_##name)api(#name))

// ---------- metrics from the record stream ----------
enum { RBM_OPS = 128 };
static _Atomic uint64_t rbm_put_n[RBM_OPS];
static uint64_t rbm_exec_n[RBM_OPS];
static uint64_t rbm_h = 0xcbf29ce484222325ull, rbm_draws, rbm_dispatches, rbm_load_bytes, rbm_store_bytes, rbm_clear_atts, rbm_dontcare_atts, rbm_copy_bytes, rbm_fill_bytes;
static inline uint64_t rbm_mix(uint64_t h, uint64_t v) { for (int i = 0; i < 8; i++) { h ^= (v >> (8 * i)) & 0xff; h *= 0x100000001b3ull; } return h; }
static void rbm_put(unsigned op) { if (op < RBM_OPS) atomic_fetch_add_explicit(&rbm_put_n[op], 1, memory_order_relaxed); }
// Canonical object numbers by first sight (pointers differ from one process to the next; the order of first use does not when the work is the same)
static nvn_hmap rbm_ids = {.klen = 8}; static uint64_t rbm_next_id;
static uint64_t rbm_id(uint64_t p) { if (!p) return 0; void *v = nvn_hm_get(&rbm_ids, &p); if (v) return (uint64_t)(uintptr_t)v; nvn_hm_put(&rbm_ids, &p, (void *)(uintptr_t)++rbm_next_id); return rbm_next_id; }
static struct { uint64_t pso, dss, vp[6], sc[4], cull, wind, fill, bias[3], clip, sref[2], blend[4], cpso;
    uint64_t tex[5][32], smp[5][32]; uint32_t buf[5]; } rbm_s;
// The open render pass: its attachments, for the load / store byte account at its end
static struct { id tex[10]; int load[10], store[10], n; } rbm_pass;
static uint64_t rbm_bpp(id<MTLTexture> t) {
    switch (t.pixelFormat) { case MTLPixelFormatRGBA16Float: return 8; case MTLPixelFormatRGBA32Float: return 16; case MTLPixelFormatR8Unorm: return 1;
        case MTLPixelFormatDepth32Float_Stencil8: return 5; default: return 4; }
}
static void rbm_pass_begin(id d) {
    MTLRenderPassDescriptor *p = d; memset(&rbm_pass, 0, sizeof rbm_pass);
    for (int i = 0; i < 8; i++) { MTLRenderPassColorAttachmentDescriptor *c = p.colorAttachments[i]; if (!c.texture) continue;
        int k = rbm_pass.n++; rbm_pass.tex[k] = c.texture; rbm_pass.load[k] = (int)c.loadAction; rbm_pass.store[k] = (int)c.storeAction; }
    if (p.depthAttachment.texture) { int k = rbm_pass.n++; rbm_pass.tex[k] = p.depthAttachment.texture; rbm_pass.load[k] = (int)p.depthAttachment.loadAction; rbm_pass.store[k] = 100 + (int)p.depthAttachment.storeAction; }
    for (int k = 0; k < rbm_pass.n; k++) {
        id<MTLTexture> t = rbm_pass.tex[k];
        if (rbm_pass.load[k] == MTLLoadActionLoad) rbm_load_bytes += t.width * t.height * rbm_bpp(t);
        else if (rbm_pass.load[k] == MTLLoadActionClear) rbm_clear_atts++;
        else rbm_dontcare_atts++;
        rbm_h = rbm_mix(rbm_h, 0x7000 + rbm_id((uint64_t)(uintptr_t)(__bridge void *)t)); }
}
static void rbm_pass_store(int depth, int index, int action) {   // a deferred store action (setColorStoreAction / setDepthStoreAction)
    int c = 0; for (int k = 0; k < rbm_pass.n; k++) { int is_depth = rbm_pass.store[k] >= 100;
        if (depth ? is_depth : (!is_depth && c++ == index)) { rbm_pass.store[k] = (is_depth ? 100 : 0) + action; return; } }
}
// Per-pass attachment trace of the frame being replayed (reset by main between frames, after the queue is idle): canonical texture, size, load / store actions
static char rbm_ptrace[16384]; static size_t rbm_ptrace_n;
static void rbm_pass_end(void) {
    if (rbm_pass.n && rbm_ptrace_n < sizeof rbm_ptrace - 256) rbm_ptrace_n += (size_t)snprintf(rbm_ptrace + rbm_ptrace_n, sizeof rbm_ptrace - rbm_ptrace_n, " |");
    for (int k = 0; k < rbm_pass.n; k++) { int s = rbm_pass.store[k] % 100; id<MTLTexture> t = rbm_pass.tex[k];
        if (s == MTLStoreActionStore || s == MTLStoreActionStoreAndMultisampleResolve) rbm_store_bytes += t.width * t.height * rbm_bpp(t);
        if (rbm_ptrace_n < sizeof rbm_ptrace - 96)   // tN:WxH L<load> S<store>, load 0 dont-care 1 load 2 clear, store 0 dont-care 1 store
            rbm_ptrace_n += (size_t)snprintf(rbm_ptrace + rbm_ptrace_n, sizeof rbm_ptrace - rbm_ptrace_n, " t%llu:%lux%lu%s L%d S%d", (unsigned long long)rbm_id((uint64_t)(uintptr_t)(__bridge void *)t),
                                            (unsigned long)t.width, (unsigned long)t.height, rbm_pass.store[k] >= 100 ? "d" : "", rbm_pass.load[k], s); }
    rbm_pass.n = 0;
}
static uint64_t rbm_state(void) {
    uint64_t h = 0x84222325cbf29ce4ull;
    h = rbm_mix(h, rbm_s.pso); h = rbm_mix(h, rbm_s.dss); for (int i = 0; i < 6; i++) h = rbm_mix(h, rbm_s.vp[i]); for (int i = 0; i < 4; i++) h = rbm_mix(h, rbm_s.sc[i]);
    h = rbm_mix(h, rbm_s.cull); h = rbm_mix(h, rbm_s.wind); h = rbm_mix(h, rbm_s.fill); for (int i = 0; i < 3; i++) h = rbm_mix(h, rbm_s.bias[i]);
    h = rbm_mix(h, rbm_s.clip); h = rbm_mix(h, rbm_s.sref[0]); h = rbm_mix(h, rbm_s.sref[1]); for (int i = 0; i < 4; i++) h = rbm_mix(h, rbm_s.blend[i]);
    for (int s = 0; s < 5; s++) { h = rbm_mix(h, rbm_s.buf[s]); for (int i = 0; i < 32; i++) { h = rbm_mix(h, rbm_s.tex[s][i]); h = rbm_mix(h, rbm_s.smp[s][i]); } }
    return h;
}
// Without a residency set: the encode thread's open encoder declares every resident allocation before its first call (a residency stand-in, not counted in the metrics)
static void rbm_track(void) {
    static __unsafe_unretained id last;
    if (!rbm_tracked || !g_rx_enc || g_rx_enc == last) return;
    last = g_rx_enc;
    pthread_mutex_lock(&g_res_mu); NSArray *all = g_res_objects.allObjects; pthread_mutex_unlock(&g_res_mu);
    NSUInteger n = all.count; if (!n) return;
    __unsafe_unretained id<MTLResource> *v = (__unsafe_unretained id<MTLResource> *)calloc(n, sizeof *v); NSUInteger k = 0;
    for (id o in all) if ([o conformsToProtocol:@protocol(MTLResource)]) v[k++] = o;
    const MTLResourceUsage u = MTLResourceUsageRead | MTLResourceUsageWrite;
    if ([g_rx_enc conformsToProtocol:@protocol(MTLRenderCommandEncoder)]) [(id<MTLRenderCommandEncoder>)g_rx_enc useResources:v count:k usage:u stages:MTLRenderStageVertex | MTLRenderStageFragment];
    else if ([g_rx_enc conformsToProtocol:@protocol(MTLComputeCommandEncoder)]) [(id<MTLComputeCommandEncoder>)g_rx_enc useResources:v count:k usage:u];
    free(v);
}
// RBM_TRACE=<file>: one line per pass begin / end, draw and dispatch of the measured frames, with the canonical ids the state digest mixes,
//   so that two runs can be compared line by line (replay_compare.py names the first line where the baseline's own runs part)
static FILE *rbm_tf;
static void rbm_trace(const rec_t *r) {
    if (!rbm_tf) return;
    switch (r->op) {
    case RO_RE_BEGIN: fprintf(rbm_tf, "P"); for (int k = 0; k < rbm_pass.n; k++) fprintf(rbm_tf, " %llu:%d", (unsigned long long)rbm_id((uint64_t)(uintptr_t)(__bridge void *)rbm_pass.tex[k]), rbm_pass.load[k]); fprintf(rbm_tf, "\n"); break;
    case RO_END: fprintf(rbm_tf, "E\n"); break;
    case RO_C_DISPATCH: case RO_C_DISPATCH_IND: case RO_C_DISPATCH_THREADS: case RO_C_DISPATCH_IND_B: fprintf(rbm_tf, "K %u cpso=%llu\n", r->op, (unsigned long long)rbm_s.cpso); break;
    case RO_R_DRAW: case RO_R_DRAW_INST: case RO_R_DRAW_IND: case RO_R_DRAW_IDX: case RO_R_DRAW_IDX_IND: case RO_R_DRAW_IND_B: case RO_R_DRAW_IDX_B: case RO_R_DRAW_IDX_IND_B:
    case RO_R_MESH: case RO_R_MESH_IND: case RO_R_MESH_IND_B:
        fprintf(rbm_tf, "D %u pso=%llu dss=%llu vp=%llx,%llx sc=%llx,%llx cull=%llu blend=%llx bufs=%x,%x,%x,%x,%x tex=", r->op, (unsigned long long)rbm_s.pso, (unsigned long long)rbm_s.dss,
                (unsigned long long)rbm_s.vp[2], (unsigned long long)rbm_s.vp[3], (unsigned long long)rbm_s.sc[2], (unsigned long long)rbm_s.sc[3], (unsigned long long)rbm_s.cull,
                (unsigned long long)rbm_s.blend[0], rbm_s.buf[0], rbm_s.buf[1], rbm_s.buf[2], rbm_s.buf[3], rbm_s.buf[4]);
        for (int s = 0; s < 5; s++) for (int i = 0; i < 32; i++) if (rbm_s.tex[s][i] || rbm_s.smp[s][i]) fprintf(rbm_tf, "%d.%d:%llu/%llu ", s, i, (unsigned long long)rbm_s.tex[s][i], (unsigned long long)rbm_s.smp[s][i]);
        fprintf(rbm_tf, "st=%016llx", (unsigned long long)rbm_state());
        for (int i = 0, n = r->op == RO_R_DRAW ? 3 : r->op == RO_R_DRAW_INST ? 5 : 0; i < n; i++) fprintf(rbm_tf, " a%d=%llu", i, (unsigned long long)r->a[i]);
        fprintf(rbm_tf, "\n"); break;
    default: break;
    }
}
static void rbm_exec(const void *rp) {
    const rec_t *r = rp; const uint64_t *a = r->a; if (r->op < RBM_OPS) rbm_exec_n[r->op]++;
    rbm_track();
    if (rbm_tf && r->op != RO_RE_BEGIN) rbm_trace(r);
    switch (r->op) {
    case RO_RE_BEGIN: memset(&rbm_s, 0, sizeof rbm_s); rbm_pass_begin(rec_id(a[0])); rbm_trace(r); break;   // a new encoder starts with no state
    case RO_CE_BEGIN: case RO_CE_BEGIN_D: case RO_CB_BLIT: memset(&rbm_s, 0, sizeof rbm_s); break;
    case RO_END: rbm_pass_end(); break;
    case RO_R_STORE_C: rbm_pass_store(0, (int)a[1], (int)a[0]); break;
    case RO_R_STORE_D: rbm_pass_store(1, 0, (int)a[0]); break;
    case RO_R_PSO: rbm_s.pso = rbm_id(a[0]); break;
    case RO_C_PSO: rbm_s.cpso = rbm_id(a[0]); break;
    case RO_R_DSS: rbm_s.dss = rbm_id(a[0]); break;
    case RO_R_VIEWPORT: memcpy(rbm_s.vp, a, sizeof rbm_s.vp); break;
    case RO_R_SCISSOR: memcpy(rbm_s.sc, a, sizeof rbm_s.sc); break;
    case RO_R_CULL: rbm_s.cull = a[0]; break;
    case RO_R_WINDING: rbm_s.wind = a[0]; break;
    case RO_R_FILL: rbm_s.fill = a[0]; break;
    case RO_R_BIAS: for (int i = 0; i < 3; i++) rbm_s.bias[i] = (uint32_t)a[i]; break;   // floats in the low 32 bits (rec_fv); the high bits are not written
    case RO_R_CLIP: rbm_s.clip = a[0]; break;
    case RO_R_SREF: rbm_s.sref[0] = (uint32_t)a[0]; rbm_s.sref[1] = (uint32_t)a[1]; break;
    case RO_R_BLEND: for (int i = 0; i < 4; i++) rbm_s.blend[i] = (uint32_t)a[i]; break;
    case RO_M3_TEX: if (a[1] < 5 && a[2] < 32) rbm_s.tex[a[1]][a[2]] = rbm_id(a[0]); break;
    case RO_M3_SMP: if (a[1] < 5 && a[2] < 32) rbm_s.smp[a[1]][a[2]] = rbm_id(a[0]); break;
    case RO_M3_BUF: if (a[1] < 5 && a[3] < 32) rbm_s.buf[a[1]] |= 1u << a[3]; break;   // the slot, not the scratch offset: argument contents are checked through the pixels
    case RO_C_COPY_BB: rbm_copy_bytes += a[4]; break;
    case RO_C_COPY_BT: case RO_C_COPY_TB: rbm_copy_bytes += a[5 + (r->op == RO_C_COPY_TB ? 2 : 0)] * a[6 + (r->op == RO_C_COPY_TB ? 2 : 0)] * a[7 + (r->op == RO_C_COPY_TB ? 2 : 0)] * 4; break;
    case RO_C_COPY_TT: rbm_copy_bytes += a[7] * a[8] * a[9] * 4; break;
    case RO_C_FILL: rbm_fill_bytes += a[2]; break;
    case RO_R_DRAW: case RO_R_DRAW_INST: case RO_R_DRAW_IND: case RO_R_DRAW_IDX: case RO_R_DRAW_IDX_IND: case RO_R_DRAW_IND_B: case RO_R_DRAW_IDX_B: case RO_R_DRAW_IDX_IND_B:
    case RO_R_MESH: case RO_R_MESH_IND: case RO_R_MESH_IND_B:
        rbm_draws++; rbm_h = rbm_mix(rbm_h, rbm_state()); rbm_h = rbm_mix(rbm_h, r->op);
        // Only the slots the call reads (rec_exec): a record block is reused, so slots past them hold whatever an earlier record left there
        for (int i = 0, n = r->op == RO_R_DRAW ? 3 : r->op == RO_R_DRAW_INST ? 5 : 0; i < n; i++) rbm_h = rbm_mix(rbm_h, a[i]);
        break;
    case RO_C_DISPATCH: case RO_C_DISPATCH_IND: case RO_C_DISPATCH_THREADS: case RO_C_DISPATCH_IND_B:
        rbm_dispatches++; rbm_h = rbm_mix(rbm_h, 0xd15 ^ rbm_s.cpso); rbm_h = rbm_mix(rbm_h, rbm_state()); break;
    default: break;
    }
}

// ---------- the synthetic frame ----------
enum { W = 256, POOL = 64 << 20, CMD = 4 << 20, UBO = 32 << 20, SSBO = 40 << 20, TPOOL = 48 << 20, SPOOL = 49 << 20, OBJ = 256, MAT = 8, LIGHTS = 16, UI = 32 };
static NVNdevice dev; static NVNqueue queue; static NVNmemoryPool pool; static NVNcommandBuffer cmd; static NVNtexturePool tpool; static NVNsamplerPool spool;
static uint8_t *mem; static NVNbufferAddress ga; static size_t tex_off = 8 << 20;
static NVNtexture t_shadow, t_g0, t_g1, t_depth, t_light, t_half, t_quarter, t_final;
static prog_t p_depth, p_mrt[4], p_cs, p_light, p_lamp, p_down, p_comp, p_ui;
static void texture(NVNtexture *t, int w, int h, NVNformat f, int id) {
    NVNtextureBuilder b; API(nvnTextureBuilderSetDefaults)(&b); API(nvnTextureBuilderSetDevice)(&b, &dev); API(nvnTextureBuilderSetTarget)(&b, NVN_TEXTURE_TARGET_2D);
    API(nvnTextureBuilderSetSize2D)(&b, w, h); API(nvnTextureBuilderSetFormat)(&b, f); API(nvnTextureBuilderSetLevels)(&b, 1);
    API(nvnTextureBuilderSetFlags)(&b, NVN_TEXTURE_FLAGS_COMPRESSIBLE);
    size_t al = API(nvnTextureBuilderGetStorageAlignment)(&b), sz = API(nvnTextureBuilderGetStorageSize)(&b);
    tex_off = (tex_off + al - 1) / al * al; REQUIRE(tex_off + sz <= UBO); API(nvnTextureBuilderSetStorage)(&b, &pool, (ptrdiff_t)tex_off); tex_off += sz;
    REQUIRE(API(nvnTextureInitialize)(t, &b));
    if (id >= 0) API(nvnTexturePoolRegisterTexture)(&tpool, id, t, NULL);
}
static NSString *const kMSL = @"#include <metal_stdlib>\nusing namespace metal;\n"
"struct VA { constant float4 *obj [[id(0)]]; };\n"
"vertex float4 vs_obj(uint i [[vertex_id]], constant VA &a [[buffer(0)]]) {\n"
"  const float2 q[6] = {float2(0,0),float2(1,0),float2(0,1),float2(1,0),float2(1,1),float2(0,1)}; float4 r = a.obj[0];\n"
"  return float4(r.xy + q[i] * r.zw, a.obj[1].x, 1); }\n"
"vertex float4 vs_full(uint i [[vertex_id]]) { const float2 p[3] = {float2(-1,-1),float2(3,-1),float2(-1,3)}; return float4(p[i], 0, 1); }\n"
"fragment void fs_none() {}\n"
"struct FA { constant float4 *mat [[id(0)]]; };\n"
"struct MRT { float4 a [[color(0)]]; float4 b [[color(1)]]; };\n"
"fragment MRT fs_mrt0(float4 p [[position]], constant FA &a [[buffer(0)]]) { MRT o; o.a = a.mat[0]; o.b = float4(p.z, a.mat[0].y, 0.25, 1); return o; }\n"
"fragment MRT fs_mrt1(float4 p [[position]], constant FA &a [[buffer(0)]]) { MRT o; o.a = a.mat[0] * 0.75; o.b = float4(p.z, 0.5, a.mat[0].x, 1); return o; }\n"
"fragment MRT fs_mrt2(float4 p [[position]], constant FA &a [[buffer(0)]]) { MRT o; o.a = a.mat[0].zyxw; o.b = float4(p.z, 0.125, 0.5, 1); return o; }\n"
"fragment MRT fs_mrt3(float4 p [[position]], constant FA &a [[buffer(0)]]) { MRT o; o.a = float4(a.mat[0].xy, 1, 1); o.b = float4(p.z, 1, 0, 1); return o; }\n"
"struct CA { constant float4 *prm [[id(0)]]; device float4 *out [[id(1)]]; };\n"
"kernel void cs_fill(constant CA &a [[buffer(0)]], uint i [[thread_position_in_grid]]) { a.out[i] = a.prm[0] * float(i & 15) / 15.0; }\n"
"struct LA { texture2d<float, access::read> g0 [[id(0)]]; texture2d<float, access::read> g1 [[id(1)]]; constant float4 *prm [[id(2)]]; device float4 *cs [[id(3)]]; };\n"
"fragment float4 fs_light(float4 p [[position]], constant LA &a [[buffer(0)]]) { uint2 c = uint2(p.xy);\n"
"  float4 g0 = a.g0.read(c), g1 = a.g1.read(c); return float4(g0.rgb * a.prm[0].rgb + a.cs[c.x & 63].rgb * 0.25 * g1.g, 1); }\n"
"struct PA { constant float4 *col [[id(0)]]; };\n"
"fragment float4 fs_lamp(constant PA &a [[buffer(0)]]) { return a.col[0]; }\n"
"struct DA { texture2d<float, access::read> src [[id(0)]]; };\n"
"fragment float4 fs_down(float4 p [[position]], constant DA &a [[buffer(0)]]) { uint2 c = uint2(p.xy) * 2;\n"
"  return (a.src.read(c) + a.src.read(c + uint2(1,0)) + a.src.read(c + uint2(0,1)) + a.src.read(c + uint2(1,1))) * 0.25; }\n"
"struct XA { texture2d<float, access::read> l [[id(0)]]; texture2d<float, access::read> b [[id(1)]]; };\n"
"fragment float4 fs_comp(float4 p [[position]], constant XA &a [[buffer(0)]]) { uint2 c = uint2(p.xy);\n"
"  return float4(a.l.read(c).rgb + a.b.read(c / 4).rgb * 0.5, 1); }\n"
"fragment float4 fs_ui(constant PA &a [[buffer(0)]]) { return a.col[0]; }\n";
static id<MTLLibrary> lib;
static NvShader *shader(NSString *fn, int stage, NSArray *bindings, NSArray *colors) {
    NvShader *s = [NvShader new]; s->stage = stage; s->fn = [lib newFunctionWithName:fn]; REQUIRE(s->fn);
    NSMutableDictionary *j = [@{ @"route": @"B", @"bindings": bindings ?: @[] } mutableCopy];
    if (colors) j[@"raster"] = @{ @"colors": colors, @"discard": @0, @"sample_mask": @0 };
    if (stage == 5) j[@"threadgroup_size"] = @[@64, @1, @1];
    char e[256]; REQUIRE(!nvn_refl_from_json(j, &s->rf, e, sizeof e));
    if (bindings.count) { s->ae = [s->fn newArgumentEncoderWithBufferIndex:0]; REQUIRE(s->ae); s->arg_len = s->ae.encodedLength; }
    s->rf.has_user = stage == 0 ? 1 : stage == 1 ? 2 : 0;
    snprintf(s->key, sizeof s->key, "%016llx_b", (unsigned long long)(0x5eed000000000000ull + (uint64_t)[fn hash] % 0xffffffffffull));
    return s;
}
static void program(prog_t *p, NvShader *vs, NvShader *fs, NvShader *cs) {
    NvProg *g = [NvProg new]; g->sh[0] = vs; g->sh[1] = fs; g->sh[5] = cs; g->smask = (vs ? 1 : 0) | (fs ? 2 : 0) | (cs ? 32 : 0);
    *p = (prog_t){.magic = MAGIC('P', 'R', 'O', 'G'), .serial = nvn_new_serial()}; serial_put(p->serial, g);
}
static NVNbufferAddress ubo(int block) { return ga + UBO + (NVNbufferAddress)block * 256; }
static float *ubo_cpu(int block) { return (float *)(mem + UBO + (size_t)block * 256); }
enum { B_OBJ = 0, B_MAT = OBJ, B_LIGHT = OBJ + MAT, B_LAMP = B_LIGHT + 1, B_UI = B_LAMP + LIGHTS, B_CS = B_UI + UI, B_END };
static NVNdepthStencilState ds_on, ds_off; static NVNcolorState cs_none, cs_blend; static NVNblendState bl_add, bl_alpha;
static void bind_rt(int n, NVNtexture *c0, NVNtexture *c1, NVNtexture *depth, int w) {
    const NVNtexture *c[2] = {c0, c1}; API(nvnCommandBufferSetRenderTargets)(&cmd, n, n ? c : NULL, NULL, depth, NULL);
    API(nvnCommandBufferSetViewport)(&cmd, 0, 0, w, w); API(nvnCommandBufferSetScissor)(&cmd, 0, 0, w, w);
}
static void record_frame(void) {
    const int B = NVN_BARRIER_ORDER_FRAGMENTS_BIT | NVN_BARRIER_INVALIDATE_TEXTURE_BIT;
    const float zero[4] = {0, 0, 0, 0}, sky[4] = {0.1f, 0.2f, 0.3f, 1};
    API(nvnCommandBufferSetTexturePool)(&cmd, &tpool); API(nvnCommandBufferSetSamplerPool)(&cmd, &spool);
    // ① shadow depth pass: 64 objects, depth only
    bind_rt(0, NULL, NULL, &t_shadow, W); API(nvnCommandBufferClearDepthStencil)(&cmd, 1.0f, 1, 0, 0);
    API(nvnCommandBufferBindDepthStencilState)(&cmd, &ds_on); API(nvnCommandBufferBindColorState)(&cmd, &cs_none);
    API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_depth, NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
    for (int i = 0; i < 64; i++) { API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_VERTEX, 0, ubo(B_OBJ + i * 4), 256); API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 6); }
    API(nvnCommandBufferBarrier)(&cmd, B);
    // ② G-buffer: two colour targets and depth, 256 objects, 4 programs, per-object and per-material uniforms, redundant depth-state and scissor binds
    bind_rt(2, &t_g0, &t_g1, &t_depth, W);
    API(nvnCommandBufferClearColor)(&cmd, 0, zero, 15); API(nvnCommandBufferClearColor)(&cmd, 1, zero, 15); API(nvnCommandBufferClearDepthStencil)(&cmd, 1.0f, 1, 0, 0);
    for (int i = 0; i < OBJ; i++) {
        if (!(i & 63)) API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_mrt[i >> 6], NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
        if (!(i & 7)) API(nvnCommandBufferBindDepthStencilState)(&cmd, &ds_on);
        if (!(i & 3)) API(nvnCommandBufferSetScissor)(&cmd, 0, 0, W, W);
        API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_VERTEX, 0, ubo(B_OBJ + i), 256);
        API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, ubo(B_MAT + (i % MAT)), 256);
        API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 6);
    }
    API(nvnCommandBufferBarrier)(&cmd, B);
    // ③ compute: fills a storage buffer the lighting pass reads
    API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_cs, NVN_SHADER_STAGE_COMPUTE_BIT);
    API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_COMPUTE, 0, ubo(B_CS), 256);
    API(nvnCommandBufferBindStorageBuffer)(&cmd, NVN_SHADER_STAGE_COMPUTE, 0, ga + SSBO, 64 * 16);
    API(nvnCommandBufferDispatchCompute)(&cmd, 1, 1, 1);
    API(nvnCommandBufferBarrier)(&cmd, NVN_BARRIER_ORDER_PRIMITIVES_BIT | B);
    // ④ lighting: reads both G-buffer targets and the storage buffer, then 16 additive light quads
    bind_rt(1, &t_light, NULL, NULL, W); API(nvnCommandBufferClearColor)(&cmd, 0, sky, 15);
    API(nvnCommandBufferBindDepthStencilState)(&cmd, &ds_off);
    API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_light, NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
    API(nvnCommandBufferBindTexture)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, (NVNtextureHandle)1); API(nvnCommandBufferBindTexture)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 1, (NVNtextureHandle)2);
    API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, ubo(B_LIGHT), 256);
    API(nvnCommandBufferBindStorageBuffer)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, ga + SSBO, 64 * 16);
    API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    API(nvnCommandBufferBindColorState)(&cmd, &cs_blend); API(nvnCommandBufferBindBlendState)(&cmd, &bl_add);
    API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_lamp, NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
    for (int i = 0; i < LIGHTS; i++) { API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_VERTEX, 0, ubo(B_OBJ + i * 16), 256);
        API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, ubo(B_LAMP + i), 256); API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 6); }
    API(nvnCommandBufferBindColorState)(&cmd, &cs_none);
    API(nvnCommandBufferBarrier)(&cmd, B);
    // ⑤ two downsamples
    API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_down, NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
    bind_rt(1, &t_half, NULL, NULL, W / 2); API(nvnCommandBufferBindTexture)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, (NVNtextureHandle)3);
    API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3); API(nvnCommandBufferBarrier)(&cmd, B);
    bind_rt(1, &t_quarter, NULL, NULL, W / 4); API(nvnCommandBufferBindTexture)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, (NVNtextureHandle)4);
    API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3); API(nvnCommandBufferBarrier)(&cmd, B);
    // ⑥ composite, then UI quads with alpha blending, split by a rebind of the same target in the middle
    bind_rt(1, &t_final, NULL, NULL, W); API(nvnCommandBufferClearColor)(&cmd, 0, zero, 15);
    API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_comp, NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
    API(nvnCommandBufferBindTexture)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, (NVNtextureHandle)3); API(nvnCommandBufferBindTexture)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 1, (NVNtextureHandle)5);
    API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 3);
    API(nvnCommandBufferBindColorState)(&cmd, &cs_blend); API(nvnCommandBufferBindBlendState)(&cmd, &bl_alpha);
    API(nvnCommandBufferBindProgram)(&cmd, (const NVNprogram *)&p_ui, NVN_SHADER_STAGE_VERTEX_BIT | NVN_SHADER_STAGE_FRAGMENT_BIT);
    for (int i = 0; i < UI; i++) {
        if (i == UI / 2) bind_rt(1, &t_final, NULL, NULL, W);   // the same target again (a UI layer recorded by another system)
        API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_VERTEX, 0, ubo(B_OBJ + i * 8 + 1), 256);
        API(nvnCommandBufferBindUniformBuffer)(&cmd, NVN_SHADER_STAGE_FRAGMENT, 0, ubo(B_UI + i), 256); API(nvnCommandBufferDrawArrays)(&cmd, NVN_DRAW_PRIMITIVE_TRIANGLES, 0, 6); }
}
static uint64_t readback(NVNtexture *t, int w, int bpp) {
    id<MTLTexture> m = tex_mtl((const tex_t *)t); REQUIRE(m);
    id<MTLBuffer> out = [g_dev newBufferWithLength:(NSUInteger)(w * w * bpp) options:MTLResourceStorageModeShared];
    id<MTLCommandQueue> q = [g_dev newCommandQueue]; id<MTLCommandBuffer> cb = [q commandBuffer]; id<MTLBlitCommandEncoder> be = [cb blitCommandEncoder];
    [be copyFromTexture:m sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake((NSUInteger)w, (NSUInteger)w, 1) toBuffer:out destinationOffset:0
        destinationBytesPerRow:(NSUInteger)(w * bpp) destinationBytesPerImage:(NSUInteger)(w * w * bpp)];
    [be endEncoding]; [cb commit]; [cb waitUntilCompleted]; REQUIRE(cb.status == MTLCommandBufferStatusCompleted);
    const uint8_t *p = out.contents; uint64_t h = 0xcbf29ce484222325ull; for (int i = 0; i < w * w * bpp; i++) { h ^= p[i]; h *= 0x100000001b3ull; }
    return h;
}
int main(int argc, char **argv) { @autoreleasepool {
    setvbuf(stdout, NULL, _IOLBF, 0);
    int frames = argc > 1 ? atoi(argv[1]) : 3; if (frames < 1) frames = 1;
    char map[] = "/tmp/t_rbm_map_XXXXXX", user[] = "/tmp/t_rbm_user_XXXXXX"; int fd = mkstemp(map); close(fd); fd = mkstemp(user); close(fd);
    setenv("DM_NVN_SHMAP", map, 1); setenv("DM_PSO_USER", user, 1); setenv("DM_PSO_ARCHIVE", "0", 1); setenv("DM_PRESENT_LINK", "0", 1);
    NVNdeviceBuilder db; API(nvnDeviceBuilderSetDefaults)(&db); REQUIRE(API(nvnDeviceInitialize)(&dev, &db));
    NVNqueueBuilder qb; API(nvnQueueBuilderSetDefaults)(&qb); API(nvnQueueBuilderSetDevice)(&qb, &dev); REQUIRE(API(nvnQueueInitialize)(&queue, &qb)); mtl_init();
    REQUIRE(!posix_memalign((void **)&mem, 65536, POOL)); memset(mem, 0, POOL);
    NVNmemoryPoolBuilder pb; API(nvnMemoryPoolBuilderSetDefaults)(&pb); API(nvnMemoryPoolBuilderSetDevice)(&pb, &dev);
    API(nvnMemoryPoolBuilderSetStorage)(&pb, mem, POOL); API(nvnMemoryPoolBuilderSetFlags)(&pb, NVN_MEMORY_POOL_FLAGS_CPU_UNCACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED);
    REQUIRE(API(nvnMemoryPoolInitialize)(&pool, &pb)); ga = API(nvnMemoryPoolGetBufferAddress)(&pool);
    REQUIRE(API(nvnCommandBufferInitialize)(&cmd, &dev)); static uint8_t control[65536]; API(nvnCommandBufferAddControlMemory)(&cmd, control, sizeof control);
    REQUIRE(API(nvnTexturePoolInitialize)(&tpool, &pool, TPOOL, 512)); REQUIRE(API(nvnSamplerPoolInitialize)(&spool, &pool, SPOOL, 64));
    texture(&t_shadow, W, W, NVN_FORMAT_DEPTH32F, -1); texture(&t_g0, W, W, NVN_FORMAT_RGBA8, 1); texture(&t_g1, W, W, NVN_FORMAT_RGBA8, 2);
    texture(&t_depth, W, W, NVN_FORMAT_DEPTH32F, -1); texture(&t_light, W, W, NVN_FORMAT_RGBA8, 3); texture(&t_half, W / 2, W / 2, NVN_FORMAT_RGBA8, 4);
    texture(&t_quarter, W / 4, W / 4, NVN_FORMAT_RGBA8, 5); texture(&t_final, W, W, NVN_FORMAT_RGBA8, 6);
    // Uniform contents: deterministic, independent of the backend
    for (int i = 0; i < OBJ; i++) { float *o = ubo_cpu(B_OBJ + i); float x = -1 + (float)(i % 16) * 0.125f, y = -1 + (float)(i / 16) * 0.125f;
        o[0] = x; o[1] = y; o[2] = 0.2f + 0.01f * (float)(i % 5); o[3] = 0.2f + 0.01f * (float)(i % 7); o[4] = 0.1f + 0.003f * (float)(i % 97); }
    for (int i = 0; i < MAT; i++) { float *m = ubo_cpu(B_MAT + i); m[0] = 0.1f * (float)(i + 1); m[1] = 1 - 0.1f * (float)i; m[2] = 0.5f; m[3] = 1; }
    { float *l = ubo_cpu(B_LIGHT); l[0] = 0.9f; l[1] = 0.8f; l[2] = 0.7f; l[3] = 1; }
    for (int i = 0; i < LIGHTS; i++) { float *l = ubo_cpu(B_LAMP + i); l[0] = 0.02f * (float)i; l[1] = 0.01f; l[2] = 0.03f; l[3] = 1; }
    for (int i = 0; i < UI; i++) { float *u = ubo_cpu(B_UI + i); u[0] = 1; u[1] = 1; u[2] = 1; u[3] = 0.25f + 0.02f * (float)i; }
    { float *c = ubo_cpu(B_CS); c[0] = 0.5f; c[1] = 0.25f; c[2] = 1; c[3] = 1; }
    NSError *err = nil; lib = [g_dev newLibraryWithSource:kMSL options:nil error:&err]; if (!lib) { fprintf(stderr, "MSL: %s\n", err.localizedDescription.UTF8String); return 2; }
    NSArray *cb0 = @[ @{ @"kind": @"cbuf", @"reg": @0, @"arg_id": @0 } ];
    NvShader *vs_obj = shader(@"vs_obj", 0, cb0, nil), *vs_full = shader(@"vs_full", 0, nil, nil);
    program(&p_depth, vs_obj, shader(@"fs_none", 1, nil, @[]), nil);
    for (int k = 0; k < 4; k++) program(&p_mrt[k], vs_obj, shader([NSString stringWithFormat:@"fs_mrt%d", k], 1, cb0, @[@0, @1]), nil);
    program(&p_cs, nil, nil, shader(@"cs_fill", 5, @[ @{ @"kind": @"cbuf", @"reg": @0, @"arg_id": @0 }, @{ @"kind": @"sbuf", @"reg": @0, @"arg_id": @1, @"rw": @YES } ], nil));
    program(&p_light, vs_full, shader(@"fs_light", 1, @[ @{ @"kind": @"tex", @"reg": @0, @"arg_id": @0, @"msl_type": @"texture2d<float, access::read>" },
        @{ @"kind": @"tex", @"reg": @1, @"arg_id": @1, @"msl_type": @"texture2d<float, access::read>" }, @{ @"kind": @"cbuf", @"reg": @0, @"arg_id": @2 },
        @{ @"kind": @"sbuf", @"reg": @0, @"arg_id": @3 } ], @[@0]), nil);
    program(&p_lamp, vs_obj, shader(@"fs_lamp", 1, cb0, @[@0]), nil);
    program(&p_down, vs_full, shader(@"fs_down", 1, @[ @{ @"kind": @"tex", @"reg": @0, @"arg_id": @0, @"msl_type": @"texture2d<float, access::read>" } ], @[@0]), nil);
    program(&p_comp, vs_full, shader(@"fs_comp", 1, @[ @{ @"kind": @"tex", @"reg": @0, @"arg_id": @0, @"msl_type": @"texture2d<float, access::read>" },
        @{ @"kind": @"tex", @"reg": @1, @"arg_id": @1, @"msl_type": @"texture2d<float, access::read>" } ], @[@0]), nil);
    program(&p_ui, vs_obj, shader(@"fs_ui", 1, cb0, @[@0]), nil);
    API(nvnDepthStencilStateSetDefaults)(&ds_on); API(nvnDepthStencilStateSetDepthTestEnable)(&ds_on, 1); API(nvnDepthStencilStateSetDepthWriteEnable)(&ds_on, 1);
    API(nvnDepthStencilStateSetDepthFunc)(&ds_on, NVN_DEPTH_FUNC_LESS); API(nvnDepthStencilStateSetDefaults)(&ds_off);
    API(nvnColorStateSetDefaults)(&cs_none); API(nvnColorStateSetDefaults)(&cs_blend); API(nvnColorStateSetBlendEnable)(&cs_blend, 0, 1);
    API(nvnBlendStateSetDefaults)(&bl_add); API(nvnBlendStateSetBlendTarget)(&bl_add, 0); API(nvnBlendStateSetBlendFunc)(&bl_add, NVN_BLEND_FUNC_ONE, NVN_BLEND_FUNC_ONE, NVN_BLEND_FUNC_ONE, NVN_BLEND_FUNC_ONE);
    API(nvnBlendStateSetDefaults)(&bl_alpha); API(nvnBlendStateSetBlendTarget)(&bl_alpha, 0);
    API(nvnBlendStateSetBlendFunc)(&bl_alpha, NVN_BLEND_FUNC_SRC_ALPHA, NVN_BLEND_FUNC_ONE_MINUS_SRC_ALPHA, NVN_BLEND_FUNC_ONE, NVN_BLEND_FUNC_ONE_MINUS_SRC_ALPHA);
    // Warm-up frame (pipelines, textures, residency), then the measured frames
    uint64_t base_put[RBM_OPS] = {0}, base_exec[RBM_OPS] = {0}, pass0 = 0, draw0 = 0, bwl0 = 0, bws0 = 0, ar0 = 0, arb0 = 0, rs0 = 0, d0 = 0, k0 = 0, ld0 = 0, st0 = 0, cl0 = 0, dc0 = 0, cp0 = 0, fl0 = 0, cut0 = 0, pcut0 = 0;
    double frame_ms[64]; int nfm = 0;   // wall time of each measured frame, submit to queue finish (Mac runner: CPU encode + GPU + idle, not an iPhone frame time)
    for (int f = 0; f <= frames; f++) {
        rbm_ptrace_n = 0; rbm_ptrace[0] = 0;   // the queue is idle here: the trace holds the last frame only
        if (f == 1) { for (int i = 0; i < RBM_OPS; i++) { base_put[i] = atomic_load(&rbm_put_n[i]); base_exec[i] = rbm_exec_n[i]; }
            pass0 = g_stat_pass; draw0 = g_stat_draw; bwl0 = g_bw_load; bws0 = g_bw_store; ar0 = rbm_arena_calls; arb0 = rbm_arena_bytes; rs0 = rbm_res_adds;
            cut0 = g_cuts; pcut0 = g_pass_cuts; d0 = rbm_draws; k0 = rbm_dispatches; ld0 = rbm_load_bytes; st0 = rbm_store_bytes; cl0 = rbm_clear_atts; dc0 = rbm_dontcare_atts; cp0 = rbm_copy_bytes; fl0 = rbm_fill_bytes;
            rbm_h = 0xcbf29ce484222325ull;
            const char *tp = getenv("RBM_TRACE"); if (tp && *tp) { rbm_tf = fopen(tp, "w"); REQUIRE(rbm_tf); } }
        if (rbm_tf && f >= 1) fprintf(rbm_tf, "F %d\n", f);
        API(nvnCommandBufferAddCommandMemory)(&cmd, &pool, 0, CMD); API(nvnCommandBufferBeginRecording)(&cmd);
        record_frame();
        NVNcommandHandle h = API(nvnCommandBufferEndRecording)(&cmd); REQUIRE(h);
        struct timespec t0, t1; clock_gettime(CLOCK_MONOTONIC, &t0);
        API(nvnQueueSubmitCommands)(&queue, 1, &h); API(nvnQueueFinish)(&queue); REQUIRE(!mtl_last_commit_error());
        clock_gettime(CLOCK_MONOTONIC, &t1);
        if (f >= 1 && nfm < 64) frame_ms[nfm++] = (t1.tv_sec - t0.tv_sec) * 1e3 + (t1.tv_nsec - t0.tv_nsec) / 1e6;
    }
    if (rbm_tf) { FILE *tf = rbm_tf; rbm_tf = NULL; fclose(tf); }
    uint64_t px = 0xcbf29ce484222325ull; NVNtexture *outs[] = {&t_g0, &t_g1, &t_light, &t_final}; int sz[] = {W, W, W, W};
    for (int i = 0; i < 4; i++) px = rbm_mix(px, readback(outs[i], sz[i], 4));
    px = rbm_mix(px, readback(&t_half, W / 2, 4)); px = rbm_mix(px, readback(&t_quarter, W / 4, 4));
    { const uint8_t *s = mem + SSBO; for (int i = 0; i < 64 * 16; i++) px = rbm_mix(px, s[i]); }
    // One JSON line: per measured frame (frames > 0)
    #define PF(v) ((double)(v) / frames)
    uint64_t pr[RBM_OPS], ex[RBM_OPS]; for (int i = 0; i < RBM_OPS; i++) { pr[i] = atomic_load(&rbm_put_n[i]) - base_put[i]; ex[i] = rbm_exec_n[i] - base_exec[i]; }
    uint64_t barriers = pr[RO_BAR_QUEUE] + pr[RO_BAR_AFTER_STAGES] + pr[RO_BAR_ENCODER] + pr[RO_M3_WAIT] + pr[RO_M3_UPD] + pr[RO_M3_MB];
    uint64_t state = pr[RO_R_PSO] + pr[RO_R_DSS] + pr[RO_R_VIEWPORT] + pr[RO_R_SCISSOR] + pr[RO_R_CULL] + pr[RO_R_WINDING] + pr[RO_R_FILL] + pr[RO_R_BIAS] + pr[RO_R_CLIP]
                   + pr[RO_R_SREF] + pr[RO_R_BLEND] + pr[RO_R_VIS] + pr[RO_C_PSO] + pr[RO_R_STORE_C] + pr[RO_R_STORE_D] + pr[RO_R_STORE_S];
    uint64_t args = pr[RO_T_ADDR] + pr[RO_T_TEX] + pr[RO_T_SAMP] + pr[RO_R_TABLE] + pr[RO_C_TABLE] + pr[RO_M3_BUF] + pr[RO_M3_TEX] + pr[RO_M3_SMP];
    uint64_t total = 0; for (int i = 0; i < RBM_OPS; i++) total += pr[i];
    printf("METRICS {\"backend\":\"Metal%d\",\"enc_thread\":%d,\"frames\":%d,\"records\":%.1f,\"render_encoders\":%.1f,\"compute_encoders\":%.1f,\"blit_encoders\":%.1f,"
           "\"barriers_fences\":%.1f,\"state_records\":%.1f,\"pso_binds\":%.1f,\"dss_binds\":%.1f,\"viewport_scissor\":%.1f,\"argument_records\":%.1f,\"m3_buffer_binds\":%.1f,\"m3_texture_binds\":%.1f,"
           "\"table_writes\":%.1f,\"draws\":%.1f,\"dispatches\":%.1f,\"commits\":%.1f,\"load_bytes\":%.0f,\"store_bytes\":%.0f,\"cleared_attachments\":%.1f,\"dontcare_loads\":%.1f,"
           "\"copy_bytes\":%.0f,\"fill_bytes\":%.0f,\"arena_allocs\":%.1f,\"arena_bytes\":%.0f,\"residency_adds\":%.1f,\"engine_passes\":%.1f,\"engine_draws\":%.1f,"
           "\"engine_load_bytes\":%.0f,\"engine_store_bytes\":%.0f,\"cuts\":%.1f,\"pass_cuts\":%.1f,\"state_digest\":\"%016llx\",\"pixel_digest\":\"%016llx\",\"exec_equals_put\":%d}\n",
           g_m3 ? 3 : 4, rec_on(), frames, PF(total), PF(pr[RO_RE_BEGIN]), PF(pr[RO_CE_BEGIN] + pr[RO_CE_BEGIN_D]), PF(pr[RO_CB_BLIT]),
           PF(barriers), PF(state), PF(pr[RO_R_PSO] + pr[RO_C_PSO]), PF(pr[RO_R_DSS]), PF(pr[RO_R_VIEWPORT] + pr[RO_R_SCISSOR]), PF(args), PF(pr[RO_M3_BUF]), PF(pr[RO_M3_TEX] + pr[RO_M3_SMP]),
           PF(pr[RO_T_ADDR] + pr[RO_T_TEX] + pr[RO_T_SAMP]), PF(rbm_draws - d0), PF(rbm_dispatches - k0), PF(pr[RO_COMMIT] + pr[RO_COMMIT_REAL] + pr[RO_COMMIT_M3]),
           PF(rbm_load_bytes - ld0), PF(rbm_store_bytes - st0), PF(rbm_clear_atts - cl0), PF(rbm_dontcare_atts - dc0), PF(rbm_copy_bytes - cp0), PF(rbm_fill_bytes - fl0),
           PF(rbm_arena_calls - ar0), PF(rbm_arena_bytes - arb0), PF(rbm_res_adds - rs0), PF(g_stat_pass - pass0), PF(g_stat_draw - draw0), PF(g_bw_load - bwl0), PF(g_bw_store - bws0), PF(g_cuts - cut0), PF(g_pass_cuts - pcut0),
           (unsigned long long)rbm_h, (unsigned long long)px, !memcmp(pr, ex, sizeof pr));
    printf("TIMES"); for (int i = 0; i < nfm; i++) printf(" %.4f", frame_ms[i]); printf("\n");
    printf("PASSES%s\n", rbm_ptrace);
    printf("OPS");
    for (int i = 0; i < RBM_OPS; i++) if (pr[i]) printf(" %d:%llu", i, (unsigned long long)pr[i]);
    printf("\n");
    unlink(map); unlink(user);
    return rec_on() ? 0 : 3;   // without the encode thread there is no record stream to measure
} }
