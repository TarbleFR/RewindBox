// Stand-alone Metal probe for lot 7 (MTLBinaryArchive): what the API really does on the Metal device of the machine it
// runs on (the GitHub macOS runner's "Apple Paravirtual device"; not an iPhone). It answers, with times measured apart:
//   - what a binary archive removes (pipeline state creation) and what remains (MTLLibrary creation from MSL source);
//   - what collecting costs after a pipeline was created, against adding first and creating from the archive;
//   - that a pipeline really comes from the archive (MTLPipelineOptionFailOnBinaryArchiveMiss): covered pipelines must
//     succeed, a variant left out must miss, and the same variant must then be created by the normal compilation;
//   - that pipelines created from the archive draw and compute the same result as compiled ones;
//   - a damaged or cut archive, a failed save, several archives searched together, concurrent lookups and additions.
// Every shader is synthetic (generated below from an index and a salt); nothing comes from a game. The salt makes the
// sources of one run unknown to Metal's own caches, so "cold" is real whatever the machine held before.
//
// Build: clang++ -std=c++17 -fobjc-arc -O1 -framework Metal -framework Foundation -framework CoreGraphics
// Usage: metal_probe <mode> <work directory> <salt> [fragment shaders] [compute shaders] [weight]
//   modes: baseline | collect | collect-addfirst | reuse | damaged | threads
// Prints one JSON object on its last line.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <atomic>
#include <chrono>
#include <mach/mach.h>
#include <sstream>
#include <string>
#include <sys/sysctl.h>
#include <thread>
#include <unistd.h>
#include <vector>

static double nowMs() {
    using namespace std::chrono;
    return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}

static double footprintMiB() {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return -1;
    return (double)info.phys_footprint / (1024.0 * 1024.0);
}

static NSString* sysctlString(const char* name) {
    char buffer[256];
    size_t size = sizeof(buffer);
    if (sysctlbyname(name, buffer, &size, NULL, 0) != 0) return @"";
    return [NSString stringWithUTF8String: buffer];
}

struct Timing {
    double total = 0, max = 0;
    int count = 0;
    void add(double ms) { total += ms; if (ms > max) max = ms; count++; }
    NSDictionary* json() const { return @{@"count": @(count), @"totalMs": @(round(total * 100) / 100), @"maxMs": @(round(max * 100) / 100)}; }
};

// --- Synthetic shaders -------------------------------------------------------------------------------------------------

static std::string helpers(int index, uint64_t salt, int weight) {
    std::ostringstream s;
    s.precision(6);
    s << std::fixed;
    for (int h = 0; h < weight; h++) {
        s << "static float3 h" << h << "(float3 p, float t) {\n";
        s << "    float3 q = p * " << (1.0 + 0.013 * h + (double)(salt % 97) * 0.001 + index * 0.11) << " + float3(t);\n";
        for (int k = 0; k < 10; k++) {
            s << "    q = mix(sin(q.yzx * " << (1.3 + 0.07 * k + index * 0.011) << " + q.zxy), cos(q * " << (0.7 + 0.05 * k)
              << "), fract(q.x * " << (k + 1) << ".0 + " << (double)((salt + (uint64_t)h * 31 + (uint64_t)k * 7 + (uint64_t)index) % 1000) * 0.001 << "));\n";
        }
        s << "    return q;\n}\n";
    }
    return s.str();
}

static std::string vertexSource() {
    return "#include <metal_stdlib>\nusing namespace metal;\n"
           "struct VOut { float4 pos [[position]]; float2 uv; };\n"
           "vertex VOut vmain(uint vid [[vertex_id]]) {\n"
           "    VOut o; float2 p = float2((vid << 1) & 2, vid & 2);\n"
           "    o.pos = float4(p * 2.0 - 1.0, 0.0, 1.0); o.uv = p; return o;\n}\n";
}

static std::string fragmentSource(int index, uint64_t salt, int weight) {
    std::ostringstream s;
    s << "#include <metal_stdlib>\nusing namespace metal;\n";
    s << "struct VOut { float4 pos [[position]]; float2 uv; };\n";
    s << "struct Params { float4 a; float4 b; };\n";
    s << helpers(index, salt, weight);
    s << "fragment float4 fmain(VOut in [[stage_in]], constant Params& u [[buffer(0)]]) {\n";
    s << "    float3 c = float3(in.uv, u.a.x);\n";
    for (int h = 0; h < weight; h++) s << "    c += h" << h << "(c + u.b.xyz, u.a.y + " << h << ".0) * " << (1.0 / (h + 2)) << ";\n";
    s << "    return float4(fract(abs(c)), 1.0);\n}\n";
    return s.str();
}

static std::string computeSource(int index, uint64_t salt, int weight) {
    std::ostringstream s;
    s << "#include <metal_stdlib>\nusing namespace metal;\n";
    s << helpers(index + 1000, salt, weight);
    s << "kernel void kmain(device float* out [[buffer(0)]], uint3 id [[thread_position_in_grid]]) {\n";
    s << "    float3 c = float3(float(id.x) * 0.01, 0.25, 0.5);\n";
    for (int h = 0; h < weight; h++) s << "    c += h" << h << "(c, float(id.x & 7u) + " << h << ".0) * " << (1.0 / (h + 2)) << ";\n";
    s << "    out[id.x] = floor(fract(abs(c.x + c.y + c.z)) * 4096.0);\n}\n";
    return s.str();
}

// --- The set of pipelines ----------------------------------------------------------------------------------------------

struct Shaders {
    id<MTLFunction> vertex;
    NSMutableArray<id<MTLFunction>>* fragments = [NSMutableArray array];
    NSMutableArray<id<MTLFunction>>* computes = [NSMutableArray array];
    Timing libraries;
    NSMutableArray<NSString*>* errors = [NSMutableArray array];
};

static id<MTLFunction> compileFunction(id<MTLDevice> device, const std::string& source, NSString* name, Shaders& shaders) {
    NSError* error = nil;
    double start = nowMs();
    id<MTLLibrary> library = [device newLibraryWithSource: [NSString stringWithUTF8String: source.c_str()] options: [MTLCompileOptions new] error: &error];
    shaders.libraries.add(nowMs() - start);
    if (!library) {
        [shaders.errors addObject: [NSString stringWithFormat: @"library %@: %@", name, error.localizedDescription]];
        return nil;
    }
    return [library newFunctionWithName: name];
}

static void buildShaders(id<MTLDevice> device, uint64_t salt, int fragments, int computes, int weight, Shaders& shaders) {
    shaders.vertex = compileFunction(device, vertexSource(), @"vmain", shaders);
    for (int i = 0; i < fragments; i++) {
        id<MTLFunction> f = compileFunction(device, fragmentSource(i, salt, weight), @"fmain", shaders);
        if (f) [shaders.fragments addObject: f];
    }
    for (int i = 0; i < computes; i++) {
        id<MTLFunction> f = compileFunction(device, computeSource(i, salt, weight), @"kmain", shaders);
        if (f) [shaders.computes addObject: f];
    }
}

static MTLRenderPipelineDescriptor* renderDescriptor(const Shaders& shaders, int fragment, MTLPixelFormat format, BOOL blend) {
    MTLRenderPipelineDescriptor* d = [MTLRenderPipelineDescriptor new];
    d.vertexFunction = shaders.vertex;
    d.fragmentFunction = shaders.fragments[fragment];
    d.colorAttachments[0].pixelFormat = format;
    d.colorAttachments[0].blendingEnabled = blend;
    if (blend) {
        d.colorAttachments[0].sourceRGBBlendFactor = MTLBlendFactorSourceAlpha;
        d.colorAttachments[0].destinationRGBBlendFactor = MTLBlendFactorOneMinusSourceAlpha;
    }
    return d;
}

// Four states per fragment shader (two formats, blending on and off). The variant left out of every archive is
// fragment 0 with BGRA8Unorm.
static NSArray<MTLRenderPipelineDescriptor*>* renderDescriptors(const Shaders& shaders) {
    NSMutableArray* list = [NSMutableArray array];
    for (int f = 0; f < (int)shaders.fragments.count; f++) {
        for (NSNumber* format in @[@(MTLPixelFormatRGBA8Unorm), @(MTLPixelFormatRGBA16Float)]) {
            [list addObject: renderDescriptor(shaders, f, (MTLPixelFormat)format.unsignedIntegerValue, NO)];
            [list addObject: renderDescriptor(shaders, f, (MTLPixelFormat)format.unsignedIntegerValue, YES)];
        }
    }
    return list;
}

static NSArray<MTLComputePipelineDescriptor*>* computeDescriptors(const Shaders& shaders) {
    NSMutableArray* list = [NSMutableArray array];
    for (id<MTLFunction> f in shaders.computes) {
        MTLComputePipelineDescriptor* d = [MTLComputePipelineDescriptor new];
        d.computeFunction = f;
        [list addObject: d];
    }
    return list;
}

static uint64_t fnv(const void* data, size_t length) {
    uint64_t hash = 1469598103934665603ull;
    const uint8_t* bytes = (const uint8_t*)data;
    for (size_t i = 0; i < length; i++) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    return hash;
}

// One draw with a render pipeline into a 64x64 RGBA8 target, read back; one dispatch with a compute pipeline.
static NSDictionary* drawAndCompute(id<MTLDevice> device, id<MTLRenderPipelineState> render, id<MTLComputePipelineState> compute) {
    id<MTLCommandQueue> queue = [device newCommandQueue];
    MTLTextureDescriptor* td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat: MTLPixelFormatRGBA8Unorm width: 64 height: 64 mipmapped: NO];
    td.usage = MTLTextureUsageRenderTarget;
    td.storageMode = MTLStorageModePrivate;
    id<MTLTexture> target = [device newTextureWithDescriptor: td];
    id<MTLBuffer> pixels = [device newBufferWithLength: 64 * 64 * 4 options: MTLResourceStorageModeShared];
    id<MTLBuffer> params = [device newBufferWithLength: 32 options: MTLResourceStorageModeShared];
    float values[8] = {0.25f, 0.5f, 0.75f, 1.0f, 0.125f, 0.375f, 0.625f, 0.875f};
    memcpy(params.contents, values, sizeof(values));
    id<MTLBuffer> output = [device newBufferWithLength: 1024 * sizeof(float) options: MTLResourceStorageModeShared];
    memset(output.contents, 0, output.length);

    id<MTLCommandBuffer> commands = [queue commandBuffer];
    if (render) {
        MTLRenderPassDescriptor* pass = [MTLRenderPassDescriptor renderPassDescriptor];
        pass.colorAttachments[0].texture = target;
        pass.colorAttachments[0].loadAction = MTLLoadActionClear;
        pass.colorAttachments[0].storeAction = MTLStoreActionStore;
        id<MTLRenderCommandEncoder> encoder = [commands renderCommandEncoderWithDescriptor: pass];
        [encoder setRenderPipelineState: render];
        [encoder setFragmentBuffer: params offset: 0 atIndex: 0];
        [encoder drawPrimitives: MTLPrimitiveTypeTriangle vertexStart: 0 vertexCount: 3];
        [encoder endEncoding];
        id<MTLBlitCommandEncoder> blit = [commands blitCommandEncoder];
        [blit copyFromTexture: target sourceSlice: 0 sourceLevel: 0 sourceOrigin: MTLOriginMake(0, 0, 0) sourceSize: MTLSizeMake(64, 64, 1)
                     toBuffer: pixels destinationOffset: 0 destinationBytesPerRow: 64 * 4 destinationBytesPerImage: 64 * 64 * 4];
        [blit endEncoding];
    }
    if (compute) {
        id<MTLComputeCommandEncoder> encoder = [commands computeCommandEncoder];
        [encoder setComputePipelineState: compute];
        [encoder setBuffer: output offset: 0 atIndex: 0];
        [encoder dispatchThreads: MTLSizeMake(1024, 1, 1) threadsPerThreadgroup: MTLSizeMake(MIN((NSUInteger)64, compute.maxTotalThreadsPerThreadgroup), 1, 1)];
        [encoder endEncoding];
    }
    [commands commit];
    [commands waitUntilCompleted];
    const uint8_t* p = (const uint8_t*)pixels.contents;
    int nonZero = 0;
    for (int i = 0; i < 64 * 64 * 4; i += 4) if (p[i] | p[i + 1] | p[i + 2]) nonZero++;
    return @{@"status": @(commands.status == MTLCommandBufferStatusCompleted),
             @"drawHash": [NSString stringWithFormat: @"%016llx", fnv(pixels.contents, pixels.length)],
             @"drawNonBlackPixels": @(nonZero),
             @"computeHash": [NSString stringWithFormat: @"%016llx", fnv(output.contents, output.length)],
             @"computeFirst": @(((float*)output.contents)[1])};
}

// --- Metal's own cache directories ---------------------------------------------------------------------------------------

static NSArray<NSDictionary*>* metalCacheDirectories(BOOL removeOwn, NSString* processName, NSMutableArray* removed) {
    char buffer[1024];
    NSMutableArray* found = [NSMutableArray array];
    if (confstr(_CS_DARWIN_USER_CACHE_DIR, buffer, sizeof(buffer)) == 0) return found;
    NSString* root = [NSString stringWithUTF8String: buffer];
    NSFileManager* files = NSFileManager.defaultManager;
    for (NSString* first in [files contentsOfDirectoryAtPath: root error: nil] ?: @[]) {
        NSString* parent = [root stringByAppendingPathComponent: first];
        for (NSString* second in [files contentsOfDirectoryAtPath: parent error: nil] ?: @[]) {
            if (![second hasPrefix: @"com.apple.metal"]) continue;
            NSString* path = [parent stringByAppendingPathComponent: second];
            unsigned long long bytes = 0;
            for (NSString* item in [files subpathsOfDirectoryAtPath: path error: nil] ?: @[]) {
                bytes += [[files attributesOfItemAtPath: [path stringByAppendingPathComponent: item] error: nil] fileSize];
            }
            BOOL own = [first isEqualToString: processName];
            if (own && removeOwn && [files removeItemAtPath: path error: nil]) [removed addObject: first];
            [found addObject: @{@"owner": first, @"name": second, @"bytes": @(bytes), @"own": @(own)}];
        }
    }
    return found;
}

// --- Modes ---------------------------------------------------------------------------------------------------------------

int main(int argc, const char* argv[]) {
    @autoreleasepool {
        if (argc < 4) { fprintf(stderr, "usage: metal_probe <mode> <work directory> <salt> [fragments] [computes] [weight] [--clear-system-cache]\n"); return 2; }
        NSString* mode = [NSString stringWithUTF8String: argv[1]];
        NSString* work = [NSString stringWithUTF8String: argv[2]];
        uint64_t salt = strtoull(argv[3], NULL, 10);
        int fragments = argc > 4 ? atoi(argv[4]) : 12, computes = argc > 5 ? atoi(argv[5]) : 6, weight = argc > 6 ? atoi(argv[6]) : 24;
        BOOL clearSystemCache = NO;
        for (int i = 1; i < argc; i++) if (strcmp(argv[i], "--clear-system-cache") == 0) clearSystemCache = YES;
        NSString* processName = NSProcessInfo.processInfo.processName;
        NSMutableDictionary* report = [NSMutableDictionary dictionary];
        NSMutableArray* removed = [NSMutableArray array];
        report[@"mode"] = mode;
        report[@"process"] = processName;
        report[@"systemCacheBefore"] = metalCacheDirectories(clearSystemCache, processName, removed);
        report[@"systemCacheRemoved"] = removed;

        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { printf("{\"error\": \"no Metal device\"}\n"); return 3; }
        report[@"device"] = device.name;
        report[@"osVersion"] = NSProcessInfo.processInfo.operatingSystemVersionString;
        report[@"osBuild"] = sysctlString("kern.osversion");
        report[@"apple7"] = @([device supportsFamily: MTLGPUFamilyApple7]);
        report[@"set"] = @{@"fragmentShaders": @(fragments), @"computeShaders": @(computes), @"weight": @(weight), @"salt": @(salt)};
        [NSFileManager.defaultManager createDirectoryAtPath: work withIntermediateDirectories: YES attributes: nil error: nil];
        NSURL* archiveURL = [NSURL fileURLWithPath: [work stringByAppendingPathComponent: @"pipelines.metalarchive"]];
        double footprintStart = footprintMiB();

        Shaders shaders;
        buildShaders(device, salt, fragments, computes, weight, shaders);
        report[@"libraries"] = shaders.libraries.json();
        report[@"libraryErrors"] = shaders.errors;
        if (shaders.errors.count || !shaders.vertex) { NSData* d = [NSJSONSerialization dataWithJSONObject: report options: 0 error: nil]; printf("%s\n", (const char*)[[NSString alloc] initWithData: d encoding: NSUTF8StringEncoding].UTF8String); return 4; }
        NSArray<MTLRenderPipelineDescriptor*>* renders = renderDescriptors(shaders);
        NSArray<MTLComputePipelineDescriptor*>* kernels = computeDescriptors(shaders);
        MTLRenderPipelineDescriptor* absent = renderDescriptor(shaders, 0, MTLPixelFormatBGRA8Unorm, NO);
        NSMutableArray<NSString*>* errors = [NSMutableArray array];
        id<MTLRenderPipelineState> firstRender = nil;
        id<MTLComputePipelineState> firstCompute = nil;
        NSError* error = nil;

        if ([mode isEqualToString: @"baseline"] || [mode isEqualToString: @"collect"]) {
            // The normal compilation of every pipeline, then (collect) each descriptor added to a new archive.
            Timing create;
            for (MTLRenderPipelineDescriptor* d in renders) {
                double start = nowMs();
                id<MTLRenderPipelineState> state = [device newRenderPipelineStateWithDescriptor: d error: &error];
                create.add(nowMs() - start);
                if (!state) [errors addObject: error.localizedDescription ?: @"render pipeline"];
                if (!firstRender) firstRender = state;
            }
            Timing createCompute;
            for (MTLComputePipelineDescriptor* d in kernels) {
                double start = nowMs();
                id<MTLComputePipelineState> state = [device newComputePipelineStateWithDescriptor: d options: MTLPipelineOptionNone reflection: nil error: &error];
                createCompute.add(nowMs() - start);
                if (!state) [errors addObject: error.localizedDescription ?: @"compute pipeline"];
                if (!firstCompute) firstCompute = state;
            }
            report[@"createRender"] = create.json();
            report[@"createCompute"] = createCompute.json();
            if ([mode isEqualToString: @"collect"]) {
                id<MTLBinaryArchive> archive = [device newBinaryArchiveWithDescriptor: [MTLBinaryArchiveDescriptor new] error: &error];
                report[@"archiveCreated"] = @(archive != nil);
                if (!archive) [errors addObject: [NSString stringWithFormat: @"new archive: %@", error.localizedDescription]];
                Timing add, addCompute;
                for (MTLRenderPipelineDescriptor* d in renders) {
                    double start = nowMs();
                    if (![archive addRenderPipelineFunctionsWithDescriptor: d error: &error]) [errors addObject: [NSString stringWithFormat: @"add render: %@", error.localizedDescription]];
                    add.add(nowMs() - start);
                }
                for (MTLComputePipelineDescriptor* d in kernels) {
                    double start = nowMs();
                    if (![archive addComputePipelineFunctionsWithDescriptor: d error: &error]) [errors addObject: [NSString stringWithFormat: @"add compute: %@", error.localizedDescription]];
                    addCompute.add(nowMs() - start);
                }
                report[@"addAfterCreateRender"] = add.json();
                report[@"addAfterCreateCompute"] = addCompute.json();
                // A failed save (a directory that does not exist) must leave nothing and report an error.
                NSURL* nowhere = [NSURL fileURLWithPath: [work stringByAppendingPathComponent: @"missing-directory/pipelines.metalarchive"]];
                NSError* saveError = nil;
                BOOL savedNowhere = [archive serializeToURL: nowhere error: &saveError];
                report[@"saveToMissingDirectory"] = @{@"succeeded": @(savedNowhere), @"error": saveError.localizedDescription ?: @""};
                NSURL* temporary = [archiveURL URLByAppendingPathExtension: @"tmp"];
                double start = nowMs();
                BOOL saved = [archive serializeToURL: temporary error: &error];
                double saveMs = nowMs() - start;
                if (!saved) [errors addObject: [NSString stringWithFormat: @"serialize: %@", error.localizedDescription]];
                else if (rename(temporary.path.fileSystemRepresentation, archiveURL.path.fileSystemRepresentation) != 0) [errors addObject: @"rename"];
                report[@"save"] = @{@"ms": @(round(saveMs * 100) / 100),
                                    @"bytes": @([[NSFileManager.defaultManager attributesOfItemAtPath: archiveURL.path error: nil] fileSize])};
            }
        } else if ([mode isEqualToString: @"collect-addfirst"]) {
            // The other order: each descriptor is added to the archive first (Metal compiles it there), then the pipeline
            // is created from the archive only (strict).
            id<MTLBinaryArchive> archive = [device newBinaryArchiveWithDescriptor: [MTLBinaryArchiveDescriptor new] error: &error];
            Timing add, create;
            int strictFailures = 0;
            for (MTLRenderPipelineDescriptor* d in renders) {
                double start = nowMs();
                if (![archive addRenderPipelineFunctionsWithDescriptor: d error: &error]) [errors addObject: [NSString stringWithFormat: @"add render: %@", error.localizedDescription]];
                add.add(nowMs() - start);
                d.binaryArchives = @[archive];
                start = nowMs();
                id<MTLRenderPipelineState> state = [device newRenderPipelineStateWithDescriptor: d options: MTLPipelineOptionFailOnBinaryArchiveMiss reflection: nil error: &error];
                create.add(nowMs() - start);
                if (!state) strictFailures++;
                if (!firstRender) firstRender = state;
            }
            report[@"addFirstRender"] = add.json();
            report[@"createFromFreshArchiveRender"] = create.json();
            report[@"strictFailures"] = @(strictFailures);
        } else if ([mode isEqualToString: @"reuse"] || [mode isEqualToString: @"damaged"]) {
            NSString* path = archiveURL.path;
            if ([mode isEqualToString: @"damaged"]) {
                // Two damaged copies of the valid archive: cut in half, and its middle overwritten.
                NSData* whole = [NSData dataWithContentsOfFile: path];
                NSMutableDictionary* damaged = [NSMutableDictionary dictionary];
                NSMutableData* garbled = [whole mutableCopy];
                if (garbled.length > 4096) memset((uint8_t*)garbled.mutableBytes + garbled.length / 2 - 1024, 0xA5, 2048);
                NSDictionary* copies = @{@"cut": [whole subdataWithRange: NSMakeRange(0, whole.length / 2)], @"garbled": garbled,
                                         @"empty": [NSData data], @"text": [@"not an archive" dataUsingEncoding: NSUTF8StringEncoding]};
                for (NSString* name in copies) {
                    NSString* copy = [work stringByAppendingPathComponent: [name stringByAppendingString: @".metalarchive"]];
                    [copies[name] writeToFile: copy atomically: YES];
                    MTLBinaryArchiveDescriptor* ad = [MTLBinaryArchiveDescriptor new];
                    ad.url = [NSURL fileURLWithPath: copy];
                    NSError* loadError = nil;
                    double start = nowMs();
                    id<MTLBinaryArchive> archive = [device newBinaryArchiveWithDescriptor: ad error: &loadError];
                    double loadMs = nowMs() - start;
                    int hits = 0, misses = 0;
                    if (archive) {
                        for (MTLRenderPipelineDescriptor* d in renders) {
                            d.binaryArchives = @[archive];
                            id<MTLRenderPipelineState> state = [device newRenderPipelineStateWithDescriptor: d options: MTLPipelineOptionFailOnBinaryArchiveMiss reflection: nil error: nil];
                            if (state) hits++; else misses++;
                            d.binaryArchives = nil;
                        }
                    }
                    damaged[name] = @{@"loaded": @(archive != nil), @"loadMs": @(round(loadMs * 100) / 100), @"error": loadError.localizedDescription ?: @"",
                                      @"errorCode": @(loadError.code), @"strictHits": @(hits), @"strictMisses": @(misses), @"bytes": @([copies[name] length])};
                }
                report[@"damaged"] = damaged;
                // After the damaged copies, the normal compilation still serves every pipeline.
                int served = 0;
                for (MTLRenderPipelineDescriptor* d in renders) if ([device newRenderPipelineStateWithDescriptor: d error: nil]) served++;
                report[@"servedByNormalCompilation"] = @(served);
            } else {
                MTLBinaryArchiveDescriptor* ad = [MTLBinaryArchiveDescriptor new];
                ad.url = archiveURL;
                double before = footprintMiB();
                double start = nowMs();
                id<MTLBinaryArchive> archive = [device newBinaryArchiveWithDescriptor: ad error: &error];
                report[@"archiveLoad"] = @{@"loaded": @(archive != nil), @"ms": @(round((nowMs() - start) * 100) / 100), @"error": error.localizedDescription ?: @"",
                                           @"footprintDeltaMiB": @(round((footprintMiB() - before) * 100) / 100)};
                if (archive) {
                    // Strict: only the archive may serve.
                    Timing strict, strictCompute;
                    int hits = 0, misses = 0, computeHits = 0, computeMisses = 0;
                    for (MTLRenderPipelineDescriptor* d in renders) {
                        d.binaryArchives = @[archive];
                        double begin = nowMs();
                        id<MTLRenderPipelineState> state = [device newRenderPipelineStateWithDescriptor: d options: MTLPipelineOptionFailOnBinaryArchiveMiss reflection: nil error: &error];
                        strict.add(nowMs() - begin);
                        if (state) hits++; else misses++;
                        if (!firstRender) firstRender = state;
                    }
                    for (MTLComputePipelineDescriptor* d in kernels) {
                        d.binaryArchives = @[archive];
                        double begin = nowMs();
                        id<MTLComputePipelineState> state = [device newComputePipelineStateWithDescriptor: d options: MTLPipelineOptionFailOnBinaryArchiveMiss reflection: nil error: &error];
                        strictCompute.add(nowMs() - begin);
                        if (state) computeHits++; else computeMisses++;
                        if (!firstCompute) firstCompute = state;
                    }
                    report[@"strictRender"] = @{@"hits": @(hits), @"misses": @(misses), @"time": strict.json()};
                    report[@"strictCompute"] = @{@"hits": @(computeHits), @"misses": @(computeMisses), @"time": strictCompute.json()};
                    // The variant left out: strict must miss; the normal creation must then compile it.
                    absent.binaryArchives = @[archive];
                    NSError* missError = nil;
                    double begin = nowMs();
                    id<MTLRenderPipelineState> missed = [device newRenderPipelineStateWithDescriptor: absent options: MTLPipelineOptionFailOnBinaryArchiveMiss reflection: nil error: &missError];
                    double missMs = nowMs() - begin;
                    begin = nowMs();
                    id<MTLRenderPipelineState> fallback = [device newRenderPipelineStateWithDescriptor: absent error: &error];
                    double fallbackMs = nowMs() - begin;
                    report[@"absentVariant"] = @{@"strictSucceeded": @(missed != nil), @"strictMs": @(round(missMs * 1000) / 1000),
                                                 @"strictError": missError.localizedDescription ?: @"", @"strictErrorDomain": missError.domain ?: @"", @"strictErrorCode": @(missError.code),
                                                 @"normalSucceeded": @(fallback != nil), @"normalMs": @(round(fallbackMs * 100) / 100)};
                    // The normal creation with the archive offered (what a product path does): no option.
                    Timing offered;
                    for (MTLRenderPipelineDescriptor* d in renders) {
                        double b = nowMs();
                        id<MTLRenderPipelineState> state = [device newRenderPipelineStateWithDescriptor: d error: &error];
                        offered.add(nowMs() - b);
                        if (!state) [errors addObject: @"offered"];
                    }
                    report[@"normalWithArchiveOfferedRender"] = offered.json();
                    // Two archives searched together: an empty one first, then the loaded one.
                    id<MTLBinaryArchive> empty = [device newBinaryArchiveWithDescriptor: [MTLBinaryArchiveDescriptor new] error: nil];
                    int twoHits = 0;
                    if (empty) {
                        for (MTLRenderPipelineDescriptor* d in renders) {
                            d.binaryArchives = @[empty, archive];
                            if ([device newRenderPipelineStateWithDescriptor: d options: MTLPipelineOptionFailOnBinaryArchiveMiss reflection: nil error: nil]) twoHits++;
                        }
                    }
                    report[@"twoArchivesStrictHits"] = @(twoHits);
                    // The missed variant added to the loaded archive, saved as a second file, previous file untouched.
                    absent.binaryArchives = nil;
                    double b = nowMs();
                    BOOL added = [archive addRenderPipelineFunctionsWithDescriptor: absent error: &error];
                    double addMs = nowMs() - b;
                    NSURL* second = [NSURL fileURLWithPath: [work stringByAppendingPathComponent: @"pipelines-2.metalarchive"]];
                    b = nowMs();
                    BOOL saved = [archive serializeToURL: second error: &error];
                    report[@"addMissedAndSave"] = @{@"added": @(added), @"addMs": @(round(addMs * 100) / 100), @"saved": @(saved), @"saveMs": @(round((nowMs() - b) * 100) / 100),
                                                    @"bytes": @([[NSFileManager.defaultManager attributesOfItemAtPath: second.path error: nil] fileSize]),
                                                    @"firstFileBytes": @([[NSFileManager.defaultManager attributesOfItemAtPath: archiveURL.path error: nil] fileSize])};
                }
            }
        } else if ([mode isEqualToString: @"threads"]) {
            // Lookups from four threads on a loaded archive while a fifth adds to a second archive and saves it, and the
            // same with additions to the very archive being searched. A crash ends the process: the caller sees it.
            MTLBinaryArchiveDescriptor* ad = [MTLBinaryArchiveDescriptor new];
            ad.url = archiveURL;
            id<MTLBinaryArchive> loaded = [device newBinaryArchiveWithDescriptor: ad error: &error];
            id<MTLBinaryArchive> collecting = [device newBinaryArchiveWithDescriptor: [MTLBinaryArchiveDescriptor new] error: &error];
            NSMutableDictionary* threads = [NSMutableDictionary dictionary];
            for (NSString* target in @[@"separate", @"same"]) {
                id<MTLBinaryArchive> destination = [target isEqualToString: @"same"] ? loaded : collecting;
                std::atomic<int> hits{0}, misses{0}, added{0}, addErrors{0}, saves{0};
                std::atomic<bool> stop{false};
                std::vector<std::thread> workers;
                for (int t = 0; t < 4; t++) {
                    workers.emplace_back([&, t] {
                        @autoreleasepool {
                            for (int round = 0; round < 6; round++) {
                                for (NSUInteger i = t; i < renders.count; i += 4) {
                                    MTLRenderPipelineDescriptor* d = [renders[i] copy];
                                    d.binaryArchives = loaded ? @[loaded] : nil;
                                    id<MTLRenderPipelineState> state = [device newRenderPipelineStateWithDescriptor: d options: MTLPipelineOptionFailOnBinaryArchiveMiss reflection: nil error: nil];
                                    if (state) hits++; else misses++;
                                }
                            }
                        }
                    });
                }
                std::thread adder([&] {
                    @autoreleasepool {
                        int n = 0;
                        while (!stop) {
                            MTLRenderPipelineDescriptor* d = renderDescriptor(shaders, n % (int)shaders.fragments.count, MTLPixelFormatBGRA8Unorm, (n / (int)shaders.fragments.count) % 2);
                            NSError* e = nil;
                            if ([destination addRenderPipelineFunctionsWithDescriptor: d error: &e]) added++; else addErrors++;
                            if (++n % 8 == 0) {
                                NSURL* out = [NSURL fileURLWithPath: [work stringByAppendingPathComponent: [NSString stringWithFormat: @"threads-%@.metalarchive.tmp", target]]];
                                if ([destination serializeToURL: out error: &e]) saves++;
                            }
                            if (n >= 2 * (int)shaders.fragments.count) break;
                        }
                    }
                });
                for (auto& w : workers) w.join();
                stop = true;
                adder.join();
                threads[target] = @{@"strictHits": @(hits.load()), @"strictMisses": @(misses.load()), @"added": @(added.load()), @"addErrors": @(addErrors.load()), @"saves": @(saves.load())};
            }
            report[@"threads"] = threads;
        } else {
            fprintf(stderr, "unknown mode\n");
            return 2;
        }

        if (firstRender || firstCompute) report[@"result"] = drawAndCompute(device, firstRender, firstCompute);
        report[@"errors"] = errors;
        report[@"footprintDeltaMiB"] = @(round((footprintMiB() - footprintStart) * 100) / 100);
        report[@"systemCacheAfter"] = metalCacheDirectories(NO, processName, removed);
        NSData* data = [NSJSONSerialization dataWithJSONObject: report options: NSJSONWritingSortedKeys error: nil];
        printf("%s\n", [[NSString alloc] initWithData: data encoding: NSUTF8StringEncoding].UTF8String);
    }
    return 0;
}
