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
static unsigned serializations, refuse_serializations, adds;
static __weak id<MTLBinaryArchive> last_rejected_archive;
static int verify_same_archive;
static int expire_on_refusal;
static BOOL serialize_fixture(id<MTLBinaryArchive> archive, NSURL *url, NSError **error);
#define RB_ARCHIVE_TEST_SERIALIZE(a, url, e) serialize_fixture(a, url, e)
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
// Supply the renderer callbacks omitted by this isolated archive fixture.
enum { RB_RENDER, RB_COMPUTE };
static int rb_heap_on(void) { return 1; }
static int nvn_be_stopping(void) { return 0; }   // patch 0300: archive jobs stand down for a session that is ending; this fixture never ends one
static int rb_pso_cap_on(void) { return 0; }
static void rb_pso_track(id ps, unsigned kind, NSString *key, BOOL hit) { (void)ps; (void)kind; (void)key; (void)hit; }
static void rb_recreated(NSString *key, id ps, uint64_t start) { (void)key; (void)ps; (void)start; }
static int test_scope_enabled, test_storage_scope;
static const char *test_scope_build;
#define RB_PAR_SCOPED() test_scope_enabled
#define RB_PAR_STORAGE_SCOPE() (test_storage_scope || test_scope_enabled)
#define RB_PAR_MEASURE() RB_PAR_STORAGE_SCOPE()
#define RB_PAR_BUILD() test_scope_build
static _Thread_local int fixture_submit;
static int fixture_preopen;
static NSString *fixture_seed_key;
#define RB_PAR_SEED_RECIPES(keys) do { if (fixture_seed_key) [(keys) addObject:fixture_seed_key]; } while (0)
#define RB_PAR_SUBMIT_THREAD() fixture_submit
#define RB_PAR_PREOPEN() fixture_preopen
#ifndef RB_ARCHIVE_TEST_793_CONTROL
static int injected_archive_thermal = -1;
#define RB_PAR_WRITE_MODE() rb_archive_write_mode(injected_archive_thermal >= 0, injected_archive_thermal, (1024ull << 20) + 1)
#endif
#include "pso_archive.h"
#include "rb_archive_relaunch.inc"

static BOOL serialize_fixture(id<MTLBinaryArchive> archive, NSURL *url, NSError **error) {
    ++serializations;
    if (verify_same_archive) {
        REQUIRE(last_rejected_archive == archive);
        verify_same_archive = 0;
    }
    if (!refuse_serializations) return [archive serializeToURL:url error:error];
    --refuse_serializations;
    last_rejected_archive = archive;  // weak: only the writer may keep the object alive
    verify_same_archive = 1;
    if (expire_on_refusal) {
        REQUIRE(atomic_load(&g_par_close_until));
        atomic_store(&g_par_close_until, bp_now());
    }
    if (error) *error = [NSError errorWithDomain:@"RBFixtureMetalSerialization" code:1 userInfo:nil];
    return NO;
}
enum { INTERRUPT_AT = 7 };
static dispatch_semaphore_t at_boundary, release_writer;
static NSMutableArray<NSString *> *attempts;
static void after_descriptor(NSString *key) {
    ++adds;
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
    unsigned variant = control_793 ? 0 : closing ? 3 : one ? 2 : 1;
    for (unsigned i = 0; i < PAR_BATCH; i++)
        [source appendFormat:@"kernel void b%u_k%u(device uint *p [[buffer(0)]]) { *p = %uu; }\n",
            variant, i, variant * PAR_BATCH + i + 1];
    NSError *err = nil; id<MTLLibrary> lib = [g_dev newLibraryWithSource:source options:nil error:&err]; REQUIRE(lib);
    attempts = [NSMutableArray array];
    at_boundary = dispatch_semaphore_create(0); release_writer = dispatch_semaphore_create(0);
    for (unsigned i = 0; i < PAR_BATCH; i++) {
        NSString *function = [NSString stringWithFormat:@"b%u_k%u", variant, i];
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
        if (one) {
            refuse_serializations = 1;  // first ONE archive after the original 7
            rb_spec_done(&other_lease);
        } else rb_spec_publish(&g_spec_gate, RB_SPEC_RUN);
    }
    struct timespec deadline; clock_gettime(CLOCK_REALTIME, &deadline); deadline.tv_sec += 30;
    REQUIRE(!par_wait_idle(&deadline));
    NSUInteger finished = closing ? INTERRUPT_AT : PAR_BATCH;
    REQUIRE([attempts isEqual:[keys subarrayWithRange:NSMakeRange(0, finished)]]);
    REQUIRE(atomic_load(&g_par_written) == finished && !atomic_load(&g_par_write_failed));
    if (one) REQUIRE(!verify_same_archive && adds == PAR_BATCH);
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
static void test_held_writer(const char *directory, const char *mode, int replay) {
    int resume = !strcmp(mode, "resume"), shared = !strcmp(mode, "shared");
    int retry = !strcmp(mode, "retry"), failed = !strcmp(mode, "fail"), expired = !strcmp(mode, "expire-retry");
    REQUIRE(resume || shared || retry || failed || expired || !strcmp(mode, "close"));
    // "shared" starts with an empty application archive and uses exactly the
    // successful resume scenario's kernel and key in this new process. Each
    // independent scenario's replay uses exactly its own original descriptor.
    NSString *entry = resume || shared ? @"held" : expired ? @"held_expire_retry" : [@"held_" stringByAppendingString:@(mode)];
    uint32_t expected = resume || shared ? 1 : retry ? 29 : failed ? 31 : expired ? 37 : 17;
    if (!replay) { refuse_serializations = failed ? 2 : retry || expired; expire_on_refusal = expired; }
    g_dev = MTLCreateSystemDefaultDevice();
    REQUIRE(g_dev);
    NSString *path = [@(directory) stringByAppendingPathComponent:@"pso_user.tsv"];
    REQUIRE(setenv("DM_PSO_USER", path.fileSystemRepresentation, 1) == 0);
    par_open_dir();
    REQUIRE(g_par_on);
    NSError *error = nil;
    NSString *source = [NSString stringWithFormat:@"#include <metal_stdlib>\nusing namespace metal; "
        "kernel void %@(device uint *v [[buffer(0)]]) { *v = %uu; }", entry, expected];
    id<MTLLibrary> lib = [g_dev newLibraryWithSource:source options:nil error:&error];
    REQUIRE(lib);
    id<MTLFunction> function = [lib newFunctionWithName:entry];
    REQUIRE(function);
    NSString *key = [@"c" stringByAppendingString:par_hash(entry.UTF8String, strlen(entry.UTF8String))];
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
        if (!resume) par_begin_close();
        else rb_spec_publish(&g_spec_gate, RB_SPEC_RUN);
        struct timespec deadline;
        clock_gettime(CLOCK_REALTIME, &deadline);
        deadline.tv_sec += 30;
        REQUIRE(!par_wait_idle(&deadline));
        REQUIRE(!g_par_pending_keys.count && !g_par_todo.count && adds == 1);
#ifndef RB_ARCHIVE_TEST_793_CONTROL
        REQUIRE(!g_par_retry && !g_par_ga_held);
        if (retry || failed || expired) {
            REQUIRE(serializations == (expired ? 1 : 2) && atomic_load(&g_par_serialize_retries) == (unsigned)!expired);
        }
#endif
        REQUIRE(atomic_load(&g_par_written) == (failed || expired ? 0 : 1));
    }
    // New descriptor, same entry and configuration, like the next call to par_compute.
    id<MTLBinaryArchive> archive = par_archive_for(key);
    if (failed || expired) {
        REQUIRE(!archive && !g_par_bmap[key] && ![g_par_have containsObject:key]);
        // No application archive or index may claim this failed descriptor.
        id<MTLBinaryArchive> empty = [g_dev newBinaryArchiveWithDescriptor:[MTLBinaryArchiveDescriptor new] error:&error];
        REQUIRE(empty);
        MTLComputePipelineDescriptor *missing = [MTLComputePipelineDescriptor new];
        missing.computeFunction = function; missing.binaryArchives = @[empty];
        REQUIRE(![g_dev newComputePipelineStateWithDescriptor:missing options:MTLPipelineOptionFailOnBinaryArchiveMiss reflection:nil error:&error]);
        printf("PASS %s terminal archive miss, replay=%d\n", mode, replay);
        return;
    }
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
    REQUIRE(cmd.status == MTLCommandBufferStatusCompleted && *(uint32_t *)output.contents == expected);
    printf("PASS deferred writer mode=%s replay=%d strict compute hit, output=%u\n", mode, replay, expected);
}
#ifndef RB_ARCHIVE_TEST_793_CONTROL
static void await_test_archive_writer(void) {
    struct timespec until;
    REQUIRE(!clock_gettime(CLOCK_REALTIME, &until));
    until.tv_sec += 30;
    REQUIRE(!par_wait_idle(&until));
}
static void retire_drained_test_archive(void) {
    // Production session_wait_backend drains the archive before retiring paths.
    await_test_archive_writer();
    par_retire_session();
}
static void check_index_bytes(NSString *path, NSData *expected, const char *phase) {
    NSError *error = nil;
    NSData *actual = [NSData dataWithContentsOfFile:path options:0 error:&error];
    if (!actual || ![actual isEqualToData:expected]) {
        fprintf(stderr, "FAIL legacy index %s at %s: expected %lu bytes, read %lu, error %s, expected_sha256_prefix=%s actual_sha256_prefix=%s\n",
                phase, path.fileSystemRepresentation, (unsigned long)expected.length, (unsigned long)actual.length,
                error.localizedDescription.UTF8String ?: "none", par_hash(expected.bytes, expected.length).UTF8String,
                actual ? par_hash(actual.bytes, actual.length).UTF8String : "unavailable");
        exit(1);
    }
}
// Demand-compile a render pipeline while every speculative lease is denied.
// The warm invocation is a fresh process and Metal's strict archive probe has
// to load the exact render state. Neither invocation enqueues a test descriptor.
static void test_live_render_archive(const char *directory, int thermal, BOOL warm) {
    REQUIRE(thermal == 1 || thermal == 2);
    injected_archive_thermal=thermal;
    rb_spec_publish(&g_spec_gate,RB_SPEC_HOLD);
    REQUIRE(!setenv("DM_PSO_USER", [@(directory) stringByAppendingPathComponent:@"pso_user.tsv"].fileSystemRepresentation, 1));
    g_dev=MTLCreateSystemDefaultDevice(); REQUIRE(g_dev);
    NSString *source=@"#include <metal_stdlib>\nusing namespace metal;\n"
         "vertex float4 vs(uint i [[vertex_id]]) { return float4(float(i),0,0,1); }\n"
         "fragment float4 ps(){return float4(1,0,0,1);}";
    NSError *error=nil;
    id<MTLLibrary> lib=[g_dev newLibraryWithSource:source options:nil error:&error]; REQUIRE(lib);
    MTLRenderPipelineDescriptor *d=[MTLRenderPipelineDescriptor new];
    d.vertexFunction=[lib newFunctionWithName:@"vs"];
    d.fragmentFunction=[lib newFunctionWithName:@"ps"];
    d.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;
    NSString *key=par_hash("warm-render",sizeof("warm-render")-1);
    fixture_preopen = 1;
    rb_archive_preopen_start();
    REQUIRE(!dispatch_group_wait(rb_archive_jobs(), dispatch_time(DISPATCH_TIME_NOW, 10*NSEC_PER_SEC)));
    if (warm) {
        REQUIRE(atomic_load(&rb_preopened) == 1);
        fixture_submit = 1;
        REQUIRE(rb_archive_get(key, RB_LOCAL));
        uint64_t samples[101];
        for (int i = 0; i < 101; ++i) {
            uint64_t begin = bp_now();
            REQUIRE(rb_archive_get(key, RB_LOCAL));
            samples[i] = bp_now() - begin;
        }
        for (int i = 1; i < 101; ++i) {
            uint64_t ns = samples[i]; int j = i;
            while (j && ns < samples[j-1]) { samples[j]=samples[j-1]; --j; }
            samples[j] = ns;
        }
        REQUIRE(samples[50] < 100000 && !atomic_load(&rb_cold_submit));
        printf("PASS warm archive memory lookup p50_ns=%llu p99_ns=%llu n=101\n",
               (unsigned long long)samples[50], (unsigned long long)samples[99]);
    }
    REQUIRE(par_render(d,key,&error));
    await_test_archive_writer();
    REQUIRE(atomic_load(&g_par_written)==(unsigned)!warm);
    REQUIRE(atomic_load(&g_par_hits)==(unsigned)warm);
    REQUIRE(atomic_load(&g_par_misses)==(unsigned)!warm);
    fixture_submit = 0;
    rb_archive_preopen_retire();
    REQUIRE([NSFileManager.defaultManager fileExistsAtPath:rb_hot_index()]);
    REQUIRE([NSFileManager.defaultManager fileExistsAtPath:[g_par_dir stringByAppendingPathComponent:@"batches.tsv"]]);
    printf("PASS thermal=%d render written=%llu from_archive=%llu\n", thermal,
           (unsigned long long)atomic_load(&g_par_written),(unsigned long long)atomic_load(&g_par_hits));
}
static void test_scoped_archive(const char *directory) {
    NSString *parent = @(directory);
    REQUIRE(setenv("DM_PSO_USER", [parent stringByAppendingPathComponent:@"pso_user.tsv"].fileSystemRepresentation, 1) == 0);
    REQUIRE(setenv("S2A_RB_DIRECT_GAME_ID", "04007EF01F8AE000", 1) == 0);
    g_dev = MTLCreateSystemDefaultDevice();
    REQUIRE(g_dev);
    NSError *error = nil;
    NSString *source = @"#include <metal_stdlib>\nusing namespace metal; kernel void scope_test(device int* x [[buffer(0)]]){x[0]=42;}";
    id<MTLLibrary> lib = [g_dev newLibraryWithSource:source options:nil error:&error];
    REQUIRE(lib);
    id<MTLFunction> fn = [lib newFunctionWithName:@"scope_test"];
    REQUIRE(fn);
    NSString *key = [@"c" stringByAppendingString:par_hash("scoped-key", 10)];
    MTLComputePipelineDescriptor *d = [MTLComputePipelineDescriptor new];
    d.computeFunction = fn;
    REQUIRE(par_open_dir() && g_par_on);
    REQUIRE(par_write_batch(@[@[key, d]]) == 1 && atomic_load(&g_par_written) == 1);
    NSString *legacyIndex = [g_par_dir stringByAppendingPathComponent:@"batches.tsv"];
    NSData *expectedIndex = [NSData dataWithContentsOfFile:legacyIndex];
    REQUIRE(expectedIndex.length);
    retire_drained_test_archive();
    test_storage_scope = 1; // generic disk identity with legacy scheduling
    REQUIRE(!test_scope_enabled);
    test_scope_build = "";
    REQUIRE(!par_open_dir());
    test_scope_build = "0123456789abcdef0123456789abcdef";
    REQUIRE(par_open_dir() && g_par_on && g_par_legacy_dir);
    // Upgrading an on-disk legacy catalogue: no startup-key plist exists.
    // A recipe from the old manifest should already have its batch in memory.
    fixture_seed_key = key; fixture_preopen = 1;
    rb_archive_preopen_start();
    REQUIRE(!dispatch_group_wait(rb_archive_jobs(), dispatch_time(DISPATCH_TIME_NOW, 10*NSEC_PER_SEC)));
    REQUIRE(atomic_load(&rb_preopened) == 1 && rb_archive_fetch(key, RB_LEGACY, YES));
    REQUIRE(!atomic_load(&rb_cold_submit));
    fixture_seed_key = nil;
    NSString *scopedA = g_par_dir;
    REQUIRE([g_par_legacy_have containsObject:key] && ![g_par_have containsObject:key]);
    REQUIRE(par_compute(fn, key, &error)); // actual GPU, fail-on-miss for the old file
    await_test_archive_writer();
    uint64_t stats[16]; rb_par_snapshot(stats);
    REQUIRE(stats[6] == 1 && !stats[7] && !stats[14]);
    REQUIRE([g_par_have containsObject:key]);
    check_index_bytes(legacyIndex, expectedIndex, "after legacy promotion");
    retire_drained_test_archive();
    REQUIRE(par_open_dir() && [g_par_dir isEqual:scopedA] && [g_par_have containsObject:key]);
    uint64_t before[16]; rb_par_snapshot(before);
    uint64_t writesBeforeReopen = atomic_load(&g_par_written), staleBeforeReopen = atomic_load(&g_par_stale);
    REQUIRE(par_compute(fn, key, &error));
    retire_drained_test_archive();
    rb_par_snapshot(stats);
    // A scoped batch rejected by Metal may be promoted again from the same
    // immutable legacy archive. Capture that outcome without assuming a hit
    // identifies which of the bundle, scoped and legacy probes succeeded.
    fprintf(stderr, "scoped reopen: demand_hits=%llu demand_misses=%llu compute_builds=%llu "
                    "keys_written=%llu rejected_scoped_pipelines=%llu\n",
            (unsigned long long)(stats[6]-before[6]), (unsigned long long)(stats[7]-before[7]),
            (unsigned long long)(stats[14]-before[14]),
            (unsigned long long)(atomic_load(&g_par_written)-writesBeforeReopen),
            (unsigned long long)(atomic_load(&g_par_stale)-staleBeforeReopen));
    check_index_bytes(legacyIndex, expectedIndex, "after scoped reopen");
    test_scope_build = "1123456789abcdef0123456789abcdef";
    REQUIRE(par_open_dir() && ![g_par_dir isEqual:scopedA] && ![g_par_have containsObject:key]);
    NSString *scopedB = g_par_dir;
    retire_drained_test_archive();
    REQUIRE(setenv("S2A_RB_DIRECT_GAME_ID", "04007EF01F8AE001", 1) == 0);
    REQUIRE(par_open_dir() && ![g_par_dir isEqual:scopedA] && ![g_par_dir isEqual:scopedB]);
    check_index_bytes(legacyIndex, expectedIndex, "after title/build isolation");
    REQUIRE([[NSFileManager defaultManager] fileExistsAtPath:[scopedA stringByAppendingPathComponent:@"batches.tsv"]]);
    printf("scoped archive strict legacy hit, promotion, reopen and title/build isolation passed\n");
}
#endif
// Exercise the real archive serializer's optional error parameter and file/index
// transaction with a protocol-shaped archive. No Metal GPU support is required.
@interface RBErrorNilArchive : NSObject { @public BOOL reject, saw_nil; unsigned calls; }
@end
@implementation RBErrorNilArchive
- (BOOL)serializeToURL:(NSURL *)url error:(NSError **)error {
    calls++; saw_nil=error==nil;
    if (reject) { if (error) *error=[NSError errorWithDomain:@"rb.fixture" code:7 userInfo:nil]; return NO; }
    return [@"fixture archive bytes" writeToURL:url atomically:NO encoding:NSUTF8StringEncoding error:error];
}
@end
static void test_error_nil(void) {
    NSString *dir=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    REQUIRE([NSFileManager.defaultManager createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:nil]);
    unsigned checks=0;
#define NIL_CHECK(expr) do { REQUIRE(expr); checks++; } while (0)
    g_rb_archive_batch32=0;
    for (int mode=0;mode<2;mode++) {
        atomic_store(&g_rb_archive_error_nil,mode);
        RBErrorNilArchive *archive=[RBErrorNilArchive new];
        NSString *key=[NSString stringWithFormat:@"key-%d",mode];
        NSString *path=[dir stringByAppendingPathComponent:[key stringByAppendingString:@".metalarch"]];
        BOOL refused=NO; NSError *error=nil;
        NIL_CHECK(par_serialize((id)archive,path,@[key],&refused,&error));
        NIL_CHECK(!refused); NIL_CHECK(archive->calls==1); NIL_CHECK(archive->saw_nil==(BOOL)mode);
        NIL_CHECK([NSFileManager.defaultManager fileExistsAtPath:path]);
        NIL_CHECK(![NSFileManager.defaultManager fileExistsAtPath:[path stringByAppendingString:@".tmp"]]);
        NSString *index=[NSString stringWithContentsOfFile:[dir stringByAppendingPathComponent:@"batches.tsv"] encoding:NSUTF8StringEncoding error:nil];
        NIL_CHECK([index containsString:key]);
        archive->reject=YES; error=nil;
        NSString *failed=[path stringByAppendingString:@"-refused"];
        NIL_CHECK(!par_serialize((id)archive,failed,@[[key stringByAppendingString:@"-refused"]],&refused,&error));
        NIL_CHECK(refused); NIL_CHECK(archive->calls==2); NIL_CHECK(archive->saw_nil==(BOOL)mode);
        NIL_CHECK(mode ? error==nil : error.code==7);
        NIL_CHECK(![NSFileManager.defaultManager fileExistsAtPath:failed]);
        NIL_CHECK(![NSFileManager.defaultManager fileExistsAtPath:[failed stringByAppendingString:@".tmp"]]);
        archive->reject=NO;
        NIL_CHECK(par_serialize((id)archive,failed,@[[key stringByAppendingString:@"-retry"]],&refused,&error));
        NIL_CHECK(!refused); NIL_CHECK(archive->calls==3);
    }
    REQUIRE([NSFileManager.defaultManager removeItemAtPath:dir error:nil]);
    printf("PASS real archive serializer transaction: %u checks, error capture on/off, refusal, cleanup, same-object retry, rename and index\n",checks);
#undef NIL_CHECK
}
int main(int argc, char **argv) { @autoreleasepool {
    if (argc==2 && !strcmp(argv[1],"--error-nil")) { test_error_nil(); return 0; }
    if (argc == 2 && !strcmp(argv[1], "--probe")) return MTLCreateSystemDefaultDevice() ? 0 : 77;
#ifndef RB_ARCHIVE_TEST_793_CONTROL
    if (argc == 5 && !strcmp(argv[1],"--live-render") &&
        (!strcmp(argv[4],"cold") || !strcmp(argv[4],"warm"))) {
        test_live_render_archive(argv[2],atoi(argv[3]),!strcmp(argv[4],"warm"));
        return 0;
    }
    if (argc == 3 && !strcmp(argv[1], "--scoped")) { test_scoped_archive(argv[2]); return 0; }
#endif
    if (argc == 4 && !strcmp(argv[1], "--relaunch") && (!strcmp(argv[3], "cold") || !strcmp(argv[3], "warm")))
        return rb_archive_relaunch(argv[2], !strcmp(argv[3], "warm"));
    if (argc == 5 && !strcmp(argv[1], "--held") && (!strcmp(argv[4], "write") || !strcmp(argv[4], "replay"))) {
        test_held_writer(argv[2], argv[3], !strcmp(argv[4], "replay"));
        return 0;
    }
    if (argc == 4 && !strcmp(argv[1], "--mid-batch")) { test_mid_batch(argv[2], argv[3]); return 0; }
    fprintf(stderr, "Unexpected arguments\n");
    return 2;
} }
