#include <stdio.h>
#include <time.h>
#include "nvn_hmap.h"
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1e9+t.tv_nsec;}
int main(){ enum{N=1024,L=400000}; static uint8_t k[N*344]; for(int i=0;i<N*344;i++)k[i]=(uint8_t)(i*7);
 for(int len=184;len<=344;len+=160){ volatile uint64_t acc=0; double t=now(); for(int i=0;i<L;i++){acc+=nvn_hm_slot_hash(k+((unsigned)(i*2246822519u)&(N-1))*len,len);} double th=(now()-t)/L;
  t=now(); for(int i=0;i<L;i++){unsigned a=(unsigned)(i*2246822519u)&(N-1); acc+=nvn_hm_eq(k+a*len,k+a*len,len);} double te=(now()-t)/L;
  nvn_hmap m; nvn_hm_init(&m,len); for(int i=0;i<N;i++){memcpy(k+i*len,&i,4); nvn_hm_put(&m,k+i*len,(void*)(uintptr_t)(i+1));}
  t=now(); for(int i=0;i<L;i++){acc+=(uintptr_t)nvn_hm_get(&m,k+((unsigned)(i*2246822519u)&(N-1))*len);} double tg=(now()-t)/L;
  printf("len %d hash %.1f ns eq %.1f ns get %.1f ns\n",len,th,te,tg);}
}
