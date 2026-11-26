#define _POSIX_C_SOURCE 200809L
#include "nvn_deswizzle.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <assert.h>
extern int base_nvn_deswizzle(const nvn_texdesc *,unsigned,unsigned,const void*,void*,size_t);
extern int candidate_nvn_deswizzle(const nvn_texdesc *,unsigned,unsigned,const void*,void*,size_t);
extern int base_nvn_swizzle(const nvn_texdesc *,unsigned,unsigned,const void*,size_t,void*);
extern int candidate_nvn_swizzle(const nvn_texdesc *,unsigned,unsigned,const void*,size_t,void*);
extern int base_nvn_deswizzle_from(const nvn_texdesc *,unsigned,unsigned,const void*,uint64_t,void*,size_t);
extern int candidate_nvn_deswizzle_from(const nvn_texdesc *,unsigned,unsigned,const void*,uint64_t,void*,size_t);
int main(void) {
    const size_t size=262144;
    FILE *f=tmpfile();assert(f && !ftruncate(fileno(f),size));
    uint8_t *m1=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fileno(f),0),*m2=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fileno(f),0);
    assert(m1!=MAP_FAILED && m2!=MAP_FAILED && m1!=m2);
    uint8_t *orig=malloc(size),*expect=malloc(size),*row=malloc(1024);
    uint32_t rnd=451;for(size_t i=0;i<size;i++){rnd^=rnd<<13;rnd^=rnd>>17;rnd^=rnd<<5;orig[i]=(uint8_t)rnd;}
    int sizes[]={16,32,64,128,256,512,1024},heights[]={3,5,13,32,128};int fails[3]={0},tests[3]={0};
    for(int i=0;i<7;i++)for(int j=0;j<5;j++)for(int inverse=0;inverse<2;inverse++)for(int dir=0;dir<3;dir++)for(int shift=0;shift<2;shift++) {
        int rb=sizes[i],n=heights[j];nvn_texdesc d={.target=1,.flags=0x10,.format=1,.width=rb,.height=n,.stride=rb,.levels=1};
        size_t a=shift?rb:0,b=shift?0:rb;
        uint8_t *s=(inverse?m2:m1)+a,*dst=(inverse?m1:m2)+b;
        memcpy(expect,orig,size);
        for(int k=0;k<n;k++){memcpy(row,expect+a+k*rb,rb);memcpy(expect+b+k*rb,row,rb);}
        for(int variant=0;variant<2;variant++) {
            memcpy(m1,orig,size);int r;
            if(dir==0)r=variant?candidate_nvn_deswizzle(&d,0,0,s,dst,rb):base_nvn_deswizzle(&d,0,0,s,dst,rb);
            else if(dir==1)r=variant?candidate_nvn_swizzle(&d,0,0,s,rb,dst):base_nvn_swizzle(&d,0,0,s,rb,dst);
            else r=variant?candidate_nvn_deswizzle_from(&d,0,0,s,0,dst,rb):base_nvn_deswizzle_from(&d,0,0,s,0,dst,rb);
            assert(r==0 && !memcmp(m2,m1,size));
            int changed=!!memcmp(m1,expect,size);
            if(!variant)assert(!changed);
            else {fails[dir]+=changed;tests[dir]++;}
        }
    }
    for(int dir=0;dir<3;dir++){
        printf("public=%d intervals virtually disjoint; reference mismatches=0/%d; candidate mismatches=%d/%d\n",dir,tests[dir],fails[dir],tests[dir]);assert(fails[dir]>0);
    }
    free(row);free(expect);free(orig);munmap(m1,size);munmap(m2,size);fclose(f);
}
