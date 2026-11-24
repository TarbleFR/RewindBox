// macOS host fixture. Only an absent Metal device permits a skip (77).
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "nvn_deswizzle.h"

enum { Side = 128, Pitch = Side * 4, Bytes = Pitch * Side };

static uint8_t pixel(unsigned x, unsigned y, unsigned channel) {
    const unsigned values[] = { x, y, x * 17u + y * 73u, 255u - ((x ^ y) & 127u) };
    return (uint8_t)values[channel];
}

// Walk the 64 KiB tile in physical order, reversing the GOB's interleaved
// address bits. The production linear-to-block address routine is not used.
static void make_tile(uint8_t *tile, int nvn2) {
    for (unsigned at = 0; at < Bytes; at++) {
        unsigned gob_column = at >> 13;
        unsigned gob_row = (at >> 9) & 15;
        unsigned byte_x = gob_column * 64 + ((at >> 8) & 1) * 32
                        + ((at >> (nvn2 ? 6 : 5)) & 1) * 16 + (at & 15);
        unsigned y = gob_row * 8 + ((at >> 7) & 1) * 4
                   + ((at >> (nvn2 ? 5 : 6)) & 1) * 2 + ((at >> 4) & 1);
        tile[at] = pixel(byte_x / 4, y, byte_x & 3);
    }
}

static int check_arm(id<MTLDevice> device, id<MTLCommandQueue> queue,
                     const uint8_t *tile, int layout, int grouped) {
    id<MTLBuffer> upload = [device newBufferWithLength:Bytes options:MTLResourceStorageModeShared];
    id<MTLBuffer> readback = [device newBufferWithLength:Bytes options:MTLResourceStorageModeShared];
    MTLTextureDescriptor *descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
              width:Side height:Side mipmapped:NO];
    descriptor.storageMode = MTLStorageModePrivate;
    id<MTLTexture> texture = [device newTextureWithDescriptor:descriptor];
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLBlitCommandEncoder> blit = [cb blitCommandEncoder];
    if (!upload.contents || !readback.contents || !texture || !blit) {
        fprintf(stderr, "Metal resource or blit encoder unavailable\n");
        return 1;
    }
    nvn_texdesc d = { .target = 1, .format = 0x25, .flags = 0x20, .width = Side, .height = Side,
                      .depth = 1, .levels = 1, .pkg_layout = 5 };
    uint32_t width = 0, rows = 0;
    int rc = nvn_deswizzle_tile_mode(&d, 0, 0, 0, tile, upload.contents, Pitch, &width, &rows, grouped);
    if (rc || width != Pitch || rows != Side) {
        fprintf(stderr, "Decode failed with %d, width %u bytes, rows %u\n", rc, width, rows);
        return 1;
    }
    memset(readback.contents, 0xcd, Bytes);
    MTLOrigin origin = MTLOriginMake(0, 0, 0);
    MTLSize size = MTLSizeMake(Side, Side, 1);
    [blit copyFromBuffer:upload sourceOffset:0 sourceBytesPerRow:Pitch sourceBytesPerImage:Bytes
              sourceSize:size toTexture:texture destinationSlice:0 destinationLevel:0 destinationOrigin:origin];
    [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:origin sourceSize:size toBuffer:readback
        destinationOffset:0 destinationBytesPerRow:Pitch destinationBytesPerImage:Bytes];
    [blit endEncoding];
    [cb commit];
    [cb waitUntilCompleted];
    if (cb.status != MTLCommandBufferStatusCompleted || cb.error) {
        fprintf(stderr, "GPU blit failed, status %ld, error %s\n", (long)cb.status, cb.error.description.UTF8String ?: "(none)");
        return 1;
    }
    const uint8_t *bytes = readback.contents;
    for (unsigned y = 0; y < Side; y++) for (unsigned x = 0; x < Side; x++) {
        for (unsigned c = 0; c < 4; c++) {
            unsigned got = bytes[y * Pitch + x * 4 + c], want = pixel(x, y, c);
            if (got != want) {
                fprintf(stderr, "layout=%d grouped=%d pixel=(%u,%u) channel=%u got=%u expected=%u\n",
                        layout, grouped, x, y, c, got, want);
                return 1;
            }
        }
    }
    printf("layout=%d grouped=%d private RGBA8 readback: %d/%d pixels exact\n",
           layout, grouped, Side * Side, Side * Side);
    return 0;
}

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { fprintf(stderr, "No Metal device; fixture skipped\n"); return 77; }
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!queue) { fprintf(stderr, "Cannot create Metal queue\n"); return 1; }
        uint8_t tile[Bytes];
        for (int layout = 0; layout < 2; layout++) {
            make_tile(tile, layout);
            nvn_gob_switch2 = layout;
            for (int grouped = 0; grouped < 2; grouped++) {
                if (check_arm(device, queue, tile, layout, grouped)) return 1;
            }
        }
        return 0;
    }
}
