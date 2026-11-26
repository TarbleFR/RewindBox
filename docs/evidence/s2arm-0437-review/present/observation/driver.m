#define HR 2048
#define g_ft g_s2a_hud_ft
#define g_fn g_s2a_hud_fn
#define memory_order_relaxed __ATOMIC_RELAXED
#define memory_order_release __ATOMIC_RELEASE
#define memory_order_acquire __ATOMIC_ACQUIRE
#define atomic_load_explicit __c11_atomic_load
#define atomic_store_explicit __c11_atomic_store
typedef struct { uint64_t phys_footprint; } task_vm_info_data_t;
typedef unsigned mach_msg_type_number_t;
typedef void *task_info_t;
#define TASK_VM_INFO_COUNT 0
#define TASK_VM_INFO 0
#define KERN_SUCCESS 0
#define task_info(...) 1
#define S2A_UI(key) key
#define S2A_UI_HUD_MEM_FAIL "?"
#define S2A_UI_HUD_BRIEF_CAP "%d"
#define S2A_UI_HUD_BRIEF "%llu fps %s %.1f ms %s"
static uint64_t fake_clock;
static uint64_t now_ns(void) {return fake_clock;}
static uint64_t mono_ns(void) {return fake_clock;}
static int cap_fps(void) {return 0;}
static _Atomic uint64_t g_ft[HR],g_fn;
#include "hud.inc"
static void dispatch_presented(int slot) {
    if (!presented[slot]) return;
    presented[slot](objects[slot]); Block_release(presented[slot]); presented[slot]=nil;
}
#if HAS_STATS
typedef struct { uint64_t ids[32]; pthread_barrier_t barrier; } rb_parallel_group;
typedef struct { rb_parallel_group *group; int gpu; } rb_parallel_event;
static void *publish_pairs(void *arg) {
    rb_parallel_event *work=arg;
    pthread_barrier_wait(&work->group->barrier);
    for(int j=0;j<32;j++){
        int i=work->gpu ? j : 31-j;
        rb_fi_stats_update(work->group->ids[i],work->gpu?RB_FI_GPU_READY:RB_FI_DISPLAY_READY,
                           RB_FI_METALFX,1.0+i);
    }
    return NULL;
}
#endif
int main(int argc,char **argv) {
    if (argc!=6 && argc!=7) return 1;
    const int failure=argc==7 ? atoi(argv[6]) : 0;
#if HAS_STATS
    validate_log=atoi(argv[5])<10000;
    rb_fi_stats_begin_session();
#endif
    const int show=atoi(argv[1]),cut=atoi(argv[2]),allow=atoi(argv[3]),reverse=atoi(argv[4]),n=atoi(argv[5]);
    for(int i=0;i<7;i++){objects[i]=class_createInstance(objc_getClass("Fake"),0);objects[i]->slot=i;}
    CAMetalLayer *layer=class_createInstance(objc_getClass("CAMetalLayer"),0);
    NvPresentFI f={.w=16,.h=16,.mvFlag=objects[0],.motion=objects[0],.cb={nil,objects[1],objects[2]},.slot_free={NULL,&leased[1],&leased[2]},
        .in_tex={objects[5],objects[6]},.mid_tex=objects[3],.psoMid=objects[4]};
    cut_word=0;
    unsigned types[5]={0};
    struct timespec start={0},end={0},cpu0={0},cpu1={0};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID,&cpu0); clock_gettime(CLOCK_MONOTONIC,&start);
    for (int j=1;j<=n;j++) {
        // Each synthetic game frame enters the production HUD exactly once.
        fake_clock=1000000000ULL+j*1000000000ULL/n; s2a_hud_frame();
        cut_word=cut==2 ? (j%2==0) : cut;
        tk=j; g_pq_done=tk-1;g_rb_present_source[j%RB_PRESENT_CAP]=objects[0];
        outcome[2]=SUBMIT;
        outcome[1]=failure==2 ? NO_DRAWABLE : failure==3 ? ENCODE_FAIL : failure==4 ? NO_FEEDBACK : SUBMIT;
        feedback_mode=failure==1 ? 1 : failure==5 ? 2 : 0; option_slot=1; owns=1; layer_calls=0; script=allow;
        for(int s=1;s<3;s++){leased[s]=1;submitted[s]=completed[s]=0;}
        fi_inflight=1;encoding_type=0;f.last_seq=j-1;
        fi_job(&f,layer,objects[0],(fi_crop){0},NO,0,j,1./30,tk,1,allow);
        shown_time[1]=show==2 ? (j%2!=0) : show==3 ? (j%2==0) : show>0; shown_time[2]=show>=0 ? 1 : 0;
        if(failure==7 && j==n) {
            dispatch_presented(1); dispatch_presented(2); deliver(2);
        } else if(failure==6 && j==n){
            // Delayed drawable after the session ends. The native state is still owned by the mock.
            deliver(2); deliver(1); dispatch_presented(2);
        } else if(reverse){dispatch_presented(2);dispatch_presented(1);deliver(2);deliver(1);}
        else {deliver(1);deliver(2);dispatch_presented(1);dispatch_presented(2);}
        if (encoding_type && shown_time[1]>0) types[encoding_type]++;
    }
    clock_gettime(CLOCK_MONOTONIC,&end); clock_gettime(CLOCK_THREAD_CPUTIME_ID,&cpu1);
    const int64_t elapsed=((int64_t)end.tv_sec-start.tv_sec)*1000000000LL+end.tv_nsec-start.tv_nsec;
    char hud[128];s2a_hud_brief(hud,sizeof hud);
    printf("guest=%d real=%llu midpoint=%llu fx_request=%d made=%llu cuts=%llu fx_shown=%u previous=%u cut=%u dup=%u hud=%s\n",
        n,(unsigned long long)atomic_load(&g_fi_on_real),(unsigned long long)atomic_load(&g_fi_on_mid),fx_calls,
        (unsigned long long)f.made,(unsigned long long)f.cuts,types[1],types[2],types[3],types[4],hud);
    printf("elapsed_ns=%lld cpu_ns=%lld\n",(long long)elapsed,((long long)cpu1.tv_sec-cpu0.tv_sec)*1000000000LL+cpu1.tv_nsec-cpu0.tv_nsec);
#if HAS_STATS
    rb_fi_counts c=g_rb_fi_counts;
    printf("registered=%llu pending=%llu failed=%llu discarded=%llu fx=%llu dup=%llu prev=%llu cut=%llu unknown=%llu first=%.1f last=%.1f\n",
        (unsigned long long)c.registered,(unsigned long long)c.pending,(unsigned long long)c.failed_submit,
        (unsigned long long)c.discarded,(unsigned long long)c.shown[0],(unsigned long long)c.shown[1],(unsigned long long)c.shown[2],
        (unsigned long long)c.shown[3],(unsigned long long)c.shown[4],c.first_display_s,c.last_display_s);
    if(atomic_load(&g_rb_fi_stats_on)>0){
        assert(c.registered==c.pending+c.overwritten+c.failed_submit+c.discarded+c.invalid_time+c.shown[0]+c.shown[1]+c.shown[2]+c.shown[3]+c.shown[4]);
        rb_fi_stats_report(1);
        if (validate_log) {
            assert(strstr(last_stats_log,"final=1"));
            int complete=!c.pending && !c.overwritten && !c.invalid_time && !c.shown[RB_FI_GPU_ERROR];
            assert(strstr(last_stats_log,complete ? "classification_complete=1" : "classification_complete=0"));
        }
        assert(!g_rb_fi_observations);
        if(failure==6 || failure==7){
            rb_fi_stats_begin_session(); if(failure==6) dispatch_presented(1); else deliver(1);
            assert(g_rb_fi_counts.registered==0 && g_rb_fi_counts.pending==0);
            rb_fi_stats_report(1);
        }
        if(failure==9){
            rb_fi_stats_begin_session();
            rb_parallel_group group;
            pthread_t t[2];
            rb_parallel_event work[2]={{&group,0},{&group,1}};
            assert(!pthread_barrier_init(&group.barrier,0,3));
            for(int i=0;i<32;i++) group.ids[i]=rb_fi_stats_reserve();
            for(int i=0;i<2;i++) assert(!pthread_create(&t[i],0,publish_pairs,&work[i]));
            pthread_barrier_wait(&group.barrier);
            for(int i=0;i<2;i++) assert(!pthread_join(t[i],0));
            assert(!pthread_barrier_destroy(&group.barrier));
            assert(g_rb_fi_counts.pending==0 && g_rb_fi_counts.shown[RB_FI_METALFX]==32);
            assert(g_rb_fi_counts.first_display_s==1 && g_rb_fi_counts.last_display_s==32);
            rb_fi_stats_report(1);
        }
        if(failure==8) {
            rb_fi_stats_begin_session();
            uint64_t old=rb_fi_stats_reserve(), newest=0;
            for(int k=0;k<RB_FI_OBSERVATIONS;k++) newest=rb_fi_stats_reserve();
            assert(g_rb_fi_counts.overwritten==1 && g_rb_fi_counts.pending==RB_FI_OBSERVATIONS);
            rb_fi_stats_update(old,RB_FI_DISPLAY_READY,RB_FI_GPU_ERROR,3);
            rb_fi_stats_update(old,RB_FI_GPU_READY,RB_FI_CUT,0);
            rb_fi_stats_update(newest,RB_FI_DISPLAY_READY,RB_FI_GPU_ERROR,17.7);
            rb_fi_stats_update(newest,RB_FI_GPU_READY,RB_FI_METALFX,0);
            rb_fi_stats_update(newest,RB_FI_GPU_READY,RB_FI_CUT,0);
            assert(g_rb_fi_counts.shown[RB_FI_METALFX]==1 && g_rb_fi_counts.shown[RB_FI_CUT]==0);
            uint64_t keyed=rb_fi_stats_reserve(); rb_fi_stats_update(keyed,RB_FI_GPU_READY,RB_FI_METALFX,0);
            rb_fi_stats_update(keyed,RB_FI_DISPLAY_READY,RB_FI_GPU_ERROR,8.3);
            assert(g_rb_fi_counts.first_display_s==8.3 && g_rb_fi_counts.last_display_s==17.7);
            uint64_t bad=rb_fi_stats_reserve(); rb_fi_stats_update(bad,RB_FI_GPU_READY,RB_FI_METALFX,0);
            rb_fi_stats_update(bad,RB_FI_DISPLAY_READY,RB_FI_GPU_ERROR,NAN);
            assert(g_rb_fi_counts.invalid_time==1);
            rb_fi_stats_report(1);
            rb_fi_stats_update(old,RB_FI_GPU_READY,RB_FI_PREVIOUS,0);
        }
    } else assert(!g_rb_fi_observations);
#endif
}
