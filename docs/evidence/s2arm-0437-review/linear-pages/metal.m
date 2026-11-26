#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <assert.h>
#include <stdint.h>
#include "nvn_tex.h"
typedef struct { nvn_texdesc d; nvn_texlayout L; } tex_t;
#include IMPL

typedef struct {
    __unsafe_unretained id<MTLBlitCommandEncoder> blit;
    __unsafe_unretained id<MTLBuffer> staging;
    __unsafe_unretained id<MTLTexture> texture;
    size_t stagingPitch;
    unsigned bw,bh,bpb;
    size_t payload, rects;
} Transfer;

static void upload(void *user, unsigned level, unsigned layer, uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    Transfer *t = user;
    size_t offset = y / t->bh * t->stagingPitch + x / t->bw * t->bpb;
    [t->blit copyFromBuffer:t->staging sourceOffset:offset sourceBytesPerRow:t->stagingPitch
        sourceBytesPerImage:0 sourceSize:MTLSizeMake(w,h,1) toTexture:t->texture destinationSlice:layer
        destinationLevel:level destinationOrigin:MTLOriginMake(x,y,0)];
    t->payload += ((size_t)w+t->bw-1)/t->bw * (((size_t)h+t->bh-1)/t->bh) * t->bpb;
    t->rects++;
}

static int run(id<MTLDevice> dev, id<MTLCommandQueue> queue, int format, MTLPixelFormat metal,
               unsigned width, unsigned height, unsigned flags) {
    int bw,bh;
    int bpb=nvn_fmt_bpb(format,&bw,&bh);
    assert(bpb && bw && bh);
    const size_t cols=(width+bw-1)/bw, rows=(height+bh-1)/bh;
    const size_t rowBytes=cols*bpb, stagingPitch=(rowBytes+255)&~(size_t)255;
    tex_t t={.d={.target=1,.width=width,.height=height,.levels=1,.flags=flags,.format=format,
                .stride=(uint32_t)(rowBytes+32)}};
    nvn_tex_layout(&t.d,&t.L);
    assert(t.L.size==t.d.stride*rows);
    MTLTextureDescriptor *desc=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:metal width:width height:height mipmapped:NO];
    desc.storageMode=MTLStorageModePrivate;
    id<MTLTexture> dst=[dev newTextureWithDescriptor:desc];
    assert(dst);
    id<MTLBuffer> original=[dev newBufferWithLength:stagingPitch*rows options:MTLResourceStorageModeShared];
    id<MTLBuffer> stage=[dev newBufferWithLength:stagingPitch*rows options:MTLResourceStorageModeShared];
    id<MTLBuffer> back=[dev newBufferWithLength:stagingPitch*rows options:MTLResourceStorageModeShared];
    assert(original && stage && back);
    memset(original.contents,0xa1,stagingPitch*rows);
    memset(stage.contents,0x32,stagingPitch*rows);
    const uint64_t ranges[][2]={{0,t.L.size},{193,193+16384},{rowBytes,rowBytes+16},
        {t.d.stride+bpb-1,2*t.d.stride+1},{t.L.size-34,t.L.size-32},{17,t.L.size/2}};
    unsigned wrong=0;
    size_t copied=0, copies=0;
    for(unsigned sample=0;sample<sizeof(ranges)/sizeof(ranges[0]);sample++) @autoreleasepool {
        uint64_t lo=ranges[sample][0],hi=ranges[sample][1];
        id<MTLCommandBuffer> cb=[queue commandBuffer];
        id<MTLBlitCommandEncoder> enc=[cb blitCommandEncoder];
        assert(cb && enc);
        [enc copyFromBuffer:original sourceOffset:0 sourceBytesPerRow:stagingPitch sourceBytesPerImage:0
            sourceSize:MTLSizeMake(width,height,1) toTexture:dst destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0,0,0)];
        Transfer transfer={.blit=enc,.staging=stage,.texture=dst,.stagingPitch=stagingPitch,.bw=bw,.bh=bh,.bpb=bpb};
        tex_bytes_rects(&t,lo,hi,upload,&transfer);
        [enc copyFromTexture:dst sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
            sourceSize:MTLSizeMake(width,height,1) toBuffer:back destinationOffset:0 destinationBytesPerRow:stagingPitch destinationBytesPerImage:0];
        [enc endEncoding];[cb commit];[cb waitUntilCompleted];
        if(cb.status!=MTLCommandBufferStatusCompleted){ NSLog(@"Metal error %@",cb.error);abort(); }
        const uint8_t *actual=back.contents;
        size_t mismatch=0;
        for(size_t y=0;y<rows;++y)for(size_t x=0;x<rowBytes;++x){
            size_t block=y*t.d.stride+(x/bpb)*bpb;
            uint8_t expected=block<hi && block+bpb>lo ? 0x32:0xa1;
            mismatch+=actual[y*stagingPitch+x]!=expected;
        }
        wrong+=mismatch!=0;
        copied+=transfer.payload; copies+=transfer.rects;
    }
    printf("format=%#x flags=%#x size=%ux%u bad_surfaces=%u/6 bytes_encoded=%zu blits=%zu\n",
           format,flags,width,height,wrong,copied,copies);
#ifdef EXPECT_FIXED
    assert(!wrong);
#else
    assert(wrong);
#endif
    return 1;
}

int main(void) {
    @autoreleasepool {
        id<MTLDevice> dev=MTLCreateSystemDefaultDevice(); assert(dev);
        id<MTLCommandQueue> queue=[dev newCommandQueue]; assert(queue);
        NSLog(@"Native Metal geometric readback on %@",dev.name);
        for(unsigned i=0;i<5;++i) {
            unsigned flags=(i&1)?0x10:0x40;
            run(dev,queue,1,MTLPixelFormatR8Unorm,513,129,flags);
            run(dev,queue,0x25,MTLPixelFormatRGBA8Unorm,389,193,flags);
            if(dev.supportsBCTextureCompression)
                run(dev,queue,0x42,MTLPixelFormatBC1_RGBA,259,259,flags);
            if([dev supportsFamily:MTLGPUFamilyApple2])
                run(dev,queue,0x8b,MTLPixelFormatASTC_6x6_sRGB,387,197,flags);
        }
    }
}
