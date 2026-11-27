from pathlib import Path
import argparse
p=argparse.ArgumentParser()
p.add_argument('--reference',required=True);p.add_argument('--candidate',required=True);p.add_argument('--output',required=True)
a=p.parse_args()
out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
refs=[Path(a.reference),Path(a.candidate)]
def extract(s, sig):
    a=s.index(sig); b=s.index('{',a); level=1; e=b+1
    while level:
        if s[e]=='{':level+=1
        if s[e]=='}':level-=1
        e+=1
    return s[a:e]
common=r'''#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static pthread_mutex_t g_mu=PTHREAD_MUTEX_INITIALIZER;
#define GMU_LOCK() pthread_mutex_lock(&g_mu)
#define GMU_UNLOCK() pthread_mutex_unlock(&g_mu)
#define APP_POOL (1ULL<<30)
#define S2A_OBJ_THREAD 2
#define S2A_OBJ_EVENT_R 3
#define S2A_OBJ_TMEM 4
#define S2A_OBJ_SESSION 5
typedef struct { int refs; int proc; int64_t lim[5],cur[5],peak[5]; } reslimit_t;
static reslimit_t g_rl={1,1,{0,608,700,128,894},{0},{0}};
static reslimit_t other={1,0,{5,6,7,8,9},{1,2,3,4,5},{2,3,4,5,6}};
static uint64_t g_heap_cur,g_phys,g_mem_peak;
static uint64_t pool_fixed(void){return g_phys;}
static void *s2a_native_handle_obj(uint32_t h,uint32_t sub){(void)sub;return h==1?&g_rl:h==2?&other:NULL;}
static void s2a_handle_kind_count(uint32_t kind,int *cur,int *peak){*cur=(int)kind+10;*peak=(int)kind+20;}
'''
common+='\n'+extract(refs[0].read_text(),'static uint64_t mem_used(void)')+'\n'
main=r'''
static pthread_mutex_t sync_mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t sync_cv=PTHREAD_COND_INITIALIZER;
static int mid,release_writer,reader_done;
static int read_what;
static int64_t observed;
static void *writer(void *unused){
    (void)unused;
    GMU_LOCK();
    // Synthetic mapping update paused half way through its critical section.
    g_phys=32768;
    pthread_mutex_lock(&sync_mu);mid=1;pthread_cond_broadcast(&sync_cv);
    while(!release_writer)pthread_cond_wait(&sync_cv,&sync_mu);
    pthread_mutex_unlock(&sync_mu);
    g_phys=65536;g_mem_peak=65536;
    GMU_UNLOCK();return NULL;
}
static void *reader(void *unused){
    (void)unused;
    assert(rl_value(1,0,read_what,&observed)==0);
    pthread_mutex_lock(&sync_mu);reader_done=1;pthread_cond_broadcast(&sync_cv);pthread_mutex_unlock(&sync_mu);return NULL;
}
static void basic(void){
    int64_t v;
    assert(rl_value(0,0,1,&v)==0xE401);
    assert(rl_value(1,5,1,&v)==0xF001);
    assert(rl_value(1,0,0,&v)==0 && v==APP_POOL);
    g_heap_cur=4096;g_phys=8192;g_mem_peak=16384;
    assert(rl_value(1,0,1,&v)==0 && v==12288);
    assert(rl_value(1,0,2,&v)==0 && v==16384);
    g_mem_peak=1;
    assert(rl_value(1,0,2,&v)==0 && v==12288);
    for(int w=0;w<3;w++)for(int k=0;k<5;k++){
        int64_t expected=w==0?other.lim[k]:w==1?other.cur[k]:other.peak[k];
        assert(rl_value(2,k,w,&v)==0 && v==expected);
    }
    for(int k=1;k<5;k++)for(int w=0;w<3;w++){
        const int kind[5]={0,2,3,4,5};
        int64_t expected=w==0?g_rl.lim[k]:kind[k]+(w==1?10:20);
        assert(rl_value(1,k,w,&v)==0 && v==expected);
    }
}
int main(void){
    basic();
    int while_locked=0,final=0;
    for(read_what=1;read_what<=2;read_what++)for(int trial=0;trial<5;trial++){
        mid=release_writer=reader_done=0;g_heap_cur=g_phys=g_mem_peak=0;
        pthread_t wt,rt;assert(!pthread_create(&wt,NULL,writer,NULL));
        pthread_mutex_lock(&sync_mu);while(!mid)pthread_cond_wait(&sync_cv,&sync_mu);pthread_mutex_unlock(&sync_mu);
        assert(!pthread_create(&rt,NULL,reader,NULL));
        struct timespec deadline;clock_gettime(CLOCK_REALTIME,&deadline);deadline.tv_nsec+=30000000;
        if(deadline.tv_nsec>=1000000000){deadline.tv_nsec-=1000000000;deadline.tv_sec++;}
        pthread_mutex_lock(&sync_mu);int rc=0;
        while(!reader_done && !rc)rc=pthread_cond_timedwait(&sync_cv,&sync_mu,&deadline);
        assert(rc==0||rc==ETIMEDOUT);
        int completed_while_locked=reader_done;
        release_writer=1;pthread_cond_broadcast(&sync_cv);pthread_mutex_unlock(&sync_mu);
        assert(!pthread_join(wt,NULL));assert(!pthread_join(rt,NULL));
        while_locked+=completed_while_locked;final+=observed==65536;
#ifdef FIXED
        assert(!completed_while_locked && observed==65536);
#else
        assert(completed_while_locked && observed==32768);
#endif
    }
    printf("{\"variant\":\"%s\",\"reader_completed_while_writer_locked\":%d,\"final_snapshots\":%d,\"concurrent_cases\":10,\"api_cases\":33}\n",
#ifdef FIXED
    "candidate",
#else
    "reference",
#endif
    while_locked,final);
    return 0;
}
'''
for i,p in enumerate(refs):
    fun=extract(p.read_text(),'static int rl_value(')
    (out/('candidate.c' if i else 'reference.c')).write_text(common+fun+'\n'+main)
