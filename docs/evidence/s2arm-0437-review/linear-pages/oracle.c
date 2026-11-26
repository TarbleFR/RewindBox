#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nvn_tex.h"
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
typedef struct { nvn_texdesc d; nvn_texlayout L; } tex_t;
#include IMPL

typedef struct { unsigned w,h,bw,bh,bpb,nx,ny,count; uint64_t pitch; uint8_t *seen; } result;
static void pixels(void *user, unsigned l,unsigned a,uint32_t x,uint32_t y,uint32_t w,uint32_t h) {
    result *r=user;
    assert(!l&&!a&&w&&h&&x<r->w&&y<r->h&&w<=r->w-x&&h<=r->h-y);
    assert(x%r->bw==0&&y%r->bh==0); ++r->count;
    for(unsigned v=y;v<y+h;v+=r->bh) for(unsigned u=x;u<x+w;u+=r->bw){
        uint8_t *k=&r->seen[v/r->bh*r->nx+u/r->bw];
        assert(!*k);*k=1;
    }
}
static void span(void *user,uint64_t a,uint64_t b) {
    result *r=user; assert(a<b && b<=r->pitch*r->ny);++r->count;
    for(;a<b;++a){ assert(!r->seen[a]);r->seen[a]=1; }
}
static uint32_t random_state=1;
static unsigned sample(unsigned n){ random_state=random_state*1664525u+1013904223u;return random_state%n; }
int main(void) {
    const unsigned formats[]={1,0x25,0x42,0x8b};
    unsigned ranges=0,regions=0,wide=0,incorrect=0;
    for(unsigned k=0;k<60;k++) {
        tex_t t={.d={.width=27+k%5,.height=33+k%7,.levels=1,.target=1,.flags=(int[]){0x10,0x40,0x50}[k%3],.format=formats[k%4]}};
        int bw,bh;int bpb=nvn_fmt_bpb(t.d.format,&bw,&bh);assert(bw>0&&bh>0&&bpb>0);
        result r={.w=t.d.width,.h=t.d.height,.bw=bw,.bh=bh,.bpb=bpb,
                  .nx=(t.d.width+bw-1)/bw,.ny=(t.d.height+bh-1)/bh};
        if(k%5) t.d.stride=r.nx*bpb+((k/5)%5)*4;
        nvn_tex_layout(&t.d,&t.L);r.pitch=t.L.size/r.ny;
        r.seen=malloc(t.L.size);assert(r.seen);
        for(unsigned i=0;i<128;i++){
            uint64_t a=sample(t.L.size+8),b=sample(t.L.size+8);
            if(i%4==0)b=a+1;else if(i%4==1)b=a;else if(i%4==2)b=t.L.size;
            if(b<a){uint64_t tmp=a;a=b;b=tmp;}
            if(i==0){a=0;b=t.L.size;}
            memset(r.seen,0,t.L.size);r.count=0;
            tex_bytes_rects(&t,a,b,pixels,&r);assert(r.count<=3);
            size_t bad=0;
            for(unsigned y=0;y<r.ny;++y)for(unsigned x=0;x<r.nx;++x){
                uint64_t off=y*r.pitch+x*bpb;
                int hit=a<b && a<off+bpb && off<b;
                bad+=hit!=r.seen[y*r.nx+x];
            }
            incorrect+=!!bad;ranges++;
            unsigned x=sample(r.w),y=sample(r.h),w=1+sample(r.w-x),h=1+sample(r.h-y);
            if(i==0){x=y=0;w=h=0;}
            memset(r.seen,0,t.L.size);r.count=0;tex_rect_bytes(&t,0,0,x,y,w,h,span,&r);
            bad=0;
            for(unsigned v=0;v<r.ny;v++)for(unsigned u=0;u<r.pitch;u++){
                unsigned xx=(u/bpb)*r.bw,yy=v*r.bh;
                int hit=!w||!h||(u<r.nx*bpb && x<xx+r.bw && xx<x+w && y<yy+r.bh && yy<y+h);
                bad+=hit!=r.seen[v*r.pitch+u];
            }
            wide+=!!bad;regions++;
        }
        free(r.seen);
    }
    printf("byte ranges=%u incorrect=%u ; GPU regions=%u incorrect=%u\n",ranges,incorrect,regions,wide);
#ifdef EXPECT_FIXED
    assert(!incorrect&&!wide);
#else
    assert(incorrect&&wide);
#endif
}
