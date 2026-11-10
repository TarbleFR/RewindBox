#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <new>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>
#include <cstdint>
using usz=std::size_t;using u32=std::uint32_t;
constexpr auto umax=static_cast<usz>(-1);
static thread_local bool count_allocations=false;
static thread_local usz allocations=0;
__attribute__((noinline)) void* operator new(std::size_t n){if(count_allocations)++allocations;if(auto p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
__attribute__((noinline)) void operator delete(void* p) noexcept{std::free(p);}
__attribute__((noinline)) void operator delete(void* p,std::size_t) noexcept{std::free(p);}
@REPLACE@
@PARAMS@
@HELPER@
constexpr int RSX_FP_OPCODE_TEXBEM=1,RSX_FP_OPCODE_TXPBEM=2;
struct SRC0{static constexpr int index=0;};struct SRC1{static constexpr int index=1;};struct SRC2{static constexpr int index=2;};
struct Boundary {
    int mode=0;std::vector<int> events;ParamArray params;
    struct {int tex_num=3,opcode=0;bool fp16=false;}dst;
    struct {int tex_num=7;}d2;
    struct {bool has_native_half_support=false;}device_props;
    std::string invoke(int key){
        events.push_back(key);
        const auto name=std::string("param")+std::to_string(key);
        params.AddParam(PF_PARAM_NONE,"vec4",name,mode);
        switch(mode%5){
        case 0:return name;
        case 1:return {};
        case 2:return "$0$$"+name;
        case 3:return std::string(100,'x')+name;
        default:return std::string("x\0$Ty",5)+name;
        }
    }
    std::string AddAddrReg(){return invoke(3);}
    std::string GetCond(){return mode%3==0?"true":invoke(4);}
    std::string GetOptionalBranchCond(){return invoke(5);}
    std::string GetMask(){return invoke(6);}
    std::string AddConst(){return invoke(7);}
    std::string getFloatTypeName(usz n){return invoke(10+static_cast<int>(n));}
    std::string getHalfTypeName(usz n){return invoke(20+static_cast<int>(n));}
    void reset(int value){mode=value;events.clear();params.Clear();}
    std::string declarations()const{
        std::string result;for(const auto& group:params.params)for(const auto& type:group)for(const auto& item:type.items)
            result+=type.type+"/"+item.name+"/"+item.value+"/"+std::to_string(item.location)+";";
        return result;
    }
};
// BEGIN BOUNDARY
struct VertexProgramDecompiler:Boundary{
    std::string GetSRC(u32 n){return invoke(static_cast<int>(n));}
    struct Instr{std::vector<std::string>body;}instruction;
    Instr* m_cur_instr=&instruction;std::vector<std::string>m_body;
    std::string Format(const std::string& code);void AddCode(const std::string& code);
};
struct FragmentProgramDecompiler:Boundary{
    SRC0 src0;SRC1 src1;SRC2 src2;
    template<typename T>std::string GetSRC(T){return invoke(T::index);}
    std::string Format(const std::string& code,bool ignore_redirects=false);
};
// END BOUNDARY
static const std::vector<std::string> corpus={@CORPUS@};
static std::uint64_t random_state=0x14067a9d65dull;
static u32 random_value(){random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return static_cast<u32>(random_state);}
static usz checks=0,addcode_checks=0;
static void check(const std::string& input,int mode){
    before::VertexProgramDecompiler a;after::VertexProgramDecompiler b;desktop::VertexProgramDecompiler d;
    a.reset(mode);b.reset(mode);d.reset(mode);
    const auto old=a.Format(input),cur=b.Format(input),desk=d.Format(input);
    assert(old==cur&&old==desk&&a.events==b.events&&a.events==d.events);
    assert(a.declarations()==b.declarations()&&a.declarations()==d.declarations());++checks;
    a.reset(mode);b.reset(mode);d.reset(mode);a.AddCode(input);b.AddCode(input);d.AddCode(input);
    assert(a.m_body==b.m_body&&a.m_body==d.m_body&&a.instruction.body==b.instruction.body&&a.instruction.body==d.instruction.body);
    assert(a.declarations()==b.declarations()&&a.declarations()==d.declarations());
    assert(a.events.size()==2*b.events.size());
    assert(std::equal(b.events.begin(),b.events.end(),a.events.begin()));++addcode_checks;
    for(int opcode=0;opcode<3;++opcode)for(bool ignore:{false,true}){
        before::FragmentProgramDecompiler fa;after::FragmentProgramDecompiler fb;desktop::FragmentProgramDecompiler fd;
        for(auto* ptr:std::vector<Boundary*>{&fa,&fb,&fd}){ptr->reset(mode);ptr->dst.opcode=opcode;ptr->dst.fp16=(mode&1);ptr->device_props.has_native_half_support=(mode&2);}
        const auto x=fa.Format(input,ignore),y=fb.Format(input,ignore),z=fd.Format(input,ignore);
        assert(x==y&&x==z&&fa.events==fb.events&&fa.events==fd.events);
        assert(fa.declarations()==fb.declarations()&&fa.declarations()==fd.declarations());++checks;
    }
}
static volatile usz sink=0;
template<class T>static std::pair<double,usz> benchmark(const std::string& input,int mode,int loops){
    T instance;instance.reset(mode);instance.events.reserve(1000000);
    for(int i=0;i<4;++i){const auto value=instance.Format(input);sink=value.size();}
    allocations=0;count_allocations=true;const auto started=std::chrono::steady_clock::now();
    for(int i=0;i<loops;++i){instance.events.clear();const auto result=instance.Format(input);sink=result.size();}
    const auto stopped=std::chrono::steady_clock::now();count_allocations=false;
    return {std::chrono::duration<double,std::nano>(stopped-started).count()/loops,allocations};
}
int main(int argc,char**){
    for(const auto& input:corpus)for(int mode=0;mode<10;++mode)check(input,mode);
    const std::vector<std::string>parts={"abc"," ","$","$$","$0","$1","$2","$s","$t","$a","$m","$_c","$_i","$Ty","$cond","$ifcond ","$ifbcond","$float4","$float_t","$half2","$half_t","$unknown","\n",std::string("\0",1)};
    check({},0);check("$",0);check(std::string(4096,'z'),0);
    for(int i=0;i<10000;++i){std::string input;for(u32 j=random_value()%20;j;--j)input+=parts[random_value()%parts.size()];check(input,static_cast<int>(random_value()%10));}
    std::cout<<"{\"formatChecks\":"<<checks<<",\"addCodeChecks\":"<<addcode_checks<<",\"productionTokenLiterals\":"<<corpus.size()<<",\"identicalTextAndCallbackOrder\":true,\"sameDeclarations\":true,\"benchmarks\":[";
    if(argc>1){
        const std::vector<std::pair<std::string,std::string>> cases={{"literal",std::string(160,'x')},{"typical","$ifcond r0$m = clamp($0 * $1 + $2, 0.0, 1.0)$m;"},{"tokens",std::string(20,'$')+"$0$1$2$cond$Ty$float4$half4$_c"}};
        bool first=true;for(const auto& [name,input]:cases)for(int mode:{0,1,3}){
            const auto a=benchmark<before::FragmentProgramDecompiler>(input,mode,3000);const auto b=benchmark<after::FragmentProgramDecompiler>(input,mode,3000);
            const auto va=benchmark<before::VertexProgramDecompiler>(input,mode,3000);const auto vb=benchmark<after::VertexProgramDecompiler>(input,mode,3000);
            if(!first)std::cout<<",";
            first=false;
            std::cout<<"{\"case\":\""<<name<<"\",\"mode\":"<<mode<<",\"fragmentBeforeNs\":"<<a.first<<",\"fragmentAfterNs\":"<<b.first<<",\"fragmentBeforeAllocations\":"<<a.second<<",\"fragmentAfterAllocations\":"<<b.second<<",\"vertexBeforeNs\":"<<va.first<<",\"vertexAfterNs\":"<<vb.first<<",\"vertexBeforeAllocations\":"<<va.second<<",\"vertexAfterAllocations\":"<<vb.second<<",\"iterations\":3000}";
        }
    }
    std::cout<<"]}\n";
}
