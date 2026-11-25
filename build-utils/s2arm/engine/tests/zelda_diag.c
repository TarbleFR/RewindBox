// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 S2Arm contributors
#define _POSIX_C_SOURCE 200809L
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rb_allocator_frame.h"
#include "rb_dispatch_order.h"
#include "rb_gpu_facts.h"
#include "rb_guest_early.h"
#include "rb_raster_clear.h"
#include "rb_probe_policy.h"
#include "rb_wait_latency.inc"
#include "rb_wake.inc"
#define RB_FENCE_DIAG(kind, ns, call) RB_WAKE_CALL(kind, ns, call)
#include "rb_fence_wait.h"
static unsigned checks;
#define CHECK(c) do { ++checks; if (!(c)) { fprintf(stderr,"FAIL line %u: %s\n",__LINE__,#c); exit(1); } } while (0)
static void *counts_worker(void *arg) {
    (void)arg;
    for (unsigned i=0;i<1000;i++) {
        // One shared static call site, registered concurrently by four workers.
        int result=RB_WAKE_CALL("fixture.concurrent", -1, 17);
        if (result!=17) abort();
    }
    return NULL;
}
static pthread_mutex_t mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv=PTHREAD_COND_INITIALIZER;
static int entered, go;
static void *condition_worker(void *arg) {
    (void)arg; pthread_mutex_lock(&mu);
    entered=1; pthread_cond_broadcast(&cv);
    while (!go) RB_WAKE_CALL("fixture.condition", -1, pthread_cond_wait(&cv,&mu));
    pthread_mutex_unlock(&mu); return NULL;
}
static unsigned report_lines;
static void emit(const char *s) { CHECK(strncmp(s,"[rb-wake",8)==0); report_lines++; }
int main(void) {
    s2a_rb_wait_latency_reset(); rb_latency_add(0,50000); rb_latency_add(0,1000001);
    CHECK(atomic_load(&rb_latency_count[0])==2 && atomic_load(&rb_latency_sum[0])==1050001);
    CHECK(atomic_load(&rb_latency_bins[0][1])==1 && atomic_load(&rb_latency_bins[0][5])==1);
    CHECK(atomic_load(&rb_latency_max[0])==1000001);
    s2a_rb_wait_latency_reset(); CHECK(!atomic_load(&rb_latency_count[0]));
    uint8_t ctl[0x5c]={0}; uint32_t magic=0x98761234u,version=0xc9u;
    memcpy(ctl,&magic,4); memcpy(ctl+4,&version,4);
    CHECK(rb_guest_early_nvn2(ctl,sizeof ctl)==1);
    ctl[0x5b]=1; CHECK(rb_guest_early_nvn2(ctl,sizeof ctl)==2);
    CHECK(!rb_guest_early_nvn2(ctl,0x5b)); ctl[4]=0; CHECK(!rb_guest_early_nvn2(ctl,sizeof ctl));
    struct { op_hdr h; p_depth_range v; op_hdr clear; p_clear_color c; op_hdr end; } stream={
        .h={OP_DEPTH_RANGE,8+sizeof(p_depth_range)},.clear={OP_CLEAR_COLOR,8+sizeof(p_clear_color)},.end={OP_END,8}};
    CHECK(rb_raster_then_clear((const uint8_t *)&stream)==(const uint8_t *)&stream.clear);
    stream.h.op=OP_WAIT_SYNC; CHECK(!rb_raster_then_clear((const uint8_t *)&stream));
    stream.h.op=OP_SCISSOR; CHECK(!rb_raster_then_clear((const uint8_t *)&stream));
    stream.h.op=OP_DEPTH_RANGE; stream.h.size=8; CHECK(!rb_raster_then_clear((const uint8_t *)&stream));

    CHECK(!rb_allocator_frame_reuse(0,4,4,0,3));
    CHECK(!rb_allocator_frame_reuse(1,4,3,0,3));
    CHECK(!rb_allocator_frame_reuse(1,4,4,-1,3));
    CHECK(!rb_allocator_frame_reuse(1,4,4,3,3));
    CHECK(!rb_allocator_frame_reuse(1,UINT64_MAX,UINT64_MAX,0,3));
    for (int slot=0;slot<8;slot++) CHECK(rb_allocator_frame_reuse(1,42,42,slot,8));
    CHECK(rb_probe_every_parse(NULL)==-1); CHECK(rb_probe_every_parse("0")==0);
    CHECK(rb_probe_every_parse("30")==30); CHECK(rb_probe_every_parse("30x")==-1);
    CHECK(rb_probe_every_parse("-1")==-1); CHECK(rb_probe_every_parse("999999999999999999999")==-1);
    unsigned samples=0;
    for (uint64_t frame=1;frame<=180;frame++) if (rb_probe_due(30,frame,frame-1)) samples++;
    CHECK(samples==6); CHECK(!rb_probe_due(30,60,60)); CHECK(!rb_probe_due(0,60,59));
    CHECK(!rb_probe_due(-1,60,59)); CHECK(!rb_probe_due(30,UINT64_MAX,0));
    CHECK(!rb_dispatch_game(NULL)); CHECK(!rb_dispatch_game("full")); CHECK(rb_dispatch_game("game"));
    CHECK(!rb_dispatch_needs_barrier(1,1,0)); CHECK(rb_dispatch_needs_barrier(0,1,0));
    CHECK(rb_dispatch_needs_barrier(1,0,0));
    for (unsigned bits=1;bits<256;bits++) CHECK(rb_dispatch_needs_barrier(1,1,bits));
    CHECK(rb_dispatch_needs_barrier(1,1,0x80000000u));
    CHECK(rb_gpu_msl_facts(NULL)==0);
    CHECK(rb_gpu_msl_facts("// discard_fragment();\n/* [[early_fragment_tests]] */ \"atomic_fetch_or_explicit\"")==0);
    CHECK(rb_gpu_msl_facts("discard_fragment_other(); sample_masked depth_value;")==0);
    CHECK(rb_gpu_msl_facts("[[early_fragment_tests]] fragment float4 main0() { discard_fragment(); }")==(RB_MSL_EARLY|RB_MSL_DISCARD));
    CHECK(rb_gpu_msl_facts("float d [[depth (any)]]; uint m [[sample_mask]]; atomic_fetch_or_explicit(a,b,c);")==(RB_MSL_DEPTH|RB_MSL_SMASK|RB_MSL_POOL_ATOMIC));
    CHECK(rb_gpu_early_missing(2,1,0)); CHECK(!rb_gpu_early_missing(2,1,RB_MSL_EARLY));
    CHECK(!rb_gpu_early_missing(0,1,0)); CHECK(!rb_gpu_early_missing(1,1,0)); CHECK(!rb_gpu_early_missing(2,0,0));
    s2a_rb_wake_configure(0); int evaluated=0;
    CHECK(RB_WAKE_CALL("fixture.off", (++evaluated,1), 23)==23); CHECK(evaluated==0); CHECK(rb_wake_count==0);
    s2a_rb_wake_configure(1);
    pthread_t workers[4];
    for (int i=0;i<4;i++) CHECK(pthread_create(&workers[i],NULL,counts_worker,NULL)==0);
    for (int i=0;i<4;i++) CHECK(pthread_join(workers[i],NULL)==0);
    CHECK(rb_wake_count==1); CHECK(atomic_load(&rb_wake_rows[0].waits)==4000);
    CHECK(atomic_load(&rb_wake_rows[0].resumes)==4000); CHECK(atomic_load(&rb_wake_rows[0].errors)==4000);
    CHECK(pthread_create(&workers[0],NULL,condition_worker,NULL)==0);
    pthread_mutex_lock(&mu); while (!entered) pthread_cond_wait(&cv,&mu);
    go=1; CHECK(RB_WAKE_SIGNAL_CALL("fixture.signal",pthread_cond_broadcast(&cv))==0);
    pthread_mutex_unlock(&mu); CHECK(pthread_join(workers[0],NULL)==0);
    CHECK(rb_wake_count==3); CHECK(atomic_load(&rb_wake_rows[1].waits)>=1);
    CHECK(atomic_load(&rb_wake_rows[1].resumes)==atomic_load(&rb_wake_rows[1].waits));
    CHECK(atomic_load(&rb_wake_rows[2].signals)==1); CHECK(atomic_load(&rb_wake_rows[2].resumes)==0);
    struct timespec past={0}; pthread_mutex_lock(&mu);
    CHECK(RB_WAKE_CALL("fixture.timeout",1000,pthread_cond_timedwait(&cv,&mu,&past))==ETIMEDOUT);
    pthread_mutex_unlock(&mu); CHECK(atomic_load(&rb_wake_rows[3].timeouts)==1);
    CHECK(atomic_load(&rb_wake_rows[3].short_waits)==1);
    static s2a_rb_wake_site site={__FILE__,"fixture.stale",__LINE__,0};
    s2a_rb_wake_token token=s2a_rb_wake_begin(&site,-1);
    s2a_rb_wake_configure(1); s2a_rb_wake_end(token,0);
    CHECK(atomic_load(&rb_wake_rows[token.slot-1].resumes)==0);
    for (unsigned i=0;i<rb_wake_count;i++) CHECK(atomic_load(&rb_wake_rows[i].waits)==0);
    token=s2a_rb_wake_begin(&site,-1); s2a_rb_wake_end(token,0);
    s2a_rb_wake_report(300,emit); CHECK(report_lines==2);
    // A kqueue event count of one is success, not an errno. EINTR remains a
    // native -1 return and errno, without being reported as a failed condition.
    unsigned syscall_site=rb_wake_count;
    errno=EINTR; CHECK(RB_WAKE_SYSCALL("fixture.syscall",1,-1)==-1); CHECK(errno==EINTR);
    CHECK(atomic_load(&rb_wake_rows[syscall_site].errors)==0);
    syscall_site=rb_wake_count;
    CHECK(RB_WAKE_SYSCALL("fixture.event-count",1,1)==1);
    CHECK(atomic_load(&rb_wake_rows[syscall_site].errors)==0);
    // Exercise the actual production fence helper with its predicate mutex held.
    unsigned before_sites=rb_wake_count;
    rb_fence_waiters fences={.changed=PTHREAD_COND_INITIALIZER};
    pthread_mutex_lock(&mu);
    CHECK(rb_fence_sleep_locked(&fences,&mu,7,&past)==ETIMEDOUT);
    CHECK(fences.sleeping==0); CHECK(fences.sleeps==1); CHECK(rb_wake_count==before_sites+1);
    CHECK(atomic_load(&rb_wake_rows[before_sites].timeouts)==1);
    fences.sleeping=1; fences.earliest=7;
    rb_fence_advanced_locked(&fences,6); CHECK(fences.broadcasts==0);
    rb_fence_advanced_locked(&fences,7); CHECK(fences.broadcasts==1);
    CHECK(fences.earliest==UINT64_MAX); CHECK(rb_wake_count==before_sites+2);
    CHECK(atomic_load(&rb_wake_rows[before_sites+1].signals)==1);
    pthread_mutex_unlock(&mu); pthread_cond_destroy(&fences.changed);
    s2a_rb_wake_configure(0); report_lines=0; s2a_rb_wake_report(301,emit); CHECK(report_lines==0);
    printf("PASS Zelda diagnostic policies and real pthread accounting: %u assertions; four concurrent publishers, condition signal, timeout, disabled fast path and session epoch\n",checks);
    return 0;
}
