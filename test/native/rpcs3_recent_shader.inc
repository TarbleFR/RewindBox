#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <bitset>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <random>
#include <set>
#include <shared_mutex>
#include <span>
#include <source_location>
#include <string>
#include <thread>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using usz=std::size_t; using uchar=unsigned char;
using u64=std::uint64_t; using u32=std::uint32_t; using u16=std::uint16_t;
using u8=std::uint8_t; using f32=float;
namespace fmt {template<class... T>[[noreturn]]void raw_range_error(T&&...){std::abort();}}
template<class T>T format_object_simplified(T value){return value;}
template<class T> using atomic_t=std::atomic<T>;
using shared_mutex=std::shared_mutex;
struct reader_lock {
    shared_mutex& mutex; bool exclusive=false;
    explicit reader_lock(shared_mutex& m):mutex(m){mutex.lock_shared();}
    void upgrade(){mutex.unlock_shared();mutex.lock();exclusive=true;}
    ~reader_lock(){if(exclusive)mutex.unlock();else mutex.unlock_shared();}
};
#define ensure(condition) do { if(!(condition)) std::abort(); } while(false)
using uint32x4_t=std::array<u32,4>;
inline uint32x4_t veorq_u32(uint32x4_t a,uint32x4_t b){for(usz i=0;i<4;++i)a[i]^=b[i];return a;}
inline u32 vmaxvq_u32(uint32x4_t a){return *std::max_element(a.begin(),a.end());}
union v128 {
    __uint128_t _u; u64 _u64[2];u32 _u32[4];
    static v128 loadu(const void* p,usz index=0){v128 v;std::memcpy(&v,static_cast<const u8*>(p)+index*16,16);return v;}
    explicit operator uint32x4_t()const{return {_u32[0],_u32[1],_u32[2],_u32[3]};}
};
namespace rsx {inline constexpr u32 max_vertex_program_instructions=544; enum class texture_dimension_extended:u8 {};}
// PRODUCTION_TYPES
namespace rsx {
bool fragment_program_texture_state::operator==(const fragment_program_texture_state& p)const {
    return texture_dimensions==p.texture_dimensions&&redirected_textures==p.redirected_textures&&shadow_textures==p.shadow_textures&&multisampled_textures==p.multisampled_textures;
}
bool vertex_program_texture_state::operator==(const vertex_program_texture_state& p)const {
    return texture_dimensions==p.texture_dimensions&&multisampled_textures==p.multisampled_textures;
}
}
namespace program_hash_util {
struct vertex_program_utils {static usz get_vertex_program_ucode_hash(const RSXVertexProgram&);};
struct fragment_program_utils {static bool is_any_src_constant(v128);static usz get_fragment_program_ucode_hash(const RSXFragmentProgram&);};
struct vertex_program_storage_hash{usz operator()(const RSXVertexProgram&)const;};
struct fragment_program_storage_hash{usz operator()(const RSXFragmentProgram&)const;};
struct vertex_program_compare{static bool compare_properties(const RSXVertexProgram&,const RSXVertexProgram&);bool operator()(const RSXVertexProgram&,const RSXVertexProgram&)const;};
struct fragment_program_compare{static bool compare_properties(const RSXFragmentProgram&,const RSXFragmentProgram&);bool operator()(const RSXFragmentProgram&,const RSXFragmentProgram&)const;};
}
using namespace program_hash_util;
// PRODUCTION_HASHES
inline std::atomic<u64> vertex_hashes{0},fragment_hashes{0};
inline bool count_hashes=true;
struct CountedVertexHash:vertex_program_storage_hash {
    usz operator()(const RSXVertexProgram& p)const{if(count_hashes)++vertex_hashes;return vertex_program_storage_hash::operator()(p);}
};
struct CountedFragmentHash:fragment_program_storage_hash {
    usz operator()(const RSXFragmentProgram& p)const{if(count_hashes)++fragment_hashes;return fragment_program_storage_hash::operator()(p);}
};
struct Log {template<class... A>void trace(A&&...){} template<class... A>void notice(A&&...){}
template<class... A>void success(A&&...){} template<class... A>void error(A&&...){} };
inline Log rsx_log;
namespace rpcs3::ios::shader_timing {
struct BuildOriginScope{explicit BuildOriginScope(u32){}};
struct Profile{void record_origin(u32){} struct Recorder{void record(u64){}} pending_wait;std::atomic<u64> abandoned{0};};
inline Profile pipeline_profile;
}
namespace rpcs3::ios::compile_pressure {struct BlockingBuildScope{explicit BlockingBuildScope(bool){}};}
namespace rsx {
struct program_cache_hint_t {
    void* vertex=nullptr;void* fragment=nullptr;
    bool has_vertex_program()const{return vertex!=nullptr;} bool has_fragment_program()const{return fragment!=nullptr;}
    template<class T>T* get_vertex_program()const{return static_cast<T*>(vertex);}
    template<class T>T* get_fragment_program()const{return static_cast<T*>(fragment);}
    static void cache_vertex_program(program_cache_hint_t* hint,const RSXVertexProgram&,void* ptr){if(hint)hint->vertex=ptr;}
    static void cache_fragment_program(program_cache_hint_t* hint,const RSXFragmentProgram&,void* ptr){if(hint)hint->fragment=ptr;}
};
inline void write_fragment_constants_to_buffer(std::span<f32>,const RSXFragmentProgram&,const std::vector<u32>&,bool){}
}
// Independent, deliberately scalar descriptions of the shader's relevant words.
std::vector<u32> oracle(const RSXVertexProgram& p) {
    std::vector<u32> words{p.ctrl,p.output_mask,p.texture_state.texture_dimensions,p.texture_state.multisampled_textures};
    words.push_back(static_cast<u32>(p.data.size()));
    for(u32 i:p.jump_table)words.push_back(i);
    words.push_back(~0u);
    for(usz i=0;i<p.data.size()/4;++i)if(p.instruction_mask[i])for(usz lane=0;lane<4;++lane)words.push_back(p.data[i*4+lane]);
    return words;
}
std::vector<u32> oracle(const RSXFragmentProgram& p) {
    std::vector<u32> words{p.ctrl,p.ucode_length,p.texcoord_control_mask,p.mrt_buffers_count,p.two_sided_lighting?1u:0u,
        p.texture_state.texture_dimensions,p.texture_state.redirected_textures,p.texture_state.shadow_textures,p.texture_state.multisampled_textures};
    const auto* bytes=static_cast<const u8*>(p.get_data());
    for(usz i=0;i<p.ucode_length/16;++i){
        std::array<u32,4> instruction{};std::memcpy(instruction.data(),bytes+i*16,16);
        for(u32 word:instruction)words.push_back(word);
        bool constant=false;for(usz lane=1;lane<4;++lane)constant|=((instruction[lane]>>8)&3)==2;
        if(constant)++i;
    }
    return words;
}
struct TestShader {u32 id=0;std::vector<u32> canonical,constant_offsets;};
struct TestPipeline{};
struct TestProps {u32 field=0;bool operator==(const TestProps&)const=default;};
struct Traits {
    using vertex_program_type=TestShader;using fragment_program_type=TestShader;
    using pipeline_type=TestPipeline;using pipeline_storage_type=std::unique_ptr<TestPipeline>;using pipeline_properties=TestProps;
    inline static std::atomic<u64> compilations{0};
    inline static std::atomic<bool> gate{false},entered{false};
    template<class P>static void compile(const P& p,TestShader& shader,usz id){
        if(gate.load()){entered=true;while(gate.load())std::this_thread::yield();}
        shader.id=static_cast<u32>(id);shader.canonical=oracle(p);++compilations;
    }
    static void recompile_vertex_program(const RSXVertexProgram& p,TestShader& s,usz id){compile(p,s,id);}
    static void recompile_fragment_program(const RSXFragmentProgram& p,TestShader& s,usz id){compile(p,s,id);}
};
// PRODUCTION_CACHES
template<class Base>struct Exposed:Base {
    using Base::search_vertex_program;using Base::search_fragment_program;
    auto vertex(const RSXVertexProgram& p){return this->search_vertex_program(nullptr,p);}
    auto fragment(const RSXFragmentProgram& p){return this->search_fragment_program(nullptr,p);}
    void reset(){this->clear();}
};
struct After:Exposed<after_cache<Traits>> {
    using after_cache<Traits>::recent_shader_slot;
    bool remembered_vertex()const{for(const auto& h:this->m_recent_vertex_shaders)if(h.load())return true;return false;}
    bool remembered_fragment()const{for(const auto& h:this->m_recent_fragment_shaders)if(h.load())return true;return false;}
    usz vertex_count()const{return this->m_vertex_shader_cache.size();}
};
using Before=Exposed<before_cache<Traits>>;
RSXVertexProgram vertex(u32 id,u32 instructions=96){
    RSXVertexProgram p;p.data.resize(instructions*4);p.ctrl=17;p.output_mask=15;
    std::mt19937 random(id);
    for(auto& word:p.data)word=random();
    for(u32 i=0;i<instructions;++i)p.instruction_mask.set(i);
    return p;
}
RSXFragmentProgram fragment(u32 id,u32 instructions=96){
    RSXFragmentProgram p;p.ctrl=5;p.ucode_length=instructions*32;p.total_length=p.ucode_length;
    p.data.local_storage.resize(p.ucode_length);p.data.data_ptr=p.data.local_storage.data();
    std::mt19937 random(id);auto* bytes=static_cast<u8*>(p.get_data());
    for(u32 i=0;i<instructions;++i){
        std::array<u32,8> w{};for(auto& word:w)word=random();
        w[1]=(w[1]&~0x300u)|0x200u; // one constant literal after every instruction
        std::memcpy(bytes+i*32,w.data(),32);
    }
    return p;
}
template<class Program>void verify(Before& b,After& a,const Program& p){
    auto query=[](auto& cache,const auto& prog){if constexpr(std::is_same_v<Program,RSXVertexProgram>)return cache.vertex(prog);else return cache.fragment(prog);};
    auto old=query(b,p),now=query(a,p);
    assert(std::get<0>(old).canonical==oracle(p));
    assert(std::get<0>(now).canonical==std::get<0>(old).canonical);
    assert(std::get<1>(old)==std::get<1>(now));
}
void correctness(){
    Before b;After a;std::mt19937 random(20261029);
    for(u32 i=0;i<4000;++i){
        auto vp=vertex(i%139,1+random()%256);auto fp=fragment(i%137,1+random()%128);
        vp.ctrl^=random()%4;fp.texture_state.multisampled_textures=random()%4;
        verify(b,a,vp);verify(b,a,fp);verify(b,a,vp);verify(b,a,fp);
    }
    // Constants vary each draw; they never create a new compiled fragment.
    auto fp=fragment(991);verify(b,a,fp);const auto id=std::get<0>(a.fragment(fp)).id;
    auto* bytes=static_cast<u8*>(fp.get_data());
    for(u32 i=0;i<500;++i){bytes[16+(i%16)]^=static_cast<u8>(i+1);verify(b,a,fp);assert(std::get<0>(a.fragment(fp)).id==id);}
    // Unused vertex instructions retain the original masked comparison.
    auto vp=vertex(91);vp.instruction_mask.reset(2);verify(b,a,vp);
    for(u32 i=0;i<100;++i){vp.data[8]^=i+1;verify(b,a,vp);}
    // Different masks are never accepted by the hint: the map hash also
    // depends on the mask, and its comparison alone assumes that invariant.
    auto mask_a=vertex(120);auto mask_b=mask_a;mask_b.instruction_mask.reset(1);
    verify(b,a,mask_a);verify(b,a,mask_b);verify(b,a,mask_a);verify(b,a,mask_b);
    // An exact slot collision still compares the complete code/properties.
    auto v1=vertex(1),v2=v1;v2.data[120]^=0x12345;
    assert(After::recent_shader_slot(v1)==After::recent_shader_slot(v2));
    for(u32 i=0;i<100;++i){verify(b,a,v1);verify(b,a,v2);}
    auto f1=fragment(1),f2=f1;auto* fbytes=static_cast<u8*>(f2.get_data());fbytes[128]^=71;
    assert(After::recent_shader_slot(f1)==After::recent_shader_slot(f2));
    for(u32 i=0;i<100;++i){verify(b,a,f1);verify(b,a,f2);}
    // Borrowed, unaligned guest bytes are cloned into an owned map key.
    auto original=fragment(21);std::vector<u8> guest(original.ucode_length+1);
    std::memcpy(guest.data()+1,original.get_data(),original.ucode_length);
    auto borrowed=original;borrowed.data=RSXFragmentProgram::data_storage_helper(guest.data()+1);
    verify(b,a,borrowed);guest[1+64]^=19;verify(b,a,borrowed);verify(b,a,original);
    // Rehash cannot invalidate hints; clear must invalidate them before reuse.
    auto stable=vertex(7);verify(b,a,stable);const auto old_id=std::get<0>(a.vertex(stable)).id;
    for(u32 i=0;i<2000;++i){auto p=vertex(70000+i,4);verify(b,a,p);}
    verify(b,a,stable);assert(std::get<0>(a.vertex(stable)).id==old_id);
    b.reset();a.reset();assert(!a.remembered_vertex()&&!a.remembered_fragment());
    verify(b,a,stable);assert(std::get<0>(a.vertex(stable)).id!=old_id);
    auto empty=vertex(0,0);verify(b,a,empty);verify(b,a,empty);
}
void pending(){
    After cache;auto vp=vertex(313);auto fp=fragment(314);
    auto run=[&](auto& p,bool fragment_stage){
        Traits::entered=false;Traits::gate=true;
        auto query=[&]{if constexpr(std::is_same_v<std::decay_t<decltype(p)>,RSXVertexProgram>)return cache.vertex(p);else return cache.fragment(p);};
        std::thread writer([&]{query();});while(!Traits::entered.load())std::this_thread::yield();
        // Preserve the pre-existing map placeholder result; don't read shader fields while it compiles.
        const auto result=query();assert(std::get<1>(result));
        if(fragment_stage)assert(!cache.remembered_fragment());else assert(!cache.remembered_vertex());
        Traits::gate=false;writer.join();assert(std::get<0>(query()).canonical==oracle(p));
    };
    run(vp,false);run(fp,true);
}
void concurrency(){
    After cache;std::vector<RSXVertexProgram> vertices;std::vector<RSXFragmentProgram> fragments;
    for(u32 i=0;i<64;++i){vertices.push_back(vertex(i,16));fragments.push_back(fragment(i,16));cache.vertex(vertices.back());cache.fragment(fragments.back());}
    std::array<std::thread,5> threads;
    for(u32 t=0;t<4;++t)threads[t]=std::thread([&,t]{for(u32 i=0;i<5000;++i){const auto index=(i*17+t)%64;assert(std::get<0>(cache.vertex(vertices[index])).canonical==oracle(vertices[index]));assert(std::get<0>(cache.fragment(fragments[index])).canonical==oracle(fragments[index]));}});
    threads[4]=std::thread([&]{for(u32 i=0;i<1000;++i){auto p=vertex(80000+i,24);cache.vertex(p);}});
    for(auto& thread:threads)thread.join();
}
int main(int argc,char**){
    correctness();pending();concurrency();
    std::vector<RSXVertexProgram> vp;std::vector<RSXFragmentProgram> fp;std::set<usz> vslots,fslots;
    for(u32 id=1;vp.size()<8||fp.size()<8;++id){
        auto v=vertex(id,256);if(vp.size()<8&&vslots.insert(After::recent_shader_slot(v)).second)vp.push_back(std::move(v));
        auto f=fragment(id,128);if(fp.size()<8&&fslots.insert(After::recent_shader_slot(f)).second)fp.push_back(std::move(f));
    }
    Before b;After a;for(usz i=0;i<8;++i){b.vertex(vp[i]);b.fragment(fp[i]);a.vertex(vp[i]);a.fragment(fp[i]);}
    vertex_hashes=fragment_hashes=0;
    for(usz i=0;i<10000;++i){b.vertex(vp[i%8]);b.fragment(fp[i%8]);}
    const u64 old_v=vertex_hashes,old_f=fragment_hashes;vertex_hashes=fragment_hashes=0;
    for(usz i=0;i<10000;++i){a.vertex(vp[i%8]);a.fragment(fp[i%8]);}
    const u64 new_v=vertex_hashes,new_f=fragment_hashes;
    assert(old_v==10000&&old_f==10000&&new_v==0&&new_f==0);
    std::cout<<"{\"randomizedQueries\":16000,\"constantOnlyChanges\":500,\"maskedVertexChanges\":100,\"differentVertexMasks\":4,\"collidingQueries\":400,\"concurrentQueries\":40000,\"pendingStagesChecked\":2,\"ownershipRehashClearPassed\":true,\"beforeVertexHashes\":"<<old_v<<",\"afterVertexHashes\":"<<new_v<<",\"beforeFragmentHashes\":"<<old_f<<",\"afterFragmentHashes\":"<<new_f;
    if(argc>1){
        count_hashes=false;auto bench=[&](auto& cache){auto start=std::chrono::steady_clock::now();u64 sum=0;for(usz i=0;i<40000;++i){sum+=std::get<0>(cache.vertex(vp[i%8])).id;sum+=std::get<0>(cache.fragment(fp[i%8])).id;}assert(sum);return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();};
        std::array<double,7> old_ms{},new_ms{};for(usz i=0;i<7;++i){if(i&1){new_ms[i]=bench(a);old_ms[i]=bench(b);}else{old_ms[i]=bench(b);new_ms[i]=bench(a);}}
        std::sort(old_ms.begin(),old_ms.end());std::sort(new_ms.begin(),new_ms.end());
        std::cout<<",\"synthetic80000LookupsMedianMs\":{\"before\":"<<old_ms[3]<<",\"after\":"<<new_ms[3]<<"}";
    }
    std::cout<<"}\n";
}
