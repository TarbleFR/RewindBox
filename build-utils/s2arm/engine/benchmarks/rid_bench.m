// macOS-only measurement of the real Metal gpuResourceID message against its
// existing cached value. This isolates tex_fast_rid's changed suffix: it is not
// a replay of tex_by_id, an iPhone result, or a frame-time benchmark.
// cc -O3 -fobjc-arc -framework Foundation -framework Metal rid_bench.m -o rid_bench
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>

static _Atomic int g_course_exact = 1, g_course_on = 1;
static int rb_course_enabled(void) { return atomic_load_explicit(&g_course_on,memory_order_acquire); }
static int rb_course_exact(void) { return atomic_load_explicit(&g_course_exact,memory_order_relaxed) && rb_course_enabled(); }
static int rb_view_rid_on(void) {
    static int mode = -2;
    if (mode == -2) { const char *v = getenv("S2A_RB_VIEW_RID_REUSE"); mode = v ? strcmp(v, "0") != 0 : -1; }
    return mode < 0 ? rb_course_exact() : mode;
}
static struct { void *view; uint64_t view_rid; } g_treg[16];
static int g_ntreg = 16;
static uint64_t rb_view_rid_reused;
static __attribute__((noinline)) uint64_t original(int tid, id<MTLTexture> t) {
    (void)tid;
    return t ? t.gpuResourceID._impl : 0;
}
static __attribute__((noinline)) uint64_t candidate(int tid, id<MTLTexture> t) {
    if (rb_view_rid_on() && t && tid >= 0 && tid < g_ntreg && g_treg[tid].view == (__bridge void *)t) {
        rb_view_rid_reused++; return g_treg[tid].view_rid;
    }
    return t ? t.gpuResourceID._impl : 0;
}
// tex_by_id's non-nil return has already checked tid and registered view_rid.
// Its caller holds g_rmu. No second title check, atomic read or counter is needed.
static __attribute__((noinline)) uint64_t candidate_direct(int tid, id<MTLTexture> t) {
    return t ? g_treg[tid].view_rid : 0;
}
static uint64_t clock_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec; }
typedef uint64_t (*lookup)(int,id<MTLTexture>);
static volatile uint64_t sink;
static uint64_t measure(lookup fn, NSArray *textures, unsigned long n, uint64_t *sum) {
    // NSArray indexing/ARC would dominate the tiny changed suffix. Retained by
    // the NSArray for the entire batch, these pointers mirror engine ownership.
    __unsafe_unretained id<MTLTexture> objects[16];
    for (unsigned k=0;k<16;k++) objects[k]=textures[k];
    uint64_t total=0,start=clock_ns();
    for(unsigned long i=0;i<n;i++) {
        unsigned k=i&15;
        total+=fn(k,objects[k]);
        __asm__ __volatile__("" : : "r"(total) : "memory");
    }
    uint64_t elapsed=clock_ns()-start; sink=total; *sum=total; return elapsed;
}
int main(void) { @autoreleasepool {
    int direct = getenv("RID_VARIANT") && !strcmp(getenv("RID_VARIANT"), "direct");
    lookup tested = direct ? candidate_direct : candidate;
    id<MTLDevice> device=MTLCreateSystemDefaultDevice();
    if (!device) { puts("SKIP: no Metal device, no fabricated resource-ID timing"); return 0; }
    fprintf(stderr,"Metal device: %s; macOS: %s; variant: %s\n",device.name.UTF8String,NSProcessInfo.processInfo.operatingSystemVersionString.UTF8String,direct ? "direct" : "dynamic");
    NSMutableArray *textures=[NSMutableArray array];
    for(unsigned k=0;k<16;k++) {
        MTLTextureDescriptor *d=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:16 height:16 mipmapped:NO];
        id<MTLTexture> t=[device newTextureWithDescriptor:d];
        if (!t) { puts("SKIP: texture allocation failed"); return 0; }
        [textures addObject:t]; g_treg[k].view=(__bridge void *)t; g_treg[k].view_rid=t.gpuResourceID._impl;
    }
    const unsigned long n=8388608;
    if (tested(-1, nil) != 0 || tested(INT32_MAX, nil) != 0) return 3;
    uint64_t a,b; measure(original,textures,10000,&a); measure(tested,textures,10000,&b);
    if(a!=b)return 3;
    puts("trial,original_ns_per_call,candidate_ns_per_call,ratio,checksum_equal");
    for(unsigned k=0;k<11;k++) {
        uint64_t x,y;
        if(k&1){y=measure(tested,textures,n,&b);x=measure(original,textures,n,&a);}
        else{x=measure(original,textures,n,&a);y=measure(tested,textures,n,&b);}
        printf("%u,%.5f,%.5f,%.6f,%d\n",k,(double)x/n,(double)y/n,(double)y/x,a==b);
        if(a!=b)return 3;
    }
    return 0;
} }
