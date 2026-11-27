/* Used by queue_bench.py, which inserts audited engine code at both source markers. */
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "nvn.h"

#define NVN(name, ret, ...) static ret name(__VA_ARGS__)
#define NVN_NOPROTO NVN
#define RB_SUBMIT 1
#define DM_BLOCK_BEGIN() block_hook(__func__)
#define DM_BLOCK_END() ((void)0)
#define LOG(...) ((void)0)
static pthread_mutex_t g_susp_mu = PTHREAD_MUTEX_INITIALIZER;
static int g_inflight_api;
static _Atomic unsigned rb_replay_pending;
static _Atomic int rb_replay_shadow_pressure;
static _Thread_local int rb_replay_worker_thread;
typedef struct { int held; } rb_replay_guard;
typedef struct { NVNwindowOriginMode origin; } dev_t_;
static dev_t_ device;
static NVNqueue queue;
static int dm_host_work;
static _Atomic int open_gate = 1, entered, joins, saturated, finished, frec, stopping;
static _Atomic int refuse_thread;
static long delay;
static uint64_t trace[512];
static size_t trace_count;
static uint64_t now_ns(void) {
    struct timespec t;
    assert(clock_gettime(CLOCK_MONOTONIC, &t) == 0);
    return (uint64_t)t.tv_sec * 1000000000 + (uint64_t)t.tv_nsec;
}
static void pause_ns(long ns) {
    struct timespec t = {0, ns};
    while (nanosleep(&t, &t) != 0) {}
}
static void await(_Atomic int *event, int target) {
    uint64_t limit = now_ns() + 3000000000ull;
    while (atomic_load(event) < target) { assert(now_ns() < limit); pause_ns(100000); }
}
static int rb_lf_switch(int phase) { (void)phase; return -1; }
static void gfx_enter(void) {
    pthread_mutex_lock(&g_susp_mu); g_inflight_api++; pthread_mutex_unlock(&g_susp_mu);
}
static void gfx_leave(void) {
    pthread_mutex_lock(&g_susp_mu); assert(g_inflight_api > 0); g_inflight_api--; pthread_mutex_unlock(&g_susp_mu);
}
int nvn_rb_thermal_scope(void) { return 1; }
static int nvn_frec_on(void) { return frec; }
static int dm_gfx_session_stopping(void) { return stopping; }
static void rb_submit_replay(NVNqueue *q, int n, const NVNcommandHandle *h) {
    assert(q == &queue && n > 0);
    atomic_fetch_add(&entered, 1);
    await(&open_gate, 1);
    if (delay) pause_ns(delay);
    assert(trace_count < sizeof(trace) / sizeof(trace[0]));
    trace[trace_count++] = h[0];
    device.origin = NVN_WINDOW_ORIGIN_MODE_UPPER_LEFT;
}
static void block_hook(const char *fn);
static int make_thread(pthread_t *id, const pthread_attr_t *attr, void *(*fn)(void *), void *arg) {
    return refuse_thread ? EAGAIN : pthread_create(id, attr, fn, arg);
}
#define pthread_create make_thread
/* SOURCE_WORKER */
#undef pthread_create
/* SOURCE_QUERIES */
static void block_hook(const char *fn) {
    if (!strcmp(fn, "rb_replay_join") && rb_replay_done < rb_replay_sent) atomic_fetch_add(&joins, 1);
    if (!strcmp(fn, "rb_replay_enqueue") && rb_replay_count == RB_REPLAY_JOBS) atomic_fetch_add(&saturated, 1);
}
static void submit(uint64_t id) {
    NVNcommandHandle h = id;
    nvnQueueSubmitCommands(&queue, 1, &h);
}
static void check_queries(uint64_t u) {
    const NVNdevice *d = NULL; /* all seven take d by value and never dereference it */
    int t = (int)(uint32_t)u, s = INT_MIN;
    assert(nvnDeviceGetImageHandle(d, t) == (uint64_t)t);
    assert(nvnDeviceGetSeparateTextureHandle(d, t).value == (uint64_t)t);
    assert(nvnDeviceGetSeparateSamplerHandle(d, s).value == (uint64_t)s << 20);
    assert(nvnDeviceGetTextureHandle(d, t, s) == ((uint64_t)(uint32_t)t | (uint64_t)(uint32_t)s << 20));
    assert(nvnDeviceGetTexelFetchHandle(d, t) == (uint32_t)t);
    assert(nvnDeviceGetCommandHandleMemorySize(d, u) == ((u & 3) == 2 ? (u >> 38) & 0x3fffffc : 0));
    assert(nvnDeviceGetUniformBufferHandle(d, u, u >> 8) ==
           (((0x1e0000000000ull + ((u >> 8) << 41)) & 0xffffe00000000000ull) | (u >> 4)));
}
static void *queries(void *unused) {
    (void)unused;
    uint64_t values[] = {0, 1, UINT64_MAX, UINT64_MAX - 1, INT32_MAX, UINT32_MAX, UINT64_C(1) << 63};
    for (size_t i = 0; i < sizeof(values)/sizeof(values[0]); i++) check_queries(values[i]);
    atomic_fetch_add(&finished, 1); return NULL;
}
static void *dependent(void *unused) {
    (void)unused;
    assert(nvnDeviceGetWindowOriginMode((NVNdevice *)&device) == NVN_WINDOW_ORIGIN_MODE_UPPER_LEFT);
    atomic_fetch_add(&finished, 1); return NULL;
}
static void *tenth(void *unused) { (void)unused; submit(10); atomic_fetch_add(&finished, 1); return NULL; }
static void *oversized(void *unused) {
    (void)unused; NVNcommandHandle h[257] = {11};
    nvnQueueSubmitCommands(&queue, 257, h); atomic_fetch_add(&finished, 1); return NULL;
}
static void clean(int n) {
    rb_replay_stop();
    assert(!g_inflight_api && !rb_replay_pending && !rb_replay_count && rb_replay_sent == rb_replay_done);
    assert(trace_count == (size_t)n);
    for (int i = 0; i < n; i++) assert(trace[i] == (uint64_t)i + 1);
}
static void gated(int fast) {
    pthread_t q, d, t, f;
    rb_replay_begin(); open_gate = 0;
    submit(1); await(&entered, 1);
    for (int i = 2; i <= 9; i++) submit(i);
    assert(rb_replay_pending == 9);
    assert(!pthread_create(&q, NULL, queries, NULL));
    if (fast) await(&finished, 1); else await(&joins, 1);
    assert(finished == fast);
    assert(!pthread_create(&d, NULL, dependent, NULL));
    if (fast) await(&joins, 1);
    assert(finished == fast);
    open_gate = 1; assert(!pthread_join(q, NULL)); assert(!pthread_join(d, NULL));
    clean(9);

    rb_replay_begin(); trace_count = 0; entered = 0; finished = 0; joins = 0; open_gate = 0;
    submit(1); await(&entered, 1);
    for (int i = 2; i <= 9; i++) submit(i);
    assert(!pthread_create(&t, NULL, tenth, NULL)); await(&saturated, 1);
    assert(!finished && rb_replay_pending == 9);
    assert(!pthread_create(&f, NULL, oversized, NULL));
    open_gate = 1;
    assert(!pthread_join(t, NULL)); assert(!pthread_join(f, NULL));
    assert(finished == 2 && rb_replay_sent == 10);
    clean(11); /* more than 256 handle arguments use ordered synchronous replay */
}
static void *stop_session(void *unused) { (void)unused; rb_replay_stop(); atomic_fetch_add(&finished, 1); return NULL; }
static void stop_in_flight(void) {
    rb_replay_begin(); trace_count = 0; entered = 0; finished = 0; open_gate = 0;
    submit(1); await(&entered, 1);
    for (int i = 2; i <= 9; i++) submit(i);
    pthread_t stop;
    assert(!pthread_create(&stop, NULL, stop_session, NULL));
    pthread_mutex_lock(&rb_replay_mu);
    while (!rb_replay_closed) pthread_cond_wait(&rb_replay_cv, &rb_replay_mu);
    pthread_mutex_unlock(&rb_replay_mu);
    assert(!finished && rb_replay_pending == 9);
    open_gate = 1; assert(!pthread_join(stop, NULL)); assert(finished == 1);
    clean(9);
}
static void fallback(void) {
    rb_replay_begin(); trace_count = 0; frec = 1;
    submit(1); assert(rb_replay_sent == 0 && !rb_replay_active);
    frec = 0; stopping = 1; submit(999); stopping = 0;
    clean(1);
}
static int compare_u64(const void *lhs, const void *rhs) {
    uint64_t a = *(const uint64_t *)lhs, b = *(const uint64_t *)rhs;
    return (a > b) - (a < b);
}
static void measure(void) {
    enum { N = 80 };
    uint64_t samples[N];
    delay = 1000000; rb_replay_begin();
    uint64_t start = now_ns();
    for (int i = 0; i < N; i++) {
        submit((uint64_t)i + 1);
        uint64_t t = now_ns(); check_queries((uint64_t)i); samples[i] = now_ns() - t;
        pause_ns(1000000); /* deterministic independent guest preparation stand-in */
    }
    clean(N);
    uint64_t elapsed = now_ns() - start, hash = 0;
    for (int i = 0; i < N; i++) hash = hash * 31 + trace[i];
    qsort(samples, N, sizeof(samples[0]), compare_u64);
    printf("%d,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%016" PRIx64 "\n",
           N, elapsed, rb_replay_wait_ns, samples[39], samples[75], samples[79], hash);
}
int main(int argc, char **argv) {
    assert(argc == 3);
    int fast = !strcmp(argv[1], "1");
    int enabled = strcmp(argv[1], "off") != 0;
    assert(!setenv("S2A_RB_REPLAY_WORKER", enabled ? "1" : "0", 1));
    if (!strcmp(argv[1], "absent")) assert(!unsetenv("S2A_RB_REPLAY_SCALAR_QUERIES"));
    else assert(!setenv("S2A_RB_REPLAY_SCALAR_QUERIES", enabled ? argv[1] : "1", 1));
    if (!strcmp(argv[2], "measure")) { measure(); return 0; }
    if (enabled) gated(fast);
    else {
        rb_replay_begin(); submit(1); assert(!rb_replay_active && !rb_replay_pending && !rb_replay_sent);
        queries(NULL); clean(1);
    }
    if (enabled) {
        stop_in_flight();
        rb_replay_begin(); trace_count = 0; refuse_thread = 1;
        submit(1); submit(2);
        assert(rb_replay_failed && !rb_replay_active && !rb_replay_sent);
        clean(2); refuse_thread = 0;
    }
    fallback();
    printf("PASS mode=%s\n", argv[1]);
}
