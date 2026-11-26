#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "rb_fb_dirty.h"
#include "rb_args_ubo.h"

typedef struct { uint8_t count, stale, disable, seed, change; } NvProg;
#define __bridge
static uint64_t g_draw_seq, g_fb_seq, g_fb_rid[4], g_rb_fb_draws, g_rb_fb_same, g_rb_fb_marks;
static int g_fb_n, narrow;
static const void *g_fb_src[4], *g_fb_use[4];
static rb_fb_subst g_rb_fb_prev;
static rb_args_mod g_rb_mod[6]; static uint8_t g_args_dirty[6], objects[256];
static int rb_fb_dirty_narrow_on(void) { return narrow; }
// Supply the substitution produced by the Metal body, which is outside the benchmark.
static __attribute__((noinline)) void fb_prepare_(NvProg *v) {
    g_draw_seq++;
    narrow = !v->disable;
    g_fb_n = v->count;
    g_fb_seq = v->stale ? g_draw_seq - 1 : g_draw_seq;
    for (int i = 0; i < g_fb_n && i < 4; i++) {
        unsigned x = (v->seed + i) & 255;
        g_fb_src[i] = &objects[(x + (v->change == 1)) & 255];
        g_fb_use[i] = &objects[(x + (v->change == 2)) & 255];
        g_fb_rid[i] = x + (v->change == 3);
    }
}
#include IMPL

static uint64_t now_ns(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
static uint64_t mix(uint64_t h,uint64_t x){return (h^x)*UINT64_C(1099511628211);}
static uint64_t digest(uint64_t h) {
    h = mix(mix(mix(h, g_rb_fb_draws),g_rb_fb_same),g_rb_fb_marks);
    h = mix(mix(mix(h,g_draw_seq),g_fb_seq),g_rb_fb_prev.n);
    for (int i=0; i<6; i++) h = mix(h, g_args_dirty[i] | ((unsigned)g_rb_mod[i].other << 8));
    for(int i=0;i<4;i++) {
        h=mix(h,g_rb_fb_prev.src[i] ? (uintptr_t)g_rb_fb_prev.src[i]-(uintptr_t)objects+1u : 0);
        h=mix(h,g_rb_fb_prev.use[i] ? (uintptr_t)g_rb_fb_prev.use[i]-(uintptr_t)objects+1u : 0);
        h=mix(h,g_rb_fb_prev.rid[i]);
    }
    return h;
}
int main(int argc,char **argv){
    assert(argc==2);const char *mode=argv[1];size_t n=1u<<20;
    int verify=!strcmp(mode,"verify");
    if(verify)n=200000;
    NvProg *v=calloc(n,sizeof *v);assert(v);
    if(!strcmp(mode,"burst")){
        // A deterministic burst of eight substitutions every 256 calls. The second
        // half changes the resource ID; the remaining calls have no substitution.
        for(size_t j=0;j<n;j++) if(j%256<8) v[j]=(NvProg){2,0,0,(j/256)%255,j%256>=4?3:0};
    }else if(!strcmp(mode,"same")||!strcmp(mode,"varies")||!strcmp(mode,"stale")){
        for(size_t i=0;i<n;i++)v[i]=(NvProg){4,!strcmp(mode,"stale"),0,!strcmp(mode,"varies") ? i%255:1,0};
    }else if(verify){
        uint32_t s=42;
        for(size_t i=0;i<n;i++){
            s=s*1664525u+1013904223u;
            if(i && (s&15)<6) v[i]=v[i-1];
            else v[i]=(NvProg){(s>>9)%6,(s>>12)%11==0,(s>>18)%13==0,(s>>20)%7,(s>>14)%4};
        }
    }else assert(!strcmp(mode,"empty"));
    uint64_t t0=now_ns(),h=123;
    for(size_t i=0;i<n;i++){
        if(verify){
            if(i%1741==0)memset(&g_rb_fb_prev,0,sizeof g_rb_fb_prev);
            for(int j=0;j<6;j++){g_args_dirty[j]=(i+j)%3;g_rb_mod[j].other=(i+j)%2;}
        }
        fb_prepare(&v[i]);
        if(verify)h=digest(h);
    }
    uint64_t elapsed=now_ns()-t0;h=digest(h);
    printf("%.6f %016llx %llu %llu %llu\n",elapsed/1e6,(unsigned long long)h,(unsigned long long)g_rb_fb_draws,(unsigned long long)g_rb_fb_same,(unsigned long long)g_rb_fb_marks);
    free(v);
}
