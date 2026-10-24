// SPDX-License-Identifier: MIT
// Production methods and v128 are supplied by rpcs3_simd526_test.py. These
// register/opcode/scale adapters have no emulator, guest memory or GPU service.
#include <algorithm>
#include <array>
#include <bit>
#include <cassert>
#include <cfenv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
#if defined(ARCH_ARM64)
#include <arm_neon.h>
#include "Emu/CPU/sse2neon.h" // Baseline differential control only.
#else
#include <immintrin.h>
#endif
#include "util/v128.hpp"
namespace utils { inline bool has_avx512() { return false; } inline bool has_fma3() { return true; } }
#include "native-gv.hpp"
struct spu_thread { v128 gpr[8]; };
struct spu_opcode_t
{
    u32 ra=0, rb=1, rc=2, rt=3, rt4=4, i7=0, i8=0, i16=0, i18=0;
    s32 si10=0, si16=0;
};
struct ScaleTable
{
    std::array<v128, 329> values{};
    ScaleTable() { for (s32 i=-155; i<174; ++i) values[i+155] = v128::fromf32p(static_cast<float>(std::exp2(i))); }
    const v128& operator[](s32 index) const { assert(index >= -155 && index < 174); return values[index+155]; }
};
struct { ScaleTable scale; } g_spu_imm;
#include "luts.hpp"
#include "instructions.hpp"
struct TestCase { const char* name; bool (*before)(spu_thread&, spu_opcode_t); bool (*after)(spu_thread&, spu_opcode_t); };
#include "cases.hpp"
#include "wrappers.hpp"

static u64 random_state=0x721086ab32f14a09ull;
static u64 random64() { random_state ^= random_state<<13; random_state ^= random_state>>7; random_state ^= random_state<<17; return random_state; }
static spu_thread registers()
{
    spu_thread result;
    for (auto& v: result.gpr) { v._u64[0]=random64(); v._u64[1]=random64(); }
    return result;
}
static u64 checks=0;
static u64 scalar_reference_checks=0;
static u64 legacy_macro_mismatches=0;
static u32 legacy_macro_control_mismatches=0;

// Independent CELL lane semantics. No gv/SSE/NEON operation is used here.
// ROTMAI: IBM/Sony/Toshiba SPU ISA v1.2 (27 Jan 2007), printed p.148;
// https://moss.csc.ncsu.edu/~mueller/cluster/ps3/SDK3.0/docs/arch/SPU_ISA_v1.2_27Jan2007_pub.pdf
// The production SPULLVMRecompiler::ROTMAI independently uses the same
// modulo-64 negated count followed by a sign-filling right shift.
// Arithmetic shifts construct the sign fill explicitly rather than relying
// on the host's signed-shift or integer-negation behavior.
static bool reference_immediate(const TestCase& test, const spu_thread& input,
    spu_opcode_t op, spu_thread& expected)
{
    enum class Kind { rotate, left, right, arithmetic };
    Kind kind; u32 width;
    if (!std::strcmp(test.name,"ROTI")) {kind=Kind::rotate;width=32;}
    else if (!std::strcmp(test.name,"ROTMI")) {kind=Kind::right;width=32;}
    else if (!std::strcmp(test.name,"ROTMAI")) {kind=Kind::arithmetic;width=32;}
    else if (!std::strcmp(test.name,"SHLI")) {kind=Kind::left;width=32;}
    else if (!std::strcmp(test.name,"ROTHI")) {kind=Kind::rotate;width=16;}
    else if (!std::strcmp(test.name,"ROTHMI")) {kind=Kind::right;width=16;}
    else if (!std::strcmp(test.name,"ROTMAHI")) {kind=Kind::arithmetic;width=16;}
    else if (!std::strcmp(test.name,"SHLHI")) {kind=Kind::left;width=16;}
    else return false;
    expected=input;
    const u32 mask=width==32?0xffffffffu:0xffffu;
    const u32 count=kind==Kind::rotate?(op.i7&(width-1)):
        kind==Kind::left?(op.i7&(width*2-1)):((0u-op.i7)&(width*2-1));
    for(u32 lane=0;lane<128/width;++lane)
    {
        const u32 value=width==32?input.gpr[op.ra]._u32[lane]:input.gpr[op.ra]._u16[lane];
        u32 result;
        if(kind==Kind::rotate)
            result=count?u32((u64(value)<<count)|(value>>(width-count)))&mask:value;
        else if(kind==Kind::left)
            result=count<width?u32(u64(value)<<count)&mask:0;
        else if(kind==Kind::right)
            result=count<width?value>>count:0;
        else
        {
            const u32 fill=(value>>(width-1))?mask:0;
            result=count>=width?fill:count?((value>>count)|(fill^(fill>>count))):value;
        }
        if(width==32) expected.gpr[op.rt]._u32[lane]=result;
        else expected.gpr[op.rt]._u16[lane]=u16(result);
    }
    return true;
}
static void compare(const TestCase& test, const spu_thread& input, spu_opcode_t op)
{
    auto a=input, b=input;
    const auto before=test.before(a,op), after=test.after(b,op);
    spu_thread expected;
    const bool has_reference=reference_immediate(test,input,op,expected);
    if(has_reference)
    {
        ++scalar_reference_checks;
        if(std::memcmp(&b,&expected,sizeof(b)))
        {
            std::cerr << "Candidate disagrees with independent CELL shift reference: " << test.name << " i7=" << op.i7 << '\n';
            std::exit(1);
        }
    }
#if defined(ARCH_ARM64)
    // The old srai32 macro uses -imm rather than -(imm). In ROTMAI,
    // -(0-op.i7)&63 becomes a positive left-shift count. Preserve and count
    // the real control failure; only the candidate must match CELL here.
    if(!std::strcmp(test.name,"ROTMAI") && std::memcmp(&a,&b,sizeof(a)))
    {
        const u32 count=(0u-op.i7)&63;
        auto broken=input;broken.gpr[op.rt]={};
        if(!has_reference || !before || !after || count==0 || count>=32 ||
            std::memcmp(&a,&broken,sizeof(a)))
        {
            std::cerr << "Unexpected legacy shift discrepancy\n";
            std::exit(1);
        }
        ++legacy_macro_mismatches;
        ++checks;
        return;
    }
#endif
    if (before!=after || std::memcmp(&a,&b,sizeof(a)))
    {
        std::cerr << "Mismatch " << test.name << " case=" << checks << " rounding=" << fegetround() << " i7=" << op.i7 << " i8=" << op.i8 << " rt=" << op.rt << " rt4=" << op.rt4 << '\n';
        for (u32 r=0;r<8;++r) for (u32 l=0;l<4;++l) if(a.gpr[r]._u32[l]!=b.gpr[r]._u32[l])
            std::cerr << " r=" << r << " lane=" << l << " input_a=" << std::hex << input.gpr[op.ra]._u32[l] << " b=" << input.gpr[op.rb]._u32[l] << " c=" << input.gpr[op.rc]._u32[l] << " old=" << a.gpr[r]._u32[l] << " new=" << b.gpr[r]._u32[l] << std::dec << '\n';
        std::exit(1);
    }
    ++checks;
}
static const TestCase& find_case(const char* name)
{
    for(const auto& c:cases) if(!std::strcmp(c.name,name)) return c;
    std::abort();
}
static spu_opcode_t opcode(u32 i)
{
    spu_opcode_t op;
    op.i7=i&127;op.i8=i&255;op.i16=i&65535;op.i18=i&262143;
    op.si10=s32(i&1023)-512;op.si16=s32(i&65535)-32768;
    op.rt=(i>>3)%5;op.rt4=(i>>6)%5;
    return op;
}
static void legacy_shift_macro_control()
{
    const auto& test=find_case("ROTMAI");
    for(u32 immediate=0;immediate<128;++immediate)
    {
        spu_thread input{};spu_opcode_t op;op.i7=immediate;
        input.gpr[0]=v128::from32(0xffffffffu,0x80000000u,0x12345678u,0);
        auto old=input,actual=input;spu_thread expected;
        assert(reference_immediate(test,input,op,expected));
        assert(test.before(old,op) && test.after(actual,op));
        if(std::memcmp(&actual,&expected,sizeof(actual)))std::abort();
        if(std::memcmp(&old,&expected,sizeof(old)))
        {
            ++legacy_macro_control_mismatches;
            auto broken=input;broken.gpr[3]={};
            assert(((immediate&63)>=33) && !std::memcmp(&old,&broken,sizeof(old)));
        }
    }
#if defined(ARCH_ARM64)
    assert(legacy_macro_control_mismatches==62);
#else
    assert(legacy_macro_control_mismatches==0);
#endif
}
static void differential()
{
    legacy_shift_macro_control();
    const int original_round=fegetround();
    const std::array<int,4> modes={FE_TONEAREST,FE_TOWARDZERO,FE_UPWARD,FE_DOWNWARD};
    // Four rounding modes, destination aliasing all sources, all immediate
    // widths, and high count bits exercise the production instruction bodies.
    for(bool flush : {false, true})
    {
    if (flush) gv_set_zeroing_denormals(); else gv_unset_zeroing_denormals();
    for(int mode:modes)
    {
        fesetround(mode);
        for(const auto& c:cases)
        {
            for(u32 i=0;i<4096;++i) compare(c,registers(),opcode(i));
            constexpr u32 special[]={0,0x80000000,1,0x80000001,0x007fffff,0x807fffff,0x00800000,0x80800000,
                0x3f800000,0xbf800000,0x3f000000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,
                0x7fc00000,0x7f800001,0xff800001,0x7fffffff,0xffffffff,0x4effffff,0x4f000000,
                0x4f000001,0x4f7fffff,0x4f800000,0x4f800001,0xcf000000,0xcf000001};
            for(u32 i=0;i<std::size(special)*std::size(special);++i)
            {
                auto input=registers();
                for(u32 r=0;r<8;++r) for(u32 l=0;l<4;++l)
                    input.gpr[r]._u32[l]=special[(i/std::size(special)+r+l)%std::size(special)];
                input.gpr[0]=v128::from32p(special[i%std::size(special)]);
                compare(c,input,opcode(i));
            }
            constexpr u64 doubles[]={0,0x8000000000000000ull,1,0x000fffffffffffffull,0x0010000000000000ull,
                0x3ff0000000000000ull,0xbff0000000000000ull,0x7fefffffffffffffull,0xffefffffffffffffull,
                0x7ff0000000000000ull,0xfff0000000000000ull,0x7ff0000000000001ull,0x7ff800000000beefull,0xfff8000000001234ull};
            for(u32 i=0;i<std::size(doubles)*std::size(doubles);++i)
            {
                auto input=registers();
                for(u32 r=0;r<8;++r) for(u32 l=0;l<2;++l)
                    input.gpr[r]._u64[l]=doubles[(i/std::size(doubles)+r+l)%std::size(doubles)];
                input.gpr[0]._u64[0]=doubles[i%std::size(doubles)];
                compare(c,input,opcode(i));
            }
        }
    }
    }
    gv_unset_zeroing_denormals();
    fesetround(original_round);
    // Every mask and every SHUFB control byte, including all special classes.
    for(u32 i=0;i<65536;++i)
    {
        auto input=registers();auto op=opcode(i);op.rt=3;op.rt4=4;
        input.gpr[0]._u32[3]=i;
        compare(find_case("FSMBI"),input,op);
        compare(find_case("FSMB"),input,op);
        compare(find_case("FSMH"),input,op);
        compare(find_case("FSM"),input,op);
    }
    for(u32 i=0;i<256;++i)
    {
        auto input=registers();input.gpr[2]=v128::from8p(i);
        compare(find_case("SHUFB"),input,opcode(i));
    }
    // Logical and arithmetic shifts must not wrap at 16/32, including lane
    // counts with every high bit set. Also exercise byte shift zero fill.
    for(u32 count=0;count<128;++count)
    {
        auto input=registers();input.gpr[1]=v128::from32p(count);
        for(const char* name:{"ROT","ROTM","ROTMA","SHL","ROTI","ROTMI","ROTMAI","SHLI","ROTQBYBI","ROTQBY","ROTQBYI","ROTQMBYBI","ROTQMBY","ROTQMBYI","SHLQBYBI","SHLQBY","SHLQBYI"})
            compare(find_case(name),input,opcode(count));
        input.gpr[1]=v128::from16p(count);
        for(const char* name:{"ROTH","ROTHM","ROTMAH","SHLH","ROTHI","ROTHMI","ROTMAHI","SHLHI"})
            compare(find_case(name),input,opcode(count));
    }
    std::cout << "{\"mode\":\"differential\",\"instruction_count\":" << std::size(cases) << ",\"register_comparisons\":" << checks << ",\"scalar_shift_reference_checks\":" << scalar_reference_checks << ",\"known_legacy_shift_macro_mismatches\":" << legacy_macro_mismatches << ",\"legacy_macro_control_cases\":128,\"legacy_macro_control_mismatches\":" << legacy_macro_control_mismatches << ",\"rounding_modes\":4,\"denormal_modes\":2,\"exhaustive_mask16\":65536,\"shufb_control_values\":256,\"legacy_adapter_used_only_by_control\":true}\n";
}
static volatile u64 consumed=0;
struct Timing { double wall_ns; double cpu_ns; };
static Timing sample(bool(*function)(spu_thread&,spu_opcode_t), u32 n)
{
    random_state=0x5316bbfe99102e17ull;
    auto state=registers();spu_opcode_t op;
    auto begin=std::chrono::steady_clock::now();const auto cpu=std::clock();
    for(u32 i=0;i<n;++i)
    {
        op.i7=i&127;op.i8=(i&63)+128;
        function(state,op);
        state.gpr[0]=state.gpr[3]^v128::from32p(i*0x9e3779b9u);
        state.gpr[2]=state.gpr[4]^state.gpr[0];
        state.gpr[1]._u32[3]=i;
    }
    const auto cpu_end=std::clock();const auto end=std::chrono::steady_clock::now();
    consumed=state.gpr[0]._u64[0]^state.gpr[4]._u64[1];
    return {std::chrono::duration<double,std::nano>(end-begin).count()/n, double(cpu_end-cpu)*1e9/CLOCKS_PER_SEC/n};
}
static double median(std::vector<double> x) { std::sort(x.begin(),x.end());return(x[4]+x[5])/2; }
static void benchmark()
{
    std::cout << "{\"mode\":\"synthetic_component_benchmark\",\"rounds\":12,\"discarded_rounds\":2,\"iterations_per_round\":1000000,\"samples\":[";
    bool first=true;
    for(const char* name:{"CNTB","SHUFB","ROTM","ROTHM","ROTQBY","ROTQMBY","SHLQBY","CFLTU"})
    {
        const auto& c=find_case(name);std::vector<double> a,b,ac,bc;
        for(u32 round=0;round<12;++round)
        {
            Timing before,after;
            if(round&1){after=sample(c.after,1000000);before=sample(c.before,1000000);}
            else{before=sample(c.before,1000000);after=sample(c.after,1000000);}
            if(round>=2){a.push_back(before.wall_ns);b.push_back(after.wall_ns);ac.push_back(before.cpu_ns);bc.push_back(after.cpu_ns);}
        }
        if(!first)std::cout<<',';first=false;
        std::cout << "{\"instruction\":\""<<name<<"\",\"before_wall_ns\":"<<median(a)<<",\"after_wall_ns\":"<<median(b)<<",\"before_cpu_ns\":"<<median(ac)<<",\"after_cpu_ns\":"<<median(bc)<<",\"before_rounds_ns\":[";
        for(u32 i=0;i<a.size();++i){if(i)std::cout<<',';std::cout<<a[i];}std::cout<<"],\"after_rounds_ns\":[";
        for(u32 i=0;i<b.size();++i){if(i)std::cout<<',';std::cout<<b[i];}std::cout<<"]}";
    }
    std::cout << "],\"physical_device_tested\":false,\"cache_temperature\":\"not_a_game_or_storage_test\"}\n";
}
int main(int argc,char**argv)
{
    if(argc>1 && !std::strcmp(argv[1],"--baseline-undefined-negation"))
    {
        spu_thread state{}; spu_opcode_t op;
        state.gpr[1]._u32[3]=0x80000000;
        return !baseline_control::ROTQMBI(state,op);
    }
    if(argc>1 && !std::strcmp(argv[1],"--benchmark")) benchmark();
    else differential();
}
