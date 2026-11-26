#include <assert.h>
#include <stdint.h>
#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <math.h>
#include <time.h>
#include <objc/Object.h>
#include <objc/runtime.h>
#include <Block.h>
#include "rule.h"
#undef nil
#define nil ((void *)0)
#define API_AVAILABLE(...)
#define MLOG(...)
#define RB_WAKE_CALL(a,b,op) op
#define RB_PRESENT_CAP 8
#define DISPATCH_TIME_FOREVER 0
#define atomic_fetch_add(p,v) __c11_atomic_fetch_add(p,v,__ATOMIC_SEQ_CST)
#define atomic_load(p) __c11_atomic_load(p,__ATOMIC_SEQ_CST)
#define atomic_store(p,v) __c11_atomic_store(p,v,__ATOMIC_SEQ_CST)
typedef unsigned long NSUInteger;
typedef int *dispatch_semaphore_t;
typedef Object NSError;
@protocol MTLTexture
@property(readonly) NSUInteger width;
@end
@protocol CAMetalDrawable
@property(readonly) id<MTLTexture> texture;
- (void)present;
- (void)presentAfterMinimumDuration:(double)duration;
@end
@protocol MTLFXFrameInterpolatorBase
@property(assign) id colorTexture, prevColorTexture, outputTexture, depthTexture, motionTexture;
@property(assign) float motionVectorScaleX, motionVectorScaleY, deltaTime, nearPlane, farPlane, fieldOfView, aspectRatio, jitterOffsetX, jitterOffsetY;
@property(assign) BOOL depthReversed, shouldResetHistory;
@end
@interface Fake : Object <CAMetalDrawable, MTLTexture> {
@public int slot;
}
- (void)endCommandBuffer;
- (void)encodeToCommandBuffer:(id)cb;
- (void)waitForDrawable:(id)d;
- (void)signalDrawable:(id)d;
- (void)removeAllAllocations;
- (void)commit;
@property(readonly) void *contents;
@property(readonly) NSError *error;
@property(readonly) double GPUStartTime, GPUEndTime;
@end
static int outcome[3], syncslot[3], leased[3], feedback_mode;
enum { SUBMIT, NO_DRAWABLE, ENCODE_FAIL, NO_FEEDBACK, NO_INPUT };
static int early_release, late_cpu_access, early_submit, premature_reuse, untracked, release_count;
static int submitted[3], completed[3], waits[3], signals[3], feedback_nil, feedback_errors;
static uint32_t cut_word;
static Fake *objects[7];
static int script, layer_calls;
static _Atomic uint64_t g_fi_on_mid, g_fi_on_real;
static BOOL checking_cpu, do_bench;
@implementation Fake
- (NSUInteger)width { return 16; }
- (id<MTLTexture>)texture { return self; }
- (void)present { }
- (void)presentAfterMinimumDuration:(double)duration { }
- (void)endCommandBuffer { }
- (void)encodeToCommandBuffer:(id)cb { }
- (void)waitForDrawable:(id)d { waits[((Fake *)d)->slot]++; }
- (void)signalDrawable:(id)d { signals[((Fake *)d)->slot]++; }
- (void)removeAllAllocations { release_count++; }
- (void)commit { }
- (void *)contents { if (!do_bench && checking_cpu && leased[1]) late_cpu_access++; return &cut_word; }
- (NSError *)error { return feedback_mode==1 ? self : nil; }
- (double)GPUStartTime { return 1; }
- (double)GPUEndTime { return 2; }
@end
@interface CAMetalLayer : Object
- (id<CAMetalDrawable>)nextDrawable;
@end
@implementation CAMetalLayer
- (id<CAMetalDrawable>)nextDrawable {
    int s = script && !layer_calls ? 1 : 2; layer_calls++;
    return outcome[s]==NO_DRAWABLE ? nil : objects[s];
}
@end
typedef struct {
 int w,h;
 id<MTLTexture> in_tex[2], mid_tex, motion, depth;
 id mfx, psoCopy, psoMid, tab[4], uv[4], alloc[3], cb[3];
 Fake *mvFlag;
 dispatch_semaphore_t slot_free[3];
 uint64_t last_seq,last_pair_seq,declined,unpaired,made,shown_mid,jobs,gpu_n,cuts;
 _Atomic uint64_t cut_seq;
 unsigned consec_declined;
 double gpu_sum,gpu_max;
} NvPresentFI;
typedef struct {int has,c[4];} fi_crop;
static pthread_mutex_t g_pq_mu=PTHREAD_MUTEX_INITIALIZER, g_fi_enc_mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_pq_cv=PTHREAD_COND_INITIALIZER;
static int g_pq_inflight, fi_inflight=0, option_slot, owns;
static unsigned long long tk;
static uint64_t g_pq_done, g_rb_present_completed[RB_PRESENT_CAP];
static id g_rb_present_pin[RB_PRESENT_CAP],g_rb_present_source[RB_PRESENT_CAP];
#include "complete.inc"
static void dispatch_semaphore_wait(int *s, int unused) { assert(*s==1); *s=0; }
static void dispatch_semaphore_signal(int *s) { assert(*s==0); *s=1; }
typedef void (^Feedback)(id);
static Feedback pending[3];
static id fb_new(void) { int s=option_slot++; return outcome[s]==NO_FEEDBACK ? nil : objects[s]; }
static void fb_add(id opts, Feedback cb) {
    if (!opts) return;
    int s=((Fake *)opts)->slot; assert(!pending[s]); pending[s]=Block_copy(cb);
}
static void deliver(int s) {
    if (completed[s] || !submitted[s]) return;
    if (!g_rb_present_source[tk%RB_PRESENT_CAP]) early_release++;
    completed[s]=1; Feedback fb=pending[s]; pending[s]=nil;
    if (fb) {
        checking_cpu=YES;
        fb(feedback_mode==2 ? nil : objects[0]);
        checking_cpu=NO;
        Block_release(fb);
    }
}
static void m4_commit_one(id cb, id opts) {
    int s=((Fake *)cb)->slot;
    if (!g_rb_present_source[tk%RB_PRESENT_CAP]) early_submit++;
    assert(!submitted[s] && !leased[s]); submitted[s]=1;
    if (!opts) {untracked++; return;}
    if (syncslot[s]) deliver(s);
}
static id rb_present_queue(void) {return objects[0];}
static void m4_begin_on(id cb,id alloc) {}
static int mtl_gpu_cb_error(NSError *e,const char *name,uint64_t slot) {feedback_errors++;return 1;}
static void res_commit(void) {}
static int fi_may_take_drawable(void) {return owns;}
static int fi_all_on(void) {return 0;}
static int fi_mv_mode(void) {return 1;}
static int fi_dup(void) {return 0;}
static double rb_fi_patch_aspect(void) {return 0;}
static void fi_inflight_add(int d) {fi_inflight+=d;}
static int fi_pass(id cb, id a, id b, id c, id d, id e, id f, const int*g, int h, NSUInteger i, NSUInteger j) {return outcome[1]!=ENCODE_FAIL;}
static void fi_mv_encode(NvPresentFI *f,id cb,int k,int use,float sign) {}
static int present_blit_m4(id cb,id src,id dst,const int*crop,id uv,id tab,BOOL flip) {return outcome[((Fake *)cb)->slot]!=ENCODE_FAIL;}
static void present_note(id dr,uint64_t ticket) {}
static void fi_count_on(id dr,_Atomic uint64_t *count) {}
#include "job.inc"
static int cases, known_bad;
static uint64_t hsh;
static void one(NvPresentFI f,CAMetalLayer *layer,int a,int b,int mode,int sx,int sy,int reverse,int mine,int pair) {
    int base_release=release_count, saved_late=late_cpu_access, saved_early=early_release+early_submit;
    tk++; int i=tk%RB_PRESENT_CAP;
    g_rb_present_source[i]=objects[0];g_rb_present_pin[i]=objects[0];
    // Prior cases with deliberately missing callbacks never complete on the baseline.
    g_pq_done=tk-1; g_pq_inflight=0; fi_inflight=1; owns=mine; outcome[1]=a;outcome[2]=b;
    syncslot[1]=sx;syncslot[2]=sy; feedback_mode=mode; layer_calls=0;
    option_slot=a==NO_INPUT?2:1;
    for(int s=1;s<=2;s++){leased[s]=1;submitted[s]=completed[s]=waits[s]=signals[s]=0;pending[s]=nil;}
    script=pair && a!=NO_INPUT; f.last_seq=0;
    fi_job(&f,layer,objects[0],(fi_crop){0},NO,0,1,1./30,tk,a!=NO_INPUT,pair);
    if (g_pq_done==tk && ((submitted[1]&&!completed[1])||(submitted[2]&&!completed[2]))) premature_reuse++;
    deliver(reverse?2:1);
    if (g_pq_done==tk && ((submitted[1]&&!completed[1])||(submitted[2]&&!completed[2]))) premature_reuse++;
    deliver(reverse?1:2);
    int missing=untracked; untracked=0;
    int fail=g_pq_done!=tk || release_count!=base_release+1 || g_pq_inflight || fi_inflight || !leased[1]||!leased[2] || waits[1]!=signals[1] || waits[2]!=signals[2] || late_cpu_access!=saved_late || early_release+early_submit!=saved_early || missing;
    if (fail) known_bad++;
    cases++;hsh=hsh*33+submitted[1]+submitted[2]*2+f.shown_mid*4;
}
#if HAS_PARTS
static int g_rb_present_encoding, g_link_started, g_classic_busy;
static uint64_t g_pq_in;
static pthread_cond_t drain_step=PTHREAD_COND_INITIALIZER;
static int drain_reached, drain_exited, timeout_injected;
static struct timespec session_deadline(void) {
    struct timespec ts; clock_gettime(CLOCK_REALTIME,&ts); ts.tv_sec+=timeout_injected ? -1 : 5; return ts;
}
static void link_stop_locked(void) { drain_reached=1; pthread_cond_broadcast(&drain_step); }
static int stop_body(void) {
#include "stop.inc"
    return 0;
}
static void *drain_thread(void *kind) {
    if ((uintptr_t)kind==1) { assert(stop_body()==0); }
    else {
        pthread_mutex_lock(&g_pq_mu);
        link_stop_locked();
        uint64_t tk=g_pq_in;
#include "stall.inc"
        pthread_mutex_unlock(&g_pq_mu);
    }
    pthread_mutex_lock(&g_pq_mu); drain_exited=1;pthread_cond_broadcast(&drain_step);pthread_mutex_unlock(&g_pq_mu);
    return NULL;
}
static void drains(NvPresentFI f,CAMetalLayer *layer) {
    for(int kind=0;kind<2;kind++) {
        tk++;g_pq_in=tk+1; // next queued ticket is dropped after the last submitted read retires
        g_rb_present_source[tk%RB_PRESENT_CAP]=objects[0];g_rb_present_pin[tk%RB_PRESENT_CAP]=objects[0];
        owns=1; outcome[1]=outcome[2]=SUBMIT; feedback_mode=0; option_slot=1; layer_calls=0;script=1;
        for(int s=1;s<=2;s++){leased[s]=1;submitted[s]=completed[s]=syncslot[s]=0;}
        f.last_seq=0;fi_inflight=1;fi_job(&f,layer,objects[0],(fi_crop){0},NO,0,1,1./30,tk,1,1);
        assert(g_pq_inflight==2);
        drain_reached=drain_exited=0;
        pthread_t th;pthread_create(&th,NULL,drain_thread,(void *)(uintptr_t)kind);
        pthread_mutex_lock(&g_pq_mu);while(!drain_reached)pthread_cond_wait(&drain_step,&g_pq_mu);pthread_mutex_unlock(&g_pq_mu);
        deliver(2);
        pthread_mutex_lock(&g_pq_mu);assert(g_pq_done<tk && !drain_exited && g_rb_present_source[tk%RB_PRESENT_CAP]);pthread_mutex_unlock(&g_pq_mu);
        deliver(1);pthread_join(th,NULL);assert(g_pq_done==g_pq_in);tk=g_pq_in;
    }
    // No feedback ever arrives. The engine's actual error branch must preserve its source.
    tk++;g_pq_in=tk;g_rb_present_source[tk%RB_PRESENT_CAP]=objects[0];g_pq_inflight=1;timeout_injected=1;
    assert(stop_body()==-ETIMEDOUT && g_pq_done<tk && g_rb_present_source[tk%RB_PRESENT_CAP]);
    timeout_injected=0;g_pq_inflight=0;rb_present_complete(tk);
}
static void ring(void) {
    uint32_t rng=205; unsigned rounds=1000;
    for(unsigned round=0;round<rounds;round++) {
        uint64_t first=tk+1;int order[RB_PRESENT_CAP*2],done[RB_PRESENT_CAP]={0};
        for(int j=0;j<RB_PRESENT_CAP;j++) {
            uint64_t ticket=first+j;unsigned k=ticket%RB_PRESENT_CAP;
            g_rb_present_source[k]=objects[0];g_rb_present_pin[k]=objects[0];order[j*2]=j*2;order[j*2+1]=j*2+1;
        }
        for(int j=RB_PRESENT_CAP*2-1;j>0;j--){rng=rng*1664525u+1013904223u;unsigned k=rng%(j+1);int z=order[k];order[k]=order[j];order[j]=z;}
        for(int j=0;j<RB_PRESENT_CAP*2;j++){
            int z=order[j], idx=z/2,slot=(z%2)+1;uint64_t ticket=first+idx;
            fi_finish_read_locked(ticket,slot);
            fi_finish_read_locked(ticket,slot);  // duplicate part cannot complete the other reader
            if(round && g_pq_done>=ticket-RB_PRESENT_CAP)
                fi_finish_read_locked(ticket-RB_PRESENT_CAP,3-slot);
            ++done[idx];assert((g_rb_present_source[ticket%RB_PRESENT_CAP]!=nil)==(done[idx]<2));
            uint64_t expect=first-1;for(int n=0;n<RB_PRESENT_CAP&&done[n]==2;n++)expect++;
            assert(g_pq_done==expect);
        }
        tk+=RB_PRESENT_CAP;
    }
    printf("ring: %u tickets, two readers + duplicate and late old notifications; contiguous releases\n",rounds*RB_PRESENT_CAP);
}
#endif
int main(int argc,char **argv) {
    for(int j=0;j<7;j++){objects[j]=class_createInstance(objc_getClass("Fake"),0);objects[j]->slot=j;}
    CAMetalLayer *layer=class_createInstance(objc_getClass("CAMetalLayer"),0);
    NvPresentFI f={.w=16,.h=16,.mvFlag=objects[0],.motion=objects[0],.cb={nil,objects[1],objects[2]},.slot_free={NULL,&leased[1],&leased[2]}};
    if (argc>1) {
        do_bench=YES;
        struct timespec t0,t1;
        for(int warm=0;warm<10000;warm++) one(f,layer,SUBMIT,SUBMIT,0,0,0,0,1,1);
        clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t0);
        for(int i=0;i<200000;i++) one(f,layer,SUBMIT,SUBMIT,0,0,0,0,1,1);
        clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t1);
        printf("%lld\n",(long long)(t1.tv_sec-t0.tv_sec)*1000000000LL+t1.tv_nsec-t0.tv_nsec);
        return 0;
    }
    for(int a=0;a<=NO_INPUT;a++)for(int b=0;b<=NO_FEEDBACK;b++)for(int m=0;m<3;m++)
    for(int sx=0;sx<2;sx++)for(int sy=0;sy<2;sy++)for(int r=0;r<2;r++)for(int mine=0;mine<2;mine++)for(int pair=0;pair<2;pair++) one(f,layer,a,b,m,sx,sy,r,mine,pair);
#if HAS_PARTS
    drains(f,layer);ring();
    puts("shutdown and stall wait for both readers; shutdown timeout preserves the ticket");
#endif
    printf("cases=%d divergent=%d late-feedback-read=%d missing-live-source-on-gpu=%d already-released-while-inflight=%d release-before-submit=%d checksig=%llx\n",cases,known_bad,late_cpu_access,early_release,premature_reuse,early_submit,(unsigned long long)hsh);
    return known_bad?1:0;
}
