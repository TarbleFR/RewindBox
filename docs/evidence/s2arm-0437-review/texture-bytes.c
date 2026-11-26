#include "nvn_deswizzle.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int ref_nvn_gob_switch2;
extern __typeof__(nvn_deswizzle) ref_nvn_deswizzle;
extern __typeof__(nvn_swizzle) ref_nvn_swizzle;
extern __typeof__(nvn_deswizzle_from) ref_nvn_deswizzle_from;
extern __typeof__(nvn_deswizzle_tile_mode) ref_nvn_deswizzle_tile_mode;

static uint64_t seed = UINT64_C(0xdbda82063604bbe3);
static unsigned checks, regular, sparse, sparse_full, sparse_partial, sparse_empty;
static size_t compared;
enum { GUARD=37 };
static void fill(uint8_t *p, size_t len) {
    for(size_t i=0; i<len;) {
        seed ^= seed >> 12; seed ^= seed << 25; seed ^= seed >> 27;
        uint64_t w=seed*UINT64_C(0x2545F4914F6CDD1D);
        size_t n=len-i<sizeof w ? len-i : sizeof w;
        memcpy(p+i,&w,n);
        i+=n;
    }
}
static void check_bytes(const uint8_t *a,const uint8_t *b,size_t n) {
    if(memcmp(a,b,n)){fprintf(stderr,"diff at check %u, seed %llu\n",checks,(unsigned long long)seed);abort();}
    for(unsigned i=0;i<GUARD;i++)assert(a[i]==0xca&&a[n-i-1]==0xca);
    checks++;compared+=n;
}
static void one(const nvn_texdesc *d,unsigned level,unsigned layer) {
    uint32_t wb,rows,slices,bpb; unsigned th,td; uint64_t base;
    if (nvn_deswizzle_geom(d,level,layer,&wb,&rows,&slices,&base,&th,&td,&bpb))return;
    nvn_texlayout layout;
    nvn_tex_layout(d,&layout);
    assert(layout.size && base<layout.size);
    const size_t pitch=wb+(checks%19);
    size_t ln=pitch*rows*slices,bn=layout.size,cap=ln>bn?ln:bn;
    uint8_t *src=malloc(bn+GUARD*2),*lin=malloc(ln+GUARD*2),*a=malloc(cap+GUARD*2),*b=malloc(cap+GUARD*2);
    assert(src&&lin&&a&&b); fill(src,bn+GUARD*2);fill(lin,ln+GUARD*2);
    for(int op=0;op<5;op++){
        size_t n=op==1?bn:ln; int old=-1,now=-1;
        memset(a,0xca,n+2*GUARD);memset(b,0xca,n+2*GUARD);
        switch(op){
          case 0:
            old=ref_nvn_deswizzle(d,level,layer,src+GUARD,a+GUARD,pitch);
            now=nvn_deswizzle(d,level,layer,src+GUARD,b+GUARD,pitch);break;
          case 1:
            old=ref_nvn_swizzle(d,level,layer,lin+GUARD,pitch,a+GUARD);
            now=nvn_swizzle(d,level,layer,lin+GUARD,pitch,b+GUARD);break;
          case 2:
            old=ref_nvn_deswizzle_from(d,level,layer,src+GUARD+base,base,a+GUARD,pitch);
            now=nvn_deswizzle_from(d,level,layer,src+GUARD+base,base,b+GUARD,pitch);break;
          case 3:
            old=ref_nvn_deswizzle_from(d,level,layer,src+GUARD,base+1,a+GUARD,pitch);
            now=nvn_deswizzle_from(d,level,layer,src+GUARD,base+1,b+GUARD,pitch);break;
          case 4:
            old=ref_nvn_deswizzle(d,level,layer,src+GUARD,a+GUARD,wb-1);
            now=nvn_deswizzle(d,level,layer,src+GUARD,b+GUARD,wb-1);break;
        }
        assert(old==now && old==(op>2?-1:0));
        check_bytes(a,b,n+2*GUARD);regular++;
    }
    free(src);free(lin);free(a);free(b);
}
static void tiles(void) {
    nvn_texdesc d={.target=1,.format=0x25,.flags=0x20,.width=535,.height=493,.depth=1,.levels=5};
    uint8_t *tile=malloc(65536);
    assert(tile);
    for(int zero=0;zero<2;zero++){
        if(zero) memset(tile,0,65536); else fill(tile,65536);
        for(unsigned l=0;l<4;l++){
            uint32_t wb,rows,s,bpb;unsigned th,td;uint64_t ofs;
            assert(!nvn_deswizzle_geom(&d,l,0,&wb,&rows,&s,&ofs,&th,&td,&bpb));
            unsigned txw=(128u>>th)*64,trows=8u<<th;size_t pitch=txw+13,n=pitch*trows;
            uint8_t *a=malloc(n+2*GUARD),*b=malloc(n+2*GUARD); assert(a&&b);
            for(unsigned x=0;x<=wb/txw+1;x++)for(unsigned y=0;y<=rows/trows+1;y++)for(int group=0;group<4;group++){
                uint32_t w1,w2,r1,r2;memset(a,0xca,n+2*GUARD);memset(b,0xca,n+2*GUARD);
                int r=ref_nvn_deswizzle_tile_mode(&d,l,x,y,tile,a+GUARD,pitch,&w1,&r1,group);
                int q=nvn_deswizzle_tile_mode(&d,l,x,y,tile,b+GUARD,pitch,&w2,&r2,group);
                assert(!r&&!q&&r1==r2&&w1==w2);check_bytes(a,b,n+2*GUARD);sparse++;
                if(!w1||!r1)sparse_empty++;else if(w1==txw&&r1==trows)sparse_full++;else sparse_partial++;
            }
            free(a);free(b);
        }
    }
    free(tile);
}
int main(void){
    const unsigned widths[]={1,7,15,16,17,31,32,33,63,64,65,127,128,129,255,300,519};
    const unsigned heights[]={1,2,7,8,9,15,16,17,31,32,33,63,64,65,129,177,231};
    const int formats[]={1,0x25,0x7d,0x29};
    for(int sw=0;sw<2;sw++){
        nvn_gob_switch2=ref_nvn_gob_switch2=sw;
        for(unsigned i=0;i<17;i++)for(unsigned fmt=0;fmt<4;fmt++){
            int target=(int[]){1,2,4,1}[(i+fmt)%4];
            nvn_texdesc d={.target=target,.format=formats[fmt],.width=widths[i],
             .height=heights[(i+3*fmt)%17],.depth=target==2?5:target==4?3:1,.levels=4,.samples=1};
            nvn_texlayout lay;nvn_tex_layout(&d,&lay);
            for(unsigned level=0;level<d.levels;level++)for(unsigned layer=0;layer<lay.layers;layer++)one(&d,level,layer);
        }
        tiles();
    }
    assert(sparse_full&&sparse_partial&&sparse_empty);
    printf("%u checks, %u regular, %u sparse (%u full, %u edge, %u outside), %zu bytes compared\n",checks,regular,sparse,sparse_full,sparse_partial,sparse_empty,compared);
}
