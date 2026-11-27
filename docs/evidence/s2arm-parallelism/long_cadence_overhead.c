// SPDX-License-Identifier: Apache-2.0
#define _POSIX_C_SOURCE 200809L
#include "rb_long_cadence.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <time.h>

enum { EVENTS=200000, PAIRS=9 };
static rb30_data live;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static _Atomic uint64_t generation;
static uint64_t now_ns(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
static void event(void) {
    if (!atomic_load_explicit(&generation,memory_order_relaxed)) return;
    pthread_mutex_lock(&lock); rb30_observe(&live,now_ns()); pthread_mutex_unlock(&lock);
}
int main(void) {
    puts("pair,enabled,events,ns_per_call");
    for (int pair=0;pair<=PAIRS;++pair) for (int j=0;j<2;++j) {
        unsigned enabled=(unsigned)(pair+j)%2;
        memset(&live,0,sizeof live); live.start=now_ns(); atomic_store(&generation,enabled);
        uint64_t start=now_ns();
        for (int i=0;i<EVENTS;++i) event();
        uint64_t elapsed=now_ns()-start;
        if (enabled && live.minute[0].count+live.clock_errors!=EVENTS) return 1;
        if (pair) printf("%d,%u,%d,%.3f\n",pair,enabled,EVENTS,(double)elapsed/EVENTS);
    }
    return 0;
}
