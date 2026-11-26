#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static id<MTLLibrary> library(id<MTLDevice> dev, NSString *source) {
    NSError *error = nil;
    id<MTLLibrary> lib = [dev newLibraryWithSource:source options:nil error:&error];
    if (!lib) NSLog(@"MSL: %@", error);
    return lib;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 5) return 2;
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev) return 77;
        id<MTLCommandQueue> queue = [dev newCommandQueue];
        if (!queue) return 1;
        NSLog(@"Metal device: %@", dev.name);
        NSError *error = nil;
        NSString *msl = [NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&error];
        if (!msl) { NSLog(@"read: %@", error); return 1; }
        id<MTLFunction> fn = [library(dev, msl) newFunctionWithName:@(argv[2])];
        NSData *expected = [NSData dataWithContentsOfFile:@(argv[4])];
        BOOL compute = strcmp(argv[3], "comp") == 0;
        const NSUInteger width = 64, height = 64;
        const NSUInteger bytes = compute ? 64 * sizeof(uint32_t) : width * height * 4;
        if (!fn || expected.length != bytes) return 1;
        id<MTLBuffer> buffer = [dev newBufferWithLength:bytes options:MTLResourceStorageModeShared];
        if (!buffer) return 1;
        id<MTLComputePipelineState> cp = nil;
        id<MTLRenderPipelineState> rp = nil;
        id<MTLTexture> image = nil;
        if (compute) {
            cp = [dev newComputePipelineStateWithFunction:fn error:&error];
            if (!cp) { NSLog(@"compute PSO: %@", error); return 1; }
        } else {
            NSString *vs = @"#include <metal_stdlib>\nusing namespace metal;\n"
                "struct V { float4 pos [[position]]; float4 value [[user(locn0)]]; };\n"
                "vertex V seed(uint i [[vertex_id]]) { float2 p = float2((i<<1)&2, i&2); "
                "return {float4(p*2.0f-1.0f,0,1),float4(.25f,.5f,.75f,1.0f)}; }";
            MTLRenderPipelineDescriptor *desc = [MTLRenderPipelineDescriptor new];
            desc.vertexFunction = [library(dev, vs) newFunctionWithName:@"seed"];
            desc.fragmentFunction = fn;
            desc.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
            rp = [dev newRenderPipelineStateWithDescriptor:desc error:&error];
            if (!rp) { NSLog(@"render PSO: %@", error); return 1; }
            MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
                width:width height:height mipmapped:NO];
            td.usage = MTLTextureUsageRenderTarget; td.storageMode = MTLStorageModePrivate;
            image = [dev newTextureWithDescriptor:td];
            if (!image) return 1;
        }
        for (int run = 0; run < 6; run++) {
            memset(buffer.contents, 0xcd, bytes);
            id<MTLCommandBuffer> cb = [queue commandBuffer];
            if (!cb) return 1;
            if (compute) {
                uint32_t *words = buffer.contents;
                for (unsigned i = 0; i < 64; i++) words[i] = i;
                words[0] = 17;
                id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
                if (!ce) return 1;
                [ce setComputePipelineState:cp];
                [ce setBuffer:buffer offset:0 atIndex:2];
                [ce dispatchThreadgroups:MTLSizeMake(1,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];
                [ce endEncoding];
            } else {
                MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
                pass.colorAttachments[0].texture = image;
                pass.colorAttachments[0].loadAction = MTLLoadActionClear;
                pass.colorAttachments[0].storeAction = MTLStoreActionStore;
                pass.colorAttachments[0].clearColor = MTLClearColorMake(0,0,0,0);
                id<MTLRenderCommandEncoder> re = [cb renderCommandEncoderWithDescriptor:pass];
                if (!re) return 1;
                [re setRenderPipelineState:rp];
                [re drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
                [re endEncoding];
                id<MTLBlitCommandEncoder> blit = [cb blitCommandEncoder];
                if (!blit) return 1;
                [blit copyFromTexture:image sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
                    sourceSize:MTLSizeMake(width,height,1) toBuffer:buffer destinationOffset:0
                    destinationBytesPerRow:width*4 destinationBytesPerImage:bytes];
                [blit endEncoding];
            }
            [cb commit]; [cb waitUntilCompleted];
            if (cb.status != MTLCommandBufferStatusCompleted) { NSLog(@"execution: %@", cb.error); return 1; }
            if (memcmp(buffer.contents, expected.bytes, bytes)) {
                fprintf(stderr, "output mismatch at repetition %d\n", run); return 1;
            }
        }
        printf("%s: 6 exact Metal readbacks of %zu bytes\n",argv[2],(size_t)bytes);
    }
    return 0;
}
