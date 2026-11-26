#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(__APPLE__)
#import <Foundation/Foundation.h>
#define BufferBase NSObject
#else
#include <objc/Object.h>
#define BufferBase Object
#endif
#include <objc/runtime.h>
#include "nvn_refl.h"

@protocol MTLBuffer
@property(readonly) void *contents;
@property(readonly) uint64_t gpuAddress;
@end

@interface TestBuffer : BufferBase <MTLBuffer> {
@public
    uint8_t *bytes;
    uint64_t gpu;
}
@end

@implementation TestBuffer
- (void *)contents { return bytes; }
- (uint64_t)gpuAddress { return gpu; }
@end

typedef struct {
    uint8_t *cpu;
    uint64_t gpu;
    size_t used;
    id<MTLBuffer> buf;
} Arena;
typedef struct { int32_t stage, index; uint64_t addr, size; } p_bind_buf;
typedef struct { struct { nvn_rbind b[64]; int nb; } rf; } NvShader;

static uint64_t g_geo_size[5] = {1, 2, 3, 4, 5};
static struct { p_bind_buf ubo[6][16], ssbo[6][16]; } S;
#define GMEM_ENTRIES 1024
#define GMEM_ENTRY 16
#define GML_BYTES 4096
static Arena arenas[2], *g_cur_arena;
static int rb_bounds_reuse;
static uint64_t rb_bounds_hits, rb_bounds_misses, g_arena_gen = 1;
enum { arena_bytes = 256 * 64, verification_calls = 2048 };

static __attribute__((noinline)) size_t arena_alloc(size_t n, id<MTLBuffer> *buf) {
    n = (n + 255) & ~(size_t)255;
    if (g_cur_arena->used + n > arena_bytes) {
        g_cur_arena = g_cur_arena == &arenas[0] ? &arenas[1] : &arenas[0];
        g_cur_arena->used = 0;
        g_arena_gen++;
    }
    size_t offset = g_cur_arena->used;
    g_cur_arena->used += n;
    *buf = g_cur_arena->buf;
    return offset;
}

#include "baseline.inc"
#include "candidate.inc"

static uint32_t rng_state;
static uint32_t next_random(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return rng_state;
}

static uint64_t reference_addr[verification_calls];
static uint8_t reference_bytes[verification_calls][256];

static uint64_t run(int candidate_on, int mode, int verify) {
    NvShader shader = {0};
    uint64_t caps[NVN_UBOLEN_N];
    rng_state = 0x0db114eeu;
    g_cur_arena = &arenas[0];
    g_arena_gen += 100000;
    rb_bounds_hits = rb_bounds_misses = 0;
    for (int i = 0; i < 2; i++) {
        memset(arenas[i].cpu, 0xad, arena_bytes);
        arenas[i].used = 0;
    }
    memset(&S, 0, sizeof S);
    for (int slot = 0; slot < 16; slot++) {
        shader.rf.b[slot] = (nvn_rbind){
            .kind = slot % 3 ? NVN_RB_SBUFP : NVN_RB_UBOP, .reg = slot, .aid = slot
        };
        for (int stage = 0; stage < 6; stage++) {
            S.ubo[stage][slot].addr = slot % 5 ? 0x1000 + slot : 0;
            S.ubo[stage][slot].size = next_random() % 65570;
            S.ssbo[stage][slot] = S.ubo[stage][slot];
        }
    }
    shader.rf.nb = 16;
    for (int i = 0; i < NVN_UBOLEN_N; i++) caps[i] = UINT64_MAX;
    rb_bounds_reuse = mode >= 2;
    uint64_t sum = 0;
    const size_t repetitions = verify ? verification_calls : 500000;
    for (size_t i = 0; i < repetitions; i++) {
        int stage = i % 6;
        int kind = mode == 1 ? NVN_RB_SBSZ : NVN_RB_UBOLEN;
        if (mode != 2) {
            unsigned slot = i % NVN_UBOLEN_N;
            uint64_t data = next_random();
            S.ubo[stage][slot].size = i % 39 ? data % 100000 : UINT64_MAX - i % 20;
            S.ubo[stage][slot].addr = i % 31 ? 0x10020 : 0;
            caps[slot] = i % 2 ? 16 * ((i + 1) % 17) + i % 16 : UINT64_MAX;
        } else if (i % 1023 == 0) {
            g_arena_gen++;
        }
        const uint64_t *bounds = i % 3 ? caps : NULL;
        uint64_t addr = candidate_on ? candidate(&shader, stage, kind, bounds)
                                     : baseline(&shader, stage, kind, bounds);
        sum += addr;
        if (verify) {
            const Arena *arena = &arenas[addr >= arenas[1].gpu];
            assert(addr >= arena->gpu && addr - arena->gpu <= arena_bytes - 256);
            const uint8_t *bytes = arena->cpu + (addr - arena->gpu);
            if (!candidate_on) {
                reference_addr[i] = addr;
                memcpy(reference_bytes[i], bytes, 256);
            } else {
                assert(reference_addr[i] == addr);
                assert(memcmp(reference_bytes[i], bytes, 256) == 0);
            }
            for (unsigned j = 0; j < 256; j++) sum = (sum ^ bytes[j]) * UINT64_C(1099511628211);
        }
    }
    return sum + rb_bounds_hits + rb_bounds_misses;
}

static double cpu_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}

int main(int argc, char **argv) {
    const int verify = argc > 1;
    (void)argv;
    for (int i = 0; i < 2; i++) {
        TestBuffer *b = class_createInstance(objc_getClass("TestBuffer"), 0);
        b->bytes = malloc(arena_bytes);
        assert(b->bytes);
        b->gpu = UINT64_C(0x800000000) + i * 2 * arena_bytes;
        arenas[i] = (Arena){b->bytes, b->gpu, 0, b};
    }
    for (unsigned pair = 0; pair < (verify ? 1u : 65u); pair++) {
        for (int mode = 0; mode < 4; mode++) {
            uint64_t sums[2];
            // Balanced order over the 64 measured pairs after warm-up.
            const int first = __builtin_parity(pair & 63u);
            for (int j = 0; j < 2; j++) {
                int which = first ^ j;
                double start = cpu_ms();
                sums[which] = run(which, mode, verify);
                double elapsed = cpu_ms() - start;
                printf("%u\t%d\t%d\t%.5f\n", pair, mode, which, elapsed);
            }
            assert(sums[0] == sums[1]);
        }
    }
    for (int i = 0; i < 2; i++) {
        free(arenas[i].cpu);
        object_dispose(arenas[i].buf);
    }
    return 0;
}
