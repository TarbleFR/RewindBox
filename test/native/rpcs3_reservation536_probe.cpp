// Native Apple ARM64 experiment; never infer gameplay FPS from this harness.
#include <arm_neon.h>
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <vector>
#define FORCE_INLINE inline __attribute__((always_inline))
#define ARCH_ARM64 1
struct alignas(16) v128 { uint16x8_t value; operator uint16x8_t() const { return value; } };
using spu_rdata_t = std::uint8_t[128];
#include "baseline536.inc"

inline bool xor_tree(const void* lhs,const void* rhs)
{
    const auto* a=static_cast<const std::uint8_t*>(lhs);
    const auto* b=static_cast<const std::uint8_t*>(rhs);
    const auto d0=veorq_u8(vld1q_u8(a),vld1q_u8(b));
    const auto d1=veorq_u8(vld1q_u8(a+16),vld1q_u8(b+16));
    const auto d2=veorq_u8(vld1q_u8(a+32),vld1q_u8(b+32));
    const auto d3=veorq_u8(vld1q_u8(a+48),vld1q_u8(b+48));
    const auto d4=veorq_u8(vld1q_u8(a+64),vld1q_u8(b+64));
    const auto d5=veorq_u8(vld1q_u8(a+80),vld1q_u8(b+80));
    const auto d6=veorq_u8(vld1q_u8(a+96),vld1q_u8(b+96));
    const auto d7=veorq_u8(vld1q_u8(a+112),vld1q_u8(b+112));
    const auto lo=vorrq_u8(vorrq_u8(d0,d1),vorrq_u8(d2,d3));
    const auto hi=vorrq_u8(vorrq_u8(d4,d5),vorrq_u8(d6,d7));
    return vmaxvq_u8(vorrq_u8(lo,hi))==0;
}

inline bool two_accumulators(const void* lhs,const void* rhs)
{
    const auto* a=static_cast<const std::uint8_t*>(lhs);
    const auto* b=static_cast<const std::uint8_t*>(rhs);
    // Equal 16-bit lanes are -1, whose pairwise product is one.
    auto lanes=[&](unsigned offset){return vreinterpretq_s16_u16(vceqq_u16(vreinterpretq_u16_u8(vld1q_u8(a+offset)),vreinterpretq_u16_u8(vld1q_u8(b+offset))));};
    const auto lo=vmlaq_s16(vmulq_s16(lanes(0),lanes(16)),lanes(32),lanes(48));
    const auto hi=vmlaq_s16(vmulq_s16(lanes(64),lanes(80)),lanes(96),lanes(112));
    return vaddvq_s16(vaddq_s16(lo,hi))==32;
}

extern "C" __attribute__((noinline)) bool reference536(const void* a,const void* b)
{return cmp_rdata(*static_cast<const spu_rdata_t*>(a),*static_cast<const spu_rdata_t*>(b));}
extern "C" __attribute__((noinline)) bool xor536(const void* a,const void* b) {return xor_tree(a,b);}
extern "C" __attribute__((noinline)) bool dual536(const void* a,const void* b) {return two_accumulators(a,b);}
using Fn=bool(*)(const void*,const void*);
struct alignas(128) Pair {std::array<std::uint8_t,128> a{},b{};};

int main()
{
    std::mt19937_64 random(0x536);
    Pair p;
    std::uint64_t verified=0;
    auto check=[&]{const bool expected=std::memcmp(p.a.data(),p.b.data(),128)==0;
        for(Fn f:{reference536,xor536,dual536})assert(f(p.a.data(),p.b.data())==expected);++verified;};
    check();p.a.fill(255);p.b=p.a;check();
    for(unsigned byte=0;byte<128;++byte)for(unsigned bit=0;bit<8;++bit){p.b=p.a;p.b[byte]^=1u<<bit;check();}
    for(unsigned i=0;i<25000;++i){for(auto& x:p.a)x=random();p.b=p.a;if(i%3)for(unsigned k=0;k<1+i%128;++k)p.b[random()%128]^=1u<<(random()%8);check();}
    std::cout<<"{\"verifiedCases\":"<<verified<<"}\n";
    for(unsigned pairs:{32u,4096u}){
        std::vector<Pair> data(pairs);
        for(unsigned i=0;i<pairs;++i){for(auto& x:data[i].a)x=random();data[i].b=data[i].a;if(i%2)data[i].b[(i*37)%128]^=1u<<(i%8);}
        const std::array<Fn,3> kernels{reference536,xor536,dual536};
        const std::array<const char*,3> names{"reference","xor","dual"};
        for(unsigned round=0;round<7;++round)for(unsigned order=0;order<3;++order){
            const unsigned k=(order+round)%3;auto fn=kernels[k];std::uint64_t checksum=0;
            for(unsigned i=0;i<10000;++i){const auto& item=data[i&(pairs-1)];checksum+=fn(item.a.data(),item.b.data());}
            constexpr unsigned iterations=2000000;
            const auto begin=std::chrono::steady_clock::now();
            for(unsigned i=0;i<iterations;++i){const auto& item=data[(i*29)&(pairs-1)];asm volatile("" ::: "memory");checksum+=fn(item.a.data(),item.b.data());}
            const double ns=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-begin).count()/iterations;
            assert(checksum==1005000);
            std::cout<<"{\"kernel\":\""<<names[k]<<"\",\"pairs\":"<<pairs<<",\"round\":"<<round<<",\"nsPerCall\":"<<ns<<",\"checksum\":"<<checksum<<"}\n";
        }
    }
}
