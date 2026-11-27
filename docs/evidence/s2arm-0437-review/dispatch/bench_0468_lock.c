// 0468 isolated: rec_put slow path, 2 critical sections (rec_publish + free-block take) vs 1 (swap).
// Same records, same encode worker, same dispatch; only the submit-side block hand-over differs.
#define _GNU_SOURCE
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef struct { uint32_t op, nobj; uint64_t a[15]; } rec_t;
enum { REC_BLK = 256 };
typedef struct rec_blk { struct rec_blk *next; int n; rec_t r[REC_BLK]; } rec_blk;
typedef struct { pthread_mutex_t mu; pthread_cond_t work, idle; rec_blk *cur,*head,*tail,*fl; int busy,sleeping,iw,stop; uint64_t locks, h; } Q;
static double now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1e3+t.tv_nsec*1e-6;}
static void pub(Q*q){ if(!q->cur||!q->cur->n)return; pthread_mutex_lock(&q->mu);q->locks++; q->cur->next=NULL; if(q->tail)q->tail->next=q->cur; else q->head=q->cur; q->tail=q->cur;q->cur=NULL; if(q->sleeping)pthread_cond_signal(&q->work); pthread_mutex_unlock(&q->mu);}
static __attribute__((noinline)) rec_t *put_old(Q*q,uint32_t op){
  if(q->cur&&q->cur->n==REC_BLK)pub(q);
  if(!q->cur){pthread_mutex_lock(&q->mu);q->locks++;q->cur=q->fl;if(q->cur)q->fl=q->cur->next;pthread_mutex_unlock(&q->mu);if(!q->cur)q->cur=malloc(sizeof*q->cur);q->cur->n=0;}
  rec_t*r=&q->cur->r[q->cur->n++];r->op=op;r->nobj=0;return r;}
static __attribute__((noinline)) rec_t *put_new(Q*q,uint32_t op){
  rec_blk*b=q->cur; if(__builtin_expect(b&&b->n<REC_BLK,1)){rec_t*r=&b->r[b->n++];r->op=op;r->nobj=0;return r;}
  pthread_mutex_lock(&q->mu);q->locks++;
  if(b){b->next=NULL;if(q->tail)q->tail->next=b;else q->head=b;q->tail=b;if(q->sleeping)pthread_cond_signal(&q->work);}
  rec_blk*nb=q->fl;if(nb)q->fl=nb->next;pthread_mutex_unlock(&q->mu);
  if(!nb)nb=malloc(sizeof*nb);nb->n=0;nb->next=NULL;q->cur=nb;
  rec_t*r=&nb->r[nb->n++];r->op=op;r->nobj=0;return r;}
static __attribute__((noinline)) void exec1(Q*q,const rec_t*r){ q->h=(q->h^r->op^r->a[0]^(r->a[1]*3)^(r->a[2]*7))*0x100000001b3ull; }
static void*worker(void*arg){Q*q=arg;rec_blk*dh=NULL,*dt=NULL;for(;;){pthread_mutex_lock(&q->mu);
  if(dh){dt->next=q->fl;q->fl=dh;dh=dt=NULL;}
  if(!q->head){if(q->busy){q->busy=0;if(q->iw)pthread_cond_broadcast(&q->idle);} while(!q->head&&!q->stop){q->sleeping=1;pthread_cond_wait(&q->work,&q->mu);q->sleeping=0;} if(!q->head){pthread_mutex_unlock(&q->mu);break;}}
  rec_blk*bu=q->head,*la=bu;int nb=1;while(la->next&&nb<16){la=la->next;nb++;}q->head=la->next;if(!q->head)q->tail=NULL;la->next=NULL;q->busy=1;pthread_mutex_unlock(&q->mu);
  for(rec_blk*b=bu;b;b=b->next){for(int i=0;i<b->n;i++)exec1(q,&b->r[i]);b->n=0;} dh=bu;dt=la;}return NULL;}
static void drain(Q*q){pub(q);pthread_mutex_lock(&q->mu);if(q->head||q->busy){q->iw++;while(q->head||q->busy)pthread_cond_wait(&q->idle,&q->mu);q->iw--;}pthread_mutex_unlock(&q->mu);}
static uint64_t run(int nw,int subs,int recs,double*ms,uint64_t*locks){Q q;memset(&q,0,sizeof q);pthread_mutex_init(&q.mu,0);pthread_cond_init(&q.work,0);pthread_cond_init(&q.idle,0);
  pthread_t th;assert(!pthread_create(&th,0,worker,&q));double t0=now_ms();
  for(int s=0;s<subs;s++){for(int i=0;i<recs;i++){rec_t*r=nw?put_new(&q,i&31):put_old(&q,i&31);r->a[0]=(uint64_t)s*recs+i;r->a[1]=i;r->a[2]=s;} drain(&q);}
  *ms=now_ms()-t0;pthread_mutex_lock(&q.mu);q.stop=1;pthread_cond_signal(&q.work);pthread_mutex_unlock(&q.mu);pthread_join(th,0);
  while(q.fl){rec_blk*b=q.fl;q.fl=b->next;free(b);}free(q.cur);*locks=q.locks;return q.h;}
static int cmp(const void*a,const void*b){double x=*(double*)a,y=*(double*)b;return(x>y)-(x<y);}
int main(int c,char**v){int subs=c>1&&!strcmp(v[1],"--verify")?20:300,recs=c>2?atoi(v[2]):20000; double a,b;uint64_t la,lb;
  uint64_t h=run(0,subs,recs,&a,&la);assert(run(1,subs,recs,&b,&lb)==h);
  if(subs==20){printf("VERIFY PASS hash=%016llx locks %llu->%llu\n",(unsigned long long)h,(unsigned long long)la,(unsigned long long)lb);return 0;}
  enum{P=12};double o[P],n[P],p[P];for(int i=0;i<P;i++){if(i&1){assert(run(1,subs,recs,&b,&lb)==h);assert(run(0,subs,recs,&a,&la)==h);}else{assert(run(0,subs,recs,&a,&la)==h);assert(run(1,subs,recs,&b,&lb)==h);}o[i]=a;n[i]=b;p[i]=100*(b/a-1);}
  qsort(o,P,8,cmp);qsort(n,P,8,cmp);qsort(p,P,8,cmp);
  printf("recs/sub=%d old_med=%.3f new_med=%.3f paired_med=%.2f%% p25=%.2f%% p75=%.2f%% locks %llu->%llu\n",recs,(o[5]+o[6])/2,(n[5]+n[6])/2,(p[5]+p[6])/2,(p[2]+p[3])/2,(p[8]+p[9])/2,(unsigned long long)la,(unsigned long long)lb);}
