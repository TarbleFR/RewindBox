// SPDX-License-Identifier: Apache-2.0
// Portable test and cost decomposition; excludes all Apple/Metal/driver logging costs.
#define _POSIX_C_SOURCE 200809L
#include "rb_parallel_trace.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static rb_pt_gate gate;
static _Atomic unsigned successful;
static volatile unsigned long long sink;
static uint64_t stamp(clockid_t id) {
    struct timespec ts;
    if (clock_gettime(id, &ts)) abort();
    return (uint64_t)ts.tv_sec * 1000000000 + (uint64_t)ts.tv_nsec;
}
static void *flood(void *unused) {
    (void)unused;
    for (unsigned i = 0; i < 9000; i++)
        if (rb_pt_claim(&gate, 7, 1200, &gate.cb, RB_PT_CB_CAP)) atomic_fetch_add(&successful, 1);
    return NULL;
}
static void verify(void) {
    rb_pt_configure(&gate, 7, 601);
    assert(!rb_pt_claim(&gate, 7, 600, &gate.cb, RB_PT_CB_CAP));
    assert(!rb_pt_claim(&gate, 7, 1201, &gate.cb, RB_PT_CB_CAP));
    assert(rb_pt_claim(&gate, 7, 601, &gate.present, RB_PT_PRESENT_CAP) == 7);
    pthread_t threads[6];
    for (unsigned i=0; i<6; i++) assert(!pthread_create(&threads[i], NULL, flood, NULL));
    for (unsigned i=0; i<6; i++) assert(!pthread_join(threads[i], NULL));
    assert(atomic_load(&successful) == RB_PT_CB_CAP);
    assert(rb_pt_close(&gate.cb) == RB_PT_CB_CAP + 1);
    assert(!rb_pt_claim(&gate, 7, 601, &gate.cb, RB_PT_CB_CAP));
    assert(rb_pt_close(&gate.present) == 1);
    rb_pt_configure(&gate, 8, 0);
    assert(!rb_pt_claim(&gate, 7, 0, &gate.cb, RB_PT_CB_CAP));
    assert(rb_pt_claim(&gate, 8, 0, &gate.cb, RB_PT_CB_CAP) == 8);
    assert(rb_pt_close(&gate.cb) == 1);
    assert(!rb_pt_claim(&gate, 8, 0, &gate.cb, RB_PT_CB_CAP));
    assert(!rb_pt_has_gpu(10, 0, 0));
    assert(!rb_pt_has_gpu(10, 9, 11));
    assert(!rb_pt_has_gpu(10, 10, 10));
    assert(!rb_pt_has_gpu(10, 10, INFINITY));
    assert(!rb_pt_has_gpu(10, NAN, 12));
    assert(rb_pt_has_gpu(10, 10, 11));
    rb_pt_configure(&gate, 0, 0);
    assert(atomic_load(&gate.session) == 0);
}
static void run(int mode, unsigned n, unsigned repeat) {
    // Batches fit a single production cap. Resets occur outside each measured interval.
    uint64_t elapsed = 0;
    for (unsigned counted=0; counted<n;) {
        unsigned batch = n-counted > RB_PT_CB_CAP ? RB_PT_CB_CAP : n-counted;
        rb_pt_configure(&gate, mode>=2 ? 9 : 0, 0);
        uint64_t t = stamp(CLOCK_MONOTONIC);
        unsigned long long sum = 0;
        for (unsigned i=0; i<batch; i++) {
            // All modes retain the same loop and compiler barrier.
            __asm__ volatile("" : : "r"(i) : "memory");
            if (mode == 0) continue;
            uint64_t sess = atomic_load_explicit(&gate.session, memory_order_acquire);
            if (!sess || !rb_pt_claim(&gate, sess, 0, &gate.cb, RB_PT_CB_CAP)) continue;
            if (mode == 2) { sum += sess; continue; }
            uint64_t c0=stamp(CLOCK_THREAD_CPUTIME_ID), w0=stamp(CLOCK_MONOTONIC);
            uint64_t w1=stamp(CLOCK_MONOTONIC), c1=stamp(CLOCK_THREAD_CPUTIME_ID);
            sum += w1-w0 + c1-c0;
            if (mode == 4) {
                char line[512];
                int len=snprintf(line,sizeof line,
                    "[rb-parallel] v=1 session=%llu frame=%u event=cb sub=%u cb=%u seg=0 metal=4 reason=submission prep_start_s=%.9f prep_end_s=%.9f status=ok prep_thread_ns=%llu gpu_start_s=%.9f gpu_end_s=%.9f",
                    (unsigned long long)sess,0u,i,i,w0/1e9,w1/1e9,(unsigned long long)(c1-c0),w1/1e9,(w1+10)/1e9);
                sum += (unsigned)len + (unsigned)line[10];
            }
        }
        elapsed += stamp(CLOCK_MONOTONIC)-t;
        sink += sum;
        counted += batch;
    }
    printf("%u,%s,%u,%.3f\n",repeat, (const char*[]){"baseline","off_guard","claim","four_clocks","format_proxy"}[mode],
           n, (double)elapsed / n);
}
int main(void) {
    verify();
    puts("repeat,stage,iterations,ns_per_synthetic_cb");
    for (unsigned r=0; r<9; r++)
        for (int i=0; i<5; i++) {
            int mode=(int)((r+(unsigned)i)%5);
            run(mode,mode<3 ? 2000000 : 100000, r+1);
        }
    return 0;
}
