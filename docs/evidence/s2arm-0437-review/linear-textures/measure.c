#define _POSIX_C_SOURCE 200809L
#include "nvn_deswizzle.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef int (*Read)(const nvn_texdesc *, unsigned, unsigned, const void *, void *, size_t);
typedef int (*Write)(const nvn_texdesc *, unsigned, unsigned, const void *, size_t, void *);
typedef int (*From)(const nvn_texdesc *, unsigned, unsigned, const void *, uint64_t, void *, size_t);
#define DECL(x) extern int x##_nvn_deswizzle(const nvn_texdesc *,unsigned,unsigned,const void *,void *,size_t); \
    extern int x##_nvn_swizzle(const nvn_texdesc *,unsigned,unsigned,const void *,size_t,void *); \
    extern int x##_nvn_deswizzle_from(const nvn_texdesc *,unsigned,unsigned,const void *,uint64_t,void *,size_t)
DECL(base); DECL(candidate); DECL(control);
static Read readers[]={base_nvn_deswizzle,candidate_nvn_deswizzle,control_nvn_deswizzle};
static Write writers[]={base_nvn_swizzle,candidate_nvn_swizzle,control_nvn_swizzle};
static From offsets[]={base_nvn_deswizzle_from,candidate_nvn_deswizzle_from,control_nvn_deswizzle_from};
static void geometry(const nvn_texdesc *d, size_t *rb, size_t *rows, size_t *sp) {
    int bw,bh;
    int bpb=nvn_fmt_bpb(d->format,&bw,&bh);
    assert(bpb>0);
    *rb=(d->width+bw-1)/bw*bpb;
    *rows=(d->height+bh-1)/bh;
    nvn_texlayout l;nvn_tex_layout(d,&l);assert(*rows && l.size%*rows==0);
    *sp=l.size/ *rows;
}
static void init(uint8_t *p, size_t n) {
    uint32_t v=59384715;
    for(size_t i=0;i<n;++i) {v^=v<<13;v^=v>>17;v^=v<<5;p[i]=(uint8_t)v;}
}
static long functional(void) {
    int formats[]={0x01,0x25,0x42,0x8b};
    int widths[]={13,32,79};
    int heights[]={1,17,37};
    long tests=0,alias_tests=0;
    for(int f=0;f<4;f++)for(int w=0;w<3;w++)for(int h=0;h<3;h++)
    for(int rt=0;rt<2;rt++)for(int gs=0;gs<3;gs++)for(int lp=0;lp<2;lp++){
        nvn_texdesc d={.target=1,.flags=rt?0x40:0x10,.format=formats[f],.width=widths[w],.height=heights[h],.levels=1};
        size_t rb,rows,sp;geometry(&d,&rb,&rows,&sp);
        d.stride=gs==0 ? 0 : (uint32_t)rb + (gs==2 ? 11 : 0);
        geometry(&d,&rb,&rows,&sp);
        size_t pitch=rb+(lp?19:0), maxstep=sp>pitch?sp:pitch, span=rows*maxstep;
        // Offsets around one complete row, adjacency, and one byte of global overlap.
        size_t offs[]={rb,rb+1,2*maxstep,span-1,span,span+7};
        size_t n=2*span+2*maxstep+127;
        uint8_t *initbuf=malloc(n),*expected=malloc(n),*actual=malloc(n),*row=malloc(rb);
        assert(initbuf&&expected&&actual&&row);init(initbuf,n);
        for(int k=0;k<6;k++)for(int sign=0;sign<2;sign++)for(int direction=0;direction<3;direction++){
            size_t a=29+(sign?offs[k]:0),b=29+(sign?0:offs[k]);
            int defined=1;for(size_t y=0;y<rows;++y){
                size_t m=a+y*sp,l=b+y*pitch;
                if(l<m+rb && m<l+rb){defined=0;break;}
            }
            if(!defined)continue; // Per-row memcpy in the baseline excludes overlap within a single row.
            memcpy(expected,initbuf,n);for(size_t y=0;y<rows;y++) {
                size_t m=a+y*sp,l=b+y*pitch;
                size_t src=direction==1?l:m, dst=direction==1?m:l;
                memcpy(row,expected+src,rb);memcpy(expected+dst,row,rb);
            }
            for(int v=0;v<3;v++) {
                memcpy(actual,initbuf,n);int rc;
                if(direction==0)rc=readers[v](&d,0,0,actual+a,actual+b,pitch);
                else if(direction==1)rc=writers[v](&d,0,0,actual+b,pitch,actual+a);
                else rc=offsets[v](&d,0,0,actual+a,0,actual+b,pitch);
                assert(rc==0 && !memcmp(actual,expected,n));
            }
            ++tests;
            if((a+(rows-1)*sp+rb>b) && (b+(rows-1)*pitch+rb>a))++alias_tests;
        }
        free(row);free(actual);free(expected);free(initbuf);
    }
    nvn_texdesc d={.target=1,.flags=0x10,.format=0x25,.width=32,.height=4,.levels=1,.stride=128};
    uint8_t m[560],l[560],old[560];memset(m,0xb2,sizeof m);memset(l,0xc3,sizeof l);memcpy(old,l,sizeof l);
    for(int v=0;v<3;v++) {
        assert(readers[v](&d,1,0,m,l,128)==-1 && readers[v](&d,0,1,m,l,128)==-1);
        assert(readers[v](&d,0,0,m,l,127)==-1 && offsets[v](&d,0,0,m,1,l,128)==-1);
        nvn_texdesc bad=d;bad.samples=2;assert(readers[v](&bad,0,0,m,l,128)==-1);
        bad=d;bad.stride=127;assert(readers[v](&bad,0,0,m,l,128)==-1);
        bad=d;bad.format=999;assert(readers[v](&bad,0,0,m,l,128)==-1);
        bad=d;bad.height=0;assert(readers[v](&bad,0,0,m,l,128)==-1);
        assert(!memcmp(l,old,sizeof l));
    }
    printf("valid_cases=%ld cross_row_overlap=%ld functions=3 variants=3 invalid_cases=8\n",tests,alias_tests);
    return tests;
}
typedef struct {const char *name;int format,width,height,spad,lpad,repeat,banks;} Case;
static const Case cases[]={
#if defined(S2_LINEAR_FOLLOWUP)
    {"reuse-1080p",0x25,1920,1080,0,0,10,1},
    {"reuse-2160p",0x25,3840,2160,0,0,4,1},
    {"odd-tall",0x25,1919,1081,0,0,8,4},
    {"two-row-large",0x25,8192,2,0,0,500,4},
    {"consume-1080p",0x25,1920,1080,0,0,8,4},
    {"consume-2160p",0x25,3840,2160,0,0,3,3}
#else
    {"tiny-rgba",0x25,8,2,0,0,90000,1},
    {"single-row",0x25,64,1,0,0,90000,1},
    {"short-rows",0x01,32,512,0,0,2700,4},
    {"bc1-odd",0x42,127,127,0,0,4500,4},
    {"astc-odd",0x8b,193,145,0,0,3000,4},
    {"storage-padding",0x25,63,65,4,0,2500,4},
    {"client-padding",0x25,64,65,0,8,2500,4},
    {"rgba-512",0x25,512,512,0,0,40,4},
    {"rgba-720p",0x25,1280,720,0,0,16,4},
    {"rgba-1080p",0x25,1920,1080,0,0,8,4},
    {"rgba-2160p",0x25,3840,2160,0,0,3,3}
#endif
};
static double cpu_ns(void) {struct timespec ts;assert(!clock_gettime(CLOCK_THREAD_CPUTIME_ID,&ts));return ts.tv_sec*1e9+ts.tv_nsec;}
static int permutation[6][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
static void timing(void) {
    puts("case,direction,pair,variant,bytes,banks,iterations,ns_per_copy");
    for(size_t n=0;n<sizeof cases/sizeof cases[0];n++){
        const Case *c=&cases[n];
        nvn_texdesc d={.target=1,.flags=0x10,.format=c->format,.width=c->width,.height=c->height,.levels=1};
        size_t rb,rows,sp;geometry(&d,&rb,&rows,&sp);d.stride=(uint32_t)(rb+c->spad);
        geometry(&d,&rb,&rows,&sp);
        const size_t pitch=rb+c->lpad, block=(((pitch>sp?pitch:sp)*rows+127)&~(size_t)63);
        uint8_t *guest,*linear;
        assert(!posix_memalign((void**)&guest,64,block*c->banks));
        assert(!posix_memalign((void**)&linear,64,block*c->banks));
        init(guest,block*c->banks);init(linear,block*c->banks);
        for(int pair=0;pair<=12;++pair)for(int dd=0;dd<2;dd++){
            int dir=dd^(pair&1);
            for(int ord=0;ord<3;ord++){
                int v=permutation[(pair+dir+n)%6][ord];
#ifdef S2_LINEAR_FOLLOWUP
                volatile unsigned long long observed=0;
                const int sample_after = !strncmp(c->name,"consume",7);
#endif
                double start=cpu_ns();
                for(int j=0;j<c->repeat;++j) {
                    size_t off=(size_t)(j%c->banks)*block;
                    int rc=dir ? writers[v](&d,0,0,linear+off,pitch,guest+off) : readers[v](&d,0,0,guest+off,linear+off,pitch);
                    if(rc) abort();
#ifdef S2_LINEAR_FOLLOWUP
                    if(sample_after) {
                        const uint8_t *written=(dir?guest:linear)+off;
                        unsigned long long checksum=0;
                        for(size_t i=0;i<rb*rows;i+=64)checksum+=written[i];
                        observed^=checksum;
                    }
#endif
                }
                double ns=cpu_ns()-start;
                if(pair)printf("%s,%d,%d,%d,%zu,%d,%d,%.3f\n",c->name,dir,pair,v,rb*rows,c->banks,c->repeat,ns/c->repeat);
            }
        }
        free(guest);free(linear);
    }
}
int main(int argc,char **argv) {if(argc==2 && !strcmp(argv[1],"verify"))return functional()?0:1;timing();return 0;}
