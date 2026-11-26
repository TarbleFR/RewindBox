#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <mach/mach.h>
#include <math.h>
#include <stdio.h>
#include <time.h>

enum { Width = 1280, Height = 720, Slots = 3, Frames = 180, Pairs = 12 };
typedef struct {
    double start, afterWait, committed, callback, gpuStart, gpuEnd, encodeCpu;
    int completed;
} Sample;

static double clockSeconds(clockid_t clock) {
    struct timespec t;
    if (clock_gettime(clock, &t)) abort();
    return t.tv_sec + t.tv_nsec * 1e-9;
}

static uint64_t footprint(void) {
    task_vm_info_data_t info;
    mach_msg_type_number_t size = TASK_VM_INFO_COUNT;
    kern_return_t result = task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &size);
    return result == KERN_SUCCESS ? info.phys_footprint : 0;
}

static BOOL verifySurfaces(id<MTLCommandQueue> queue, NSArray<id<MTLTexture>> *surfaces, id<MTLBuffer> readback) {
    const NSUInteger bytes = Width * Height * 4;
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLBlitCommandEncoder> blit = [cb blitCommandEncoder];
    if (!cb || !blit) return NO;
    for (NSUInteger i = 0; i < surfaces.count; ++i) {
        [blit copyFromTexture:surfaces[i] sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
            sourceSize:MTLSizeMake(Width,Height,1) toBuffer:readback destinationOffset:bytes*i
            destinationBytesPerRow:Width*4 destinationBytesPerImage:bytes];
    }
    [blit endEncoding];
    [cb commit];
    [cb waitUntilCompleted];
    if (cb.status != MTLCommandBufferStatusCompleted) return NO;
    const uint8_t expected[] = {64,128,191,255};
    const uint8_t *actual = readback.contents;
    for (NSUInteger i = 0; i < surfaces.count * bytes; i += 4)
        if (memcmp(actual + i, expected, 4) != 0) return NO;
    return YES;
}

static BOOL batch(id<MTLDevice> dev, id<MTLCommandQueue> queue, id<MTLRenderPipelineState> pipeline,
                  NSArray<id<MTLTexture>> *surfaces, id<MTLBuffer> readback, int limit, int pair, FILE *out) {
    id<MTLCommandBuffer> active[Slots] = {};
    dispatch_group_t callbacks = dispatch_group_create();
    Sample samples[Frames] = {};
    BOOL success = YES;
    uint64_t footprintBefore = footprint();
    for (int i = 0; i < Frames; ++i) @autoreleasepool {
        Sample *s = &samples[i];
        // The same three surfaces are allocated and used in both arms.
        s->start = clockSeconds(CLOCK_MONOTONIC);
        int index = i % limit;
        [active[index] waitUntilCompleted];
        s->afterWait = clockSeconds(CLOCK_MONOTONIC);
        double cpuStart = clockSeconds(CLOCK_THREAD_CPUTIME_ID);
        id<MTLCommandBuffer> cb = [queue commandBuffer];
        MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
        MTLRenderPassColorAttachmentDescriptor *color = pass.colorAttachments[0];
        color.texture = surfaces[i % Slots];
        color.loadAction = MTLLoadActionClear;
        color.clearColor = MTLClearColorMake(0,0,0,0);
        color.storeAction = MTLStoreActionStore;
        id<MTLRenderCommandEncoder> encoder = [cb renderCommandEncoderWithDescriptor:pass];
        if (!cb || !encoder) { success = NO; break; }
        [encoder setRenderPipelineState:pipeline];
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
        [encoder endEncoding];
        dispatch_group_enter(callbacks);
        [cb addCompletedHandler:^(id<MTLCommandBuffer> finished) {
            s->callback = clockSeconds(CLOCK_MONOTONIC);
            s->gpuStart = finished.GPUStartTime;
            s->gpuEnd = finished.GPUEndTime;
            s->completed = finished.status == MTLCommandBufferStatusCompleted;
            dispatch_group_leave(callbacks);
        }];
        [cb commit];
        s->committed = clockSeconds(CLOCK_MONOTONIC);
        s->encodeCpu = clockSeconds(CLOCK_THREAD_CPUTIME_ID) - cpuStart;
        active[index] = cb;
    }
    // Never return while a handler can still write through its sample pointer.
    dispatch_group_wait(callbacks, DISPATCH_TIME_FOREVER);
    uint64_t footprintAfter = footprint();
    uint64_t deviceAllocated = dev.currentAllocatedSize;
    if (!success || !verifySurfaces(queue,surfaces,readback)) return NO;
    for (int i = 0; i < Frames; ++i) {
        Sample *s = &samples[i];
        if (!s->completed || !isfinite(s->start) || !isfinite(s->afterWait) || !isfinite(s->committed) ||
            !isfinite(s->callback) || !isfinite(s->gpuStart) || !isfinite(s->gpuEnd) || !isfinite(s->encodeCpu) ||
            s->afterWait < s->start || s->committed < s->afterWait || s->callback < s->afterWait ||
            s->gpuStart <= 0 || s->gpuEnd <= s->gpuStart || s->encodeCpu < 0) return NO;
        if (pair) fprintf(out,"%d,%d,%d,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%llu,%llu,%llu\n",
            pair,limit,i,s->start,s->afterWait,s->committed,s->callback,s->gpuStart,s->gpuEnd,s->encodeCpu,
            (unsigned long long)footprintBefore,(unsigned long long)footprintAfter,
            (unsigned long long)deviceAllocated);
    }
    return YES;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 4) return 2;
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev) return 77;
        NSError *error = nil;
        NSString *fragment = [NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&error];
        if (!fragment) { NSLog(@"%@",error); return 1; }
        NSString *vertex = @"#include <metal_stdlib>\nusing namespace metal;\n"
            "struct V { float4 pos [[position]]; float4 value [[user(locn0)]]; };\n"
            "vertex V seed(uint i [[vertex_id]]) { float2 p = float2((i<<1)&2, i&2); "
            "return {float4(p*2.0f-1.0f,0,1),float4(.25f,.5f,.75f,1.0f)}; }";
        id<MTLLibrary> vs = [dev newLibraryWithSource:vertex options:nil error:&error];
        if (!vs) { NSLog(@"%@",error); return 1; }
        id<MTLLibrary> fs = [dev newLibraryWithSource:fragment options:nil error:&error];
        if (!fs) { NSLog(@"%@",error); return 1; }
        MTLRenderPipelineDescriptor *desc = [MTLRenderPipelineDescriptor new];
        desc.vertexFunction = [vs newFunctionWithName:@"seed"];
        desc.fragmentFunction = [fs newFunctionWithName:@(argv[2])];
        desc.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
        id<MTLRenderPipelineState> pipeline = [dev newRenderPipelineStateWithDescriptor:desc error:&error];
        if (!pipeline) { NSLog(@"%@",error); return 1; }
        id<MTLCommandQueue> queue = [dev newCommandQueue];
        MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
            width:Width height:Height mipmapped:NO];
        td.usage = MTLTextureUsageRenderTarget;
        td.storageMode = MTLStorageModePrivate;
        NSMutableArray<id<MTLTexture>> *surfaces = [NSMutableArray arrayWithCapacity:Slots];
        for (int i = 0; i < Slots; i++) {
            id<MTLTexture> t = [dev newTextureWithDescriptor:td];
            if (!t) return 1;
            [surfaces addObject:t];
        }
        id<MTLBuffer> readback = [dev newBufferWithLength:Slots*Width*Height*4 options:MTLResourceStorageModeShared];
        if (!queue || !readback) return 1;
        FILE *output = fopen(argv[3],"wx");
        if (!output) return 1;
        fprintf(output,"pair,limit,frame,start,after_wait,committed,callback,gpu_start,gpu_end,encode_cpu_s,footprint_before,footprint_after,device_allocated\n");
        NSLog(@"Offscreen homebrew, %@, %dx%d, %d frames/batch, %d identical textures",dev.name,Width,Height,Frames,Slots);
        BOOL ok = YES;
        for (int pair = 0; pair <= Pairs && ok; pair++) {
            for (int j = 0; j < 2 && ok; j++) @autoreleasepool {
                int limit = ((pair+j)&1) ? 3 : 1;
                ok = batch(dev,queue,pipeline,surfaces,readback,limit,pair,output);
            }
        }
        if (fclose(output)) ok = NO;
        return ok ? 0 : 1;
    }
}
