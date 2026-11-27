from pathlib import Path
import argparse
p=argparse.ArgumentParser(); p.add_argument('--source',required=True); p.add_argument('--output',required=True); a=p.parse_args()
s=Path(a.source).read_text()
h=s[s.index('static struct { uint32_t kind; uint16_t gen; void *obj; uint64_t cookie; } g_h[MAX_H];'):s.index('// 事件对象号')]
b=s[s.index('    case 0x08: {  // CreateThread'):s.index('        // 宿主栈 1 MB：',s.index('    case 0x08: {  // CreateThread'))]
head=r'''
#define _GNU_SOURCE
#define S2A_UNIT_TEST
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <errno.h>
#define MAX_H 8192
#define LIM_THREADS 608
#define LIM_HANDLES 1024
#define S2A_OBJ_THREAD 1
#define S2A_OBJ_EVENT_R 2
#define S2A_OBJ_EVENT_W 3
#define S2A_OBJ_SESSION 4
#define S2A_OBJ_SHMEM 5
#define S2A_OBJ_TMEM 6
#define R_OUT_OF_RES 0xd201
#define LOG(...) ((void)0)
typedef struct thr { struct thr *all; int exited; pthread_cond_t cv; _Atomic int in_svc; uint64_t entry,arg,stack_top,mask,id; int prio,core,base_prio; uint32_t handle; } thr_t;
static pthread_mutex_t G=PTHREAD_MUTEX_INITIALIZER;
static pthread_barrier_t barrier;
static thr_t *g_all;
static int g_h_used,g_h_peak,g_kcnt[16],g_kpeak[16];
static int g_hw_cores=8,g_def_core;
static uint64_t g_cap_core,g_cap_prio,g_next_id;
static int failure_mode;
static int lim_on(void){return 1;}
static void glock(void){pthread_mutex_lock(&G);}
static int hz_core(void){return 0;}
static int hstk_reap(int all){(void)all;if(!failure_mode)pthread_barrier_wait(&barrier);return 0;}
static void *review_calloc(size_t n,size_t z){if(failure_mode==1)return NULL;return calloc(n,z);}
static int review_cond_init(pthread_cond_t*c,const pthread_condattr_t*a){if(failure_mode==2)return EAGAIN;return pthread_cond_init(c,a);}
#define calloc review_calloc
#define pthread_cond_init review_cond_init
'''
tail=r'''
static void* creator(void*arg){uint64_t*r=arg;r[4]=44;create(r);return NULL;}
static int count_threads(void){int n=0;for(thr_t*t=g_all;t;t=t->all)n+=!t->exited;return n;}
int main(int argc,char**argv){
 failure_mode=argc>1?atoi(argv[1]):0;
 if(failure_mode){uint64_t r[8]={0};r[4]=44;create(r);printf("failure=%d result=%llx live=%d handles=%d\n",failure_mode,(unsigned long long)r[0],count_threads(),g_h_used);return 0;}
 int wrong=0;
 for(int round=0;round<100;round++){
  for(int j=0;j<607;j++){thr_t*t=review_calloc(1,sizeof*t);review_cond_init(&t->cv,NULL);t->all=g_all;g_all=t;}
  pthread_barrier_init(&barrier,NULL,2);
  uint64_t a[8]={0},b[8]={0}; pthread_t pa,pb;
  pthread_create(&pa,NULL,creator,a);pthread_create(&pb,NULL,creator,b);pthread_join(pa,NULL);pthread_join(pb,NULL);
  int count=count_threads();int good=count==608&&((a[0]==0&&b[0]==0x10801)||(b[0]==0&&a[0]==0x10801));wrong+=!good;
  if(!round)printf("race count=%d a=%llx b=%llx\n",count,(unsigned long long)a[0],(unsigned long long)b[0]);
  while(g_all){thr_t*t=g_all;g_all=t->all;pthread_cond_destroy(&t->cv);free(t);}
  memset(g_h,0,sizeof g_h);memset(g_h_live,0,sizeof g_h_live);g_h_used=g_h_peak=0;memset(g_kcnt,0,sizeof g_kcnt);memset(g_kpeak,0,sizeof g_kpeak);pthread_barrier_destroy(&barrier);
 }
 printf("rounds=100 mismatches=%d\n",wrong);return wrong?2:0;
}
'''
Path(a.output).write_text(head+h+'\nstatic int create(uint64_t *regs){switch(0x08){\n'+b+'\nregs[0]=0; regs[1]=t->handle;return 1; } } return 0;}\n#undef calloc\n#undef pthread_cond_init\n'+tail)
