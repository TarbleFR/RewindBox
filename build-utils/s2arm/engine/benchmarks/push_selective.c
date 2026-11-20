#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <time.h>
#ifdef __linux__
#include <sched.h>
#endif
#include <unistd.h>

enum { NVN2_PUSH_SLOTS=8, NVN2_PUSH_BYTES=256, OP_PUSH_CONST=1, OP_PUSH_CONST_PTR=2 };
typedef struct { uint8_t compute,slot; uint16_t offset; uint32_t size; } p_push_const;
typedef struct { uint8_t compute,slot; uint16_t offset; uint32_t size; uint64_t data; } p_push_const_ptr;
static struct { uint8_t push[2][8][256]; uint64_t push_ver[2][8]; } S;
static uint8_t g_args_dirty[6];
static uint64_t g_push_seq,rb_push_same,rb_push_changed;
static _Atomic int g_course_exact=1,g_course_on=1;
// Exact warmed atomic paths of rb_course_exact/rb_course_enabled. Cold title
// identification is excluded: the benchmark, like driving, starts identified.
static int rb_course_enabled(void) { int on=atomic_load_explicit(&g_course_on,memory_order_acquire); if(on>=0)return on; abort(); }
static int rb_course_exact(void) { return atomic_load_explicit(&g_course_exact,memory_order_relaxed) && rb_course_enabled(); }
static struct { uint64_t ver,gen,gpu; } g_push_copy[2][8];
static uint64_t g_arena_gen=1;
static uint8_t arena[256*1024],zero[256];
static size_t arena_offset;
static uint64_t copies;
static size_t arena_alloc_cpu(size_t n) { size_t x=arena_offset; arena_offset+=n; copies++; if(arena_offset>=sizeof arena)arena_offset=0; return x; }
static uint64_t zero_bank_gpu(void) { return (uint64_t)(uintptr_t)zero; }
static int rb_push_same_on(void) {
    static int mode = -2;
    if (mode == -2) { const char *v = getenv("S2A_RB_PUSH_SAME"); mode = v ? strcmp(v, "0") != 0 : -1; }
    return mode < 0 ? rb_course_exact() : mode;
}

__attribute__((noinline)) static void original(uint32_t op, const void *a) { switch(op) {
        case OP_PUSH_CONST: case OP_PUSH_CONST_PTR: { const p_push_const *pc = a; int c = pc->compute ? 1 : 0;
            const void *src = op == OP_PUSH_CONST ? (const void *)(pc + 1) : (const void *)(uintptr_t)((const p_push_const_ptr *)a)->data;
            if (pc->offset + pc->size > NVN2_PUSH_BYTES || !src) break;
            memcpy(S.push[c][pc->slot & (NVN2_PUSH_SLOTS - 1)] + pc->offset, src, pc->size); S.push_ver[c][pc->slot & (NVN2_PUSH_SLOTS - 1)] = ++g_push_seq;
            if (c) g_args_dirty[5] = 1; else memset(g_args_dirty, 1, 5);
            break; }
} }
__attribute__((noinline)) static void candidate(uint32_t op, const void *a) { switch(op) {
        case OP_PUSH_CONST: case OP_PUSH_CONST_PTR: { const p_push_const *pc = a; int c = pc->compute ? 1 : 0;
            const void *src = op == OP_PUSH_CONST ? (const void *)(pc + 1) : (const void *)(uintptr_t)((const p_push_const_ptr *)a)->data;
            if (pc->offset + pc->size > NVN2_PUSH_BYTES || !src) break;
            uint8_t *dst = S.push[c][pc->slot & (NVN2_PUSH_SLOTS - 1)] + pc->offset;
            // A deferred push is read now, exactly as before. Identical bytes do
            // not change its GPU copy or any stage's arguments. Version numbers
            // only identify content; compute-indirect destinations stay separate.
            if (rb_push_same_on() && !memcmp(dst, src, pc->size)) { rb_push_same++; break; }
            memcpy(dst, src, pc->size); S.push_ver[c][pc->slot & (NVN2_PUSH_SLOTS - 1)] = ++g_push_seq;
            rb_push_changed++;
            if (c) g_args_dirty[5] = 1; else memset(g_args_dirty, 1, 5);
            break; }
} }

__attribute__((noinline)) static void candidate_selective(uint32_t op, const void *a) { switch(op) {
        case OP_PUSH_CONST: case OP_PUSH_CONST_PTR: { const p_push_const *pc = a; int c = pc->compute ? 1 : 0;
            const void *src = op == OP_PUSH_CONST ? (const void *)(pc + 1) : (const void *)(uintptr_t)((const p_push_const_ptr *)a)->data;
            if (pc->offset + pc->size > NVN2_PUSH_BYTES || !src) break;
            uint8_t *dst = S.push[c][pc->slot & (NVN2_PUSH_SLOTS - 1)] + pc->offset;
            // A deferred push is read now, exactly as before. Identical bytes do
            // not change its GPU copy or any stage's arguments. Version numbers
            // only identify content; compute-indirect destinations stay separate.
            if (g_push_copy[c][pc->slot & (NVN2_PUSH_SLOTS - 1)].ver == S.push_ver[c][pc->slot & (NVN2_PUSH_SLOTS - 1)] && g_push_copy[c][pc->slot & (NVN2_PUSH_SLOTS - 1)].gen == g_arena_gen && (c ? !g_args_dirty[5] : !(g_args_dirty[0] | g_args_dirty[1] | g_args_dirty[2] | g_args_dirty[3] | g_args_dirty[4])) && rb_push_same_on() && !memcmp(dst, src, pc->size)) { rb_push_same++; break; }
            memcpy(dst, src, pc->size); S.push_ver[c][pc->slot & (NVN2_PUSH_SLOTS - 1)] = ++g_push_seq;
            rb_push_changed++;
            if (c) g_args_dirty[5] = 1; else memset(g_args_dirty, 1, 5);
            break; }
} }

__attribute__((noinline)) static uint64_t push_gpu(int c, int slot) {
    if (!S.push_ver[c][slot]) return zero_bank_gpu();
    if (g_push_copy[c][slot].ver == S.push_ver[c][slot] && g_push_copy[c][slot].gen == g_arena_gen) return g_push_copy[c][slot].gpu;
    size_t po = arena_alloc_cpu(NVN2_PUSH_BYTES); memcpy(arena + po, S.push[c][slot], NVN2_PUSH_BYTES);
    g_push_copy[c][slot].ver = S.push_ver[c][slot]; g_push_copy[c][slot].gen = g_arena_gen; g_push_copy[c][slot].gpu = (uint64_t)(uintptr_t)(arena + po);
    return g_push_copy[c][slot].gpu;
}


enum { N=8192, REPS=7, LOOPS=128 };
static uint8_t *records;
static size_t stride;
static volatile uint64_t observable;
static uint64_t clock_ns(void) {struct timespec t; clock_gettime(CLOCK_MONOTONIC_RAW,&t); return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
static uint32_t rng=17;
static uint32_t random32(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void prepare(unsigned size,unsigned same,int last) {
    free(records); stride=sizeof(p_push_const)+size; records=malloc(N*stride);
    uint8_t value[8][256];memset(value,0x5a,sizeof value);rng=17;
    for(unsigned i=0;i<N;i++) {
        unsigned slot=i&7; p_push_const *pc=(p_push_const*)(records+i*stride);
        *pc=(p_push_const){0,slot,0,size};
        unsigned at=last?size-1:0;
        if(i>=N-8)value[slot][at]=0x5a; // close the cyclic stream exactly
        else if(random32()%100>=same)value[slot][at]^=1;
        memcpy(pc+1,value[slot],size);
    }
}
static void reset(void) {
    memset(&S,0,sizeof S);memset(S.push,0x5a,sizeof S.push);
    for(unsigned i=0;i<2;i++)for(unsigned j=0;j<8;j++)S.push_ver[i][j]=1;
    memset(g_push_copy,0,sizeof g_push_copy);memset(g_args_dirty,0,sizeof g_args_dirty);
    g_push_seq=1;rb_push_same=rb_push_changed=copies=0;g_arena_gen=1;arena_offset=0;
}
typedef void (*command_fn)(uint32_t,const void*);
// Correctness guard outside every timed section: every output byte, not only
// the lightweight timed checksum, must match the stream's expected state.
static int verify(command_fn fn,int consumer) {
    uint8_t expected[8][256]; memset(expected,0x5a,sizeof expected);reset();
    for(unsigned i=0;i<N;i++) {
        const p_push_const *pc=(const p_push_const*)(records+i*stride);
        memcpy(expected[pc->slot]+pc->offset,pc+1,pc->size);
        if(consumer && !(i&1023))g_arena_gen++;
        fn(OP_PUSH_CONST,pc);
        if(memcmp(S.push[0][pc->slot],expected[pc->slot],256))return 0;
        if(consumer && memcmp((const void*)(uintptr_t)push_gpu(0,pc->slot),expected[pc->slot],256))return 0;
        if(consumer)memset(g_args_dirty,0,5);
    }
    return 1;
}
static uint64_t run(command_fn fn,int consumer,unsigned size,unsigned last,unsigned loops) {
    uint64_t hash=0;
    for(unsigned r=0;r<loops;r++)for(unsigned i=0;i<N;i++) {
        const p_push_const *pc=(const p_push_const*)(records+i*stride);
        if(consumer && !(i&1023))g_arena_gen++;
        fn(OP_PUSH_CONST,pc);
        if(consumer) {
            const uint8_t *out=(const uint8_t*)(uintptr_t)push_gpu(0,pc->slot);
            hash+=out[last?size-1:0];
            memset(g_args_dirty,0,5); // model a graphics argument bind after consumption
        }
        __asm__ volatile("" ::: "memory");
    }
    if(!consumer) for(unsigned i=0;i<sizeof S.push;i++)hash+=((uint8_t*)S.push)[i];
    observable=hash;return hash;
}
static int cmp_double(const void*a,const void*b){double x=*(const double*)a,y=*(const double*)b;return(x>y)-(x<y);}
int main(void) {
    int selective=getenv("PUSH_VARIANT") && !strcmp(getenv("PUSH_VARIANT"),"selective");
    command_fn tested=selective?candidate_selective:candidate;
    int pinned=-1;
#ifdef __linux__
    cpu_set_t cpus;CPU_ZERO(&cpus);if(!sched_getaffinity(0,sizeof cpus,&cpus))for(int i=0;i<CPU_SETSIZE;i++)if(CPU_ISSET(i,&cpus)){CPU_ZERO(&cpus);CPU_SET(i,&cpus);if(!sched_setaffinity(0,sizeof cpus,&cpus))pinned=i;break;}
#endif
    fprintf(stderr,"pinned_cpu=%d pid=%ld N=%d loops=%d reps=%d mode=%s\n",pinned,(long)getpid(),N,LOOPS,REPS,getenv("S2A_RB_PUSH_SAME")?getenv("S2A_RB_PUSH_SAME"):"dynamic");
    puts("model,size,identical_requested,changed_position,original_ns_median,candidate_ns_median,ratio_candidate_original,original_ns_min,original_ns_max,candidate_ns_min,candidate_ns_max,identical_observed,original_copies,candidate_copies,checksum_equal");
    unsigned sizes[]={16,64,256};
    for(int consumer=0;consumer<=1;consumer++)for(unsigned z=0;z<3;z++)for(unsigned same=0;same<=100;same+=25)for(int last=0;last<=1;last++) {
        unsigned size=sizes[z];prepare(size,same,last);double times[2][REPS];uint64_t checks[2]={0},cp[2]={0},samecount=0;
        if(!verify(original,consumer)||!verify(tested,consumer)){fprintf(stderr,"bytewise equivalence failed\n");return 3;}
        for(unsigned rep=0;rep<REPS;rep++)for(unsigned j=0;j<2;j++) {
            unsigned path=(rep+j)&1;command_fn fn=path?tested:original;reset();run(fn,consumer,size,last,4);reset();
            uint64_t start=clock_ns();checks[path]=run(fn,consumer,size,last,LOOPS);uint64_t elapsed=clock_ns()-start;
            times[path][rep]=(double)elapsed/(N*LOOPS);cp[path]=copies;if(path)samecount=rb_push_same;
        }
        for(unsigned i=0;i<2;i++)qsort(times[i],REPS,sizeof(double),cmp_double);
        printf("%s,%u,%u,%s,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%llu,%llu,%d\n",consumer?"command_plus_CPU_copy":"command_only",size,same,last?"last":"first",times[0][REPS/2],times[1][REPS/2],times[1][REPS/2]/times[0][REPS/2],times[0][0],times[0][REPS-1],times[1][0],times[1][REPS-1],(double)samecount/(N*LOOPS),(unsigned long long)cp[0],(unsigned long long)cp[1],checks[0]==checks[1]);fflush(stdout);
        if(checks[0]!=checks[1])return 2;
    }
    free(records);return 0;
}
