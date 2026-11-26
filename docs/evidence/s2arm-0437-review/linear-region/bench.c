#define _GNU_SOURCE
#include "abi.h"
#include <time.h>
#include <unistd.h>
#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
static void cold_inputs(const uint8_t *a,size_t n,const uint8_t *b,size_t m) {
    for(size_t i=0;i<n;i+=64)_mm_clflush(a+i);
    for(size_t i=0;i<m;i+=64)_mm_clflush(b+i);
    _mm_mfence();
}
#define COLD_METHOD "explicit_clflush"
#else
// Portable cache pressure, not a guarantee that every input line was evicted.
static void cold_inputs(const uint8_t *a,size_t n,const uint8_t *b,size_t m) {
    static volatile uint8_t *eviction;
    static const size_t length=(size_t)128*1024*1024;
    (void)a;(void)b;(void)n;(void)m;
    if(!eviction){eviction=malloc(length);assert(eviction);memset((void*)eviction,1,length);}
    for(size_t i=0;i<length;i+=64)eviction[i]++;
}
#define COLD_METHOD "cache_pressure_128MiB"
#endif
static uint32_t seed=5981;
static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;return seed^=seed<<5;}
typedef struct{const char*name;int format,flag,w,h,x,y,rw,rh,pad,n,level;} benchcase;
static benchcase cases[]={
{"r8-small-point",1,0x10,64,32,7,5,1,1,0,5000,0},
{"r8-small-rectangle",1,0x50,64,32,8,9,12,8,0,3000,0},
{"r8-medium-middle",1,0x10,256,256,12,60,4,4,0,260,0},
{"r8-medium-tail",1,0x10,256,256,0,248,256,8,0,650,0},
{"rgba-small",0x25,0x50,32,24,3,2,5,6,0,2500,0},
{"rgba-480-tail",0x25,0x40,640,480,0,472,640,8,32,28,0},
{"rgba-720-middle",0x25,0x10,1280,720,24,20,16,16,64,8,0},
{"rgba-720-tail",0x25,0x40,1280,720,0,712,1280,8,64,12,0},
{"rgba-1080-tail-pixel",0x25,0x40,1920,1080,1919,1079,1,1,0,8,0},
{"rgba-1080-one-full",0x25,0x10,1920,1080,0,0,1920,1080,0,5,0},
{"rgba-1080-half",0x25,0x50,1920,1080,0,540,1920,540,64,5,0},
{"bc1-part-block",0x42,0x40,67,47,64,44,3,3,0,5000,0},
{"bc1-medium-middle",0x42,0x50,517,257,128,64,16,16,0,210,0},
{"bc1-medium-tail",0x42,0x50,517,257,0,252,517,5,0,500,0},
{"bc1-full",0x42,0x10,517,257,0,0,517,257,16,250,0},
{"r8-view-refusal",1,0x10,64,64,0,1,2,2,0,8000,1},
{"r8-blocklinear",1,0,128,64,16,20,8,3,0,3000,0}};
static uint64_t now(void){struct timespec t;assert(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t)==0);return t.tv_sec*UINT64_C(1000000000)+t.tv_nsec;}
static void fill(uint8_t*p,size_t n,uint32_t s){for(size_t i=0;i<n;i++){s^=s<<13;s^=s>>17;s^=s<<5;p[i]=(uint8_t)s;}}
int main(int argc,char**argv){assert(argc==2);int cold=!strcmp(argv[1],"cold");long page_n=sysconf(_SC_PAGESIZE);assert(page_n>0);size_t page=(size_t)page_n;fprintf(stderr,"clock=thread_cpu page=%ld inputs=%s\n",page_n,cold?COLD_METHOD:"warm");writer wr[]={base,fixed,control,suffix,safe};const char*names[]={"initial","corrected","control","suffix","safe"};
    puts("pair,case,variant,calls,cpu_ns,heap_allocations_per_call,requested_heap_bytes_per_call,prepare_per_call,notify_per_call,checksum");
    for(unsigned c=0;c<sizeof cases/sizeof cases[0];c++){
        benchcase k=cases[c];if(cold)k.n=1;int bw,bh,b=nvn_fmt_bpb(k.format,&bw,&bh);assert(b);
        int tight=(k.w+bw-1)/bw*b;tex_t t={.d={.target=1,.format=k.format,.width=k.w,.height=k.h,.depth=1,.levels=1,.flags=k.flag,.stride=k.pad?tight+k.pad:0}};
        nvn_tex_layout(&t.d,&t.L);NVNcopyRegion r={k.x,k.y,0,k.rw,k.rh,1};
        size_t n=t.L.size+65536,row=(k.rw+bw-1)/bw*b+(k.pad?11:0),sn=row*((k.rh+bh-1)/bh);
        t.mem=aligned_alloc(page,(n+page-1)&~(page-1));uint8_t*input=malloc(sn);assert(t.mem&&input);fill(input,sn,12);
        view_t vw={.set_levels=1,.base_level=k.level};
        for(int j=0;j<13;j++){
            int order[]={0,1,2,3,4};for(int i=4;i>0;i--){int z=next()%(i+1),q=order[z];order[z]=order[i];order[i]=q;}
            for(int i=0;i<5;i++){
                int m=order[i];fill(t.mem,n,26);if(cold){input[0]=0;cold_inputs(t.mem,n,input,sn);}uint64_t begin=now();stats a={0};
                for(int q=0;q<k.n;q++){if(!cold)input[0]=(uint8_t)q;a=wr[m](&t,k.level?&vw:NULL,&r,input,row,0);}
                uint64_t elapsed=now()-begin,hash=UINT64_C(1469598103934665603);
                for(size_t b_=0;b_<n;b_++)hash=(hash^t.mem[b_])*UINT64_C(1099511628211);
                if(j)printf("%d,%s,%s,%d,%" PRIu64 ",%zu,%zu,%zu,%zu,%" PRIu64 "\n",j,k.name,names[m],k.n,elapsed,a.calls,a.bytes,a.prepares,a.notifies,hash);
            }
        }
        free(t.mem);free(input);
    }
}
