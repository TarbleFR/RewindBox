// Portable driver for the producer and worker extracted from nvn_rec.h.
// Apple scheduling, autorelease and the Metal command body are host substitutes.
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MDIE(...) do { fprintf(stderr, __VA_ARGS__); abort(); } while (0)
#define S2A_REC_PUT_HOOK(op) ((void)0)
#define RB_WAKE_CALL(tag, seconds, call) (call)
#define pthread_setname_np(name) ((void)0)
#define s2a_qos_set_self(class_) ((void)0)
#define rb_rt_start(who) ((void)0)
#define rb_rt_tick(who, stamp) ((void)(stamp))
#define thr_lv_take(counts) ((void)(counts))
#define thr_lv_add(who, a, b) ((void)0)

static uint64_t now_ns(void) {
    struct timespec ts;
    assert(clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
    return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}
static uint64_t t_rb_blk[2];
static void geo_run_flush(void) {} // tests drive the real rec_lane_splice explicitly

/* INSERT_TYPES */

enum { REF_COUNT = 20000 };
static _Atomic int refs[REF_COUNT];
static pthread_mutex_t gate_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_cv = PTHREAD_COND_INITIALIZER;
static uint64_t pause_at;
static int entered, release_worker;
static uint64_t executed, first_exec, encode_checksum, submit_checksum;
static int check, producer_work, consumer_work;

static uint64_t cpu_work(uint64_t value, int iterations) {
    for (int i = 0; i < iterations; i++)
        value = (value ^ (value >> 13)) * 6364136223846793005ull + 1;
    return value;
}
static void rec_exec(const rec_t *record) {
    if (!check) {
        if (record->op == 1) first_exec = now_ns();
        encode_checksum ^= cpu_work(record->a[1], consumer_work);
        return;
    }
    uint64_t seq = ++executed;
    assert(record->op == 10 && record->nobj == 1 && record->a[1] == seq);
    assert(record->a[0] == (uintptr_t)&refs[seq]);
    for (int i = 2; i < 15; i++) assert(record->a[i] == seq * 23 + (unsigned)i);
    if (seq == pause_at) {
        pthread_mutex_lock(&gate_mu);
        entered = 1;
        pthread_cond_broadcast(&gate_cv);
        while (!release_worker) pthread_cond_wait(&gate_cv, &gate_mu);
        pthread_mutex_unlock(&gate_mu);
    }
    assert(atomic_fetch_sub(&refs[seq], 1) == 1);
}

/* INSERT_QUEUE */

static void put_checked(uint64_t seq) {
    assert(seq < REF_COUNT);
    rec_t *record = rec_put(10, 1);
    assert(atomic_exchange(&refs[seq], 1) == 0);
    record->a[0] = (uintptr_t)&refs[seq];
    record->a[1] = seq;
    for (int i = 2; i < 15; i++) record->a[i] = seq * 23 + (unsigned)i;
}
static void ack(uint64_t last) {
    rec_drain();
    assert(executed == last);
    for (uint64_t i = 1; i <= last; i++) assert(atomic_load(&refs[i]) == 0);
}
static void park_next(uint64_t seq) {
    pthread_mutex_lock(&gate_mu);
    pause_at = seq;
    entered = release_worker = 0;
    pthread_mutex_unlock(&gate_mu);
}
static void wait_parked(void) {
    pthread_mutex_lock(&gate_mu);
    while (!entered) pthread_cond_wait(&gate_cv, &gate_mu);
    pthread_mutex_unlock(&gate_mu);
}
static void release_gate(void) {
    pthread_mutex_lock(&gate_mu);
    release_worker = 1;
    pthread_cond_signal(&gate_cv);
    pthread_mutex_unlock(&gate_mu);
}
static void stage_session_reset(void) {
    // The host coordinator excludes producers and drains the worker first.
    // INSERT_SESSION
}
static void test(int early, int patched) {
    uint64_t emit = 0;
    int threshold = early ? 64 : 256;
    check = 1;
    rec_drain();
    // Even the last reservation in this block is private until its caller
    // finishes writing. Inspect the queue mutex before filling those fields.
    for (int i = 1; i < threshold; i++) put_checked(++emit);
    rec_t *r = rec_put(10, 1);
    pthread_mutex_lock(&g_rb_mu);
    assert(!g_rb_head && !g_rb_busy && g_rb_cur && g_rb_cur->n == threshold);
    pthread_mutex_unlock(&g_rb_mu);
    emit++;
    assert(atomic_exchange(&refs[emit], 1) == 0);
    r->a[0] = (uintptr_t)&refs[emit];
    r->a[1] = emit;
    for (int i = 2; i < 15; i++) r->a[i] = emit * 23 + (unsigned)i;
    park_next(1);
    put_checked(++emit);
    assert(g_rb_cur && g_rb_cur->n == 1);
    wait_parked();
    assert(atomic_load(&refs[emit]) == 1 && g_rb_cur->n == 1);
    // Handover returns while the worker is held. Later main blocks use 256.
    rec_handover();
    for (int i = 0; i < 256; i++) put_checked(++emit);
    assert(g_rb_cur && g_rb_cur->n == 256);
    release_gate();
    ack(emit);
    const int sizes[] = {0,1,63,64,65,255,256,257,319,320,321,512,1024};
    for (unsigned k = 0; k < sizeof sizes / sizeof sizes[0]; k++) {
        for (int i = 0; i < sizes[k]; i++) put_checked(++emit);
        if (sizes[k]) {
            int count = sizes[k] <= threshold ? sizes[k] : 1 + (sizes[k] - threshold - 1) % 256;
            assert(g_rb_cur && g_rb_cur->n == count);
        }
        ack(emit);
    }
    // Geometry lanes keep their private records, including across an in-lane
    // drain, then splice behind the main lane in lane 1 / lane 2 order.
    enum { LANES = 270 };
    for (int i = 1; i <= LANES; i++) {
        rec_lane(2); put_checked(emit + 2 * LANES + i);
        rec_lane(1); put_checked(emit + LANES + i);
        rec_lane(0); put_checked(emit + i);
    }
    rec_lane(1); rec_drain(); assert(g_rlane == 1 && executed == emit + LANES);
    assert(atomic_load(&refs[emit + LANES + 1]) == 1);
    rec_lane(0); rec_lane_splice();
    emit += 3 * LANES;
    ack(emit);
    // A lane-only splice can occupy an idle worker before a new main block
    // opens. The main block must stay full-sized even with the option on.
    park_next(emit + 1);
    rec_lane(1); put_checked(++emit); rec_lane(0); rec_lane_splice();
    wait_parked();
    for (int i = 0; i < 21 * 256; i++) put_checked(++emit);
    assert(g_rb_cur && g_rb_cur->n == 256);
    pthread_mutex_lock(&g_rb_mu);
    int queued = 0;
    for (rec_blk *b = g_rb_head; b; b = b->next) { assert(b->n == 256); queued++; }
    assert(queued == 20 && g_rb_busy);
    pthread_mutex_unlock(&g_rb_mu);
    release_gate();
    ack(emit);
    stage_session_reset();
    // The worker persists. Verify a second session can read its own setting.
    assert(setenv("S2A_RB_REC_EARLY", early ? "0" : "1", 1) == 0);
    for (int i = 0; i < 65; i++) put_checked(++emit);
    assert(g_rb_cur && g_rb_cur->n == (!early && patched ? 1 : 65));
    ack(emit);
    printf("checked %llu records\n", (unsigned long long)executed);
}
static void bench(int frames, int records) {
    for (int f = -6; f < frames; f++) {
        uint64_t before = now_ns();
        for (int i = 0; i < records; i++) {
            rec_t *r = rec_put(i == 0, 0);
            r->a[1] = cpu_work(((unsigned)f * 997ull) + i, producer_work);
            submit_checksum ^= r->a[1];
        }
        uint64_t end_put = now_ns();
        rec_drain();
        uint64_t end = now_ns();
        if (f >= 0) printf("%d,%llu,%llu,%llu\n", f, (unsigned long long)(end - before),
                          (unsigned long long)(end - end_put), (unsigned long long)(first_exec - before));
    }
    fprintf(stderr, "checksum %llu %llu\n", (unsigned long long)submit_checksum, (unsigned long long)encode_checksum);
}
int main(int argc, char **argv) {
    if (argc == 4 && !strcmp(argv[1], "test")) test(atoi(argv[2]), atoi(argv[3]));
    else if (argc == 6 && !strcmp(argv[1], "bench")) {
        producer_work = atoi(argv[4]); consumer_work = atoi(argv[5]);
        bench(atoi(argv[2]), atoi(argv[3]));
    } else return 2;
    return 0;
}
