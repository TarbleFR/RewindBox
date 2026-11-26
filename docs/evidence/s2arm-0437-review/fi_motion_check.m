#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

// R16Float luma in the exact format consumed by match, including its clamped edge blocks.
static uint16_t sample(unsigned x, unsigned y, unsigned seed) {
    uint32_t v = x * 0x1f123bb5u + y * 0x5f356495u + seed;
    v ^= v >> 16;
    v *= 0x85ebca6bu;
    v ^= v >> 13;
    return 0x3000u + v % 0x0bffu; // finite binary16 luminance in [0.125, 1)
}

static id<MTLTexture> luma(id<MTLDevice> dev, unsigned w, unsigned h, int scene, BOOL current) {
    MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatR16Float
                                                                                  width:w height:h mipmapped:NO];
    d.storageMode = MTLStorageModeShared;
    d.usage = MTLTextureUsageShaderRead;
    id<MTLTexture> tex = [dev newTextureWithDescriptor:d];
    if (!tex) return nil;
    NSMutableData *data = [NSMutableData dataWithLength:w * h * sizeof(uint16_t)];
    uint16_t *pixels = data.mutableBytes;
    for (unsigned y = 0; y < h; y++) {
        for (unsigned x = 0; x < w; x++) {
            unsigned sx = x, sy = y;
            if (current && scene == 1) {
                sx = MIN(x + 3, w - 1);
                sy = y > 2 ? y - 2 : 0;
            }
            pixels[y*w+x] = sample(sx, sy, (scene == 2 && current) ? 170041u : 230921u);
        }
    }
    [tex replaceRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:0 withBytes:pixels bytesPerRow:w * sizeof(uint16_t)];
    return tex;
}

static id<MTLComputePipelineState> compileFive(id<MTLDevice> dev, NSString *file) {
    NSError *error = nil;
    NSString *src = [NSString stringWithContentsOfFile:file encoding:NSUTF8StringEncoding error:&error];
    if (!src) { NSLog(@"Cannot read %@: %@", file, error); return nil; }
    id<MTLLibrary> lib = [dev newLibraryWithSource:src options:nil error:&error];
    if (!lib) { NSLog(@"Runtime MSL compile failed for %@: %@", file, error); return nil; }
    id<MTLComputePipelineState> match = nil;
    for (NSString *name in @[@"down", @"down2", @"match", @"spread", @"cut"]) {
        id<MTLFunction> f = [lib newFunctionWithName:name];
        if (!f) { NSLog(@"Missing %@ in %@", name, file); return nil; }
        id<MTLComputePipelineState> pso = [dev newComputePipelineStateWithFunction:f error:&error];
        if (!pso) { NSLog(@"Cannot build %@ in %@: %@", name, file, error); return nil; }
        if ([name isEqualToString:@"match"]) match = pso;
    }
    fprintf(stdout, "%s all five PSOs ready, match SIMD width=%lu max threads/TG=%lu\n", file.lastPathComponent.UTF8String,
            (unsigned long)match.threadExecutionWidth, (unsigned long)match.maxTotalThreadsPerThreadgroup);
    return match;
}

// The engine uses the coarse match as prediction for the fine level. Use separately
// completed command buffers so this kernel check is independent of Metal 4 queue/barrier behavior.
static BOOL runLevel(id<MTLCommandQueue> queue, id<MTLComputePipelineState> pso,
                     id<MTLTexture> cur, id<MTLTexture> prev, unsigned scale,
                     id<MTLBuffer> pred, const uint32_t pn[2], id<MTLBuffer> vectors, id<MTLBuffer> sad) {
    uint32_t gm[4] = {(uint32_t)(cur.width + 7) / 8, (uint32_t)(cur.height + 7) / 8,
                       scale, scale == 16 ? 1u : 4u};
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
    if (!enc) return NO;
    [enc setComputePipelineState:pso];
    [enc setTexture:cur atIndex:0]; [enc setTexture:prev atIndex:1];
    [enc setBuffer:vectors offset:0 atIndex:0]; [enc setBytes:gm length:sizeof(gm) atIndex:1];
    [enc setBuffer:pred offset:0 atIndex:2]; [enc setBytes:pn length:2*sizeof(*pn) atIndex:3];
    [enc setBuffer:sad offset:0 atIndex:4];
    [enc dispatchThreadgroups:MTLSizeMake(gm[0],gm[1],1) threadsPerThreadgroup:MTLSizeMake(32,32,1)];
    [enc endEncoding]; [cb commit]; [cb waitUntilCompleted];
    if (cb.status != MTLCommandBufferStatusCompleted) { NSLog(@"match failed: %@", cb.error); return NO; }
    return YES;
}

static int check(id<MTLDevice> dev, NSArray *psos) {
    id<MTLCommandQueue> queue = [dev newCommandQueue];
    if (!queue) { NSLog(@"Cannot create Metal command queue"); return 1; }
    const unsigned width[] = {24, 95}, height[] = {19, 73}; // coarse = ceil(fine/4)
    uint32_t grid[2][2];
    for (unsigned l=0;l<2;l++) { grid[l][0]=(width[l]+7)/8; grid[l][1]=(height[l]+7)/8; }
    uint32_t noPred[] = {0,0};
    for (int scene=0;scene<3;scene++) {
        id<MTLTexture> current[2], previous[2];
        for (unsigned l=0;l<2;l++) {
            current[l]=luma(dev,width[l],height[l],scene,YES);
            previous[l]=luma(dev,width[l],height[l],scene,NO);
            if (!current[l] || !previous[l]) { NSLog(@"R16Float texture allocation failed"); return 1; }
        }
        NSData *referenceVec[2], *referenceSad[2];
        for (unsigned version=0;version<3;version++) {
            id<MTLBuffer> pred=[dev newBufferWithLength:8 options:MTLResourceStorageModeShared];
            if (!pred) { NSLog(@"Cannot allocate initial prediction"); return 1; }
            memset(pred.contents,0,8);
            for (unsigned l=0;l<2;l++) {
                NSUInteger blocks=grid[l][0]*grid[l][1];
                id<MTLBuffer> vec=[dev newBufferWithLength:blocks*8 options:MTLResourceStorageModeShared];
                id<MTLBuffer> sad=[dev newBufferWithLength:blocks*4 options:MTLResourceStorageModeShared];
                if (!vec || !sad) { NSLog(@"Cannot allocate readback buffers"); return 1; }
                memset(vec.contents,0xff,vec.length); memset(sad.contents,0xff,sad.length);
                if (!runLevel(queue,psos[version],current[l],previous[l],l?4:16,pred,l?grid[0]:noPred,vec,sad)) return 1;
                pred=vec;
                const float *v=vec.contents,*s=sad.contents;
                NSUInteger vecDiff=0,sadDiff=0;
                for (NSUInteger b=0;b<blocks;b++) {
                    if (!isfinite(s[b]) || !isfinite(v[2*b]) || !isfinite(v[2*b+1]) || s[b]<0 ||
                        (scene==0 && (v[2*b]!=0 || v[2*b+1]!=0 || s[b]!=0))) {
                        NSLog(@"Invalid/unwritten result scene=%d level=%u version=%u block=%lu",scene,l,version,(unsigned long)b);
                        return 1;
                    }
                    // Interior 8x8 block has exact motion (+3,-2) in the shifted fixture.
                    if (scene==1 && l==1 && b==grid[1][0]*3+4 &&
                        (v[2*b]!=12 || v[2*b+1]!=-8 || s[b]!=0)) {
                        NSLog(@"Incorrect motion in translated interior block version=%u",version); return 1;
                    }
                    if (version) {
                        vecDiff+=memcmp(v+2*b,(const uint8_t *)referenceVec[l].bytes+8*b,8)!=0;
                        sadDiff+=memcmp(s+b,(const uint8_t *)referenceSad[l].bytes+4*b,4)!=0;
                    }
                }
                if (version==0) {
                    referenceVec[l]=[NSData dataWithBytes:v length:vec.length];
                    referenceSad[l]=[NSData dataWithBytes:s length:sad.length];
                } else {
                    fprintf(stdout,"scene=%d level=%u version=%u blocks=%lu different vectors=%lu SAD=%lu\n",
                            scene,l,version,(unsigned long)blocks,(unsigned long)vecDiff,(unsigned long)sadDiff);
                    if (version==2 && (vecDiff || sadDiff)) return 1;
                }
            }
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 4) return 2;
        id<MTLDevice> dev=MTLCreateSystemDefaultDevice();
        if (!dev) { fprintf(stderr,"Unavailable: no macOS Metal device.\n"); return 77; }
        fprintf(stdout,"Metal device %s\n",dev.name.UTF8String);
        NSMutableArray *psos=[NSMutableArray array];
        for (unsigned k=1;k<4;k++) {
            id<MTLComputePipelineState> p=compileFive(dev,[NSString stringWithUTF8String:argv[k]]);
            if (!p) return 1;
            [psos addObject:p];
        }
        for (id<MTLComputePipelineState> p in psos) {
            if (p.threadExecutionWidth!=32 || p.maxTotalThreadsPerThreadgroup<1024 || !dev.hasUnifiedMemory) {
                fprintf(stderr,"Unavailable: match fixture requires unified memory, 32-lane SIMD and 1024-thread groups.\n"); return 77;
            }
        }
        return check(dev,psos);
    }
}
