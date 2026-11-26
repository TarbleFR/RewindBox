#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "nvn_deswizzle.h"
#include <stdio.h>
#include <string.h>

typedef struct {
    uint64_t src_off, dst_off, base, pitch;
    uint32_t row_bytes, rows, slices, th, td, gobs_x, gob2;
} Params;

static int compare(id<MTLDevice> dev, id<MTLCommandQueue> queue, id<MTLComputePipelineState> pso,
                   const char *name, Params p) {
    const unsigned cols = (p.row_bytes + 63) / 64, lines = (p.rows + 7) / 8;
    const unsigned bh = 1u << p.th, bd = 1u << p.td;
    const unsigned blocks_y = (lines + bh - 1) / bh, blocks_z = (p.slices + bd - 1) / bd;
    const NSUInteger src_size = p.src_off + p.base + (uint64_t)p.gobs_x * blocks_y * blocks_z * bh * bd * 512;
    const NSUInteger dst_size = p.dst_off + p.pitch * p.rows * p.slices + 61;
    id<MTLBuffer> src = [dev newBufferWithLength:src_size options:MTLResourceStorageModeShared];
    id<MTLBuffer> dst = [dev newBufferWithLength:dst_size options:MTLResourceStorageModeShared];
    NSMutableData *expected = [NSMutableData dataWithLength:dst_size];
    if (!src || !dst || !expected) return 1;
    uint8_t *input = src.contents, *oracle = expected.mutableBytes;
    uint32_t rng = 9161;
    for (NSUInteger i = 0; i < src_size; i++) {
        rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; input[i] = (uint8_t)rng;
    }
    memset(oracle,0xa7,dst_size);
    nvn_gob_switch2 = p.gob2;
    for (unsigned z = 0; z < p.slices; z++)
        for (unsigned y = 0; y < p.rows; y++)
            for (unsigned x = 0; x < p.row_bytes; x++) {
                uint64_t off = nvn_bl_offset(x,y,z,p.gobs_x*64,p.rows,p.th,p.td);
                oracle[p.dst_off + ((uint64_t)z*p.rows+y)*p.pitch+x] = input[p.src_off+p.base+off];
            }
    const unsigned passes = 12;
    for (unsigned pair = 0; pair <= 12; pair++) {
        for (unsigned j = 0; j < 4; j++) {
            // Four rotations and their reversals balance positions across groups.
            unsigned k = ((pair & 4 ? 3-j : j) + pair) % 4, gobs = 1u << k;
            memset(dst.contents,0xa7,dst_size);
            id<MTLCommandBuffer> cb = [queue commandBuffer];
            id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
            if (!cb || !enc) return 1;
            [enc setComputePipelineState:pso];
            [enc setBuffer:src offset:0 atIndex:0]; [enc setBuffer:dst offset:0 atIndex:1];
            [enc setBytes:&p length:sizeof p atIndex:2];
            for (unsigned n = 0; n < passes; n++)
                [enc dispatchThreadgroups:MTLSizeMake((cols+gobs-1)/gobs,lines,p.slices)
                    threadsPerThreadgroup:MTLSizeMake(32*gobs,1,1)];
            [enc endEncoding]; [cb commit]; [cb waitUntilCompleted];
            if (cb.status != MTLCommandBufferStatusCompleted || memcmp(dst.contents,oracle,dst_size)) {
                NSLog(@"Incorrect output or GPU error %s, %u GOBs, %@",name,gobs,cb.error); return 1;
            }
            if (pair) {
                double ms = (cb.GPUStartTime > 0 && cb.GPUEndTime > cb.GPUStartTime)
                    ? (cb.GPUEndTime - cb.GPUStartTime) * 1000 : 0;
                printf("GPU_TEXTURE,%s,%u,%u,%u,%u,%.6f\n",name,pair,gobs,passes,p.row_bytes*p.rows*p.slices,ms);
            }
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    @autoreleasepool {
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev || !dev.hasUnifiedMemory) return 77;
        NSError *err = nil;
        NSString *shader = [NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&err];
        if (!shader) return 1;
        id<MTLLibrary> lib = [dev newLibraryWithSource:shader options:nil error:&err];
        if (!lib) { NSLog(@"library: %@",err); return 1; }
        id<MTLComputePipelineState> pso = [dev newComputePipelineStateWithFunction:[lib newFunctionWithName:@"deswz"] error:&err];
        if (!pso) { NSLog(@"PSO: %@",err); return 1; }
        if (pso.maxTotalThreadsPerThreadgroup < 256) return 77;
        id<MTLCommandQueue> queue = [dev newCommandQueue];
        fprintf(stderr,"Texture GPU device: %s, SIMD lanes %zu. Times cover one batch of 12 resident-buffer dispatches.\n",
                dev.name.UTF8String,(size_t)pso.threadExecutionWidth);
        if (!queue) return 1;
        const struct { const char *name; Params p; } cases[] = {
            {"large-classic", {0,0,0,4096,4096,1024,1,4,0,64,0}},
            {"large-switch2", {0,0,0,4096,4096,1024,1,4,0,64,1}},
            {"partial-padded", {3,5,7,2081,2049,241,1,2,0,37,1}},
            {"volume", {16,32,512,640,587,39,5,1,2,10,1}},
            {"small", {0,0,0,128,96,7,1,0,0,2,0}}
        };
        for (unsigned i = 0; i < sizeof(cases)/sizeof(*cases); i++) {
            int status = compare(dev,queue,pso,cases[i].name,cases[i].p);
            if (status) return status;
        }
    }
    return 0;
}
