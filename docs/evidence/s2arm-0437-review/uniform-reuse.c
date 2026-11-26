#include "rb_ubo_versions.h"
#include <stdio.h>
#include <assert.h>
#include <stdlib.h>
static rb_ub_versions ring;
static _Alignas(4096) uint8_t guest[8192], replacement[4096], output[4096], have[4096], expected[4096], written[4096];
int main(void) {
 printf("ring=%zu frame=%zu page=%zu\n",sizeof ring,sizeof ring.frames[0], sizeof ring.pool[0]);
 for (int k=0;k<4096;k++){guest[k]=(uint8_t)(k+3);replacement[k]=(uint8_t)(k*3+73);}
 uint32_t rnd=69;
 for(unsigned round=0;round<1800;round++){
   uint64_t fence=1+round*RB_UB_FRAMES; unsigned base=round%2*4096;
   rb_ub_frame *frame=rb_ub_begin(&ring,fence);ring.pool_cursor=0;
   memset(ring.pool[0].valid,0xff,sizeof ring.pool[0].valid);memset(ring.pool[0].bytes,0x66,sizeof ring.pool[0].bytes);
   memcpy(expected,guest+base,4096);memset(written,0,4096);
   for(unsigned j=0;j<12;j++){
     rnd=rnd*1664525u+1013904223u;unsigned off=(rnd>>7)%4000,len=1+((rnd>>21)%96);
     rb_ub_capture(frame,(uintptr_t)(guest+base+off),len,replacement+off);
     memcpy(expected+off,replacement+off,len);memset(written+off,1,len);
   }
   for(int m=0;m<4096;m++){have[m]=(m%83)==0;output[m]=have[m]?77:0;}
   assert(rb_ub_base(&ring,fence-1,fence,(uintptr_t)(guest+base),(uintptr_t)(guest+base+4096),output,have));
   for(int m=0;m<4096;m++){assert(output[m]==(m%83==0?77:expected[m]));assert((have[m]!=0)==(written[m]||m%83==0));}
 }
 puts("1800 recycled slots exact");
}
