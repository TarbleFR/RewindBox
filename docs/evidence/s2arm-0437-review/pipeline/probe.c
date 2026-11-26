#include <assert.h>
#include <stdio.h>
#include <time.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "nvn_obj.h"
#include "nvn_refl.h"
#include "nvn_hmap.h"

#define __bridge
#define __unsafe_unretained
#define nil NULL
#define RED_ONCE(...) ((void)0)
typedef void *id;
typedef struct {nvn_refl rf; int has_atms;} NvShader;
typedef struct {color_st color; chmask_st chmask;ms_st ms;blend_st blend[8];va_st attr[16];vs_st stream[16];int nattr;} state_t;
static state_t *ss;
#define S (*ss)
static int g_look_try_only,async;
static int rb_async_pso(void){return async;}
static nvn_hmap g_pso;
#define hm_get_id(m,k) nvn_hm_get((m),(k))
#include IMPL

static NvShader verts[32],frags[32]; static state_t table[256];static uint32_t fmts[256][8];static uint32_t rseed=42;
static uint32_t rnd(void){rseed=rseed*1664525u+1013904223u;return rseed>>8;}
static uint64_t digest_bytes(const void *bytes,size_t n) {
 const uint8_t *p=bytes; uint64_t h=UINT64_C(14695981039346656037);
 while(n--){h^=*p++;h*=UINT64_C(1099511628211);}
 return h;
}
static uint64_t now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
int main(int argc,char **argv) {
 assert(argc==2);
 int verify=!strcmp(argv[1],"verify"),cold=!strcmp(argv[1],"cold"),warm=!strcmp(argv[1],"warm");
 int sparse=!strcmp(argv[1],"sparse"),merged=!strcmp(argv[1],"merged");
 unsigned batches=verify?256:400, per=256;
 for(int i=0;i<32;i++){
   verts[i].rf.nv=sparse?2:i; for(int j=0;j<verts[i].rf.nv;j++)verts[i].rf.v[j].nvn=rnd()%28;
   frags[i].rf.color_known=rnd()%2;frags[i].rf.color_mask=rnd();
   frags[i].has_atms=rnd()%2;
 }
 for(unsigned i=0;i<256;i++){
   state_t *s=&table[i];s->color.alpha_func=rnd()%15;s->color.blend_en=rnd();s->ms.enable=rnd()%2;s->ms.a2c=rnd()%2;s->chmask.mask=rnd();s->nattr=rnd()%17;
   for(unsigned j=0;j<8;j++){fmts[i][j]=(rnd()%3)?(1+rnd()%90):0;uint8_t *bytes=(uint8_t*)&s->blend[j];for(unsigned k=0;k<sizeof s->blend[0];k++)bytes[k]=rnd();}
   for(unsigned j=0;j<16;j++){s->attr[j].fmt=rnd()%7;s->attr[j].stream=rnd()%32;s->attr[j].offset=rnd()%1024;s->stream[j].stride=rnd()%12;s->stream[j].divisor=rnd()%3;}
 }
 async=1;nvn_hm_init(&g_pso,sizeof(pso_key));
 uint64_t signature=0,refs=0,misses=0;double times[400];static unsigned char vals[256];
 for(unsigned b=0;b<=batches;b++){
   if(cold)nvn_hm_clear(&g_pso,NULL);
   uint64_t t=now();
   for(unsigned j=0;j<per;j++){
    unsigned i=(j*197u)&255u;
    ss=&table[i];
    NvShader *vs=&verts[(i+(verify?b:0))%32],*fs=(i%7==0)?NULL:&frags[(i*7+(verify?b:0))%32];
    pso_key k;int m=verify?(b%2):merged;
    pso_key_fill(&k,vs,fs,fmts[i],i+1,0,i%4,m);
    if(verify){
      assert(k.vs==vs && k.fs==fs && k.fsfn==NULL);
      k.vs=k.fs=k.fsfn=NULL; signature=signature*31+digest_bytes(&k,sizeof k);
    }else if(cold||warm){
      pso_key copy; const pso_key *live; void* value=rb_pso_probe(&k,&copy,&live);
      if(!value){misses++;value=&vals[i];nvn_hm_put(&g_pso,live,value);}
      assert(value==&vals[i]);refs+=i;
    }else{
      __asm__ volatile(""::"m"(k):"memory");
    }
   }
   if(b)times[b-1]=(now()-t)/1e6;
 }
 double sum=0;for(unsigned i=0;i<batches;i++)sum+=times[i];
 for(unsigned i=0;i<batches;i++)for(unsigned j=i+1;j<batches;j++)if(times[i]>times[j]){double tmp=times[i];times[i]=times[j];times[j]=tmp;}
 printf("%.6f %.6f %.6f %016llx %llu %llu %zu\n",sum,times[batches/2],times[batches*95/100],(unsigned long long)signature,(unsigned long long)refs,(unsigned long long)misses,sizeof(pso_key));
 free(g_pso.keys);free(g_pso.vals);
}
