// Use exactly the engine's descriptor setup, stage loader and compiler timer.
#import <Foundation/Foundation.h>
#define main engine_pairbench_main
#include "pairbench.m"
#undef main

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 3) return 2;
        NSString *dir = @(argv[1]);
        const int pairs = atoi(argv[2]);
        if (pairs < 5 || pairs > 32) return 2;
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev) {
            fprintf(stderr, "Runtime unavailable: a Metal device is required.\n");
            return 77;
        }
        NSError *error = nil;
        BOOL metal4 = [dev supportsFamily:MTLGPUFamilyMetal4];
        id<MTL4Compiler> compiler = nil;
        if (metal4) {
            compiler = [dev newCompilerWithDescriptor:[MTL4CompilerDescriptor new] error:&error];
            if (!compiler) { NSLog(@"compiler: %@", error); return 1; }
        }
        MTL4LibraryFunctionDescriptor *verts[64], *frags[64];
        for (int i = 0; i < pairs * 2; i++) {
            frags[i] = load(dev, dir, [NSString stringWithFormat:@"f%d", i]);
            verts[i] = load(dev, dir, [NSString stringWithFormat:@"v%d", i]);
            if (!frags[i] || !verts[i]) return 1;
        }
        fprintf(stderr, "Metal device: %s. Builder: %s. Prior OS driver cache state unknown.\n",
                dev.name.UTF8String, metal4 ? "Metal 4 unspecialized" : "classic RGBA8");
        puts("pair,stage_pair,build_ms");
        const char *stage[] = {"fresh", "crossed", "one_fresh", "repeated", "vertex_fresh"};
        for (int phase = 0; phase < 5; phase++) {
            for (int i = 0; i < pairs; i++) {
                // Establish the first use of both stages before crossing them.
                // Balance the order of the four follow-up queries across pairs.
                int kind = phase ? 1 + (i + phase - 1) % 4 : 0;
                int v = kind == 4 ? i + pairs : i;
                int f = kind == 1 ? (i + 1) % pairs : kind == 2 ? i + pairs : i;
                NSString *reason = nil;
                double elapsed = 0;
                id<MTLRenderPipelineState> pso;
                if (metal4) {
                    pso = build(compiler, verts[v], frags[f], &elapsed, &reason);
                } else {
                    MTLRenderPipelineDescriptor *desc = [MTLRenderPipelineDescriptor new];
                    desc.vertexFunction = [verts[v].library newFunctionWithName:verts[v].name];
                    desc.fragmentFunction = [frags[f].library newFunctionWithName:frags[f].name];
                    desc.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
                    uint64_t start = mach_absolute_time();
                    pso = [dev newRenderPipelineStateWithDescriptor:desc error:&error];
                    elapsed = ms(start);
                    if (!pso) reason = error.localizedDescription;
                }
                if (!pso) { NSLog(@"PSO %d, %s: %@", i, stage[kind], reason); return 1; }
                printf("%d,%s,%.6f\n", i, stage[kind], elapsed);
            }
        }
    }
    return 0;
}
