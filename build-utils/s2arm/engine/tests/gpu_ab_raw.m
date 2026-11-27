// GPU A/B of the raw guest-memory LDG.128 path (Zelda's raw memory shaders) in one process on one device.
// A: the helpers dmsh_xlate emits with S2A_RB_WIDE_MEM=0 (one translated load, three window loads); B: with
// S2A_RB_WIDE_MEM=1 (one 16-byte helper). Same kernel k_ab(map, mapBytes, out, steps), one guest pool of POOL bytes
// at guest address GUEST, each thread reads `steps` consecutive 16-byte groups and writes their xor. Alternated pairs,
// outputs of A and B byte-identical and equal to a CPU oracle. Apple Paravirtual device without Metal 4: relative cost only.
// usage: gpu_ab_raw A.metallib B.metallib case threads steps interleaved [hint]  (hint 1: the 2 MiB chunk hints of the pool filled, as the engine's gmem_map does)
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { PAIRS = 12, DISPATCHES = 10 };
static const uint64_t GUEST = 0x10000000ull;
static id<MTLComputePipelineState> ps[2]; static id<MTLBuffer> map, pool, outb[2], rb[2]; static id<MTLCommandQueue> q;
static uint32_t n, steps, scatter, mapBytes;
static int cmpd(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }
static double sample(int v) {
    id<MTLCommandBuffer> run = [q commandBuffer];
    id<MTLComputeCommandEncoder> e = [run computeCommandEncoder];
    [e setComputePipelineState:ps[v]];
    [e setBuffer:map offset:0 atIndex:0];
    [e setBytes:&mapBytes length:4 atIndex:1];
    [e setBuffer:outb[v] offset:0 atIndex:2];
    [e setBytes:&steps length:4 atIndex:3];
    [e setBytes:&scatter length:4 atIndex:4];
    [e useResource:pool usage:MTLResourceUsageRead];
    NSUInteger tg = MIN((NSUInteger)256, ps[v].maxTotalThreadsPerThreadgroup);
    for (int d = 0; d < DISPATCHES; d++) [e dispatchThreads:MTLSizeMake(n, 1, 1) threadsPerThreadgroup:MTLSizeMake(tg, 1, 1)];
    [e endEncoding];
    id<MTLCommandBuffer> back = [q commandBuffer];
    id<MTLBlitCommandEncoder> c = [back blitCommandEncoder]; [c copyFromBuffer:outb[v] sourceOffset:0 toBuffer:rb[v] destinationOffset:0 size:rb[v].length]; [c endEncoding];
    [run commit]; [back commit]; [back waitUntilCompleted]; [run waitUntilCompleted];
    if (run.status == MTLCommandBufferStatusError) { fprintf(stderr, "command buffer error: %s\n", run.error.localizedDescription.UTF8String); exit(1); }
    return (run.GPUEndTime - run.GPUStartTime) * 1e3;
}
int main(int argc, char **argv) { @autoreleasepool {
    if (argc < 7) { fprintf(stderr, "usage: %s A.metallib B.metallib case threads steps scatter\n", argv[0]); return 2; }
    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    if (!dev) { fprintf(stderr, "SKIP: no Metal device\n"); return 77; }
    const char *name = argv[3]; n = (uint32_t)strtoul(argv[4], NULL, 0); steps = (uint32_t)strtoul(argv[5], NULL, 0); scatter = (uint32_t)strtoul(argv[6], NULL, 0);
    NSError *err = nil;
    for (int v = 0; v < 2; v++) {
        id<MTLLibrary> lib = [dev newLibraryWithURL:[NSURL fileURLWithPath:@(argv[1 + v])] error:&err];
        id<MTLFunction> fn = [lib newFunctionWithName:@"k_ab"];
        ps[v] = fn ? [dev newComputePipelineStateWithFunction:fn error:&err] : nil;
        if (!ps[v]) { fprintf(stderr, "pipeline %c: %s\n", 'A' + v, err.localizedDescription.UTF8String); return 1; }
    }
    q = [dev newCommandQueue];
    const uint64_t poolBytes = (uint64_t)n * steps * 16;   // every group of every thread inside the pool
    pool = [dev newBufferWithLength:poolBytes options:MTLResourceStorageModeShared];
    uint32_t *pw = (uint32_t *)pool.contents;
    for (uint64_t i = 0; i < poolBytes / 4; i++) pw[i] = (uint32_t)(i * 2654435761u) ^ 0x9e3779b9u;
    // Pool table as test_wide_mem.py's GPU check lays it out: 8192 entries of 32 bytes, entry 0 empty, entries 2.. past every address, entry 1 the pool
    mapBytes = 8192 * 32;
    map = [dev newBufferWithLength:mapBytes options:MTLResourceStorageModeShared];
    uint32_t *t = (uint32_t *)map.contents; memset(t, 0, mapBytes);
    for (int k = 1; k < 8192; k++) memset(t + k * 8, 0xff, 8);
    uint64_t *ent = (uint64_t *)(t + 8); ent[0] = GUEST; ent[1] = GUEST + poolBytes; ent[2] = pool.gpuAddress - GUEST;
    if (argc > 7 && atoi(argv[7]))   // word 6 of entry (chunk mod 8192) = chunk << 13 | entry, for each 2 MiB chunk wholly inside the pool (dmsh_abi.h DMSH_GMEM_HINT_SHIFT 21)
        for (uint64_t c = GUEST >> 21; c < (GUEST + poolBytes) >> 21; c++) t[(c & 8191) * 8 + 6] = (uint32_t)(c << 13 | 1);
    for (int v = 0; v < 2; v++) {
        outb[v] = [dev newBufferWithLength:(size_t)n * 16 options:MTLResourceStorageModePrivate];
        rb[v] = [dev newBufferWithLength:(size_t)n * 16 options:MTLResourceStorageModeShared];
    }
    sample(0); sample(1);
    double tm[2][PAIRS], pct[PAIRS]; int fails = 0;
    printf("case,pair,variant,gpu_ms\n");
    for (int p = 0; p < PAIRS; p++) {
        for (int k = 0; k < 2; k++) { int v = (p & 1) ^ k; tm[v][p] = sample(v); }
        if (memcmp(rb[0].contents, rb[1].contents, rb[0].length)) { if (fails++ < 4) fprintf(stderr, "%s pair %d: outputs differ\n", name, p); }
        printf("%s,%d,A,%.4f\n%s,%d,B,%.4f\n", name, p, tm[0][p], name, p, tm[1][p]);
        pct[p] = 100.0 * (tm[1][p] / tm[0][p] - 1.0);
    }
    const uint32_t *o = (const uint32_t *)rb[1].contents;
    for (uint32_t i = 0; i < n && fails < 8; i += 997) {
        uint32_t want[4] = {0, 0, 0, 0};
        for (uint32_t s = 0; s < steps; s++) {
            uint64_t g = scatter ? ((uint64_t)s * n + i) : ((uint64_t)i * steps + s);   // the kernel's group index
            for (int w = 0; w < 4; w++) want[w] ^= pw[g * 4 + w];
        }
        for (int w = 0; w < 4; w++) if (o[i * 4 + w] != want[w]) { if (fails++ < 8) fprintf(stderr, "%s oracle i=%u w=%d got=%08x want=%08x\n", name, i, w, o[i * 4 + w], want[w]); }
    }
    qsort(tm[0], PAIRS, 8, cmpd); qsort(tm[1], PAIRS, 8, cmpd); qsort(pct, PAIRS, 8, cmpd);
    printf("SUMMARY %s device=\"%s\" threads=%u steps=%u dispatches=%d A_median_ms=%.4f B_median_ms=%.4f paired_median_pct=%.2f p25=%.2f p75=%.2f parity=%s\n", name, dev.name.UTF8String, n, steps, DISPATCHES,
           (tm[0][5] + tm[0][6]) / 2, (tm[1][5] + tm[1][6]) / 2, (pct[5] + pct[6]) / 2, (pct[2] + pct[3]) / 2, (pct[8] + pct[9]) / 2, fails ? "FAIL" : "ok");
    return fails ? 1 : 0;
} }
