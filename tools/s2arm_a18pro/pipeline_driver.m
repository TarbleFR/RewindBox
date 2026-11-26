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
        if (!dev || ![dev supportsFamily:MTLGPUFamilyMetal4]) {
            fprintf(stderr, "Runtime unavailable: a Metal 4 device is required.\n");
            return 77;
        }
        NSError *error = nil;
        id<MTL4Compiler> compiler = [dev newCompilerWithDescriptor:[MTL4CompilerDescriptor new] error:&error];
        if (!compiler) { NSLog(@"compiler: %@", error); return 1; }
        MTL4LibraryFunctionDescriptor *verts[32], *frags[64];
        for (int i = 0; i < pairs * 2; i++) {
            frags[i] = load(dev, dir, [NSString stringWithFormat:@"f%d", i]);
            if (i < pairs) verts[i] = load(dev, dir, [NSString stringWithFormat:@"v%d", i]);
            if (!frags[i] || (i < pairs && !verts[i])) return 1;
        }
        fprintf(stderr, "Metal 4 device: %s. Prior OS driver cache state unknown.\n", dev.name.UTF8String);
        puts("pair,stage_pair,build_ms");
        const char *stage[] = {"fresh", "crossed", "one_fresh", "repeated"};
        for (int phase = 0; phase < 4; phase++) {
            for (int i = 0; i < pairs; i++) {
                // Establish the first use of both stages before crossing them.
                // Balance the order of the three follow-up queries across pairs.
                int kind = phase ? 1 + (i + phase - 1) % 3 : 0;
                int f = kind == 1 ? (i + 1) % pairs : kind == 2 ? i + pairs : i;
                NSString *reason = nil;
                double ms = 0;
                id<MTLRenderPipelineState> pso = build(compiler, verts[i], frags[f], &ms, &reason);
                if (!pso) { NSLog(@"PSO %d, %s: %@", i, stage[kind], reason); return 1; }
                printf("%d,%s,%.6f\n", i, stage[kind], ms);
            }
        }
    }
    return 0;
}
