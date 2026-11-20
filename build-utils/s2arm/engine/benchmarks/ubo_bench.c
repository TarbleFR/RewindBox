
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
enum { PC_BITS = 10, PC_RECENT = 8 };
static _Atomic uint64_t g_pool_gen = 1;
typedef struct { uintptr_t lo, hi, base; void *buf; uint64_t gpu; uintptr_t host; } pc_ent;
static __thread struct { uint64_t gen; unsigned next; pc_ent r[PC_RECENT], e[1u << PC_BITS]; } t_pc;
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static pc_ent g_pools[1];
static int pool_find(uint64_t a, uint64_t n) { (void)a; (void)n; fputs("UNSUPPORTED cold pool fallback\n",stderr); abort(); }
static void pool_res(int i) { (void)i; abort(); }
static void pc_put(int i, uint64_t a) { (void)i; (void)a; abort(); }
static int nvn_sparse_shadow(uint64_t a, uint64_t b, uint64_t c) { (void)a;(void)b;(void)c;abort(); }
static int xq_addr_want(uint64_t a,uint64_t b,void **c,uint64_t*d,uint64_t*e,uint64_t*f) { (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;abort(); }
extern uint64_t nvn_ga2ca(uint64_t a);
static _Atomic int g_course_exact=1, g_course_on=1;
static int rb_course_enabled(void) { int on=atomic_load_explicit(&g_course_on,memory_order_acquire); if(on>=0)return on; abort(); }
static int rb_course_exact(void) { return atomic_load_explicit(&g_course_exact,memory_order_relaxed) && rb_course_enabled(); }
static uint64_t bp_now(void);
static uint64_t rb_ubo_addr_hits, rb_ubo_addr_resolves, rb_ubo_addr_uncached, rb_ubo_addr_off;
static uint64_t rb_ubo_addr_calls, rb_ubo_addr_samples[3], rb_ubo_addr_ns[3];
static inline unsigned pc_slot(uint64_t addr) { return (unsigned)(((addr >> 12) * 0x9E3779B97F4A7C15ull) >> (64 - PC_BITS)); }
static inline const pc_ent *pc_get(uint64_t addr, uint64_t len) {
    if (t_pc.gen != atomic_load_explicit(&g_pool_gen, memory_order_acquire)) return NULL;
    pc_ent *c = &t_pc.e[pc_slot(addr)];
    if (addr >= c->lo && addr + len <= c->hi) return c;
    for (unsigned k = 0; k < PC_RECENT; k++) { const pc_ent *x = &t_pc.r[k]; if (addr >= x->lo && addr + len <= x->hi) { *c = *x; return c; } }
    return NULL;
}
static inline uint64_t pool_buf_end(uintptr_t hi) { static uintptr_t pg; if (!pg) pg = (uintptr_t)getpagesize(); return (hi + pg - 1) & ~(pg - 1); }
static inline int gpu_addr_want(uint64_t addr, uint64_t len, uint64_t want, void **buf, uint64_t *off, uint64_t *gpu, uint64_t *avail) {
    addr = nvn_ga2ca(addr);   // 同 nvn_be_addr
    const pc_ent *c = pc_get(addr, len);
    if (c) { *buf = (void *)c->buf; *off = addr - c->base; *gpu = c->gpu + *off; *avail = pool_buf_end(c->hi) - addr; return 1; }
    int ok = 0;
    pthread_mutex_lock(&g_mu);
    int i = pool_find(addr, len);
    if (i >= 0) { pool_res(i); pc_put(i, addr); *buf = (void *)g_pools[i].buf; *off = addr - g_pools[i].base; *gpu = g_pools[i].gpu + *off; *avail = pool_buf_end(g_pools[i].hi) - addr; ok = 1; }
    pthread_mutex_unlock(&g_mu);
    if (!ok && nvn_sparse_shadow(addr, len, want > len ? want : len)) {   // as nvn_be_addr
        pthread_mutex_lock(&g_mu); i = pool_find(addr, len);
        if (i >= 0) { pool_res(i); pc_put(i, addr); *buf = (void *)g_pools[i].buf; *off = addr - g_pools[i].base; *gpu = g_pools[i].gpu + *off; *avail = pool_buf_end(g_pools[i].hi) - addr; ok = 1; }
        pthread_mutex_unlock(&g_mu); }
    if (!ok) ok = xq_addr_want(addr, len, buf, off, gpu, avail);
    return ok;
}
static int rb_ubo_addr_on(void) {
    static int mode = -2;
    if (mode == -2) { const char *v = getenv("S2A_RB_UBO_BIND_CACHE"); mode = v ? strcmp(v, "0") != 0 : -1; }
    return mode < 0 ? rb_course_exact() : mode;
}
static void rb_ubo_addr_sample(int bin, uint64_t start, int sampled) {
    if (!sampled) return;
    rb_ubo_addr_ns[bin] += bp_now() - start;
    rb_ubo_addr_samples[bin]++;
}
static int rb_ubo_addr(int stage, int slot, uint64_t addr, uint64_t want,
                       void **buf, uint64_t *off, uint64_t *gpu, uint64_t *avail) {
    typedef struct { uint64_t addr, want, gen, off, gpu, avail; void *buf; } entry;
    static entry cache[6][16]; // submit thread only; g_pool_gen also changes at teardown
    // Select before classifying a hit, miss or disabled-path call. No clock read
    // on the other 255 calls; report sample counts, not an asserted device gain.
    int sampled = (++rb_ubo_addr_calls & 255u) == 0;
#ifdef NO_TIMING
    sampled = 0;
#endif
    uint64_t start = sampled ? bp_now() : 0;
    if (!rb_ubo_addr_on() || (unsigned)stage >= 6 || (unsigned)slot >= 16) {
        int ok = gpu_addr_want(addr, 1, want, buf, off, gpu, avail);
        rb_ubo_addr_off++; rb_ubo_addr_sample(2, start, sampled); return ok;
    }
    // Normalize every call: a GPU VA remap must never reuse its former CPU range.
    addr = nvn_ga2ca(addr);
    uint64_t gen = atomic_load_explicit(&g_pool_gen, memory_order_acquire);
    entry *c = &cache[stage][slot];
    if (c->gen == gen && c->addr == addr && c->want == want) {
        *buf = c->buf; *off = c->off; *gpu = c->gpu; *avail = c->avail;
        rb_ubo_addr_hits++; rb_ubo_addr_sample(0, start, sampled); return 1;
    }
    rb_ubo_addr_resolves++;
    // nvn_ga2ca is idempotent: CPU ranges inside its GVA window are refused by
    // gva_alloc. The ordinary lookup keeps every sparse/parked-piece fallback.
    int ok = gpu_addr_want(addr, 1, want, buf, off, gpu, avail);
    const pc_ent *p = ok ? pc_get(addr, 1) : NULL;
    // Parked-piece xq_addr_want results have another lifetime and are not cached.
    // A resident pc_get result must agree with every returned address/bounds byte.
    if (p && atomic_load_explicit(&g_pool_gen, memory_order_acquire) == gen &&
        (void *)p->buf == *buf && addr - p->base == *off &&
        p->gpu + *off == *gpu && pool_buf_end(p->hi) - addr == *avail) {
        *c = (entry){addr, want, gen, *off, *gpu, *avail, *buf};
    } else { c->gen = 0; rb_ubo_addr_uncached++; }
    rb_ubo_addr_sample(1, start, sampled); return ok;
}
static uint64_t bp_now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (uint64_t)t.tv_sec * 1000000000ull + t.tv_nsec; }

typedef struct { uint64_t addr,want; int stage,slot; } query;
enum { NQ=65536, REPEAT=80, TRIALS=9 };
static query queries[NQ];
static volatile uint64_t sink;
typedef int (*lookup_fn)(int,int,uint64_t,uint64_t,void**,uint64_t*,uint64_t*,uint64_t*);
static __attribute__((noinline)) int original(int st,int sl,uint64_t a,uint64_t n,void**b,uint64_t*o,uint64_t*g,uint64_t*v) {
    (void)st;(void)sl; return gpu_addr_want(a,1,n,b,o,g,v);
}
static __attribute__((noinline)) int candidate(int st,int sl,uint64_t a,uint64_t n,void**b,uint64_t*o,uint64_t*g,uint64_t*v) {
    return rb_ubo_addr(st,sl,a,n,b,o,g,v);
}
static void seed_pool(uint64_t base,unsigned recent) {
    pc_ent p={base,base+4096,base,(void*)(uintptr_t)(base+0x100000000ull),base+0x200000000ull,base};
    t_pc.e[pc_slot(base)]=p; t_pc.r[recent]=p;
}
static uint64_t run(lookup_fn fn,int repeats,uint64_t *digest) {
    uint64_t sum=0,beg=bp_now();
    for(int j=0;j<repeats;j++)for(unsigned i=0;i<NQ;i++) {
        query q=queries[i]; void *b=NULL; uint64_t o=0,g=0,v=0;
        int ok=fn(q.stage,q.slot,q.addr,q.want,&b,&o,&g,&v);
        sum+=(uint64_t)(uintptr_t)b+o+g+v+ok;
        __asm__ __volatile__("" : : "r"(sum) : "memory");
    }
    uint64_t end=bp_now(); sink=sum; *digest=sum; return end-beg;
}
static uint64_t rng=1234567;
static uint32_t next_random(void) { rng^=rng<<13; rng^=rng>>7; rng^=rng<<17; return (uint32_t)rng; }
static void setup(const char *scenario,int reuse) {
    memset(&t_pc,0,sizeof t_pc); t_pc.gen=atomic_load(&g_pool_gen);
    uint64_t base=0x100000000ull, other=base+4096;
    if(!strcmp(scenario,"collision"))while(pc_slot(other)!=pc_slot(base))other+=4096;
    else other=base;
    seed_pool(base,0); seed_pool(other,1);
    unsigned offsets[16]={0};
    for(unsigned i=0;i<NQ;i++) {
        unsigned sl=i%16;
        if((int)(next_random()%100)>=reuse)offsets[sl]^=256;
        queries[i]=(query){(!strcmp(scenario,"collision") && (sl&1)?other:base)+sl*32+offsets[sl],256,1,(int)sl};
    }
}
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    int reuse=atoi(argv[2]); setup(argv[1],reuse);
    // Exact output agreement for each query, outside the timed loop.
    for(unsigned i=0;i<NQ;i++) {
        query q=queries[i]; void *ab,*bb; uint64_t ao,ag,av,bo,bg,bv;
        int ar=original(q.stage,q.slot,q.addr,q.want,&ab,&ao,&ag,&av);
        int br=candidate(q.stage,q.slot,q.addr,q.want,&bb,&bo,&bg,&bv);
        if(ar!=br || ab!=bb || ao!=bo || ag!=bg || av!=bv) {
            fprintf(stderr,"per-query output mismatch at %u\n",i); return 4;
        }
    }
    uint64_t a,b; run(original,1,&a); run(candidate,1,&b); if(a!=b){fprintf(stderr,"checksum mismatch\n");return 3;}
    printf("scenario,reuse_percent,trial,original_ns_per_call,candidate_ns_per_call,ratio,hit_count,resolve_count,off_count,checksum_equal\n");
    for(int k=0;k<TRIALS;k++){
        uint64_t ta,tb,h0=rb_ubo_addr_hits,m0=rb_ubo_addr_resolves,o0=rb_ubo_addr_off;
        if(k&1){tb=run(candidate,REPEAT,&b);ta=run(original,REPEAT,&a);}else{ta=run(original,REPEAT,&a);tb=run(candidate,REPEAT,&b);}
        double count=(double)NQ*REPEAT;
        printf("%s,%d,%d,%.5f,%.5f,%.6f,%llu,%llu,%llu,%d\n",argv[1],reuse,k,ta/count,tb/count,(double)tb/ta,
          (unsigned long long)(rb_ubo_addr_hits-h0),(unsigned long long)(rb_ubo_addr_resolves-m0),(unsigned long long)(rb_ubo_addr_off-o0),a==b);
        if(a!=b)return 3;
    }
}
