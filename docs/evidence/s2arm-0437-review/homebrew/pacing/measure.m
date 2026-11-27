#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <mach/mach.h>
#include <math.h>
#include <stdio.h>
#include <time.h>

enum { Width = 1280, Height = 720, Slots = 3, Frames = 180, Pairs = 12 };
typedef struct {
    double start, afterWait, committed, callback, gpuStart, gpuEnd, encodeCpu;
    double beforeCommit, encodeThreadCpu;
    int completed, depth;
} Sample;

static double clockSeconds(clockid_t clock) {
    struct timespec t;
    if (clock_gettime(clock, &t)) abort();
    return t.tv_sec + t.tv_nsec * 1e-9;
}

// Metal command-buffer times use the host Mach absolute-time clock (awake uptime).
static double wallTime(BOOL parallelDepths) {
    return parallelDepths ? clock_gettime_nsec_np(CLOCK_UPTIME_RAW) * 1e-9 : clockSeconds(CLOCK_MONOTONIC);
}

static uint64_t footprint(void) {
    task_vm_info_data_t info;
    mach_msg_type_number_t size = TASK_VM_INFO_COUNT;
    kern_return_t result = task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &size);
    return result == KERN_SUCCESS ? info.phys_footprint : 0;
}

enum { MarkerStride = 256, MarkerBytes = 2 * Frames * MarkerStride };
_Static_assert(Frames > Slots && Frames < 255, "one nonzero byte identifies a frame");

static void frameRGBA(int frame, uint8_t rgba[4]) {
    rgba[0] = (uint8_t)(frame + 1);
    rgba[1] = (uint8_t)(255 - rgba[0]);
    rgba[2] = 90; rgba[3] = 255;
}

// Even entries are this draw's pixel. Odd entries witness the immediately
// preceding frame in its physical slot, so a swap across slots is observable.
static BOOL matchMarkers(const uint8_t *bytes, BOOL diagnose) {
    for (int i = 0; i < Frames; ++i) {
        for (int prior = 0; prior <= (i != 0); ++prior) {
            uint8_t expected[4]; frameRGBA(i - prior, expected);
            if (memcmp(&bytes[(2 * i + prior) * MarkerStride], expected, 4)) {
                if (diagnose) fprintf(stderr, "Frame %d, %s marker differs\n", i, prior ? "previous" : "current");
                return NO;
            }
        }
    }
    return YES;
}

static BOOL checkMarkers(id<MTLBuffer> markers) {
    uint8_t *bytes = markers.contents;
    if (!matchMarkers(bytes, YES)) return NO;
    // All observations passed. Swap two captured markers and require rejection.
    uint8_t *a = &bytes[0], *b = &bytes[2 * MarkerStride], temp[4];
    memcpy(temp, a, 4); memcpy(a, b, 4); memcpy(b, temp, 4);
    if (matchMarkers(bytes, NO)) { fprintf(stderr, "Marker swap escaped detection\n"); return NO; }
    return YES;
}

static BOOL verifySurfaces(id<MTLCommandQueue> queue, NSArray<id<MTLTexture>> *surfaces, id<MTLBuffer> readback, BOOL identities) {
    const NSUInteger bytes = Width * Height * 4;
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLBlitCommandEncoder> blit = [cb blitCommandEncoder];
    if (!cb || !blit) { fprintf(stderr,"Readback encoder unavailable\n"); return NO; }
    for (NSUInteger i = 0; i < surfaces.count; ++i) {
        [blit copyFromTexture:surfaces[i] sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
            sourceSize:MTLSizeMake(Width,Height,1) toBuffer:readback destinationOffset:bytes*i
            destinationBytesPerRow:Width*4 destinationBytesPerImage:bytes];
    }
    [blit endEncoding];
    [cb commit];
    [cb waitUntilCompleted];
    if (cb.status != MTLCommandBufferStatusCompleted) { NSLog(@"Readback GPU error %@",cb.error); return NO; }
    const uint8_t *actual = readback.contents;
    for (NSUInteger slot = 0; slot < surfaces.count; ++slot) {
        uint8_t expected[] = {64,128,191,255};
        if (identities) frameRGBA(Frames - 1 - (Frames - 1 - (int)slot) % Slots, expected);
        for (NSUInteger offset = 0; offset < bytes; offset += 4) {
            const uint8_t *pixel = actual + slot * bytes + offset;
            if (memcmp(pixel, expected, 4)) {
                fprintf(stderr,"Surface %zu pixel %zu expected RGBA %u %u %u %u, got %u %u %u %u\n",
                    (size_t)slot,(size_t)(offset / 4),expected[0],expected[1],expected[2],expected[3],
                    pixel[0],pixel[1],pixel[2],pixel[3]);
                return NO;
            }
        }
    }
    return YES;
}

static BOOL batch(id<MTLDevice> dev, id<MTLCommandQueue> queue, id<MTLRenderPipelineState> pipeline,
                  NSArray<id<MTLTexture>> *surfaces, id<MTLBuffer> readback, int limit, int pair, FILE *out, BOOL hostReport, BOOL parallelDepths, id<MTLBuffer> markers) {
    id<MTLCommandBuffer> active[Slots] = {};
    dispatch_group_t callbacks = dispatch_group_create();
    Sample samples[Frames] = {};
    BOOL success = YES;
    int retired = 0, depth = limit ? limit : 2;
    double windowWait = 0;
    uint64_t footprintBefore = footprint();
    for (int i = 0; i < Frames; ++i) @autoreleasepool {
        Sample *s = &samples[i];
        s->start = wallTime(parallelDepths);
        int index;
        if (parallelDepths) {
            // Experimental policy uses only earlier host observations. Reassess every 8 frames.
            if (!limit && i && i % 8 == 0) {
                double oldestAge = s->start - samples[retired].start;
                if (depth > 1 && (oldestAge > 1.0/60 || windowWait < 0.00008)) --depth;
                else if (depth < Slots && oldestAge <= 1.0/60 && windowWait > 0.0008) ++depth;
                windowWait = 0;
            }
            s->depth = depth;
            // Retire in submission order, including when a shrink must drain multiple slots.
            while (retired <= i - depth) {
                [active[retired % Slots] waitUntilCompleted];
                ++retired;
            }
            index = i % Slots;
        } else {
            index = i % limit;
            [active[index] waitUntilCompleted];
        }
        s->afterWait = wallTime(parallelDepths);
        if (!limit) windowWait += s->afterWait - s->start;
        double cpuStart = clockSeconds(CLOCK_THREAD_CPUTIME_ID);
        id<MTLCommandBuffer> cb = [queue commandBuffer];
        MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
        MTLRenderPassColorAttachmentDescriptor *color = pass.colorAttachments[0];
        color.texture = surfaces[i % Slots];
        color.loadAction = MTLLoadActionClear;
        color.clearColor = MTLClearColorMake(0,0,0,0);
        color.storeAction = MTLStoreActionStore;
        id<MTLRenderCommandEncoder> encoder = [cb renderCommandEncoderWithDescriptor:pass];
        if (!cb || !encoder) { fprintf(stderr,"Missing frame encoder %d\n",i); success = NO; break; }
        [encoder setRenderPipelineState:pipeline];
        if (markers) {
            uint8_t rgba[4]; frameRGBA(i, rgba);
            float value[4]; for (int k = 0; k < 4; ++k) value[k] = rgba[k] / 255.0f;
            [encoder setVertexBytes:value length:sizeof value atIndex:0];
        }
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
        [encoder endEncoding];
        if (markers) {
            id<MTLBlitCommandEncoder> blit = [cb blitCommandEncoder];
            if (!blit) { fprintf(stderr, "Missing marker encoder %d\n", i); success = NO; break; }
            for (int prior = 0; prior <= (i != 0); ++prior)
                [blit copyFromTexture:surfaces[(i - prior) % Slots] sourceSlice:0 sourceLevel:0
                    sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(1,1,1) toBuffer:markers
                    destinationOffset:(2 * i + prior) * MarkerStride
                    destinationBytesPerRow:MarkerStride destinationBytesPerImage:MarkerStride];
            [blit endEncoding];
        }
        dispatch_group_enter(callbacks);
        [cb addCompletedHandler:^(id<MTLCommandBuffer> finished) {
            s->callback = wallTime(parallelDepths);
            s->gpuStart = finished.GPUStartTime;
            s->gpuEnd = finished.GPUEndTime;
            s->completed = finished.status == MTLCommandBufferStatusCompleted;
            if (!s->completed) NSLog(@"Frame GPU error %@",finished.error);
            dispatch_group_leave(callbacks);
        }];
        if (parallelDepths) {
            s->encodeThreadCpu = clockSeconds(CLOCK_THREAD_CPUTIME_ID) - cpuStart;
            s->beforeCommit = wallTime(YES);
        }
        [cb commit];
        s->committed = wallTime(parallelDepths);
        s->encodeCpu = clockSeconds(CLOCK_THREAD_CPUTIME_ID) - cpuStart;
        active[index] = cb;
    }
    // Never return while a handler can still write through its sample pointer.
    dispatch_group_wait(callbacks, DISPATCH_TIME_FOREVER);
    uint64_t footprintAfter = footprint();
    uint64_t deviceAllocated = dev.currentAllocatedSize;
    if (!success || !verifySurfaces(queue,surfaces,readback,markers != nil)) return NO;
    if (markers) {
        for (int i = 0; i < Frames; ++i) if (!samples[i].completed) return NO;
        return checkMarkers(markers);
    }
    for (int i = 0; i < Frames; ++i) {
        Sample *s = &samples[i];
        if (!s->completed || !isfinite(s->start) || !isfinite(s->afterWait) || !isfinite(s->committed) ||
            !isfinite(s->callback) || !isfinite(s->gpuStart) || !isfinite(s->gpuEnd) || !isfinite(s->encodeCpu) ||
            s->afterWait < s->start || s->committed < s->afterWait || s->callback < s->afterWait ||
            s->gpuStart < 0 || s->gpuEnd < s->gpuStart ||
            (!hostReport && (s->gpuStart == 0 || s->gpuEnd == s->gpuStart)) || s->encodeCpu < 0) {
            fprintf(stderr,"Invalid time pair=%d limit=%d frame=%d completed=%d host=%.9f/%.9f/%.9f/%.9f gpu=%.9f/%.9f cpu=%.9f\n",
                pair,limit,i,s->completed,s->start,s->afterWait,s->committed,s->callback,s->gpuStart,s->gpuEnd,s->encodeCpu);
            return NO;
        }
        if (pair) {
            fprintf(out,"%d,%d,%d,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%llu,%llu,%llu",
            pair,limit,i,s->start,s->afterWait,s->committed,s->callback,s->gpuStart,s->gpuEnd,s->encodeCpu,
            (unsigned long long)footprintBefore,(unsigned long long)footprintAfter,
            (unsigned long long)deviceAllocated);
            if (parallelDepths) fprintf(out,",%.9f,%d,%.9f",s->beforeCommit,s->depth,s->encodeThreadCpu);
            fputc('\n',out);
        }
    }
    return YES;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        BOOL hostReport = argc == 5 && strcmp(argv[4], "--host-report") == 0;
        BOOL parallelDepths = argc == 5 && strcmp(argv[4], "--parallel-depths") == 0;
        if (argc != 4 && !hostReport && !parallelDepths) return 2;
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
        fprintf(output,"pair,limit,frame,start,after_wait,committed,callback,gpu_start,gpu_end,encode_cpu_s,footprint_before,footprint_after,device_allocated");
        if (parallelDepths) fprintf(output,",before_commit,admission_depth,encode_thread_cpu_s");
        fputc('\n',output);
        NSLog(@"Offscreen homebrew, %@, %dx%d, %d frames/batch, %d identical textures",dev.name,Width,Height,Frames,Slots);
        BOOL ok = YES;
        if (parallelDepths) {
            // Four blocks balance position and every ordered carry-over pair. Block 0 warms all arms.
            const int orders[4][4] = {{1,2,0,3},{2,3,1,0},{3,0,2,1},{0,1,3,2}};
            for (int block = 0; block <= 4 && ok; ++block) {
                for (int j = 0; j < 4 && ok; ++j) @autoreleasepool {
                    int policy = orders[block ? block-1 : 3][j];
                    ok = batch(dev,queue,pipeline,surfaces,readback,policy,block,output,YES,YES,nil);
                }
            }
            if (ok) {
                // Compile after all timed blocks. The same homebrew fragment now
                // receives a distinct per-frame value from its vertex stage.
                NSString *marked = @"#include <metal_stdlib>\nusing namespace metal;\n"
                    "struct V { float4 pos [[position]]; float4 value [[user(locn0)]]; };\n"
                    "vertex V marked(uint i [[vertex_id]], constant float4 &v [[buffer(0)]]) { "
                    "float2 p = float2((i<<1)&2, i&2); return {float4(p*2.0f-1.0f,0,1),v}; }";
                id<MTLLibrary> library = [dev newLibraryWithSource:marked options:nil error:&error];
                desc.vertexFunction = [library newFunctionWithName:@"marked"];
                id<MTLRenderPipelineState> oracle = desc.vertexFunction ?
                    [dev newRenderPipelineStateWithDescriptor:desc error:&error] : nil;
                id<MTLBuffer> markers = [dev newBufferWithLength:MarkerBytes options:MTLResourceStorageModeShared];
                if (!oracle || !markers) { NSLog(@"Marker oracle initialization failed: %@", error); ok = NO; }
                for (int policy = 0; policy <= Slots && ok; ++policy) @autoreleasepool {
                    memset(markers.contents, 0, MarkerBytes);
                    ok = batch(dev,queue,oracle,surfaces,readback,policy,0,NULL,YES,YES,markers);
                    if (ok) fprintf(stderr, "Marker oracle passed: policy %d, %d frames, %d final slots, swap rejected\n",
                                    policy, Frames, Slots);
                }
            }
        } else {
            for (int pair = 0; pair <= Pairs && ok; pair++) {
                for (int j = 0; j < 2 && ok; j++) @autoreleasepool {
                    int limit = ((pair+j)&1) ? 3 : 1;
                    ok = batch(dev,queue,pipeline,surfaces,readback,limit,pair,output,hostReport,NO,nil);
                }
            }
        }
        if (fclose(output)) ok = NO;
        return ok ? 0 : 1;
    }
}
