#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/mman.h>
#include <time.h>
#include <assert.h>
#include "nvn_dirty.h"
void dm_fault_hook_register(int (*fn)(void *,int,void *)) {(void)fn;}
void dm_guest_write_prep_register(void (*fn)(void *,size_t)) {(void)fn;}
void dm_log(const char *fmt,...) {(void)fmt;}
static unsigned long long now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (unsigned long long)t.tv_sec*1000000000+t.tv_nsec;}
int main(int argc,char **argv){
const unsigned n=atoi(argv[1]),pages=atoi(argv[2]);const size_t pg=getpagesize(),stride=(pages+1)*pg,count=1000000;
uint8_t *pool=mmap(NULL,n*stride,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE,-1,0);
const void **span=calloc(n,sizeof(*span));assert(pool!=MAP_FAILED&&span);
for(unsigned i=0;i<n;i++){nvn_dirty_add_range(pool+i*stride,pages*pg);span[i]=nvn_dirty_span(pool+i*stride+pg*2,pg);}
uint64_t stamp=nvn_dirty_now(),hash=0,s=42,t0=now();
for(size_t j=0;j<count;j++){s=(s*1664525u+1013904223u)&0xffffffffu;unsigned i=(s>>6)%n;unsigned p=2+((s>>16)%(pages-5));uint8_t *addr=pool+i*stride+p*pg;hash=hash*31+nvn_dirty_range_writes(&span[i],addr,2*pg);hash=hash*31+nvn_dirty_since_span(span[i],addr,2*pg,stamp);}
printf("%u %u %f %llu\n",n,pages,(now()-t0)/1e6,(unsigned long long)hash);
}
