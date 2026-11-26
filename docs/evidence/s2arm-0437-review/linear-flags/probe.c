#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nvn_deswizzle.h"
typedef struct { nvn_texdesc d; nvn_texlayout L; uint8_t *mem; int has_layout; uint64_t serial; } tex_t;
typedef struct { int set_levels,base_level,set_layers,min_layer; } view_t;
typedef struct { int xoffset,yoffset,zoffset,width,height,depth; } NVNcopyRegion;
#define LOG(...) ((void)0)
#define ONCE_LOG(...) ((void)0)
#define RED_ONCE(...) abort()
#define die(...) abort()
#define PD(...) ((void)0)
#define MAX(x,y) ((x)>(y)?(x):(y))
#define NVN_TEXTURE_TARGET_3D 2
#define DM_GAME_TEX_DIRTY_UPLOAD 0
static int writes;
static int dm_gfx_session_stopping(void){return 0;}
static void dm_guest_write_prepare(void *p,size_t n){assert(p&&n);}
static void nvn_be_tex_cpu_written(const tex_t *t){(void)t;writes++;}
static void xv_check(uint64_t s,unsigned l,unsigned y,const char *why){(void)s;(void)l;(void)y;(void)why;}
static int tex_cpu_written(uint64_t id){return !!id;}
int nvn_ft_written(const tex_t *t){(void)t;return 0;}
static uint8_t *rb_pkg_bytes(const tex_t *t,int i){(void)t;(void)i;return NULL;}
#include "actual.inc"
static void pattern(uint8_t *b,size_t n,uint32_t seed) {
    for(size_t i=0;i<n;i++){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;b[i]=(uint8_t)seed;}
}
int main(void) {
    int formats[]={1,0x25,0x42,0x8b}, flags[]={0x10,0x40,0x50};
    int counts[3]={0},mismatch_w[3]={0},mismatch_r[3]={0};
    for(int f=0;f<4;f++)for(int flags_i=0;flags_i<3;flags_i++)for(int pad=0;pad<3;pad++)
    for(int sw2=0;sw2<2;sw2++)for(int reg=0;reg<6;reg++)for(int ext=0;ext<2;ext++){
        nvn_gob_switch2=sw2;int bw,bh,bpb=nvn_fmt_bpb(formats[f],&bw,&bh);assert(bpb);
        int w=(128/bpb)*bw,h=32*bh;
        if(bw>1)w--;if(bh>1)h--; // partial final block.
        nvn_texdesc d={.target=1,.format=formats[f],.width=w,.height=h,.depth=1,.levels=1,
                       .flags=flags[flags_i],.stride=pad==0?0:pad==1?128:160};
        nvn_texlayout layout;nvn_tex_layout(&d,&layout);
        size_t sp=pad==2?160:128;assert(layout.size==sp*32);
        unsigned gfx_rows,gfx_rb,gfx_slices,th,td,dp;uint64_t base;
        int g_rc=nvn_deswizzle_geom(&d,0,0,&gfx_rb,&gfx_rows,&gfx_slices,&base,&th,&td,&dp);
        assert(g_rc==((!FIXED && d.flags==0x40)?0:-1));
        nvn_tex_level_geom geom;assert(nvn_tex_level_geom_of(&d,0,1,&geom)==0 && geom.layer_size==layout.size && geom.bpb==(uint32_t)bpb);
        NVNcopyRegion r;
        switch(reg) {
          case 0:r=(NVNcopyRegion){0,0,0,w,h,1};break;
          case 1:r=(NVNcopyRegion){0,0,0,bw,bh,1};break;
          case 2:r=(NVNcopyRegion){2*bw,3*bh,0,4*bw,3*bh,1};break;
          case 3:r=(NVNcopyRegion){(w-1)/bw*bw,(h-1)/bh*bh,0,w-(w-1)/bw*bw,h-(h-1)/bh*bh,1};break;
          case 4:r=(NVNcopyRegion){0,30*bh,0,w,h-30*bh,1};break;
          default:r=(NVNcopyRegion){(w-1)/bw*bw,0,0,w-(w-1)/bw*bw,h,1};
        }
        size_t wb=(r.width+bw-1)/bw*bpb,hb=(r.height+bh-1)/bh,crow=wb+(ext?13:0);
        size_t pool_off=ext?384:193, n=pool_off+layout.size+129;
        size_t x=(r.xoffset/bw)*bpb,y=r.yoffset/bh;
        uint8_t *pool=malloc(n),*expected=malloc(n),*in=malloc(crow*hb),*out=malloc(crow*hb+24),*want=malloc(crow*hb+24);
        assert(pool&&expected&&in&&out&&want);
        pattern(pool,n,1);pattern(in,crow*hb,71);memcpy(expected,pool,n);
        tex_t t={.L=layout,.d=d,.mem=pool+pool_off,.serial=1};
        for(size_t i=0;i<hb;i++)memcpy(expected+pool_off+(y+i)*sp+x,in+i*crow,wb);
        int old_writes=writes;
        write_texels(&t,NULL,&r,in,ext?crow:0,ext?crow*hb:0);assert(writes==old_writes+1);
        if(memcmp(expected,pool,n))++mismatch_w[flags_i];
        memset(out,0xcb,crow*hb+24);memset(want,0xcb,crow*hb+24);
        for(size_t i=0;i<hb;i++)memcpy(want+12+i*crow,expected+pool_off+(y+i)*sp+x,wb);
        read_texels(&t,NULL,&r,out+12,ext?crow:0,ext?crow*hb:0);
        if(memcmp(out,want,crow*hb+24))++mismatch_r[flags_i];
        memcpy(pool,expected,n); // Independent read oracle, with correctly populated guest storage.
        memset(out,0xcb,crow*hb+24);
        read_texels(&t,NULL,&r,out+12,ext?crow:0,ext?crow*hb:0);
        assert(!memcmp(out,want,crow*hb+24));
        assert(!memcmp(pool,expected,n));
        free(pool);free(expected);free(in);free(out);free(want);
        ++counts[flags_i];
    }
    for(int k=0;k<3;k++) {
        printf("flags=%#x, cases=%d, whole-pool write mismatches=%d, write-then-read mismatches=%d, prefilled read mismatches=0\n",
               flags[k],counts[k],mismatch_w[k],mismatch_r[k]);
        if(!FIXED && flags[k]==0x40)assert(mismatch_w[k] && mismatch_r[k]);
        else assert(!mismatch_w[k] && !mismatch_r[k]);
    }
    return 0;
}
