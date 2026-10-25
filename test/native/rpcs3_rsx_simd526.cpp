// RewindBox targeted native differential tests. MIT; production fragments retain
// their upstream RPCS3 provenance in the candidate and inverse fixture.
#include "util/types.hpp"
#include "util/v128.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <random>
#include <span>
#include <stdexcept>
#include <vector>
#if defined(ARCH_ARM64)
#include <arm_neon.h>
// Only the reference methods below use this compatibility layer. Production
// candidate methods and common operations must compile without it as well.
#include "Emu/CPU/sse2neon.h"
#define RPCS3_IOS 1
#else
#include <immintrin.h>
#endif
namespace utils { template<class T, class U> T* bless(U* p) { return reinterpret_cast<T*>(p); } }
#include "common.inc"
struct RSXFragmentProgram { const void* data; const void* get_data() const { return data; } };
namespace before {
namespace utils { using ::utils::bless; }
#include "before.inc"
}
namespace after {
#include "after.inc"
}
static std::uint64_t checks=0;
static void check(bool value) { ++checks; if(!value) throw std::runtime_error("differential assertion "+std::to_string(checks)); }
static void equal(const void* a,const void* b,std::size_t size) { check(std::memcmp(a,b,size)==0); }
struct alignas(16) guarded { std::array<u8, 144000> bytes; guarded(){bytes.fill(0xa7);} };
static void finish_stores() {
#if defined(ARCH_X64)
    _mm_sfence(); // Harness consumption of the existing x86 non-temporal stores.
#endif
}
static std::mt19937 rng(0x526a6416);
static v128 random_vector(){ v128 r;for(int i=0;i<4;++i)r._u32[i]=rng();return r; }
static void vectors() {
    for(unsigned lane=0;lane<16;++lane)for(unsigned value=0;value<256;++value){
        auto v=random_vector();v._u8[lane]=value;
        const auto x=before::decode_instruction(v),y=after::decode_instruction(v);equal(&x,&y,16);
        for(unsigned i=0;i<16;++i)check(y._u8[i]==v._u8[i^1]);
    }
    for(unsigned i=0;i<10000;++i){auto v=random_vector();const auto x=before::decode_instruction(v),y=after::decode_instruction(v);equal(&x,&y,16);}
}
static void border(){
    for(unsigned mask=0;mask<16;++mask)for(unsigned lane=0;lane<4;++lane)for(unsigned value=0;value<256;++value){
        u32 raw=0x18c6fa39;raw=(raw&~(0xffu<<(lane*8)))|(value<<(lane*8));
        const auto x=before::border_color(raw,true,mask),y=after::border_color(raw,true,mask);check(x==y);
        check(after::border_color(raw,false,mask)==raw);
        u32 expected=raw;for(unsigned b=0;b<4;++b)if(mask&(1u<<(3-b)))expected^=0x80u<<(8*b);check(y==expected);
    }
    for(unsigned i=0;i<100000;++i){u32 raw=rng(),mask=rng()&15;check(before::border_color(raw,true,mask)==after::border_color(raw,true,mask));}
}
static void iota(){
    std::vector<unsigned> sizes;for(unsigned i=0;i<100;++i)sizes.push_back(i);for(unsigned i:{257,65535,65536,65539})sizes.push_back(i);
    for(unsigned count:sizes){guarded a,b;auto* x=reinterpret_cast<u16*>(a.bytes.data()+32);auto* y=reinterpret_cast<u16*>(b.bytes.data()+32);
        before::iota16(x,count);after::iota16(y,count);finish_stores();equal(a.bytes.data(),b.bytes.data(),a.bytes.size());
        for(unsigned i=0;i<count;++i)check(y[i]==static_cast<u16>(i));
        for(unsigned i=32+count*2;i<b.bytes.size();++i)check(b.bytes[i]==0xa7);
        for(unsigned i=0;i<32;++i)check(b.bytes[i]==0xa7);
    }
}
template<int N>static void stream_memory(unsigned shift){
    alignas(16) std::array<u8,160> src,a,b;for(auto&v:src)v=rng();a.fill(0xa7);b=a;
    before::utils::stream_vector_from_memory<N>(a.data()+16,src.data()+shift);
    after::utils::stream_vector_from_memory<N>(b.data()+16,src.data()+shift);
    finish_stores();equal(a.data(),b.data(),a.size());equal(b.data()+16,src.data()+shift,N*16);
}
#if defined(ARCH_ARM64)
template<int N>static void stream_overlap(unsigned shift,int delta){
    alignas(16) std::array<u8,320> a,b;for(auto&v:a)v=rng();b=a;
    auto* x=a.data()+64+shift;auto* y=b.data()+64+shift;
    before::utils::stream_vector_from_memory<N>(x+delta,x);
    after::utils::stream_vector_from_memory<N>(y+delta,y);
    equal(a.data(),b.data(),a.size());
}
#endif
static void stream(){
    for(unsigned shift=0;shift<16;++shift){stream_memory<0>(shift);stream_memory<1>(shift);stream_memory<2>(shift);stream_memory<7>(shift);}
#if defined(ARCH_ARM64)
    // The production routine copies forward one vector at a time. Check exact
    // alias and both overlap directions against the ARM reference, including
    // the observable repeated-block behavior for dst > src.
    for(unsigned shift=0;shift<16;++shift)for(int delta:{-16,0,16}){
        stream_overlap<2>(shift,delta);stream_overlap<7>(shift,delta);
    }
#endif
    for(unsigned i=0;i<1000;++i){alignas(16) std::array<u8,64>a,b;a.fill(0xa7);b=a;auto v=random_vector();
        before::utils::stream_vector(a.data()+16,v._u32[0],v._u32[1],v._u32[2],v._u32[3]);
        after::utils::stream_vector(b.data()+16,v._u32[0],v._u32[1],v._u32[2],v._u32[3]);finish_stores();equal(a.data(),b.data(),64);equal(v._bytes,b.data()+16,16);
        a.fill(0xa7);b=a;
        before::utils::stream_vector(a.data()+16,v._f[0],v._f[1],v._f[2],v._f[3]);
        after::utils::stream_vector(b.data()+16,v._f[0],v._f[1],v._f[2],v._f[3]);finish_stores();equal(a.data(),b.data(),64);
    }
}
static void constants(){
    constexpr u32 edges[]={0,0x80000000,1,0x80000001,0x007fffff,0x807fffff,0x00800000,0x80800000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc00000,0xffc00000,0x7f800001,0xff800001,0x7fffffff,0xffffffff};
    std::array<u8,4096>source;for(auto&v:source)v=rng();
    RSXFragmentProgram prog{source.data()};
    for(unsigned round=0;round<1000;++round){
        std::vector<u32> offsets;unsigned n=round%36;
        for(unsigned j=0;j<n;++j){u32 offset=(j*19+round)%4000;offsets.push_back(offset);
            for(unsigned lane=0;lane<4;++lane){u32 v=edges[(j+lane+round)%std::size(edges)];for(unsigned b=0;b<4;++b)source[offset+lane*4+(b^1)]=static_cast<u8>(v>>(8*b));}}
        for(bool sanitize:{false,true}){alignas(16)std::array<u32,160>a,b;a.fill(0xa7a7a7a7);b=a;
            std::span<f32> x(reinterpret_cast<f32*>(a.data()+4),n*4),y(reinterpret_cast<f32*>(b.data()+4),n*4);
            before::write_constants(x,prog,offsets,sanitize);after::write_constants(y,prog,offsets,sanitize);finish_stores();equal(a.data(),b.data(),a.size()*4);
            for(unsigned j=0;j<n;++j)for(unsigned lane=0;lane<4;++lane){u32 expected=0;for(unsigned byte=0;byte<4;++byte)expected|=u32(source[offsets[j]+lane*4+(byte^1)])<<(byte*8);
                if(sanitize && (expected&0x7fffffff)>=0x7f800000)expected=0;
                check(b[4+j*4+lane]==expected);}
            for(unsigned j=0;j<4;++j)check(b[j]==0xa7a7a7a7);
            for(unsigned j=4+n*4;j<b.size();++j)check(b[j]==0xa7a7a7a7);
        }
    }
}
extern "C" __attribute__((noinline)) v128 rsx526_decode_after(v128 x){return after::decode_instruction(x);}
extern "C" __attribute__((noinline)) void rsx526_stream_after(void*p,v128 x){gv_stream(p,x);}
extern "C" __attribute__((noinline)) u32 rsx526_border_after(u32 x,u32 m){return after::border_color(x,true,m);}
extern "C" __attribute__((noinline)) u32 rsx526_border_before(u32 x,u32 m){return before::border_color(x,true,m);}
struct timing { double wall_ns, cpu_ns; u32 checksum; };
static timing border_timing(u32 (*fn)(u32,u32)) {
    std::array<u32,4096> data;std::mt19937 gen(0x526bf);for(auto&x:data)x=gen();
    constexpr unsigned iterations=1u<<22;
    u32 checksum=0;const auto cpu=std::clock();const auto wall=std::chrono::steady_clock::now();
    for(unsigned i=0;i<iterations;++i) checksum+=fn(data[i&4095],i&15);
    const auto end=std::chrono::steady_clock::now();const auto cpu_end=std::clock();
    return {std::chrono::duration<double,std::nano>(end-wall).count()/iterations,
        double(cpu_end-cpu)*1e9/CLOCKS_PER_SEC/iterations,checksum};
}
static double median(std::vector<double> values){std::sort(values.begin(),values.end());return(values[4]+values[5])*.5;}
static void benchmark(){
    std::vector<double> bw,bc,aw,ac;
    for(unsigned round=0;round<12;++round){timing b{},a{};
        if(round%2){a=border_timing(rsx526_border_after);b=border_timing(rsx526_border_before);}
        else{b=border_timing(rsx526_border_before);a=border_timing(rsx526_border_after);}
        check(a.checksum==b.checksum);
        if(round>=2){bw.push_back(b.wall_ns);bc.push_back(b.cpu_ns);aw.push_back(a.wall_ns);ac.push_back(a.cpu_ns);}
    }
    std::printf(",\"borderBenchmark\":{\"iterationsPerRound\":4194304,\"alternatingRounds\":12,\"discardedRounds\":2,\"medianBeforeWallNsPerOp\":%.9f,\"medianAfterWallNsPerOp\":%.9f,\"medianBeforeCpuNsPerOp\":%.9f,\"medianAfterCpuNsPerOp\":%.9f}",median(bw),median(aw),median(bc),median(ac));
}
int main(int argc,char**){try{vectors();border();iota();stream();constants();
#if defined(ARCH_ARM64)
 const char*arch="ARM64";const unsigned overlap_cases=96;
#else
 const char*arch="x86_64";const unsigned overlap_cases=0;
#endif
 std::printf("{\"checks\":%llu,\"architecture\":\"%s\",\"components\":5,\"borderByteValues\":256,\"borderMasks\":16,\"sourceAlignments\":16,\"iotaCounts\":104,\"shaderRounds\":1000,\"arm64OverlapCases\":%u",static_cast<unsigned long long>(checks),arch,overlap_cases);
 if(argc>1)benchmark();
 std::printf("}\n");return 0;
}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
