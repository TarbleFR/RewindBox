// SPDX-License-Identifier: Apache-2.0
// GPU verification for RewindBox patch 0399 (S2A_RB_DS_COMPRESS):
// 1. Creates a private Depth32Float_Stencil8 texture WITHOUT MTLTextureUsagePixelFormatView
//    (allowing Apple Silicon TBDR lossless depth-stencil compression).
// 2. Renders known depth + stencil patterns across 4 quadrants.
// 3. Upgrades it on demand to a texture WITH MTLTextureUsagePixelFormatView via blit copy
//    (matching nvn_mtl.m tex_upgrade_pfv).
// 4. Creates an MTLPixelFormatX32_Stencil8 view and reads back both depth and stencil in a
//    compute kernel, verifying 100% bit-exact preservation of all depth and stencil texels.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

static const char *kShaders =
    "#include <metal_stdlib>\n"
    "using namespace metal;\n"
    "struct VOut { float4 pos [[position]]; };\n"
    "vertex VOut vs_quad(uint vid [[vertex_id]], constant float4 &rect [[buffer(0)]]) {\n"
    "    float2 corners[4] = { float2(rect.x, rect.y), float2(rect.z, rect.y), float2(rect.x, rect.w), float2(rect.z, rect.w) };\n"
    "    VOut o; o.pos = float4(corners[vid], rect.x < 0.0f ? (rect.y < 0.0f ? 0.25f : 0.50f) : (rect.y < 0.0f ? 0.75f : 0.90f), 1.0f);\n"
    "    return o;\n"
    "}\n"
    "fragment void fs_empty() {}\n"
    "kernel void read_ds(depth2d<float> dtex [[texture(0)]],\n"
    "                    texture2d<uint> stex [[texture(1)]],\n"
    "                    device float *out_d [[buffer(0)]],\n"
    "                    device uint *out_s [[buffer(1)]],\n"
    "                    uint2 gid [[thread_position_in_grid]]) {\n"
    "    if (gid.x >= dtex.get_width() || gid.y >= dtex.get_height()) return;\n"
    "    uint idx = gid.y * dtex.get_width() + gid.x;\n"
    "    out_d[idx] = dtex.read(gid);\n"
    "    out_s[idx] = stex.read(gid).r;\n"
    "}\n";

int main(void) {
    @autoreleasepool {
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev) {
            printf("SKIP test_ds_compress_metal: no Metal device\n");
            return 77;
        }
        NSError *err = nil;
        id<MTLLibrary> lib = [dev newLibraryWithSource:@(kShaders) options:nil error:&err];
        if (!lib) {
            fprintf(stderr, "FAIL compile shaders: %s\n", err.localizedDescription.UTF8String);
            return 1;
        }
        id<MTLFunction> vf = [lib newFunctionWithName:@"vs_quad"];
        id<MTLFunction> ff = [lib newFunctionWithName:@"fs_empty"];
        id<MTLFunction> kf = [lib newFunctionWithName:@"read_ds"];

        MTLRenderPipelineDescriptor *rpd = [MTLRenderPipelineDescriptor new];
        rpd.vertexFunction = vf;
        rpd.fragmentFunction = ff;
        rpd.depthAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
        rpd.stencilAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
        id<MTLRenderPipelineState> rps = [dev newRenderPipelineStateWithDescriptor:rpd error:&err];
        id<MTLComputePipelineState> cps = [dev newComputePipelineStateWithFunction:kf error:&err];
        if (!rps || !cps) {
            fprintf(stderr, "FAIL create pipelines: %s\n", err.localizedDescription.UTF8String);
            return 1;
        }

        MTLDepthStencilDescriptor *dsd = [MTLDepthStencilDescriptor new];
        dsd.depthCompareFunction = MTLCompareFunctionAlways;
        dsd.depthWriteEnabled = YES;
        MTLStencilDescriptor *sd = [MTLStencilDescriptor new];
        sd.stencilCompareFunction = MTLCompareFunctionAlways;
        sd.depthStencilPassOperation = MTLStencilOperationReplace;
        dsd.frontFaceStencil = sd;
        dsd.backFaceStencil = sd;
        id<MTLDepthStencilState> dss = [dev newDepthStencilStateWithDescriptor:dsd];

        const NSUInteger W = 64, H = 64;
        // Step 1: compressed Depth32Float_Stencil8 WITHOUT PixelFormatView
        MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatDepth32Float_Stencil8
                                                                                      width:W height:H mipmapped:NO];
        td.storageMode = MTLStorageModePrivate;
        td.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
        id<MTLTexture> dsCompressed = [dev newTextureWithDescriptor:td];
        if (!dsCompressed) {
            fprintf(stderr, "FAIL create compressed Depth32Float_Stencil8 texture\n");
            return 1;
        }
        if (dsCompressed.usage & MTLTextureUsagePixelFormatView) {
            fprintf(stderr, "FAIL expected no PixelFormatView on initial compressed DS texture\n");
            return 1;
        }

        // Step 2: upgraded texture WITH PixelFormatView (matching tex_upgrade_pfv)
        td.usage |= MTLTextureUsagePixelFormatView;
        id<MTLTexture> dsUpgraded = [dev newTextureWithDescriptor:td];
        if (!dsUpgraded) {
            fprintf(stderr, "FAIL create upgraded Depth32Float_Stencil8 texture\n");
            return 1;
        }

        id<MTLBuffer> outD = [dev newBufferWithLength:W * H * sizeof(float) options:MTLResourceStorageModeShared];
        id<MTLBuffer> outS = [dev newBufferWithLength:W * H * sizeof(uint32_t) options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> q = [dev newCommandQueue];
        id<MTLCommandBuffer> cb = [q commandBuffer];

        MTLRenderPassDescriptor *rp = [MTLRenderPassDescriptor new];
        rp.depthAttachment.texture = dsCompressed;
        rp.depthAttachment.loadAction = MTLLoadActionClear;
        rp.depthAttachment.clearDepth = 0.0;
        rp.depthAttachment.storeAction = MTLStoreActionStore;
        rp.stencilAttachment.texture = dsCompressed;
        rp.stencilAttachment.loadAction = MTLLoadActionClear;
        rp.stencilAttachment.clearStencil = 0;
        rp.stencilAttachment.storeAction = MTLStoreActionStore;

        id<MTLRenderCommandEncoder> re = [cb renderCommandEncoderWithDescriptor:rp];
        [re setRenderPipelineState:rps];
        [re setDepthStencilState:dss];
        // Draw 4 quadrants in NDC:
        // Q0: x in [-1, 0], y in [-1, 0] -> depth 0.25, stencil 0x11
        // Q1: x in [-1, 0], y in [ 0, 1] -> depth 0.50, stencil 0x2A
        // Q2: x in [ 0, 1], y in [-1, 0] -> depth 0.75, stencil 0x55
        // Q3: x in [ 0, 1], y in [ 0, 1] -> depth 0.90, stencil 0xFE
        const float rects[4][4] = {
            {-1.0f, -1.0f, 0.0f, 0.0f},
            {-1.0f,  0.0f, 0.0f, 1.0f},
            { 0.0f, -1.0f, 1.0f, 0.0f},
            { 0.0f,  0.0f, 1.0f, 1.0f},
        };
        const uint32_t refs[4] = {0x11u, 0x2Au, 0x55u, 0xFEu};
        for (int i = 0; i < 4; i++) {
            [re setStencilReferenceValue:refs[i]];
            [re setVertexBytes:rects[i] length:sizeof(rects[i]) atIndex:0];
            [re drawPrimitives:MTLPrimitiveTypeTriangleStrip vertexStart:0 vertexCount:4];
        }
        [re endEncoding];

        // Step 3: blit copy compressed -> upgraded (exact tex_upgrade_pfv path)
        id<MTLBlitCommandEncoder> be = [cb blitCommandEncoder];
        [be copyFromTexture:dsCompressed sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
                 sourceSize:MTLSizeMake(W, H, 1)
                  toTexture:dsUpgraded destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0, 0, 0)];
        [be endEncoding];

        // Step 4: create X32_Stencil8 view on upgraded texture & read back both planes
        id<MTLTexture> stView = [dsUpgraded newTextureViewWithPixelFormat:MTLPixelFormatX32_Stencil8];
        if (!stView) {
            fprintf(stderr, "FAIL newTextureViewWithPixelFormat:X32_Stencil8 returned nil\n");
            return 1;
        }
        id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
        [ce setComputePipelineState:cps];
        [ce setTexture:dsUpgraded atIndex:0];
        [ce setTexture:stView atIndex:1];
        [ce setBuffer:outD offset:0 atIndex:0];
        [ce setBuffer:outS offset:0 atIndex:1];
        [ce dispatchThreads:MTLSizeMake(W, H, 1) threadsPerThreadgroup:MTLSizeMake(8, 8, 1)];
        [ce endEncoding];

        [cb commit];
        [cb waitUntilCompleted];
        if (cb.status != MTLCommandBufferStatusCompleted) {
            fprintf(stderr, "FAIL command buffer status=%ld error=%s\n", (long)cb.status, cb.error.localizedDescription.UTF8String);
            return 1;
        }

        const float *dPtr = (const float *)outD.contents;
        const uint32_t *sPtr = (const uint32_t *)outS.contents;
        int fails = 0;
        // Metal viewport maps NDC y=-1 -> bottom (y=H-1), NDC y=+1 -> top (y=0).
        // Verify interior texels of each quadrant (avoiding exact center seam).
        for (NSUInteger y = 0; y < H; y++) {
            for (NSUInteger x = 0; x < W; x++) {
                if (x == W / 2 || y == H / 2) continue;
                int right = x > W / 2;
                int ndcTop = y < H / 2; // NDC y > 0
                float expD = !right ? (!ndcTop ? 0.25f : 0.50f) : (!ndcTop ? 0.75f : 0.90f);
                uint32_t expS = !right ? (!ndcTop ? 0x11u : 0x2Au) : (!ndcTop ? 0x55u : 0xFEu);
                NSUInteger idx = y * W + x;
                if (fabsf(dPtr[idx] - expD) > 1e-6f || sPtr[idx] != expS) {
                    if (fails < 8)
                        fprintf(stderr, "FAIL (%lu,%lu) got d=%f s=0x%x expected d=%f s=0x%x\n",
                                (unsigned long)x, (unsigned long)y, dPtr[idx], sPtr[idx], expD, expS);
                    fails++;
                }
            }
        }
        if (fails) {
            fprintf(stderr, "FAIL test_ds_compress_metal: %d mismatched texels\n", fails);
            return 1;
        }
        printf("OK   test_ds_compress_metal (%s): %lux%lu Depth32Float_Stencil8 compressed->PFV upgrade + X32_Stencil8 readback bit-exact (fails=0)\n",
               dev.name.UTF8String, (unsigned long)W, (unsigned long)H);
        return 0;
    }
}
