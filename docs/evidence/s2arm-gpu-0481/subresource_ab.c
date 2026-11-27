#define _POSIX_C_SOURCE 200809L
#include "nvn_deswizzle.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { Guard=33, Page=16384, Pairs=12, Repeats=8 };
static unsigned accepted, rejected;
static volatile uint8_t sample;
static uint64_t clock_ns(void) {
    struct timespec t;
    assert(clock_gettime(CLOCK_MONOTONIC,&t)==0);
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+t.tv_nsec;
}
static void fill(uint8_t *p,size_t n) {
    uint32_t state=983254;
    for (size_t i=0;i<n;i++) {
        state ^= state << 13; state ^= state >> 17; state ^= state << 5;
        p[i]=(uint8_t)state;
    }
}
static void refusal(nvn_texdesc d,size_t size,unsigned l,unsigned a,uint64_t first,uint64_t end,uint64_t masks) {
    nvn_rect_level g;
    memset(&g,0xa5,sizeof g);
    assert(nvn_rect_level_span(&d,size,l,a,first,end,masks,&g)!=0);
    for (size_t i=0;i<sizeof g;i++) assert(((uint8_t *)&g)[i]==0xa5);
    ++rejected;
}
static nvn_texdesc array(void) {
    return (nvn_texdesc){.target=4,.format=0x25,.width=1024,.height=1024,.depth=4,.levels=6,.samples=1};
}
static void negatives(void) {
    nvn_texdesc d=array();
    nvn_texlayout L; nvn_tex_layout(&d,&L);
    const uint64_t base=2*L.layer_size+nvn_tex_level_offset(&d,1);
    const uint64_t end=base+1048576, page=base+Page;
    assert(L.size==22380544 && L.layer_size==5595136 && base==15384576 && page==15400960);
    refusal(d,L.size,1,2,base-8192,base+8192,0); // adjacent mip before this one
    refusal(d,L.size,1,2,end-8192,end+8192,0);  // adjacent mip after this one
    refusal(d,L.size,1,2,page,page+Page+L.layer_size,0); // disjoint layer dirty too
    refusal(d,L.size,1,2,page,page+Page,1u);    // interior run boundary is not GOB-column aligned
    refusal(d,L.size,1,2,page+1,page+Page,0);
    refusal(d,L.size,1,2,page,page+Page-1,0);
    refusal(d,page+Page-1,1,2,page,page+Page,0);
    refusal(d,L.size,3,2,page,page+Page,0);
    refusal(d,L.size,1,4,page,page+Page,0);
    refusal(d,L.size,1,2,page,page,0);
    refusal(d,L.size,32,2,page,page+Page,0);
    d.flags=0x20; refusal(d,L.size,1,2,page,page+Page,0);
    d.flags=0x40; refusal(d,L.size,1,2,page,page+Page,0);
    d.flags=0; d.samples=2; refusal(d,L.size,1,2,page,page+Page,0);
    d.samples=1; d.target=2; refusal(d,L.size,1,2,page,page+Page,0);
    d.target=7; refusal(d,L.size,1,2,page,page+Page,0);
    d=array(); d.width=1031; nvn_tex_layout(&d,&L);
    uint64_t at=nvn_tex_level_offset(&d,1);
    refusal(d,L.size,1,0,at,at+Page,0);    // padded GOB on the right
    d=array(); d.height=1033; nvn_tex_layout(&d,&L);
    at=nvn_tex_level_offset(&d,1);
    refusal(d,L.size,1,0,at,at+Page,0);   // padded block row at the bottom
    d=array(); nvn_tex_layout(&d,&L);
    uint64_t tail=nvn_tex_level_offset(&d,d.levels);
    assert(tail < L.layer_size);
    refusal(d,L.size,5,0,tail-512,L.layer_size+512,0); // end-of-layer padding and next layer
}
static void one(nvn_texdesc d,unsigned level,unsigned layer) {
    nvn_texlayout L; nvn_tex_layout(&d,&L);
    uint32_t pitch,rows,slices,bpb,gobs; unsigned th,td; uint64_t base;
    assert(!nvn_deswizzle_geom_ex(&d,level,layer,&pitch,&rows,&slices,&base,&th,&td,&bpb,&gobs));
    uint64_t column=UINT64_C(512)<<th;
    size_t texel_rows=8u<<th, bytes=(size_t)pitch*rows;
    uint8_t *src=malloc(L.size), *full=malloc(bytes);
    assert(src && full); fill(src,L.size);
    for(int order=0;order<2;order++) {
        nvn_gob_switch2=order;
        assert(!nvn_deswizzle(&d,level,layer,src,full,pitch));
        for(unsigned y=0;y<rows;y+=texel_rows) for(unsigned x=0;x+128<=pitch;x+=128) {
            size_t lo=base+nvn_bl_offset(x,y,0,gobs*64,rows,th,td);
            size_t hi=lo+2*column;
            nvn_rect_level g;
            assert(!nvn_rect_level_span(&d,L.size,level,layer,lo,hi,lo^hi,&g));
            assert(g.base==base && g.end==base+bytes);
            size_t n=128*texel_rows;
            uint8_t *out=malloc(n+2*Guard);
            assert(out); memset(out,0xa5,n+2*Guard);
            assert(!nvn_deswizzle_rect_level(&g,src,L.size,x,y,128,texel_rows,out+Guard));
            for(size_t r=0;r<texel_rows;r++)
                assert(!memcmp(out+Guard+r*128,full+(y+r)*(size_t)pitch+x,128));
            for(int i=0;i<Guard;i++) assert(out[i]==0xa5 && out[n+Guard+i]==0xa5);
            memset(out,0xa5,n+2*Guard);
            assert(nvn_deswizzle_rect_level(&g,src,g.end-1,x,y,128,texel_rows,out+Guard));
            for(size_t i=0;i<n+2*Guard;i++) assert(out[i]==0xa5);
            free(out); ++accepted;
        }
    }
    free(src);free(full);
}
static void parity(void) {
    negatives();
    const int formats[]={0x25,0x42,0x8b};
    for(unsigned i=0;i<3;i++) {
        nvn_texdesc d=array(); d.format=formats[i];
        if(i==2) d.width=d.height=1536; // ASTC 6x6, integral block rows at the test mips.
        one(d,1,2); one(d,2,0);
        d.target=1; d.depth=1; one(d,1,0);
    }
    printf("parity_cases=%u rejected_spans=%u formats=RGBA8,BC1,ASTC6x6 orders=2 targets=2D-array,2D\n",accepted,rejected);
}
static void bench(void) {
    nvn_texdesc d=array(); nvn_texlayout L; nvn_tex_layout(&d,&L);
    uint8_t *src=malloc(L.size), *full=malloc(1048576), *rect=malloc(Page);
    assert(src&&full&&rect); fill(src,L.size);
    memset(full,0,1048576); memset(rect,0,Page);
    puts("pair,position,mode,calls,prepared_bytes_per_call,physical_first,physical_end,wall_ns");
    nvn_gob_switch2=1;
    const uint64_t first=15400960, end=first+Page;
    for(int pair=-1;pair<Pairs;pair++){
        for(int pos=0;pos<2;pos++){
            int tight=(pos==1)^(pair>=0&&(pair&1));
            uint64_t t=clock_ns();
            for(int iter=0;iter<Repeats;iter++) {
                if(tight) {
                    nvn_rect_level g;
                    assert(!nvn_rect_level_span(&d,L.size,1,2,first,end,first^end,&g));
                    assert(!nvn_deswizzle_rect_level(&g,src,L.size,128,0,128,128,rect));
                    sample ^= rect[iter];
                } else {
                    assert(!nvn_deswizzle(&d,1,2,src,full,2048));
                    sample ^= full[128+iter];
                }
            }
            uint64_t elapsed=clock_ns()-t;
            if(pair>=0) printf("%d,%d,%s,%d,%d,%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",pair+1,pos+1,
                tight?"rect":"full",Repeats,tight?Page:1048576,first,end,elapsed);
        }
    }
    free(src); free(full); free(rect);
}
int main(int argc,char **argv) {
    if(argc==1) parity();
    else if(argc==2&&!strcmp(argv[1],"--time")) bench();
    else return 2;
    return 0;
}
