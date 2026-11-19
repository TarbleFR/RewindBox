// Focused macOS host for the pinned NVN archive. Only the surrounding renderer's
// device, paths, priority inputs and deterministic governor level are supplied.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <dispatch/dispatch.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <os/lock.h>
#include <pthread/qos.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "rb_spec_gate.h"
#include "s2a_qos.h"

#define REQUIRE(expr) do { if (!(expr)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); exit(1); } } while (0)
#define MLOG(...) do { fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); } while (0)
static id<MTLDevice> g_dev;
static NSString *g_shmap_path;
static _Atomic int g_fu_waiting;
static rb_spec_gate g_spec_gate = RB_SPEC_GATE_INITIALIZER;
static uint64_t bp_now(void) { return clock_gettime_nsec_np(CLOCK_UPTIME_RAW); }
static int rb_spec_level(void) { return atomic_load(&g_spec_gate.level); }
static int rb_spec_may(int w) { return rb_spec_worker_allowed(rb_spec_level(), w); }
static int rb_spec_take(int worker, int *lease) { return *lease = rb_spec_admit(&g_spec_gate, worker); }
static void rb_spec_done(int *lease) { rb_spec_release(&g_spec_gate, lease); }
static void after_descriptor(NSString *key);
#define RB_ARCHIVE_TEST_AFTER_DESCRIPTOR(key) after_descriptor(key)
static NSString *pso_user_path(void) {
    const char *path = getenv("DM_PSO_USER");
    return path && *path ? @(path) : nil;
}
#ifdef RB_ARCHIVE_TEST_793_CONTROL
// The 793 writer uses this global only as a hint for the queue length. Both
// hosts get the fixed entry gate to isolate the missing *in-batch* check.
#define g_spec_level g_spec_gate.level
static const int control_793 = 1;
#else
static const int control_793 = 0;
#endif
#include "pso_archive.h"
#include "rb_archive_relaunch.inc"

enum { INTERRUPT_AT = 7 };
static dispatch_semaphore_t at_boundary, release_writer;
static NSMutableArray<NSString *> *attempts;
static void after_descriptor(NSString *key) {
    if (!attempts) return;
    [attempts addObject:key];
    if (attempts.count != INTERRUPT_AT) return;
    dispatch_semaphore_signal(at_boundary);
    REQUIRE(!dispatch_semaphore_wait(release_writer, dispatch_time(DISPATCH_TIME_NOW, 10000000000ll)));
}
static void await_parked_tail(NSUInteger count) {
    uint64_t until = bp_now() + 10000000000ull;
    for (;;) {
        pthread_mutex_lock(&g_par_mu);
        BOOL parked = g_par_timer && g_par_pending_keys.count == count && g_par_todo.count == count;
        pthread_mutex_unlock(&g_par_mu);
        if (parked) return;
        REQUIRE(bp_now() < until);
        sched_yield();
    }
}
static void test_mid_batch(const char *directory, const char *mode) {
    int closing = !strcmp(mode, "expire"), one = !strcmp(mode, "one");
    REQUIRE(closing || one || !strcmp(mode, "hold"));
    if (control_793) REQUIRE(!closing && !one);
    g_dev = MTLCreateSystemDefaultDevice(); REQUIRE(g_dev);
    NSString *path = [@(directory) stringByAppendingPathComponent:@"pso_user.tsv"];
    REQUIRE(setenv("DM_PSO_USER", path.fileSystemRepresentation, 1) == 0);
    par_open_dir(); REQUIRE(g_par_on);
    rb_spec_publish(&g_spec_gate, RB_SPEC_HOLD);
    NSMutableArray *keys = [NSMutableArray array], *entries = [NSMutableArray array];
    NSMutableString *source = [NSMutableString stringWithString:@"#include <metal_stdlib>\nusing namespace metal;\n"];
    for (unsigned i = 0; i < PAR_BATCH; i++)
        [source appendFormat:@"kernel void k%u(device uint *p [[buffer(0)]]) { *p = %uu; }\n", i, i + 1];
    NSError *err = nil; id<MTLLibrary> lib = [g_dev newLibraryWithSource:source options:nil error:&err]; REQUIRE(lib);
    attempts = [NSMutableArray array];
    at_boundary = dispatch_semaphore_create(0); release_writer = dispatch_semaphore_create(0);
    for (unsigned i = 0; i < PAR_BATCH; i++) {
        NSString *function = [NSString stringWithFormat:@"k%u", i];
        NSString *key = [@"c" stringByAppendingString:par_hash(function.UTF8String, strlen(function.UTF8String))];
        MTLComputePipelineDescriptor *desc = [MTLComputePipelineDescriptor new];
        desc.computeFunction = [lib newFunctionWithName:function];
        // Follow the runtime writer contract: the exact descriptor has already
        // built a pipeline in play. This also warms the test driver's service.
        REQUIRE([g_dev newComputePipelineStateWithDescriptor:desc options:0 reflection:nil error:&err]);
        [keys addObject:key]; [entries addObject:desc]; par_note(key, desc);
    }
    await_parked_tail(PAR_BATCH);
    rb_spec_publish(&g_spec_gate, RB_SPEC_RUN);
    REQUIRE(!dispatch_semaphore_wait(at_boundary, dispatch_time(DISPATCH_TIME_NOW, 30000000000ll)));
    int other_lease = 0;
    if (one) REQUIRE(rb_spec_take(1, &other_lease));  // outstanding prior RUN work
    if (closing) {
        par_begin_close(); REQUIRE(atomic_load(&g_par_close_until));
        // The uninterruptible Metal call used the remaining close budget.
        // Expire the same production deadline deterministically.
        atomic_store(&g_par_close_until, bp_now());
    } else rb_spec_publish(&g_spec_gate, one ? RB_SPEC_ONE : RB_SPEC_HOLD);
    for (unsigned i = 0; i < PAR_BATCH; i++) par_note(keys[i], entries[i]);
    dispatch_semaphore_signal(release_writer);
    if (!closing && !control_793) {
        await_parked_tail(PAR_BATCH - INTERRUPT_AT);
        REQUIRE(attempts.count == INTERRUPT_AT && atomic_load(&g_par_written) == INTERRUPT_AT);
        for (unsigned i = INTERRUPT_AT; i < PAR_BATCH; i++) par_note(keys[i], entries[i]);
        if (one) rb_spec_done(&other_lease); else rb_spec_publish(&g_spec_gate, RB_SPEC_RUN);
    }
    struct timespec deadline; clock_gettime(CLOCK_REALTIME, &deadline); deadline.tv_sec += 30;
    REQUIRE(!par_wait_idle(&deadline));
    NSUInteger finished = closing ? INTERRUPT_AT : PAR_BATCH;
    REQUIRE([attempts isEqual:[keys subarrayWithRange:NSMakeRange(0, finished)]]);
    REQUIRE(atomic_load(&g_par_written) == finished && !atomic_load(&g_par_write_failed));
    REQUIRE(!g_par_pending_keys.count && !g_par_todo.count && !g_spec_gate.active);
    for (NSUInteger i = 0; i < finished; ++i) {
        id<MTLBinaryArchive> archive = par_archive_for(keys[i]); REQUIRE(archive);
        MTLComputePipelineDescriptor *probe = [entries[i] copy]; probe.binaryArchives = @[archive];
        err = nil;
        REQUIRE([g_dev newComputePipelineStateWithDescriptor:probe options:MTLPipelineOptionFailOnBinaryArchiveMiss reflection:nil error:&err]);
    }
    if (control_793) {
        REQUIRE(rb_spec_level() == RB_SPEC_HOLD && finished == PAR_BATCH);
        // This distinct status requires all 32 attempts, including exactly 25
        // after HOLD, and every strict Metal readback above. A crash, missing
        // device, missing callback, timeout or other assertion cannot pass.
        fprintf(stderr, "EXPECTED 793 FAILURE: %u descriptors started after HOLD (%u/%u strict hits)\n",
                (unsigned)(PAR_BATCH - INTERRUPT_AT), (unsigned)finished, (unsigned)PAR_BATCH);
        exit(86);
    }
    printf("PASS %s after descriptor %u/%u, %lu exact strict hits; no duplicate/start after deadline\n",
           mode, INTERRUPT_AT, (unsigned)PAR_BATCH, (unsigned long)finished);
}
static void test_held_writer(const char *directory, const char *mode) {
    int closing = !strcmp(mode, "close"), replay = !strcmp(mode, "replay");
    g_dev = MTLCreateSystemDefaultDevice();
    REQUIRE(g_dev);
    NSString *path = [@(directory) stringByAppendingPathComponent:@"pso_user.tsv"];
    REQUIRE(setenv("DM_PSO_USER", path.fileSystemRepresentation, 1) == 0);
    par_open_dir();
    REQUIRE(g_par_on);
    NSError *error = nil;
    id<MTLLibrary> lib = [g_dev newLibraryWithSource:
        @"#include <metal_stdlib>\nusing namespace metal; kernel void held(device uint *v [[buffer(0)]]) { *v = 1; }"
        options:nil error:&error];
    REQUIRE(lib);
    id<MTLFunction> function = [lib newFunctionWithName:@"held"];
    REQUIRE(function);
    NSString *key = [@"c" stringByAppendingString:par_hash("held", 4)];
    if (!replay) {
        // Exercise the production sequence: the first draw builds an exact PSO,
        // and par_compute then submits its descriptor to the deferred writer.
        g_par_note_play = 1;
        rb_spec_publish(&g_spec_gate, RB_SPEC_HOLD);
        id<MTLComputePipelineState> first = par_compute(function, key, &error);
        REQUIRE(first && atomic_load(&g_par_misses) == 1 && !atomic_load(&g_par_hits));
        MTLComputePipelineDescriptor *duplicate = [MTLComputePipelineDescriptor new];
        duplicate.computeFunction = function;
        par_note(key, duplicate);
        uint64_t timeout = bp_now() + 5000000000ull;
        int pending = 0;
        do {
            pthread_mutex_lock(&g_par_mu);
            pending = g_par_timer != 0 && g_par_todo.count == 1 && g_par_pending_keys.count == 1;
            pthread_mutex_unlock(&g_par_mu);
            if (!pending) sched_yield();
        } while (!pending && bp_now() < timeout);
        REQUIRE(pending);
        if (closing) par_begin_close();
        else rb_spec_publish(&g_spec_gate, RB_SPEC_RUN);
        struct timespec deadline;
        clock_gettime(CLOCK_REALTIME, &deadline);
        deadline.tv_sec += 30;
        REQUIRE(!par_wait_idle(&deadline));
        REQUIRE(atomic_load(&g_par_written) == 1 && !g_par_pending_keys.count);
    }
    // New descriptor, same entry and configuration, like the next call to par_compute.
    id<MTLBinaryArchive> archive = par_archive_for(key);
    REQUIRE(archive);
    MTLComputePipelineDescriptor *probe = [MTLComputePipelineDescriptor new];
    probe.computeFunction = function;
    probe.binaryArchives = @[archive];
    error = nil;
    id<MTLComputePipelineState> from_archive = [g_dev newComputePipelineStateWithDescriptor:probe
        options:MTLPipelineOptionFailOnBinaryArchiveMiss reflection:nil error:&error];
    if (!from_archive) {
        NSString *file = [g_par_dir stringByAppendingPathComponent:g_par_bmap[key]];
        NSDictionary *attrs = [NSFileManager.defaultManager attributesOfItemAtPath:file error:nil];
        fprintf(stderr, "strict compute miss mode=%s gpu=%s file=%s bytes=%llu error=%s/%ld %s\n",
                mode, g_dev.name.UTF8String, file.lastPathComponent.UTF8String, [attrs fileSize],
                error.domain.UTF8String, (long)error.code, error.description.UTF8String);
    }
    REQUIRE(from_archive);
    id<MTLBuffer> output = [g_dev newBufferWithLength:sizeof(uint32_t) options:MTLResourceStorageModeShared];
    REQUIRE(output);
    *(uint32_t *)output.contents = 0;
    id<MTLCommandQueue> queue = [g_dev newCommandQueue];
    id<MTLCommandBuffer> cmd = [queue commandBuffer];
    id<MTLComputeCommandEncoder> enc = [cmd computeCommandEncoder];
    [enc setComputePipelineState:from_archive];
    [enc setBuffer:output offset:0 atIndex:0];
    [enc dispatchThreadgroups:MTLSizeMake(1,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];
    [enc endEncoding];
    [cmd commit];
    [cmd waitUntilCompleted];
    REQUIRE(cmd.status == MTLCommandBufferStatusCompleted && *(uint32_t *)output.contents == 1);
    printf("PASS deferred writer mode=%s strict compute hit, output=1\n", mode);
}
int main(int argc, char **argv) { @autoreleasepool {
    if (argc == 2 && !strcmp(argv[1], "--probe")) return MTLCreateSystemDefaultDevice() ? 0 : 77;
    if (argc == 4 && !strcmp(argv[1], "--relaunch") && (!strcmp(argv[3], "cold") || !strcmp(argv[3], "warm")))
        return rb_archive_relaunch(argv[2], !strcmp(argv[3], "warm"));
    if (argc == 4 && !strcmp(argv[1], "--held") && (!strcmp(argv[3], "resume") || !strcmp(argv[3], "close") || !strcmp(argv[3], "replay"))) {
        test_held_writer(argv[2], argv[3]);
        return 0;
    }
    if (argc == 4 && !strcmp(argv[1], "--mid-batch")) { test_mid_batch(argv[2], argv[3]); return 0; }
    fprintf(stderr, "Unexpected arguments\n");
    return 2;
} }
