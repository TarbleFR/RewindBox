#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <limits>
#include <random>
#include <set>
#include <vector>
using u64=std::uint64_t;
using u128=__uint128_t;
constexpr u64 max64=std::numeric_limits<u64>::max();
#define ensure(v) do { if (!(v)) std::abort(); } while(false)
#if defined(__GNUC__) && !defined(__clang__)
#define CLOCK_NOINLINE __attribute__((noinline,noclone))
#else
#define CLOCK_NOINLINE __attribute__((noinline))
#endif
// Runtime reads stop specialization/constant folding of the old conversion.
namespace utils {
volatile u64 host_frequency=1000000000ull, counter=0;
u64 get_tsc_freq() {return host_frequency;}
u64 get_tsc() {return counter;}
}
struct Config {struct {u64 clocks_scale=100;} core;};
Config g_cfg;
u64 g_timebase_offs=0;
static constexpr u64 g_timebase_freq=80000000ull;
int fake_clock_gettime(clockid_t, timespec* out) {out->tv_sec=123;out->tv_nsec=456789012;return 0;}
#define clock_gettime fake_clock_gettime
namespace before {
// BEFORE_FUNCTIONS
}
namespace after {
// AFTER_FUNCTIONS
}
#undef clock_gettime
u64 checks=0, scale_overflows=0, frequency_fallbacks=0;
void check(u64 stamp,u64 frequency,u64 scale,u64 offset) {
    utils::counter=stamp;utils::host_frequency=frequency;
    g_cfg.core.clocks_scale=scale;g_timebase_offs=offset;
    const u64 a=before::get_system_time(),b=after::get_system_time();
    const u64 c=before::get_timebased_time(),d=after::get_timebased_time();
    const u64 ticks=static_cast<u64>(u128(stamp)*80000000ull/frequency);
    // Explicitly wrap the scale multiplication BEFORE division, as production
    // does; widening through division would change long-running counters.
    const u64 scaled=ticks*scale;
    assert(a==b && c==d);
    assert(a==static_cast<u64>(u128(stamp)*1000000ull/frequency));
    assert(c==scaled/100-offset);
    scale_overflows+=(u128(ticks)*scale)>max64;
    frequency_fallbacks+=frequency!=1000000000ull;
    ++checks;
}
void boundaries() {
    std::set<u64> stamps;
    auto around=[&](u64 center,u64 radius) {
        const u64 begin=center<radius?0:center-radius;
        const u64 end=center>max64-radius?max64:center+radius;
        for(u64 t=begin;;++t) {stamps.insert(t);if(t==end) break;}
    };
    for(u64 center:{u64(0),u64(25),u64(1000),u64(1000000000ull),max64/2,max64}) around(center,1024);
    // Every remainder of the reduced denominator at small and extreme
    // quotients, including the final partial 25-tick block of u64.
    for(u64 q:{u64(0),u64(1),u64(12345),max64/50,max64/25-1,max64/25})
        for(u64 r=0;r<25;++r) if(q*25<=max64-r) stamps.insert(q*25+r);
    // Counter positions immediately around the original 1 GHz divisions.
    for(u64 q:{u64(1),u64(19),u64(123456),u64(max64/1000000000ull)}) around(q*1000000000ull,25);
    // Boundaries where the unchanged clock-scale multiplication wraps.
    for(u64 s:{u64(10),u64(50),u64(100),u64(125),u64(3000)}) {
        const u128 center=u128(max64/s)*25/2;
        if(center<=max64) around(static_cast<u64>(center),50);
    }
    for(u64 frequency:{u64(1000000000ull),u64(24000000ull)})
        for(u64 scale:{u64(10),u64(50),u64(100),u64(125),u64(3000)})
            for(u64 offset:{u64(0),u64(1),u64(123456789012345ull),max64})
                for(u64 stamp:stamps) check(stamp,frequency,scale,offset);
}
void randomized() {
    std::mt19937_64 rng(20261029);
    constexpr u64 frequencies[]={1,2,3,1000000,19200000,24000000,25000000,80000000,100000000,1000000000ull,3000000000ull};
    for(unsigned i=0;i<150000;++i) {
        const u64 stamp=rng(), frequency=frequencies[rng()%std::size(frequencies)];
        const u64 scale=10+rng()%2991, offset=rng();
        check(stamp,frequency,scale,offset);
    }
    // Zero-frequency fallback retains exactly the original system clock path.
    utils::host_frequency=0;
    for(u64 scale:{u64(10),u64(100),u64(3000)}) for(u64 offset:{u64(0),max64}) {
        g_cfg.core.clocks_scale=scale;g_timebase_offs=offset;
        assert(before::get_system_time()==after::get_system_time());
        assert(before::get_timebased_time()==after::get_timebased_time());
    }
}
struct Timing {double system_before,system_after,timebase_before,timebase_after;};
Timing benchmark() {
    utils::host_frequency=1000000000ull;
    g_cfg.core.clocks_scale=100;g_timebase_offs=0;
    auto run=[](u64 (*fn)()) {
        const auto start=std::chrono::steady_clock::now();u64 checksum=0;
        for(u64 i=0;i<1000000;++i) {
            utils::counter=123456789012345ull+i*1709;
            checksum+=fn();
        }
        const double elapsed=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        assert(checksum);return elapsed;
    };
    std::array<double,7> sb{},sa{},tb{},ta{};
    for(unsigned i=0;i<7;++i) {
        if(i&1) {sa[i]=run(after::get_system_time);sb[i]=run(before::get_system_time);ta[i]=run(after::get_timebased_time);tb[i]=run(before::get_timebased_time);}
        else {sb[i]=run(before::get_system_time);sa[i]=run(after::get_system_time);tb[i]=run(before::get_timebased_time);ta[i]=run(after::get_timebased_time);}
    }
    for(auto* a:{&sb,&sa,&tb,&ta}) std::sort(a->begin(),a->end());
    return {sb[3],sa[3],tb[3],ta[3]};
}
int main(int argc,char**) {
    boundaries();randomized();
    assert(scale_overflows && frequency_fallbacks);
    std::cout<<"{\"arithmeticCases\":"<<checks<<",\"clockScaleOverflowCases\":"<<scale_overflows
             <<",\"genericFrequencyCases\":"<<frequency_fallbacks<<",\"zeroFrequencyFallbackCases\":6";
    if(argc>1) {
        const auto t=benchmark();
        std::cout<<",\"syntheticMillionCallsMedianMs\":{\"systemBefore\":"<<t.system_before<<",\"systemAfter\":"<<t.system_after
                 <<",\"timebaseBefore\":"<<t.timebase_before<<",\"timebaseAfter\":"<<t.timebase_after<<"}";
    }
    std::cout<<"}\n";
}
