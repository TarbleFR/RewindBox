// SPDX-License-Identifier: Apache-2.0
// Synthetic, manual A/B for the optional-work governor. No game data.
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <inttypes.h>

static _Atomic unsigned notification_calls;
static _Atomic unsigned idle_wait_returns;
static _Atomic int measure_idle_wake;
static int diag(const char *kind, int result) {
    if (!strcmp(kind, "spec.signal")) atomic_fetch_add(&notification_calls, 1);
    if (!strcmp(kind, "spec.timed") && !result && atomic_load(&measure_idle_wake))
        atomic_fetch_add(&idle_wait_returns, 1);
    return result;
}
#define RB_SPEC_DIAG(kind,ns,call) diag(kind,call)
#include "rb_spec_gate.h"
#include "rb_energy_guard.h"
#define NS UINT64_C(1000000000)
static rb_spec_gate gate=RB_SPEC_GATE_INITIALIZER;
static uint64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec*NS+t.tv_nsec;
}
static int compare(const void *a,const void *b) {
    uint64_t x=*(const uint64_t*)a,y=*(const uint64_t*)b;
    return (x>y)-(x<y);
}

static pthread_mutex_t sample_mu=PTHREAD_MUTEX_INITIALIZER;
static _Atomic uint64_t claimed, published;
static _Atomic unsigned samples;
static _Thread_local unsigned locked_reads;
static _Atomic int tier;
static int read_level(int cached) {
    if (cached) {
        uint64_t now=now_ns();
        uint64_t p=atomic_load_explicit(&published,memory_order_acquire);
        uint64_t c=atomic_load_explicit(&claimed,memory_order_acquire);
        if (rb_spec_snapshot_ready(now,c,p))
            return atomic_load_explicit(&tier,memory_order_relaxed);
    }
    locked_reads++;
    pthread_mutex_lock(&sample_mu);
    uint64_t now=now_ns(), c=atomic_load_explicit(&claimed,memory_order_relaxed);
    if ((!c || (cached && c!=atomic_load_explicit(&published,memory_order_relaxed)) ||
        (now>c && now-c>=RB_SPEC_SAMPLE_NS)) &&
        atomic_compare_exchange_strong_explicit(&claimed,&c,now,memory_order_relaxed,memory_order_relaxed)) {
        atomic_fetch_add(&samples,1);
        atomic_store_explicit(&tier,RB_SPEC_ONE,memory_order_relaxed);
        atomic_store_explicit(&published,now,memory_order_release);
    }
    pthread_mutex_unlock(&sample_mu);
    return atomic_load_explicit(&tier,memory_order_relaxed);
}
typedef struct {
    int cached;
    unsigned paths;
    uint64_t cpu_ns;
} worker_result;
static void *reader(void *payload) {
    worker_result *result=payload;
    struct timespec before, after;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID,&before);
    for (unsigned i=0;i<80000;i++) assert(read_level(result->cached)==RB_SPEC_ONE);
    clock_gettime(CLOCK_THREAD_CPUTIME_ID,&after);
    result->paths=locked_reads;
    result->cpu_ns=(after.tv_sec-before.tv_sec)*NS+after.tv_nsec-before.tv_nsec;
    return NULL;
}
static void snapshot_test(void) {
    const uint64_t stamp=NS;
    assert(!rb_spec_snapshot_ready(stamp,stamp,0));
    assert(!rb_spec_snapshot_ready(stamp,0,stamp));
    assert(!rb_spec_snapshot_ready(stamp,stamp,stamp-1));
    assert(!rb_spec_snapshot_ready(stamp-1,stamp,stamp));
    assert(rb_spec_snapshot_ready(stamp,stamp,stamp));
    assert(rb_spec_snapshot_ready(stamp+RB_SPEC_SAMPLE_NS-1,stamp,stamp));
    assert(!rb_spec_snapshot_ready(stamp+RB_SPEC_SAMPLE_NS,stamp,stamp));
    for (int step=0;step<1000;step++) {
        atomic_store(&claimed,0);
        assert(read_level(1)==RB_SPEC_ONE);
        assert(atomic_load(&published)==atomic_load(&claimed));
    }
    printf("snapshot invalidation and publish checks=1007\n");
}
static void snapshot_bench(void) {
    uint64_t ns[2][16], cpu[2][16];
    uint64_t loop=8*80000;
    unsigned visits[2]={0,0},sensor[2]={0,0};
    for (int i=0;i<16;i++) for (int direction=0;direction<2;direction++){
        int mode = (i+direction)%2;
        atomic_store(&claimed,0); atomic_store(&published,0); atomic_store(&samples,0);
        pthread_t threads[8];
        worker_result stats[8]={0};
        uint64_t start=now_ns();
        for (int t=0;t<8;t++) {
            stats[t].cached=mode;
            assert(!pthread_create(&threads[t],NULL,reader,&stats[t]));
        }
        for (int t=0;t<8;t++) assert(!pthread_join(threads[t],NULL));
        ns[mode][i]=now_ns()-start;
        cpu[mode][i]=0;
        for (int t=0;t<8;t++) {
            visits[mode]+=stats[t].paths;
            cpu[mode][i]+=stats[t].cpu_ns;
        }
        sensor[mode]+=atomic_load(&samples);
    }
    for (int i=0;i<2;i++){
        qsort(ns[i],16,sizeof(uint64_t),compare);
        qsort(cpu[i],16,sizeof(uint64_t),compare);
        printf("snapshot mode=%d median_batch_ms=%.2f max_batch_ms=%.2f cpu_ms=%.2f mutex_paths=%u sensor_calls=%u attempts=%" PRIu64 "\n",
            i,ns[i][8]*1e-6,ns[i][15]*1e-6,cpu[i][8]*1e-6,visits[i],sensor[i],loop*16);
    }
}
static void wake_test(void) {
    rb_spec_publish_plan(&gate,RB_SPEC_RUN,2,0);
    for (unsigned mode=0;mode<2;mode++){
        unsigned start=atomic_load(&notification_calls);
        // Hundreds of jobs fit in an already-available ordinary slot.
        for (int i=0;i<6000;i++) {
            int lease=rb_spec_admit_startup(&gate,0,RB_LEASE_OPTIONAL);
            assert(lease); rb_spec_release_mode(&gate,&lease,mode);
        }
        for (int i=0;i<2000;i++){
            int tickets[4];
            for (int j=0;j<4;j++) {
                tickets[j]=rb_spec_admit_startup(&gate,0,RB_LEASE_HOT_TIER);
                assert(tickets[j]);
            }
            assert(!rb_spec_admit_startup(&gate,0,RB_LEASE_HOT_TIER));
            uint64_t e=atomic_load(&gate.epoch);
            rb_spec_release_mode(&gate,&tickets[3],mode);
            assert(atomic_load(&gate.epoch)>e);
            rb_spec_release_mode(&gate,&tickets[2],mode);
            assert(!rb_spec_admit_startup(&gate,0,RB_LEASE_OPTIONAL));
            e=atomic_load(&gate.epoch);
            rb_spec_release_mode(&gate,&tickets[1],mode);
            assert(atomic_load(&gate.epoch)>e);
            int next=rb_spec_admit_startup(&gate,0,RB_LEASE_OPTIONAL);
            assert(next); rb_spec_release_mode(&gate,&next,mode);
            rb_spec_release_mode(&gate,&tickets[0],mode);
        }
        printf("wake mode=%u broadcasts_called=%u released=16000 full_boundaries=6000\n",
            mode,atomic_load(&notification_calls)-start);
    }
    rb_spec_publish_plan_mode(&gate,RB_SPEC_ONE,2,0,1);
    int opt=rb_spec_admit_startup(&gate,0,RB_LEASE_OPTIONAL);
    assert(opt && !rb_spec_admit_startup(&gate,1,RB_LEASE_OPTIONAL));
    int required=rb_spec_admit_startup(&gate,0,RB_LEASE_FOREGROUND);
    assert(required && !rb_spec_admit_startup(&gate,0,RB_LEASE_FOREGROUND));
    unsigned e=atomic_load(&gate.epoch);
    rb_spec_release_mode(&gate,&required,1);
    assert(atomic_load(&gate.epoch)>e && !rb_spec_admit_startup(&gate,0,RB_LEASE_OPTIONAL));
    required=rb_spec_admit_startup(&gate,0,RB_LEASE_FOREGROUND); assert(required);
    rb_spec_release_mode(&gate,&required,1); rb_spec_release_mode(&gate,&opt,1);
    rb_spec_publish_plan(&gate,RB_SPEC_HOLD,2,0);
    assert(!rb_spec_admit_startup(&gate,0,RB_LEASE_FOREGROUND));
    rb_spec_publish_plan(&gate,RB_SPEC_RUN,2,0);
    assert(!gate.active && gate.energy_one==0);
}
static int sample(rb_energy_guard *s,uint64_t secs,unsigned us,int busy,int nominal){
    return rb_energy_update(s,secs*NS,secs*NS,(uint64_t)us*1000,busy,nominal);
}
static void energy_test(void) {
    for (int rep=0;rep<3000;rep++) {
        rb_energy_guard s={0};
        assert(!sample(&s,1,0,1,1));
        assert(!sample(&s,2,240,1,1) && !s.baseline_ns);
        assert(!sample(&s,4,245,1,1) && s.baseline_ns==242500);
        assert(!sample(&s,6,820,0,1));  // a slow probe in a light or unknown scene
        assert(!sample(&s,8,408,1,1) && s.over==1);
        assert(!rb_energy_update(&s,9*NS,8*NS,408000,1,1) && s.over==1);  // repeated sample
        assert(!sample(&s,10,260,1,1)); // noise did not enter the tier
        assert(!sample(&s,14,540,1,1));
        assert(sample(&s,19,822,1,1));  // Nominal throughout
        assert(sample(&s,20,420,1,0));  // existing hot/low power reasons are separate
        assert(sample(&s,21,240,1,1));
        assert(sample(&s,22,246,1,1));  // min hold not yet elapsed
        assert(!sample(&s,24,245,1,1));
        assert(!sample(&s,26,810,1,1));
        assert(sample(&s,28,822,1,1));
        assert(!rb_energy_update(&s,54*NS,28*NS,822000,1,1)); // stale
        assert(!sample(&s,61,9000,1,1));   // invalid probe
        assert(!sample(&s,63,780,1,1));  // cannot instantly re-enter
        memset(&s,0,sizeof s); // reload clears calibration
        assert(!sample(&s,1,825,1,1) && !s.baseline_ns);
        assert(!sample(&s,6,885,1,1) && s.baseline_ns);
        assert(!sample(&s,11,880,1,1)); // an already warm baseline cannot imply a slowdown
    }
    unsigned optional[2]={0,0},essential[2]={0,0}; int first_cap=0;
    for (int mode=0;mode<2;mode++){
        rb_energy_guard s={0};
        for (int sec=1;sec<=60;sec++){
            int os_hold=sec>=43 && sec<=51;
            unsigned probe=sec<16?240:sec<44?800:240;
            int risk=sample(&s,sec,probe,1,!os_hold);
            if (mode && risk && !first_cap) first_cap=sec;
            int active=mode && risk && !os_hold;
            rb_spec_publish_plan_mode(&gate,os_hold?RB_SPEC_HOLD:active?RB_SPEC_ONE:RB_SPEC_RUN,2,0,active);
            int a=rb_spec_admit_startup(&gate,0,RB_LEASE_OPTIONAL);
            if (a) optional[mode]++;
            // One foreground and one optional candidate per interval. Actual
            // deployment cannot infer game latency from these admissions.
            int priority=rb_spec_admit_startup(&gate,0,RB_LEASE_FOREGROUND);
            if (priority) essential[mode]++;
            int b=rb_spec_admit_startup(&gate,1,RB_LEASE_OPTIONAL);
            if (b) optional[mode]++;
            rb_spec_release_mode(&gate,&b,1);
            rb_spec_release_mode(&gate,&priority,1);
            b=rb_spec_admit_startup(&gate,1,RB_LEASE_OPTIONAL);
            if (b) optional[mode]++;
            rb_spec_release_mode(&gate,&b,1);
            rb_spec_release_mode(&gate,&a,1);
        }
    }
    assert(essential[0]==essential[1] && optional[1]<optional[0] && first_cap==17);
    printf("simulated 60 intervals cap_at=%d os_hold_at=43 optional=%u->%u foreground=%u/%u scenarios=3000\n",
           first_cap,optional[0],optional[1],essential[0],essential[1]);
}
static uint32_t random_state = UINT32_C(0x45dc02a1);
static uint32_t next_word(void) {
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}

static void bad_probe_sequences(void) {
    unsigned checks = 0;
    for (unsigned session = 0; session < 1000; session++) {
        rb_energy_guard guard = {0};
        uint64_t now = 0;
        for (unsigned tick = 0; tick < 120; tick++) {
            uint32_t noise = next_word();
            now += (1 + noise % 12) * NS;
            uint64_t observed = noise & 4 ? now : guard.observed_ns;
            if (noise & 8) observed = 0;
            if (noise & 16) observed = now + NS;
            uint64_t probe = noise & 32 ? 230000 + noise % 50000 : 700000 + noise % 150000;
            if (noise & 64) probe = UINT64_MAX;
            int busy = !!(noise & 128), nominal = !!(noise & 256);
            int fresh = observed && observed > guard.observed_ns && observed <= now;
            int was_capped = guard.capped_since_ns != 0;
            unsigned previous_slow = guard.over;
            uint64_t prior_baseline = guard.baseline_ns;
            int capped = rb_energy_update(&guard, now, observed, probe, busy, nominal);
            if (capped && !was_capped)
                assert(fresh && busy && nominal && rb_energy_probe_valid(probe) &&
                       previous_slow && prior_baseline && probe * 5 >= prior_baseline * 8);
            if (capped)
                assert(guard.capped_since_ns <= now && guard.baseline_ns &&
                       now - guard.observed_ns <= RB_ENERGY_SAMPLE_AGE_NS);
            checks++;
        }
    }
    printf("perturbed probe checks=%u\n", checks);
}

typedef struct {
    uint64_t ticket;
    uint64_t elapsed;
    _Atomic int ready;
} sleeper;
static void *wait_for_sensor(void *arg) {
    sleeper *s=arg;
    uint64_t start=now_ns();
    atomic_store(&s->ready,1);
    rb_spec_wait_worker(&gate,s->ticket,0);
    s->elapsed=now_ns()-start;
    return NULL;
}
static void sensor_events(void) {
    uint64_t result[2][7];
    for (int i=0;i<7;i++) for (int d=0;d<2;d++) {
        int mode = (i+d)%2;
        sleeper s={.ticket=atomic_load(&gate.epoch)};
        pthread_t t;
        atomic_store(&claimed,100);
        assert(!pthread_create(&t,NULL,wait_for_sensor,&s));
        while(!atomic_load(&s.ready)) {}
        nanosleep(&(struct timespec){0,20000000},NULL);
        if (mode) {
            rb_spec_notify_sensor(&gate, &claimed);
        } else {
            atomic_store(&claimed, 0);
        }
        assert(!pthread_join(t,NULL));
        result[mode][i]=s.elapsed;
        uint64_t prev=atomic_load(&gate.epoch);
        rb_spec_notify_sensor(&gate,&claimed);
        assert(atomic_load(&gate.epoch)==prev);
    }
    for (int mode=0;mode<2;mode++){
        qsort(result[mode],7,sizeof(uint64_t),compare);
        printf("sensor mode=%d median_ms=%.3f max_ms=%.3f\n",mode,result[mode][3]/1e6,result[mode][6]/1e6);
    }
}

static _Atomic int stop_idle;
static _Atomic unsigned parked_workers;
static void *watch_idle_work(void *payload) {
    int worker = *(const int *)payload;
    atomic_fetch_add(&parked_workers, 1);
    while (!atomic_load(&stop_idle)) {
        uint64_t ticket = atomic_load(&gate.epoch);
        if (!atomic_load(&stop_idle)) rb_spec_wait_worker(&gate, ticket, worker);
    }
    return NULL;
}

static void idle_wake_bench(void) {
    for (int mode = 0; mode < 2; mode++) {
        rb_spec_publish_plan(&gate, RB_SPEC_RUN, 2, 0);
        atomic_store(&stop_idle, 0);
        atomic_store(&parked_workers, 0);
        atomic_store(&idle_wait_returns, 0);
        pthread_t threads[4];
        int lanes[] = {0, 1, 2, 3};
        for (unsigned i = 0; i < 4; i++)
            assert(!pthread_create(&threads[i], NULL, watch_idle_work, &lanes[i]));
        while (atomic_load(&parked_workers) != 4) {}
        nanosleep(&(struct timespec){0, 10000000}, NULL);
        atomic_store(&measure_idle_wake, 1);
        for (unsigned i = 0; i < 100; i++) {
            int lease = rb_spec_admit(&gate, 0);
            assert(lease);
            rb_spec_release_mode(&gate, &lease, mode);
            nanosleep(&(struct timespec){0, 2000000}, NULL);
        }
        atomic_store(&measure_idle_wake, 0);
        atomic_store(&stop_idle, 1);
        rb_spec_wake(&gate);
        for (unsigned i = 0; i < 4; i++) assert(!pthread_join(threads[i], NULL));
        printf("idle wake mode=%d successful_wait_returns=%u\n", mode, atomic_load(&idle_wait_returns));
        if (mode) assert(atomic_load(&idle_wait_returns) == 0);
        else assert(atomic_load(&idle_wait_returns) > 0);
    }
}

int main(int argc,char **argv) {
    assert(argc == 1 || (argc == 2 && !strcmp(argv[1], "bench")));
    snapshot_test();
    wake_test();
    energy_test();
    bad_probe_sequences();
    if (argc == 2) {
        snapshot_bench();
        sensor_events();
        idle_wake_bench();
    }
}
