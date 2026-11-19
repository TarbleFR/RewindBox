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
static _Atomic int g_fu_waiting, g_spec_level;
static _Atomic unsigned active;
static uint64_t bp_now(void) { return clock_gettime_nsec_np(CLOCK_UPTIME_RAW); }
static int rb_spec_may(int w) { return rb_spec_worker_allowed(atomic_load(&g_spec_level), w); }
static int rb_spec_take(int worker, int *lease) { return *lease = rb_spec_admit(&active, atomic_load(&g_spec_level), worker); }
static void rb_spec_done(int *lease) { if (*lease) { atomic_fetch_sub(&active, 1); *lease = 0; } }
static NSString *pso_user_path(void) {
    const char *path = getenv("DM_PSO_USER");
    return path && *path ? @(path) : nil;
}
#include "pso_archive.h"
#include "rb_archive_relaunch.inc"

static void test_held_writer(const char *directory, int closing) {
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
    MTLComputePipelineDescriptor *desc = [MTLComputePipelineDescriptor new];
    desc.computeFunction = [lib newFunctionWithName:@"held"];
    REQUIRE(desc.computeFunction);
    NSString *key = [@"c" stringByAppendingString:par_hash("held", 4)];
    atomic_store(&g_spec_level, RB_SPEC_HOLD);
    par_note(key, desc);
    par_note(key, desc);
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
    else atomic_store(&g_spec_level, RB_SPEC_RUN);
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += 30;
    REQUIRE(!par_wait_idle(&deadline));
    REQUIRE(atomic_load(&g_par_written) == 1 && !g_par_pending_keys.count);
    id<MTLBinaryArchive> archive = par_archive_for(key);
    REQUIRE(archive);
    desc.binaryArchives = @[archive];
    REQUIRE([g_dev newComputePipelineStateWithDescriptor:desc options:MTLPipelineOptionFailOnBinaryArchiveMiss reflection:nil error:&error]);
    puts(closing ? "PASS deferred writer on close" : "PASS deferred writer on return to RUN");
}
int main(int argc, char **argv) { @autoreleasepool {
    if (argc == 2 && !strcmp(argv[1], "--probe")) return MTLCreateSystemDefaultDevice() ? 0 : 77;
    if (argc == 4 && !strcmp(argv[1], "--relaunch") && (!strcmp(argv[3], "cold") || !strcmp(argv[3], "warm")))
        return rb_archive_relaunch(argv[2], !strcmp(argv[3], "warm"));
    if (argc == 4 && !strcmp(argv[1], "--held") && (!strcmp(argv[3], "resume") || !strcmp(argv[3], "close"))) {
        test_held_writer(argv[2], !strcmp(argv[3], "close"));
        return 0;
    }
    fprintf(stderr, "Unexpected arguments\n");
    return 2;
} }
