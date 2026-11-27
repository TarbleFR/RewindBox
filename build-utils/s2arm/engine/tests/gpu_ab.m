// GPU A/B timing of two Metal libraries with the same kernel signature (k_ab), in one process on one device.
// Used by gpu_ab.py: A is the S2A.Dsh output with a pass off, B with it on. Each sample is one command buffer of
// DISPATCHES dispatches over N threads; the time is GPUEndTime - GPUStartTime. A and B alternate (ABAB / BABA) for
// PAIRS pairs, and the output buffers of A and B must be byte-identical after every pair. Not a game replay, not an
// iPhone or Metal 4 measurement: the macOS runner exposes an Apple Paravirtual device without Metal 4.
// usage: gpu_ab A.metallib B.metallib case_name n_threads in_words binding_offset_words scatter
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { PAIRS = 12, DISPATCHES = 20 };
static int cmpd(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }

int main(int argc, char **argv) { @autoreleasepool {
    if (argc < 8) { fprintf(stderr, "usage: %s A.metallib B.metallib case n in_words bind_off scatter\n", argv[0]); return 2; }
    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    if (!dev) { fprintf(stderr, "SKIP: no Metal device\n"); return 77; }
    const char *name = argv[3];
    uint32_t n = (uint32_t)strtoul(argv[4], NULL, 0), inWords = (uint32_t)strtoul(argv[5], NULL, 0), bindOff = (uint32_t)strtoul(argv[6], NULL, 0);
    int scatter = atoi(argv[7]);
    NSError *err = nil; id<MTLComputePipelineState> ps[2];
    for (int v = 0; v < 2; v++) {
        id<MTLLibrary> lib = [dev newLibraryWithURL:[NSURL fileURLWithPath:@(argv[1 + v])] error:&err];
        id<MTLFunction> fn = [lib newFunctionWithName:@"k_ab"];
        ps[v] = fn ? [dev newComputePipelineStateWithFunction:fn error:&err] : nil;
        if (!ps[v]) { fprintf(stderr, "pipeline %c: %s\n", 'A' + v, err.localizedDescription.UTF8String); return 1; }
    }
    id<MTLCommandQueue> q = [dev newCommandQueue];
    const uint32_t outWords = n * 4;
    id<MTLBuffer> src = [dev newBufferWithLength:((size_t)inWords + bindOff + 4) * 4 options:MTLResourceStorageModePrivate];
    id<MTLBuffer> srcUp = [dev newBufferWithLength:((size_t)inWords + bindOff + 4) * 4 options:MTLResourceStorageModeShared];
    uint32_t *sp = (uint32_t *)srcUp.contents;
    for (size_t i = 0; i < (size_t)inWords + bindOff + 4; i++) sp[i] = (uint32_t)(i * 2654435761u) ^ 0x5bd1e995u;
    id<MTLBuffer> offs = [dev newBufferWithLength:(size_t)n * 4 options:MTLResourceStorageModeShared];
    int32_t *op = (int32_t *)offs.contents;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t w = scatter ? (uint32_t)(((uint64_t)i * 2654435761u) % (inWords / 4)) * 4 : (i * 4) % inWords;
        op[i] = (int32_t)(w * 4);   // byte offset of a 16-byte group inside the bound range
    }
    id<MTLBuffer> dst[2], args[2], rb[2];
    for (int v = 0; v < 2; v++) {
        dst[v] = [dev newBufferWithLength:((size_t)outWords + bindOff + 4) * 4 options:MTLResourceStorageModePrivate];
        rb[v] = [dev newBufferWithLength:((size_t)outWords + bindOff + 4) * 4 options:MTLResourceStorageModeShared];
        args[v] = [dev newBufferWithLength:16 options:MTLResourceStorageModeShared];
        uint64_t *a = (uint64_t *)args[v].contents;
        a[0] = src.gpuAddress + (uint64_t)bindOff * 4; a[1] = dst[v].gpuAddress + (uint64_t)bindOff * 4;
    }
    {   id<MTLCommandBuffer> cb = [q commandBuffer]; id<MTLBlitCommandEncoder> b = [cb blitCommandEncoder];
        [b copyFromBuffer:srcUp sourceOffset:0 toBuffer:src destinationOffset:0 size:srcUp.length]; [b endEncoding]; [cb commit]; [cb waitUntilCompleted]; }
    double t[2][PAIRS], pct[PAIRS]; int fails = 0;
    double (^sample)(int) = ^double(int v) {
        id<MTLCommandBuffer> cb = [q commandBuffer];
        id<MTLBlitCommandEncoder> f = [cb blitCommandEncoder]; [f fillBuffer:dst[v] range:NSMakeRange(0, dst[v].length) value:0xA5]; [f endEncoding];
        id<MTLCommandBuffer> run = [q commandBuffer];
        id<MTLComputeCommandEncoder> e = [run computeCommandEncoder];
        [e setComputePipelineState:ps[v]];
        [e setBuffer:args[v] offset:0 atIndex:0];
        [e setBytes:&inWords length:4 atIndex:1];
        [e setBytes:&outWords length:4 atIndex:2];
        [e setBuffer:offs offset:0 atIndex:3];
        [e useResource:src usage:MTLResourceUsageRead];
        [e useResource:dst[v] usage:MTLResourceUsageRead | MTLResourceUsageWrite];
        NSUInteger tg = MIN((NSUInteger)256, ps[v].maxTotalThreadsPerThreadgroup);
        for (int d = 0; d < DISPATCHES; d++) [e dispatchThreads:MTLSizeMake(n, 1, 1) threadsPerThreadgroup:MTLSizeMake(tg, 1, 1)];
        [e endEncoding];
        id<MTLBlitCommandEncoder> c = [run blitCommandEncoder]; [c copyFromBuffer:dst[v] sourceOffset:0 toBuffer:rb[v] destinationOffset:0 size:rb[v].length]; [c endEncoding];
        [cb commit]; [run commit]; [run waitUntilCompleted];
        if (run.status == MTLCommandBufferStatusError) { fprintf(stderr, "command buffer error: %s\n", run.error.localizedDescription.UTF8String); exit(1); }
        return (run.GPUEndTime - run.GPUStartTime) * 1e3;   // includes the read-back copy, the same for A and B
    };
    sample(0); sample(1);   // warm-up
    printf("case,pair,variant,gpu_ms\n");
    for (int p = 0; p < PAIRS; p++) {
        for (int k = 0; k < 2; k++) { int v = (p & 1) ^ k; t[v][p] = sample(v); }
        if (memcmp(rb[0].contents, rb[1].contents, rb[0].length)) { if (fails++ < 4) fprintf(stderr, "%s pair %d: outputs differ\n", name, p); }
        printf("%s,%d,A,%.4f\n%s,%d,B,%.4f\n", name, p, t[0][p], name, p, t[1][p]);
        pct[p] = 100.0 * (t[1][p] / t[0][p] - 1.0);
    }
    // CPU oracle on the last B output: every written word is the source word it copies (aligned groups inside the range)
    const uint32_t *o = (const uint32_t *)rb[1].contents + bindOff;
    for (uint32_t i = 0; i < n && fails < 8; i++) for (uint32_t k = 0; k < 4; k++) {
        uint32_t want = sp[bindOff + (uint32_t)op[i] / 4 + k];
        if (o[i * 4 + k] != want) { if (fails++ < 8) fprintf(stderr, "%s oracle i=%u k=%u got=%08x want=%08x\n", name, i, k, o[i * 4 + k], want); }
    }
    qsort(t[0], PAIRS, 8, cmpd); qsort(t[1], PAIRS, 8, cmpd); qsort(pct, PAIRS, 8, cmpd);
    printf("SUMMARY %s device=\"%s\" n=%u dispatches=%d A_median_ms=%.4f B_median_ms=%.4f paired_median_pct=%.2f p25=%.2f p75=%.2f parity=%s\n", name, dev.name.UTF8String, n, DISPATCHES,
           (t[0][5] + t[0][6]) / 2, (t[1][5] + t[1][6]) / 2, (pct[5] + pct[6]) / 2, (pct[2] + pct[3]) / 2, (pct[8] + pct[9]) / 2, fails ? "FAIL" : "ok");
    return fails ? 1 : 0;
} }
